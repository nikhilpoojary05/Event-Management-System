from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def money(value):
    """Format an amount in rupees, e.g. ₹1,500.00 (zero stays ₹0.00)."""
    if value is None or value == '':
        return ''
    return f'₹{value:,.2f}'


@register.filter
def price(value):
    """Format a price, showing 'Free' for zero."""
    if value == 0:
        return 'Free'
    return money(value)


# ---------- Presentation helpers (no data access) ----------

BANNER_VARIANTS = 6


@register.filter
def banner(event):
    """CSS class for an event's decorative banner gradient, stable per event."""
    return f'banner-{(event.pk or 0) % BANNER_VARIANTS}'


@register.filter
def percent_booked(event):
    """Share of capacity taken, 0-100, from an event annotated with seats_left."""
    capacity = getattr(event, 'capacity', 0) or 0
    seats_left = getattr(event, 'seats_left', capacity)
    if capacity <= 0:
        return 0
    return max(0, min(100, round((capacity - seats_left) * 100 / capacity)))


_ICON_PATHS = {
    'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    'clock': '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    'pin': '<path d="M12 21s-7-6.2-7-11a7 7 0 0 1 14 0c0 4.8-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/>',
    'users': '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.9M16 3.1a4 4 0 0 1 0 7.8"/>',
    'ticket': '<path d="M3 8a2 2 0 0 0 2-2h14a2 2 0 0 0 2 2v2a2 2 0 0 0 0 4v2a2 2 0 0 0-2 2H5a2 2 0 0 0-2-2v-2'
              'a2 2 0 0 0 0-4z"/><path d="M13 6v12" stroke-dasharray="2 2"/>',
    'search': '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    'inbox': '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5h13L22 12v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z"/>',
    'sparkles': '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    'bell': '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/>',
}


@register.simple_tag
def icon(name, css_class='icon'):
    """Inline, decorative SVG icon (hidden from screen readers)."""
    paths = _ICON_PATHS.get(name, '')
    return mark_safe(
        f'<svg class="{escape(css_class)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" '
        f'focusable="false">{paths}</svg>'
    )
