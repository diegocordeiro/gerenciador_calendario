"""Context processor que injeta a base URL e o caminho de estáticos em todas as páginas.

Garante que os templates gerem URLs absolutas corretas tanto no modo de
desenvolvimento (runserver) quanto no gerador estático (render_static_site).
"""
from django.conf import settings


def _active_for_path(path: str) -> str:
    """Mapeia o path de uma view de runtime para a seção do menu ativo."""
    if path in ("/",) or path.startswith("/introducao/"):
        return "inicio"
    if path.startswith("/editor/"):
        return "editor"
    if path.startswith("/calendario/") or path.startswith("/calendario"):
        return "calendario"
    if path.startswith("/versoes/"):
        return "versoes"
    return ""


def site(request):
    base = settings.SITE_BASE_URL
    return {
        "base": base,
        "root_base": base,
        "static_url": base + "static/",
        "site_title": "Calendário Acadêmico do IFPI - Campus Barras",
        "active": _active_for_path(request.path),
    }
