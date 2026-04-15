# StreamSnap — Ubuntu 24.04 Production Deployment

Internal deployment using nginx + uvicorn + self-signed SSL. No public domain required.

---

## Prerequisites

```bash
sudo apt update && sudo apt install -y \
  python3 python3-pip python3-venv \
  nginx \
  ffmpeg \
  git \
  nodejs npm
```

---

## 1. Clone and set up the app

```bash
sudo mkdir -p /srv/streamsnap
sudo chown $USER:$USER /srv/streamsnap
git clone <your-repo-url> /srv/streamsnap
cd /srv/streamsnap

python3 -m venv venv
source venv/bin/activate   # only needed for the pip install below
pip install -r requirements.txt
deactivate                 # venv no longer needed — systemd uses the absolute path
```

---

## 2. Build Tailwind CSS

The compiled CSS (`app/static/css/output.css`) is gitignored and must be built on the server.

```bash
cd /srv/streamsnap
npm install
npx tailwindcss -i app/static/css/input.css -o app/static/css/output.css --minify
```

---

## 3. Create the `.env` file

Generate a secret key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Then create the file:

```bash
cat > /srv/streamsnap/.env << 'EOF'
SECRET_KEY=9869276bd97ce805b4d39476353726d9221d45dc284ce465685e2d3891414dfb
DATABASE_URL=sqlite:////srv/streamsnap/streamsnap.db
ALLOW_REGISTRATION=false
EOF
chmod 600 /srv/streamsnap/.env
```

---

## 4. Fix ownership

```bash
sudo chown -R www-data:www-data /srv/streamsnap
```

---

## 5. Create systemd service

```bash
sudo nano /etc/systemd/system/streamsnap.service
```

```ini
[Unit]
Description=StreamSnap FastAPI app
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/srv/streamsnap
EnvironmentFile=/srv/streamsnap/.env
ExecStart=/srv/streamsnap/venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8001 \
    --workers 2
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable streamsnap
sudo systemctl start streamsnap
sudo systemctl status streamsnap
```

---

## 6. Generate self-signed SSL certificate

Replace `192.168.1.50` with your actual server private IP.

```bash
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/streamsnap.key \
  -out /etc/nginx/ssl/streamsnap.crt \
  -subj "/CN=streamsnap-internal" \
  -addext "subjectAltName=IP:192.168.1.50"
```

---

## 7. Configure nginx

> **Note:** Ports 80 and 443 are already used by another app on this server.
> StreamSnap is served on port **8443** (`https://<server-ip>:8443`).

```bash
sudo nano /etc/nginx/sites-available/streamsnap
```

```nginx
server {
    listen 8443 ssl;
    server_name _;

    ssl_certificate     /etc/nginx/ssl/streamsnap.crt;
    ssl_certificate_key /etc/nginx/ssl/streamsnap.key;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;

    client_max_body_size 2G;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/streamsnap /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

---

## 8. Firewall

```bash
# Allow internal network on port 8443 (HTTPS for StreamSnap)
sudo ufw allow from 10.0.0.0/8 to any port 8443
```

Adjust the subnet (`192.168.0.0/16` or `10.0.0.0/8`) to match your network.

---

## Accessing the app

Navigate to `https://<server-private-ip>:8443` in a browser.

On first visit, the browser will show a "Your connection is not private" warning due to the self-signed certificate. Click **Advanced → Proceed** to continue. This is a one-time step per browser.

---

## Useful commands

| Task | Command |
|---|---|
| View app logs | `sudo journalctl -u streamsnap -f` |
| Restart app | `sudo systemctl restart streamsnap` |
| Reload nginx | `sudo systemctl reload nginx` |
| Update yt-dlp | `sudo /srv/streamsnap/venv/bin/pip install -U yt-dlp` |
| Check nginx config | `sudo nginx -t` |
