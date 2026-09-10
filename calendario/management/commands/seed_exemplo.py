"""Cria calendários de exemplo (etapas + versão final) para demonstração.

Uso:
  python manage.py seed_exemplo

Idempotente e não destrutivo: só cria se ainda não houver nenhum calendário
cadastrado. Serve para o projeto nascer com um build/ de exemplo publicável.
"""
from __future__ import annotations

from datetime import date, timedelta

from django.core.management.base import BaseCommand

from calendario.data.feriados import feriados_nacionais
from calendario.models import Calendario, Feriado

SEMANAS = 20
SEMANAS_1A_PARTE = 10


def primeira_segunda(ano: int, mes: int) -> date:
    """Primeira segunda-feira do mês (data válida de início de semestre)."""
    d = date(ano, mes, 1)
    return d + timedelta(days=(7 - d.weekday()) % 7)


ETAPAS = [
    ("2026.1.etapa1", 1, ["2026-02-16", "2026-02-17", "2026-04-03"]),
    (
        "2026.1.etapa2",
        2,
        ["2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21", "2026-05-01"],
    ),
]


class Command(BaseCommand):
    help = "Cria um calendário de exemplo (2026.1) com etapas e versão final."

    def handle(self, *args, **opts):
        if Calendario.objects.exists():
            self.stdout.write(
                "Já existem calendários cadastrados; seed_exemplo não altera nada."
            )
            return

        inicio = primeira_segunda(2026, 2)
        comuns = {
            "periodo": "2026.1",
            "data_inicio": inicio,
            "total_semanas": SEMANAS,
            "semanas_primeira_parte": SEMANAS_1A_PARTE,
        }

        for versao, etapa, feriados in ETAPAS:
            cal, _ = Calendario.objects.update_or_create(
                versao=versao,
                defaults={
                    **comuns,
                    "titulo": f"Calendário acadêmico 2026.1 — etapa {etapa}",
                    "etapa": etapa,
                    "status": "etapa",
                    "observacoes": f"Etapa {etapa} da montagem do calendário 2026.1.",
                },
            )
            for iso in feriados:
                Feriado.objects.get_or_create(
                    calendario=cal, data=iso, defaults={"origem": "manual"}
                )

        final, _ = Calendario.objects.update_or_create(
            versao="2026.1.final",
            defaults={
                **comuns,
                "titulo": "Calendário acadêmico 2026.1 — versão final",
                "etapa": 3,
                "status": "final",
                "final": True,
                "atual": True,
                "observacoes": "Versão final publicada no GitHub Pages.",
            },
        )
        for item in feriados_nacionais(2026):
            Feriado.objects.get_or_create(
                calendario=final,
                data=item["data"],
                defaults={"descricao": item["descricao"], "origem": "nacional"},
            )

        self.stdout.write(
            self.style.SUCCESS(
                "seed_exemplo: calendários 2026.1.etapa1, 2026.1.etapa2 e "
                "2026.1.final (final) criados."
            )
        )
