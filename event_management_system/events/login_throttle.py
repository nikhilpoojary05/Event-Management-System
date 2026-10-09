"""Lock out logins after repeated failures, per username and per client IP.

Uses Django's cache. The default local-memory cache is per process, which is
fine for development and single-process deployments; with several worker
processes, configure a shared cache (e.g. Redis or the database cache).
"""
from django.conf import settings
from django.core.cache import cache

MAX_FAILURES = getattr(settings, 'LOGIN_MAX_FAILURES', 5)
LOCKOUT_SECONDS = getattr(settings, 'LOGIN_LOCKOUT_SECONDS', 15 * 60)


def _keys(request, username):
    ip = request.META.get('REMOTE_ADDR', 'unknown')
    return [f'login-fail:ip:{ip}', f'login-fail:user:{(username or "").strip().lower()}']


def is_locked_out(request, username):
    return any((cache.get(key) or 0) >= MAX_FAILURES for key in _keys(request, username))


def record_failure(request, username):
    for key in _keys(request, username):
        cache.add(key, 0, LOCKOUT_SECONDS)
        try:
            cache.incr(key)
        except ValueError:  # expired between add() and incr()
            cache.set(key, 1, LOCKOUT_SECONDS)


def reset(request, username):
    cache.delete_many(_keys(request, username))
