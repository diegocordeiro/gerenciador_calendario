"""Gera o site estático completo dentro de build/ (para publicar no GitHub Pages).

Uso:
  python manage.py render_static_site
  python manage.py render_static_site --output build --base-url /repo/

O build/ contém o índice (lista de versões) em ``calendario/`` e **cada versão** em
``versoes/<slug>/``; é a pasta publicada pelo workflow do GitHub Pages.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from calendario.models import Calendario
from calendario.static_site import StaticSite, normalize_base_url


class Command(BaseCommand):
    help = "Renderiza todas as páginas estáticas em build/."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output", default=None, help="Pasta de saída (padrão: <BASE_DIR>/build)."
        )
        parser.add_argument(
            "--base-url",
            default=None,
            help=(
                "URL ou path base do GitHub Pages usado nos links/assets "
                "(ex.: https://user.github.io/repo/ ou /repo/). Se omitido, usa a env "
                "SITE_BASE_URL e, em terminal interativo, pergunta ao usuário."
            ),
        )

    def handle(self, *args, **opts):
        build_root = (
            Path(opts["output"]) if opts["output"] else Path(settings.BASE_DIR) / "build"
        )
        if build_root.exists():
            import shutil

            shutil.rmtree(build_root)
        build_root.mkdir(parents=True, exist_ok=True)

        base = opts["base_url"] or settings.SITE_BASE_URL
        if (
            not opts["base_url"]
            and not os.environ.get("SITE_BASE_URL")
            and sys.stdin.isatty()
        ):
            default = settings.SITE_BASE_URL
            raw = input(f"Path/URL base do GitHub Pages [{default}]: ").strip()
            base = raw or default
        base = normalize_base_url(base)
        site = StaticSite(build_root, base)
        self.stdout.write(f"Base URL usada nos links/assets: {base}")

        if not Calendario.objects.exists():
            self.stderr.write(
                "Nenhum calendário encontrado. Monte uma versão em /editor/ "
                "ou cadastre no admin."
            )
            return

        versoes = list(Calendario.objects.all())
        versoes.sort(key=lambda c: (c.data_inicio, c.etapa), reverse=True)

        site.copy_assets()
        site.render_home(versoes)
        site.render_indice(versoes)
        site.render_redirect_versoes()

        # Todas as versões são publicadas sob /versoes/<slug>/.
        for cal in versoes:
            site.render_calendario(cal, prefix=f"versoes/{cal.slug}/")

        self.stdout.write(
            self.style.SUCCESS(
                f"Site estático gerado em: {build_root} "
                f"({len(versoes)} versão(ões) publicada(s))."
            )
        )
