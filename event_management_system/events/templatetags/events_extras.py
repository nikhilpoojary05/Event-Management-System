from django import template

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
