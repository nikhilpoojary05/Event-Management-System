from django import template

register = template.Library()


@register.filter
def price(value):
    """Format an amount in rupees, showing 'Free' for zero."""
    if value is None or value == '':
        return ''
    if value == 0:
        return 'Free'
    return f'₹{value:,.2f}'
