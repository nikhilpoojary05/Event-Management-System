# 🎉 Event Management System

[![CI](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml)

## 📌 Overview
A Django web application for browsing, booking, and managing events online. Attendees can book and cancel tickets with live seat availability; organizers can publish new events.

## 🚀 Features
- User registration & login (returns you to the page you came from)
- Upcoming / past event listings with seats left, "Sold out" and "Only N left" badges, and pagination
- Event booking with capacity checks that are safe against simultaneous bookings
- Booking summary with a live total price; each booking keeps the ticket price it was booked at
- Cancel bookings up to the event date (seats are released immediately)
- "My Bookings" page with booking status
- Event creation restricted to organizers (users with the *Can add event* permission)
- Admin panel with seat counts, filters and search
- Responsive layout for mobile

## 🛠 Technologies Used
- Python 3.13
- Django 6
- HTML, CSS
- SQLite

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

Open http://127.0.0.1:8000 in your browser. The admin panel is at http://127.0.0.1:8000/admin/.

## 👥 Roles
- **Attendees** register on the site and can book and cancel tickets.
- **Organizers** can add events. Superusers are organizers automatically. To make another user an organizer, open their account in the admin panel and give them the **events | event | Can add event** permission.

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

GitHub Actions runs the linter, Django system checks, a migrations check, and the test suite on every push to `main` and on every pull request (see `.github/workflows/ci.yml`).

## 📁 Project Structure

```
Event-Management-System/
├── requirements.txt               # runtime dependencies
├── requirements-dev.txt           # + development tools
├── pyproject.toml                 # ruff configuration
├── .github/workflows/ci.yml       # CI pipeline
└── event_management_system/
    ├── manage.py
    ├── event_management_system/   # project settings and URLs
    └── events/                    # the app
        ├── models.py              # Event, Booking (booking/seat logic lives here)
        ├── views.py
        ├── forms.py
        ├── admin.py
        ├── templates/events/      # base.html + page templates
        ├── static/events/         # style.css
        └── tests/                 # test suite
```

## 🌐 Deploying to Production

Locally the app needs no configuration: it runs in debug mode with a development-only secret key. In production, configure it with environment variables:

| Variable | Required | Description |
|---|---|---|
| `DJANGO_DEBUG` | yes | Set to `False`. This also enables secure cookies, HTTPS redirect and HSTS. |
| `DJANGO_SECRET_KEY` | yes | A long random string. The app refuses to start without it when `DJANGO_DEBUG=False`. |
| `DJANGO_ALLOWED_HOSTS` | yes | Comma-separated domain names, e.g. `example.com,www.example.com`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | if needed | Comma-separated origins with scheme, e.g. `https://example.com`. |
| `DJANGO_BEHIND_HTTPS_PROXY` | if needed | `True` when a proxy/load balancer terminates HTTPS and sets `X-Forwarded-Proto`. |
| `DJANGO_SECURE_SSL_REDIRECT` | no | Defaults to `True`; set `False` if your host already redirects to HTTPS. |
| `DJANGO_SECURE_HSTS_SECONDS` | no | HSTS duration; defaults to 30 days. |
| `DJANGO_SECURE_HSTS_PRELOAD` | no | Defaults to `False`. Only enable once HTTPS is permanent, as it is hard to undo. |

Generate a secret key with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Then collect static files and verify the configuration:

```bash
python manage.py collectstatic
python manage.py check --deploy
```

> SQLite works for small deployments. For more traffic, switch `DATABASES` to PostgreSQL.
