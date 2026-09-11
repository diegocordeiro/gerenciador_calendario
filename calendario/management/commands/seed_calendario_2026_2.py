"""Recria, no banco, o calendário acadêmico 2026.2 do documento oficial.

Uso:
  python manage.py seed_calendario_2026_2

Fonte: ``CALENDÁRIO ACADÊMICO 2026.2 - _INTEGRADO_EM_ADMINISTRAÇÃO``
(Cursos Técnico em Administração Integrado PROEJA — Campus Barras).

Cria/atualiza a versão ``2026.2.final`` com:
* cabeçalho do documento (curso, modalidade, semestre, início/término, 100 dias);
* feriados e pontos facultativos;
* tabela de eventos (matrículas, jornada, avaliações, recuperação, recesso,
  conselho, férias coletivas…);
* 11 sábados letivos, cada um com o dia da semana referenciado.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from calendario.models import Calendario, Evento, Feriado

VERSAO = "2026.2.final"
DATA_INICIO = "2026-09-14"
DATA_FIM = "2027-02-12"
DIAS_LETIVOS_PREVISTOS = 100

#: (data, tipo, descrição)
FERIADOS = [
    ("2026-09-07", "feriado", "Independência do Brasil"),
    ("2026-09-24", "feriado", "Aniversário do Município de Barras-PI"),
    ("2026-10-12", "feriado", "Nossa Senhora Aparecida"),
    ("2026-10-15", "ponto_facultativo", "Dia do Professor/TAE"),
    ("2026-10-19", "ponto_facultativo", "Dia do Piauí"),
    ("2026-10-28", "ponto_facultativo", "Dia do Servidor Público"),
    ("2026-11-02", "feriado", "Finados"),
    ("2026-11-15", "feriado", "Proclamação da República"),
    ("2026-11-20", "feriado", "Dia Nacional da Consciência Negra"),
    ("2026-12-08", "feriado", "Dia da Padroeira de Barras-PI"),
    ("2026-12-25", "feriado", "Natal"),
    ("2027-01-01", "feriado", "Confraternização Universal / 1º do Ano"),
]

#: dias letivos por mês declarados no documento (para conferência)
DIAS_LETIVOS_POR_MES = [
    {"mes": "AGO/2026", "letivos": 0},
    {"mes": "SET/2026", "letivos": 13},
    {"mes": "OUT/2026", "letivos": 21},
    {"mes": "NOV/2026", "letivos": 21},
    {"mes": "DEZ/2026", "letivos": 17},
    {"mes": "JAN/2027", "letivos": 23},
    {"mes": "FEV/2027", "letivos": 5},
]

#: (tipo, início, fim, título, dia_semana_referencia, destaque)
EVENTOS = [
    ("matricula", "2026-08-10", "2026-08-14", "Matrículas", None, False),
    ("administrativo", "2026-08-27", None, "Início do preenchimento do PSAD 2026.2", None, False),
    ("jornada_pedagogica", "2026-09-01", "2026-09-04", "Jornada Pedagógica/Planejamento", None, True),
    ("evento", "2026-09-08", "2026-09-11", "Semana de Educação para o Trânsito", None, False),
    ("evento", "2026-09-10", None, "Dia Mundial de Prevenção do Suicídio / Setembro Amarelo", None, False),
    ("evento", "2026-09-14", None, "Início do período letivo", None, True),
    ("evento", "2026-09-18", "2026-09-25", "Semana Nacional de Trânsito / Dia do Trânsito (Lei 9.503/97)", None, False),
    ("sabado_letivo", "2026-09-19", None, "Sábado letivo", 2, False),
    ("evento", "2026-09-21", None, "Atividades alusivas ao Dia Nacional de Luta das Pessoas com Deficiência", None, False),
    ("administrativo", "2026-09-27", None, "Início do preenchimento do PSAD 2026.2", None, False),
    ("sabado_letivo", "2026-10-03", None, "Sábado letivo", 0, False),
    ("administrativo", "2026-10-09", None, "Prazo final de preenchimento do PSAD 2026.2", None, False),
    ("sabado_letivo", "2026-10-10", None, "Sábado letivo", 3, False),
    ("sabado_letivo", "2026-10-24", None, "Sábado letivo", 0, False),
    ("avaliacao", "2026-11-04", "2026-11-07", "Avaliações do 1º Bimestre", None, False),
    ("avaliacao", "2026-11-09", None, "Avaliações do 1º Bimestre", None, False),
    ("sabado_letivo", "2026-11-07", None, "Sábado letivo", 2, False),
    ("avaliacao", "2026-11-10", "2026-11-14", "Avaliações do 1º Bimestre (2ª chamada – contraturno)", None, False),
    ("sabado_letivo", "2026-11-14", None, "Sábado letivo", 0, False),
    ("recuperacao", "2026-11-16", "2026-11-19", "Semana de Estudos e Avaliações de Recuperação Paralela (contraturno)", None, False),
    ("evento", "2026-11-19", None, "Fim do 1º Bimestre / Entrega de notas no SUAP", None, True),
    ("evento", "2026-11-23", None, "Início do 2º Bimestre", None, True),
    ("evento", "2026-11-23", "2026-11-27", "Semana da Consciência Negra", None, False),
    ("sabado_letivo", "2026-12-05", None, "Sábado letivo", 4, False),
    ("sabado_letivo", "2026-12-12", None, "Sábado letivo", 2, False),
    ("recesso", "2026-12-22", "2026-12-31", "Recesso de Natal e Ano Novo", None, False),
    ("sabado_letivo", "2027-01-09", None, "Sábado letivo", 2, False),
    ("sabado_letivo", "2027-01-16", None, "Sábado letivo", 3, False),
    ("avaliacao", "2027-01-19", "2027-01-23", "Avaliações do 2º Bimestre", None, False),
    ("sabado_letivo", "2027-01-23", None, "Sábado letivo", 4, False),
    ("avaliacao", "2027-01-25", "2027-01-29", "Avaliações do 2º Bimestre (2ª chamada – contraturno)", None, False),
    ("recuperacao", "2027-02-01", "2027-02-05", "Semana de Estudos e Avaliações de Recuperação Paralela", None, False),
    ("evento", "2027-02-05", None, "Fim do 2º Bimestre", None, True),
    ("avaliacao_final", "2027-02-08", "2027-02-10", "Avaliações Finais", None, False),
    ("evento", "2027-02-11", None, "Último dia para inserir frequência e notas no SUAP", None, False),
    ("conselho_classe", "2027-02-12", None, "Conselho de Classe / Término do período letivo", None, False),
    ("ferias_coletivas", "2027-02-13", None, "Férias coletivas", None, False),
]


class Command(BaseCommand):
    help = "Cria/atualiza o calendário acadêmico 2026.2 (Administração Integrado PROEJA)."

    def handle(self, *args, **opts):
        cal, criado = Calendario.objects.update_or_create(
            versao=VERSAO,
            defaults={
                "titulo": "CALENDÁRIO ACADÊMICO 2026.2 — Técnico em Administração",
                "periodo": "2026.2",
                "instituicao": Calendario.INSTITUICAO_PADRAO,
                "curso": "Cursos Técnico em Administração",
                "modalidade": "integrado_medio",
                "semestre": "2º Semestre",
                "data_inicio": DATA_INICIO,
                "data_fim": DATA_FIM,
                "total_semanas": 22,
                "semanas_primeira_parte": 11,
                "dias_letivos_previstos": DIAS_LETIVOS_PREVISTOS,
                "dias_letivos_por_mes": DIAS_LETIVOS_POR_MES,
                "etapa": 1,
                "observacoes": (
                    "Calendário oficial 2026.2 do curso Técnico em Administração "
                    "Integrado PROEJA (Campus Barras). Os totais por mês declarados no "
                    "documento são conferidos automaticamente contra o cálculo; o "
                    "documento distribui 21 dias em NOV e 17 em DEZ, enquanto o cálculo "
                    "por regra resulta 22 e 16 — o total de 100 dias confere."
                ),
            },
        )

        # Feriados e pontos facultativos.
        cal.feriados.all().delete()
        Feriado.objects.bulk_create(
            [
                Feriado(
                    calendario=cal,
                    data=data,
                    descricao=descricao,
                    origem="institucional",
                    tipo=tipo,
                )
                for data, tipo, descricao in FERIADOS
            ]
        )

        # Eventos (matrículas, avaliações, sábados letivos, recessos…).
        cal.eventos.all().delete()
        Evento.objects.bulk_create(
            [
                Evento(
                    calendario=cal,
                    titulo=titulo,
                    tipo=tipo,
                    data_inicio=inicio,
                    data_fim=fim,
                    dia_semana_referencia=ref,
                    destaque=destaque,
                )
                for tipo, inicio, fim, titulo, ref, destaque in EVENTOS
            ]
        )

        agenda = cal.agenda()
        acao = "criado" if criado else "atualizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"seed_calendario_2026_2: {VERSAO} {acao} — "
                f"{len(FERIADOS)} feriados, {len(EVENTOS)} eventos, "
                f"{len(agenda['sabados_letivos'])} sábados letivos."
            )
        )
        self.stdout.write(
            f"  dias letivos calculados: {agenda['total_letivos']} "
            f"(previstos: {DIAS_LETIVOS_PREVISTOS})"
        )
        for aviso in agenda["validacao"]["avisos"]:
            self.stdout.write(self.style.WARNING(f"  atenção: {aviso}"))

