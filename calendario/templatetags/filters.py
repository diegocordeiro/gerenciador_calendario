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


@register.filter
def data_br(iso):
    """Formata uma data ISO (``2026-09-14``) como ``14/09/2026``.

    Usado nos tooltips dos dias das grades (o mesmo rótulo que o JS do editor
    monta em ``fmtData``).
    """
    try:
        ano, mes, dia = str(iso).split("-")
    except (AttributeError, ValueError):
        return iso
    return f"{dia}/{mes}/{ano}"


@register.filter
def item_por_data(itens, iso):
    """Devolve o item (dict) cujo campo ``date`` é igual a ``iso`` (ou ``None``)."""
    if not itens:
        return None
    for item in itens:
        try:
            if item.get("date") == iso:
                return item
        except AttributeError:
            continue
    return None
