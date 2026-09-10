from django import template

register = template.Library()


@register.filter
def get_item(mapping, key):
    """Acessa ``mapping[key]`` em templates (útil para dicts por dia da semana)."""
    if mapping is None:
        return None
    try:
        return mapping.get(key)
    except AttributeError:
        return None
