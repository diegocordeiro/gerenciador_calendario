"""Feriados nacionais brasileiros, calculados por ano.

Serve de base para o comando ``seed_feriados`` pré-popular cada calendário.
Os feriados móveis (Carnaval, Sexta-feira Santa e Corpus Christi) são derivados
da Páscoa pelo algoritmo de Gauss/Meeus (mesmo método usado pelos calendários
oficiais). Os feriados fixos seguem a legislação federal — incluindo o Dia
Nacional de Zumbi e da Consciência Negra (20/11), feriado nacional desde 2024.
"""
from __future__ import annotations

import datetime as dt

FERIADOS_FIXOS = [
    ((1, 1), "Confraternização Universal"),
    ((4, 21), "Tiradentes"),
    ((5, 1), "Dia do Trabalho"),
    ((9, 7), "Independência do Brasil"),
    ((10, 12), "Nossa Senhora Aparecida"),
    ((11, 2), "Finados"),
    ((11, 15), "Proclamação da República"),
    ((11, 20), "Dia Nacional de Zumbi e da Consciência Negra"),
    ((12, 25), "Natal"),
]


def pascoa(ano: int) -> dt.date:
    """Domingo de Páscoa (algoritmo de Gauss/Meeus)."""
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes = (h + l - 7 * m + 114) // 31
    dia = ((h + l - 7 * m + 114) % 31) + 1
    return dt.date(ano, mes, dia)


def feriados_moveis(ano: int) -> list[tuple[dt.date, str]]:
    """Feriados móveis do ano, derivados da Páscoa."""
    p = pascoa(ano)
    return [
        (p - dt.timedelta(days=48), "Carnaval (segunda-feira)"),
        (p - dt.timedelta(days=47), "Carnaval (terça-feira)"),
        (p - dt.timedelta(days=2), "Sexta-feira Santa"),
        (p + dt.timedelta(days=60), "Corpus Christi"),
    ]


def feriados_nacionais(ano: int) -> list[dict]:
    """Lista de feriados nacionais do ano: ``[{data, descricao}]`` (ordenado)."""
    itens = [(dt.date(ano, m, d), desc) for (m, d), desc in FERIADOS_FIXOS]
    itens += feriados_moveis(ano)
    itens.sort(key=lambda x: x[0])
    return [{"data": data, "descricao": descricao} for data, descricao in itens]
