# Crestmont Reserve Bank — backend deploy (GitHub + Render)

## 1. Push to GitHub

Unzip this file — you should see `manage.py`, `config/`, `apps/`, etc.
directly, no extra wrapper folder. That matters: everything in this zip
needs to end up at the **root** of a new GitHub repo.

```bash
unzip crestmont-bank-backend.zip
cd crestmont-bank-backend

git init
git add .
git commit -m "Crestmont Reserve Bank backend"
```

Create a new empty repo on GitHub (github.com/new — name it something like
`crestmont-bank-backend`, don't add a README), then:

```bash
git remote add origin https://github.com/YOUR_USERNAME/crestmont-bank-backend.git
git branch -M main
git push -u origin main
```

No git installed locally? Create the empty repo on GitHub, then use
**Add file → Upload files** and drag in everything from the unzipped
folder — `manage.py`, `config`, `apps`, `requirements.txt`, `build.sh`,
`.env.example` — directly, so they land at the repo root, not nested
inside another folder.

## 2. Create the database first

In the [Render dashboard](https://dashboard.render.com):

1. **New → PostgreSQL**
2. Name it `crestmont-db`, leave the rest as defaults, **Create Database**
3. Once it's up, copy the **Internal Database URL** shown on its page —
   you'll paste this into the backend's environment variables next

## 3. Deploy the backend

1. **New → Web Service** (this time Web Service is correct — Django needs
   a real running server, unlike the static marketing site)
2. Connect the `crestmont-bank-backend` repo
3. Settings:
   - **Runtime:** Python 3
   - **Build Command:** `./build.sh`
   - **Start Command:** `gunicorn config.wsgi:application`
   - **Instance Type:** Free is fine to start
4. Add environment variables (Render's dashboard has an "Environment"
   tab) — use `.env.example` as the list of what's needed:
   - `SECRET_KEY` — generate any long random string
   - `DEBUG` — `False`
   - `ALLOWED_HOSTS` — your Render URL once assigned, e.g.
     `crestmont-bank-backend.onrender.com` (you can update this after
     first deploy once you know the URL)
   - `DATABASE_URL` — paste the Internal Database URL from step 2 directly.
     The app reads this automatically now (falls back to the individual
     `DB_*` variables only if `DATABASE_URL` isn't set).
   - `CORS_ALLOWED_ORIGINS` — your frontend's URL, e.g. the static site
     from earlier or `app.crestmontreservebank.com`
   - Email (required — account/KYC/transfer/loan/card notifications send
     through these):
     - `EMAIL_BACKEND` — `django.core.mail.backends.smtp.EmailBackend`
     - `EMAIL_HOST_USER` — `accountinfo@crestmontreservebank.com`
     - `EMAIL_HOST_PASSWORD` — a Zoho **app-specific** password (Zoho Mail
       → Settings → Security → App Passwords), not the regular login
       password
     - `DEFAULT_FROM_EMAIL` — `accountinfo@crestmontreservebank.com`
     - `SUPPORT_EMAIL` — `accountinfo@crestmontreservebank.com`
     - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_SSL` default to Zoho's SMTP
       settings (`smtp.zoho.com`, `465`, `True`) and don't need to be set
       unless you're using a different provider
   - Stripe variables can stay blank for now — nothing calls them yet
     since Stage 3 (the actual banking API) isn't built
5. Click **Create Web Service**

Render builds and deploys. First build takes a few minutes since it's
installing Python packages and running migrations.

## After deploy

Visit `https://your-service.onrender.com/health` — should return
`{"ok": true}`. That confirms the server and database are both up.

`/admin/` gives you Django's built-in admin (separate from the custom
staff console we designed) — useful for poking at data directly while
Stage 3+ is still being built. You'll need to create a superuser first:
in the Render dashboard, open the service's **Shell** tab and run
`python manage.py createsuperuser`.
