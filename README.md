# 🎉 Event Management System

[![CI](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml)

## 📌 Overview
A Django web application for browsing, booking, and managing events online. Attendees can book and cancel tickets with live seat availability; organizers can publish new events.

## 🚀 Features
- User registration & login (returns you to the page you came from)
- Upcoming / past event listings with seats left, "Sold out" and "Only N left" badges, and pagination
- Search events by name, venue or description, and filter by date range, free events, or seats available
- Event booking with capacity checks that are safe against simultaneous bookings
- Booking summary with a live total price; each booking keeps the ticket price it was booked at
- Cancel bookings up to the event date (seats are released immediately)
- "Add to calendar" (.ics) on event pages and My Bookings, also attached to confirmation emails
- Login protection: 5 failed attempts lock out further tries for 15 minutes
- Waitlist for sold-out events: when seats free up, waiting users are booked automatically in the order they joined and emailed
- Email notifications: booking confirmed or cancelled, and event cancelled or rescheduled (date, time or venue changed)
- "My Bookings" page with booking status
- Event creation restricted to organizers (users with the *Can add event* permission)
- Organizer dashboard ("My Events"): tickets sold and revenue per event, edit events, view attendees, and cancel events (which cancels their bookings)
- Admin panel with seat counts, filters and search
- Responsive design with automatic dark mode; colors are CSS variables at the top of `static/events/style.css`

## 🛠 Technologies Used
- Python 3.13
- Django 6
- HTML, CSS (no framework), with [Inter](https://fonts.google.com/specimen/Inter) and [Plus Jakarta Sans](https://fonts.google.com/specimen/Plus+Jakarta+Sans) from Google Fonts
- SQLite (development), PostgreSQL (production)
- gunicorn + WhiteNoise for deployment

## ⚙️ Installation

```bash
git clone https://github.com/nikhilpoojary05/Event-Management-System.git
cd Event-Management-System
python -m venv venv
```

Activate the virtual environment:

```bash
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

Install dependencies and set up the database:

```bash
pip install -r requirements.txt
cd event_management_system
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Optionally add some future-dated sample events to try things out:

```bash
python manage.py seed_demo
```

Open http://127.0.0.1:8000 in your browser. The admin panel is at http://127.0.0.1:8000/admin/.

In development, emails (booking confirmations etc.) are printed in the terminal running `runserver` instead of being sent.

## 👥 Roles
- **Attendees** register on the site and can book and cancel tickets.
- **Organizers** can add events and manage the events they created from **My Events**: edit details, see attendees and revenue, and cancel the event. To make a user an organizer, open their account in the admin panel and give them the **events | event | Can add event** permission.
- **Administrators** (superusers, or users with **events | event | Can change event**) can manage every event, including ones created before organizers were tracked.

## 🧪 Development

Install the development tools (includes the [ruff](https://docs.astral.sh/ruff/) linter):

```bash
pip install -r requirements-dev.txt
```

Run the linter from the repository root, and the tests from the `event_management_system` folder:

```bash
ruff check .
ruff check . --fix   # auto-fix import order, etc.
cd event_management_system
python manage.py test events
```

GitHub Actions runs the linter, Django system checks, a migrations check, the production deployment checklist and build steps, and the test suite, on both SQLite and PostgreSQL, on every push to `main` and on every pull request (see `.github/workflows/ci.yml`).

## 📁 Project Structure

```
Event-Management-System/
├── requirements.txt               # runtime dependencies
├── requirements-dev.txt           # + development tools
├── pyproject.toml                 # ruff configuration
├── .github/workflows/ci.yml       # CI pipeline
├── render.yaml                    # Render deployment blueprint
├── build.sh                       # build steps run on each deploy
└── event_management_system/
    ├── manage.py
    ├── event_management_system/   # project settings and URLs
    └── events/                    # the app
        ├── models.py              # Event, Booking, WaitlistEntry (booking/seat logic lives here)
        ├── notifications.py       # email notifications
        ├── views.py
        ├── forms.py
        ├── admin.py
        ├── templates/events/      # base.html + page templates
        ├── static/events/         # style.css
        └── tests/                 # test suite
```

## 🌐 Deploying to Production

### Option A: Render (free tier, about 10 minutes)

The repository includes a [Render Blueprint](render.yaml) that creates the web app **and** a PostgreSQL database.

1. Push this repository to GitHub (already done if you're reading this there).
2. Sign in at [render.com](https://render.com) with your GitHub account.
3. Click **New → Blueprint**, pick this repository, and click **Apply**.
4. When asked, enter the **admin account** to create: `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL` and `DJANGO_SUPERUSER_PASSWORD`.
5. Wait for the first deploy (a few minutes). Your site will be at `https://<service-name>.onrender.com`, and you can log in to `/admin/` with the account from step 4.

Everything else is configured automatically: a generated secret key, the database connection, HTTPS settings, allowed hosts, and links in emails. Each deploy runs [`build.sh`](build.sh), which installs dependencies, collects static files, applies migrations, creates your admin account if it doesn't exist yet, and adds the demo events (set `DJANGO_SEED_DEMO` to `False` to stop that).

**Emails:** until you add SMTP settings (below) in the service's **Environment** tab, emails are written to the service **Logs** instead of being sent.

> **Free-tier notes** (check [Render's pricing page](https://render.com/pricing) for current limits): free web services sleep when idle, so the first request after a quiet period is slow, and free PostgreSQL databases are time-limited. Upgrade the database plan to keep data long-term.

### Option B: any other host

The app is a standard Django project served by **gunicorn**, with static files served by **WhiteNoise**:

```bash
pip install -r requirements.txt
cd event_management_system
python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py createcachetable
gunicorn event_management_system.wsgi:application
```

### Environment variables

Locally the app needs no configuration: it runs in debug mode with SQLite and a development-only secret key. In production, configure it with environment variables:

| Variable | Required | Description |
|---|---|---|
| `DJANGO_DEBUG` | yes | Set to `False`. This also enables secure cookies, HTTPS redirect, HSTS, compressed static files and a shared database cache. |
| `DJANGO_SECRET_KEY` | yes | A long random string. The app refuses to start without it when `DJANGO_DEBUG=False`. |
| `DATABASE_URL` | recommended | e.g. `postgres://user:password@host:5432/dbname`. Without it, SQLite is used. |
| `DJANGO_ALLOWED_HOSTS` | yes* | Comma-separated domain names, e.g. `example.com,www.example.com`. *Automatic on Render. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | if needed | Comma-separated origins with scheme, e.g. `https://example.com`. Automatic on Render. |
| `DJANGO_BEHIND_HTTPS_PROXY` | if needed | `True` when a proxy or load balancer terminates HTTPS and sets `X-Forwarded-Proto` (Render, Heroku, Railway…). |
| `DJANGO_SITE_URL` | yes* | Public URL used for links in emails, e.g. `https://events.example.com`. *Automatic on Render. |
| `DJANGO_SECURE_SSL_REDIRECT` | no | Defaults to `True`; set `False` if your host already redirects to HTTPS. |
| `DJANGO_SECURE_HSTS_SECONDS` | no | HSTS duration; defaults to 30 days. |
| `DJANGO_SECURE_HSTS_PRELOAD` | no | Defaults to `False`. Only enable once HTTPS is permanent, as it is hard to undo. |
| `DJANGO_EMAIL_HOST` | for email | SMTP server, e.g. `smtp.gmail.com`. Without it, emails are printed to the logs. |
| `DJANGO_EMAIL_PORT` | no | Defaults to `587`. |
| `DJANGO_EMAIL_HOST_USER` / `DJANGO_EMAIL_HOST_PASSWORD` | if needed | SMTP login. |
| `DJANGO_EMAIL_USE_TLS` | no | Defaults to `True`. |
| `DJANGO_DEFAULT_FROM_EMAIL` | for email | Sender, e.g. `Events <noreply@example.com>`. |
| `DJANGO_SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | no | Admin account created by `python manage.py ensure_superuser` (never overwrites an existing account). |
| `DJANGO_LOG_LEVEL` | no | Defaults to `WARNING`. |

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Verify a production configuration with `python manage.py check --deploy`.
