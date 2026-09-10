"""Orquestra a renderização do site estático (gera build/).

Usa o engine de templates do Django (sem HTTP) e links prefixados por
``SITE_BASE_URL``. Cada versão/etapa vira um HTML versionado em
``build/versoes/<slug>/`` e o índice (lista de versões) em ``build/calendario/``.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.template.loader import render_to_string

SITE_TITLE = "Calendário Acadêmico do IFPI - Campus Barras"


def normalize_base_url(raw) -> str:
    """Normaliza a base URL usada nos links/assets.

    Aceita tanto um path quanto uma URL absoluta. Em URLs absolutas extrai apenas
    o path (ex.: ``https://user.github.io/repo/`` -> ``/repo/``), garantindo sempre
    ``/`` no início e no final.
    """
    raw = (raw or "").strip()
    if not raw:
        raw = "/"
    if "://" in raw:
        raw = urlparse(raw).path or "/"
    if not raw.startswith("/"):
        raw = "/" + raw
    if not raw.endswith("/"):
        raw += "/"
    return raw


def print_ctx(title, meta=None) -> dict:
    """Contexto da exportação para PDF (impressão 100% no navegador)."""
    return {"pdf_export": True, "print_title": title, "print_meta": meta}


class StaticSite:
    """Ponto de entrada para gerar todas as páginas estáticas."""

    def __init__(self, build_root: Path, base_url: str):
        self.build_root = Path(build_root)
        self.base = normalize_base_url(base_url)
        self.static_url = self.base + "static/"

    def _ctx(self, prefix="", **extra):
        """Monta o contexto padrão dos templates (ciente da versão via ``prefix``)."""
        ctx = {
            "base": self.base + prefix,
            "root_base": self.base,
            "static_url": self.static_url,
            "site_title": SITE_TITLE,
            "static_build": True,
        }
        ctx.update(extra)
        return ctx

    def _write(self, rel_path: str, template: str, ctx: dict):
        html = render_to_string(template, ctx)
        out = self.build_root / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")

    def copy_assets(self):
        static_src = Path(settings.BASE_DIR) / "static"
        if static_src.exists():
            shutil.copytree(static_src, self.build_root / "static", dirs_exist_ok=True)
        media_src = Path(settings.BASE_DIR) / "media"
        if media_src.exists():
            shutil.copytree(media_src, self.build_root / "media", dirs_exist_ok=True)
        # Evita o processamento Jekyll no GitHub Pages.
        (self.build_root / ".nojekyll").write_text("", encoding="utf-8")

    # ---------- páginas ----------
    def render_home(self, versoes):
        self._write(
            "index.html",
            "calendario/home.html",
            self._ctx(versoes=versoes, active="inicio"),
        )

    def render_indice(self, versoes):
        """Índice do calendário em ``calendario/`` — lista todas as versões."""
        self._write(
            "calendario/index.html",
            "calendario/indice.html",
            self._ctx(versoes=versoes, active="calendario"),
        )

    def render_redirect_versoes(self):
        """``versoes/index.html`` redireciona para o índice (o Pages não faz 301)."""
        self._write(
            "versoes/index.html",
            "calendario/redirect.html",
            self._ctx(destino="../calendario/"),
        )

    def render_calendario(self, cal, prefix=""):
        """Gera a página de um calendário (atual na raiz ou etapa versionada)."""
        dados = cal.build()
        titulo = cal.titulo or f"Calendário acadêmico — {cal.versao}"
        self._write(
            f"{prefix}index.html" if prefix else "calendario/index.html",
            "calendario/calendario_detail.html",
            self._ctx(
                prefix=prefix,
                cal=cal,
                dados=dados,
                agenda=cal.agenda(),
                active="calendario",
                **print_ctx(titulo, cal.periodo or None),
            ),
        )
