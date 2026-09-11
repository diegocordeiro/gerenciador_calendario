from django import template

import re

register = template.Library()


def _partes_instituicao(valor):
    """Divide a instituição pelos travessões (``IFPI — Campus Barras``)."""
    return [p.strip() for p in re.split(r"[—–-]", str(valor or "")) if p.strip()]


@register.filter
def sem_campus(valor):
    """Instituição sem o campus final.

    ``"… do Piauí — IFPI — Campus Barras"`` → ``"… do Piauí — IFPI"``: no cabeçalho
    formal o campus aparece em linha própria, como no documento oficial do campus.
    """
    partes = _partes_instituicao(valor)
    return " — ".join(partes[:-1]) if len(partes) > 1 else str(valor or "")


@register.filter
def depois_do_travessao(valor):
    """Trecho após o último travessão (``"… — Campus Barras"`` → ``"Campus Barras"``)."""
    partes = _partes_instituicao(valor)
    return partes[-1] if len(partes) > 1 else ""


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
