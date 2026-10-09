# Commonplace setup

## Local development

1. Open a terminal in this folder and create your local config:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated value into `COMMONPLACE_SECRET_KEY` in `.env`. Keep `.env` private.

2. Install packages and start the app:

```powershell
python -m pip install -r requirements.txt
python Project1.py
```

4. Open `http://127.0.0.1:5000`.
5. Create an account. With no SMTP server configured, the verification and password-reset links appear on the page for local testing.

The SQLite database and local private uploads are saved under `app-data/`. Keep `.env` and `app-data/` private and backed up.

## Email links

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` in `.env` to send verification and password-reset links. Use an app password or restricted SMTP credential. Set `APP_ENV=production` after mail delivery is configured; development links are intentionally not returned in production mode.

## S3-compatible file storage

The default `COMMONPLACE_STORAGE=local` stores files on the server disk. For AWS S3 or an S3-compatible service such as Cloudflare R2, set `COMMONPLACE_STORAGE=s3`, `S3_BUCKET`, `S3_REGION`, and (if needed) `S3_ENDPOINT_URL`. Supply `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` through the environment or the private `.env` file. Keep the bucket private; the application streams files only after checking the owner or a valid share token.

## Before public deployment

This Flask development server is for local use only. Deploy behind HTTPS with a production WSGI server, set a stable random `COMMONPLACE_SECRET_KEY`, set `COMMONPLACE_HTTPS=1`, configure SMTP and private object storage, and add backups, monitoring, and rate limiting. Do not commit `.env`, database files, or uploads.

Existing notes from the earlier browser-only prototype are not automatically copied into SQLite. They remain in that browser's IndexedDB until exported or migrated manually.
