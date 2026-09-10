"""Pré-popula os feriados nacionais nos calendários existentes.

Uso:
  python manage.py seed_feriados
  python manage.py seed_feriados --versao 2026.1.etapa1
  python manage.py seed_feriados --ano 2026

Idempotente: cria apenas os feriados nacionais que faltam (por calendário/data)
e nunca remove feriados manuais. Para os anos cobertos por cada calendário
quando ``--ano`` não é informado.
"""
from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand

from calendario.data.feriados import feriados_nacionais
from calendario.models import Calendario, Feriado


class Command(BaseCommand):
    help = "Pré-popula os feriados nacionais brasileiros nos calendários existentes."

    def add_arguments(self, parser):
        parser.add_argument("--versao", default=None, help="Aplica somente a esta versão.")
        parser.add_argument("--ano", type=int, default=None, help="Ano específico.")

    def handle(self, *args, **opts):
        calendarios = Calendario.objects.all()
        if opts["versao"]:
            calendarios = calendarios.filter(versao=opts["versao"])
        calendarios = list(calendarios)

        if not calendarios:
            self.stdout.write(
                "Nenhum calendário encontrado. Crie uma versão no /editor/ ou no admin."
            )
            return

        criados = 0
        for cal in calendarios:
            anos = {opts["ano"]} if opts["ano"] else self._anos(cal)
            for ano in sorted(anos):
                for item in feriados_nacionais(ano):
                    _, foi_criado = Feriado.objects.get_or_create(
                        calendario=cal,
                        data=item["data"],
                        defaults={"descricao": item["descricao"], "origem": "nacional"},
                    )
                    if foi_criado:
                        criados += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"seed_feriados: {criados} feriado(s) nacional(is) adicionado(s) "
                f"em {len(calendarios)} calendário(s)."
            )
        )

    @staticmethod
    def _anos(cal: Calendario) -> set[int]:
        """Anos cobertos pelo calendário (do início ao fim das semanas)."""
        fim = cal.data_inicio + timedelta(weeks=cal.total_semanas)
        return set(range(cal.data_inicio.year, fim.year + 1))
