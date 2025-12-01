from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    if dictionary and key in dictionary:
        return dictionary.get(key)
    return 0

@register.filter
def to_float(value):
    try:
        return float(value)
    except:
        return 0

@register.filter
def subtract(a, b):
    """Return numeric difference (a - b)"""
    try:
        return float(a) - float(b)
    except:
        return 0
