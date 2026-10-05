# Putting GTD online

The app keeps everything (users, bookings, rates) in one file, `gtd.db`. It must live on a disk that survives restarts.
**Do not use Streamlit Community Cloud**: it erases local files, so you would lose all data.

Before going live, decide these (all are environment variables, see the table at the bottom):
`GTD_ADMIN_PASSWORD` (set it BEFORE the first start), `GTD_ADMIN_EMAIL`, the SMTP settings, the Twilio SMS settings, `GOOGLE_MAPS_API_KEY`.

## Option A: Render (easiest, no server to manage)
1. Create a free account on GitHub and upload this folder as a new **private** repository.
2. On render.com: **New + > Blueprint**, choose that repository. It reads `render.yaml` and builds the Dockerfile.
3. Render asks for the values marked `sync: false`. Fill in at least GTD_ADMIN_PASSWORD, GTD_ADMIN_EMAIL, GTD_SMTP_USER, GTD_SMTP_PASSWORD, GTD_SMTP_FROM.
4. Deploy. Your site opens at `https://gtd-travel.onrender.com` (or the name you chose). HTTPS is automatic.
5. Log in as `admin` with your password, then use **Rate cards** to check prices.
The 1 GB disk mounted at `/data` holds `gtd.db`. A disk needs a paid Render instance (the `starter` plan in the file).

## Option B: Your own Linux server (VPS, Ubuntu)
```
sudo apt update && sudo apt install -y python3-venv nginx certbot python3-certbot-nginx
sudo mkdir -p /opt/gtd /var/lib/gtd && sudo chown $USER /opt/gtd /var/lib/gtd
# upload this folder's contents to /opt/gtd, then:
cd /opt/gtd && python3 -m venv venv && venv/bin/pip install -r requirements.txt
```
Create `/etc/gtd.env` (readable only by root: `sudo chmod 600 /etc/gtd.env`):
```
GTD_DB=/var/lib/gtd/gtd.db
GTD_ADMIN_PASSWORD=choose-a-strong-one
GTD_ADMIN_EMAIL=bookings@yourcompany.com
GTD_SMTP_HOST=smtp.gmail.com
GTD_SMTP_PORT=587
GTD_SMTP_USER=bookings@yourcompany.com
GTD_SMTP_PASSWORD=your-app-password
GTD_SMTP_FROM=GTD Travel <bookings@yourcompany.com>
```
Create `/etc/systemd/system/gtd.service`:
```
[Unit]
Description=GTD Travel
After=network.target
[Service]
WorkingDirectory=/opt/gtd
EnvironmentFile=/etc/gtd.env
ExecStart=/opt/gtd/venv/bin/streamlit run app.py --server.port=8501 --server.address=127.0.0.1 --server.headless=true
Restart=always
User=www-data
[Install]
WantedBy=multi-user.target
```
Then: `sudo chown www-data /var/lib/gtd && sudo systemctl enable --now gtd`.

Nginx (`/etc/nginx/sites-available/gtd`, link it into `sites-enabled`). Streamlit needs WebSocket headers:
```
server {
  server_name book.yourcompany.com;
  location / {
    proxy_pass http://127.0.0.1:8501;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 86400;
  }
}
```
Point your domain's DNS A record at the server, then run `sudo certbot --nginx -d book.yourcompany.com` for free HTTPS.

## Backups (do this, a lost file means lost bookings)
`python backup.py` makes a safe copy of the live database and keeps the newest 14.
- Server: `crontab -e` and add `0 2 * * * cd /opt/gtd && GTD_DB=/var/lib/gtd/gtd.db GTD_BACKUP_DIR=/var/backups/gtd venv/bin/python backup.py`
- Also copy the backups off the server now and then (your PC, Google Drive). On Render, use the Shell tab to run it and download the file.

## Settings reference
| Variable | Purpose |
|---|---|
| GTD_DB | Path of the database file (on the persistent disk) |
| GTD_ADMIN_USER / GTD_ADMIN_PASSWORD | First admin login, used only when the database is new |
| GTD_ADMIN_EMAIL | Company email that receives every booking |
| GTD_SMTP_HOST, _PORT, _USER, _PASSWORD, _FROM | Mail account that sends those emails (Gmail needs an App Password) |
| GTD_TWILIO_SID, _TOKEN, _FROM | SMS provider for the phone OTP |
| GOOGLE_MAPS_API_KEY | Google Maps |

## Before you announce it
- Log in as admin and change the password (the app nags you if you did not set GTD_ADMIN_PASSWORD).
- Make one test booking and confirm the email reaches your company inbox.
- Make one test signup and confirm the OTP SMS arrives on a real phone.
