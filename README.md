# 🎉 Event Management System

[![CI](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml/badge.svg)](https://github.com/nikhilpoojary05/Event-Management-System/actions/workflows/ci.yml)

## 📌 Overview
A Django web application for browsing, booking, and managing events online. Attendees can book and cancel tickets with live seat availability; organizers can publish new events.

## 🚀 Features
- User registration & login (returns you to the page you came from)
- Upcoming / past event listings with seats left, "Sold out" and "Only N left" badges, and pagination
- Event booking with capacity checks that are safe against simultaneous bookings
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

## ⚠️ Production Note
`settings.py` currently has a hard-coded `SECRET_KEY` and `DEBUG = True`, which are only suitable for local development. Change these before deploying.
