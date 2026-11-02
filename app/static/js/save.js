/*
 * StreamSnap — canonical "save to the user's computer" flow.
 *
 * The server no longer keeps finished files. For each item the browser POSTs
 * to an endpoint that builds the file in a temp job dir and streams it back
 * (POST /download, POST /upload/extract); this script writes the bytes to
 * wherever the user chose:
 *   - Chrome / Edge / Brave: File System Access API — "Save As" dialog for one
 *     file, folder picker for a batch.
 *   - Safari / Firefox: normal browser download (the browser's own setting
 *     decides whether it asks where to save).
 *
 * Entry points (called from form onsubmit): StreamSnapSave.startUrlDownload(form),
 * StreamSnapSave.startUploadExtract(form).
 */
const StreamSnapSave = (() => {
    const canPickFile = typeof window.showSaveFilePicker === 'function';
    const canPickDir  = typeof window.showDirectoryPicker === 'function';

    // ── Choosing where to save ───────────────────────────
    // Must be called before any network await: browsers only open pickers
    // during the user's click.
    async function pickTarget(count, suggestedName) {
        try {
            if (count === 1 && canPickFile) {
                return { kind: 'file', handle: await window.showSaveFilePicker({ suggestedName, id: 'streamsnap' }) };
            }
            if (count > 1 && canPickDir) {
                return { kind: 'dir', handle: await window.showDirectoryPicker({ id: 'streamsnap', mode: 'readwrite' }) };
            }
        } catch (e) {
            if (e.name === 'AbortError') return null;          // user cancelled the dialog
            console.warn('Save picker unavailable, using browser download:', e);
        }
        return { kind: 'browser' };
    }

    function filenameFromResponse(response, fallback) {
        const cd = response.headers.get('Content-Disposition') || '';
        const star = cd.match(/filename\*\s*=\s*(?:UTF-8|utf-8)''([^;]+)/);
        if (star) {
            try { return decodeURIComponent(star[1].trim()); } catch (_) { /* fall through */ }
        }
        const plain = cd.match(/filename\s*=\s*"?([^";]+)"?/);
        return plain ? plain[1].trim() : fallback;
    }

    // Never overwrite a file already in the chosen folder: "name (1).ext", "name (2).ext", …
    async function uniqueFileHandle(dirHandle, name) {
        const dot  = name.lastIndexOf('.');
        const stem = dot > 0 ? name.slice(0, dot) : name;
        const ext  = dot > 0 ? name.slice(dot) : '';
        for (let n = 0; n < 1000; n++) {
            const candidate = n === 0 ? name : `${stem} (${n})${ext}`;
            try {
                await dirHandle.getFileHandle(candidate);       // exists → try next
            } catch (e) {
                if (e.name === 'NotFoundError') return dirHandle.getFileHandle(candidate, { create: true });
                throw e;
            }
        }
        throw new Error('Too many files with the same name');
    }

    async function readBody(response, onChunk, onProgress) {
        const reader = response.body.getReader();
        let received = 0;
        for (;;) {
            const { done, value } = await reader.read();
            if (done) return received;
            await onChunk(value);
            received += value.length;
            onProgress(received);
        }
    }

    function browserDownload(blob, name) {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = name;
        document.body.appendChild(a);
        a.click();
        a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
    }

    async function saveResponse(response, target, name, onProgress) {
        if (target.kind === 'browser') {
            const chunks = [];
            await readBody(response, c => { chunks.push(c); }, onProgress);
            browserDownload(new Blob(chunks), name);
            return name;
        }
        const handle   = target.kind === 'file' ? target.handle : await uniqueFileHandle(target.handle, name);
        const writable = await handle.createWritable();
        try {
            await readBody(response, c => writable.write(c), onProgress);
            await writable.close();
        } catch (e) {
            await writable.abort().catch(() => {});
            throw e;
        }
        return handle.name;
    }

    async function errorMessage(response) {
        try {
            const data = await response.json();
            if (data && data.error) return data.error;
        } catch (_) { /* not JSON */ }
        return `Server error (${response.status})`;
    }

    // ── Progress list UI ────────────────────────────────
    function mb(bytes) { return (bytes / 1024 / 1024).toFixed(1) + ' MB'; }

    function renderList(container, labels, target) {
        container.innerHTML = '';
        const box = document.createElement('div');
        box.className = 'fade-up';
        box.style.cssText = 'background:var(--surf-2); border:1px solid var(--border); padding:16px; border-radius:2px; margin-top:12px;';

        const head = document.createElement('p');
        head.style.cssText = "font-size:0.68rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; color:var(--text-muted); margin-bottom:10px; font-family:'JetBrains Mono',monospace;";
        head.textContent = target.kind === 'dir'
            ? `Saving ${labels.length} file(s) to folder “${target.handle.name}”`
            : target.kind === 'file'
                ? `Saving to “${target.handle.name}”`
                : `Saving ${labels.length} file(s) via your browser's downloads`;
        box.appendChild(head);

        const rows = labels.map(label => {
            const row = document.createElement('div');
            row.style.cssText = 'display:flex; align-items:center; justify-content:space-between; gap:12px; padding:9px 12px; background:var(--surf); border:1px solid var(--border); border-radius:2px; margin-top:6px;';
            const name = document.createElement('span');
            name.style.cssText = 'min-width:0; flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:0.8125rem; color:var(--text);';
            name.textContent = label;
            const status = document.createElement('span');
            status.style.cssText = "flex-shrink:0; font-size:0.72rem; color:var(--text-muted); font-family:'JetBrains Mono',monospace; text-align:right; max-width:55%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;";
            status.textContent = 'Waiting';
            row.append(name, status);
            box.appendChild(row);
            return {
                set(text, color) { status.textContent = text; status.title = text; status.style.color = color || 'var(--text-muted)'; },
            };
        });

        container.appendChild(box);
        return rows;
    }

    // ── Queue: one request per item, saved one after another ──
    async function runQueue({ labels, suggestedName, container, button, send }) {
        const target = await pickTarget(labels.length, suggestedName);
        if (!target) return;                                  // cancelled — do nothing

        const rows = renderList(container, labels, target);
        if (button) button.disabled = true;
        try {
            for (let i = 0; i < labels.length; i++) {
                const row = rows[i];
                row.set('Preparing on server…');
                try {
                    const response = await send(i);
                    if (response.redirected && new URL(response.url).pathname === '/login') {
                        row.set('Session expired — log in again', 'var(--red)');
                        rows.slice(i + 1).forEach(r => r.set('Skipped', 'var(--red)'));
                        return;
                    }
                    if (!response.ok) {
                        row.set(await errorMessage(response), 'var(--red)');
                        continue;
                    }
                    const name  = filenameFromResponse(response, labels[i]);
                    const saved = await saveResponse(response, target, name, n => row.set('Saving… ' + mb(n)));
                    row.set((target.kind === 'browser' ? 'Downloaded ' : 'Saved ') + saved, 'var(--green)');
                } catch (e) {
                    console.error(e);
                    row.set('Failed: ' + (e.message || e.name || 'unknown error'), 'var(--red)');
                }
            }
        } finally {
            if (button) button.disabled = false;
        }
    }

    // ── Entry point: URL download form (partials/format_options.html) ──
    function startUrlDownload(form) {
        const urls   = form.elements['urls'].value.split('\n').filter(u => u.trim());
        const titles = JSON.parse(form.dataset.titles || '[]');
        const fd0    = new FormData(form);
        const isAudio = fd0.get('download_type') === 'audio';
        const ext    = isAudio ? (fd0.get('audio_format') || 'mp3') : 'mp4';
        const custom = fd0.getAll('custom_names');
        const base   = (fd0.get('rename_mode') === 'individual' && (custom[0] || '').trim()) || titles[0] || 'download';

        return runQueue({
            labels: urls.map((u, i) => titles[i] || u),
            suggestedName: `${base}.${ext}`,
            container: document.getElementById('download-result'),
            button: form.querySelector('button[type="submit"]'),
            send: i => {
                const fd = new FormData(form);
                fd.set('item_index', String(i));
                return fetch('/download', { method: 'POST', body: fd, credentials: 'same-origin' });
            },
        });
    }

    // ── Entry point: local file → audio form (index.html upload tab) ──
    function startUploadExtract(form) {
        const files = Array.from(document.getElementById('file-input').files);
        if (!files.length) return;
        const fd0    = new FormData(form);
        const ext    = fd0.get('audio_format') || 'mp3';
        const custom = fd0.getAll('custom_names');
        const stem   = files[0].name.replace(/\.[^/.]+$/, '');
        const base   = (fd0.get('rename_mode') === 'individual' && (custom[0] || '').trim()) || stem;

        return runQueue({
            labels: files.map(f => f.name),
            suggestedName: `${base}.${ext}`,
            container: document.getElementById('upload-result'),
            button: document.getElementById('upload-btn'),
            send: i => {
                const fd = new FormData(form);
                fd.delete('files');                            // send only this item's file
                fd.set('file', files[i]);
                fd.set('item_index', String(i));
                return fetch('/upload/extract', { method: 'POST', body: fd, credentials: 'same-origin' });
            },
        });
    }

    return { startUrlDownload, startUploadExtract };
})();
