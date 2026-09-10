"""Port fiel do algoritmo do app original (academic-callendar-scheduler).

Reimplementa, em Python, a lógica de ``src/pages/Index.vue``: a partir da data
de início do semestre, do número de semanas e das semanas da 1ª parte, monta a
grade de dias letivos e **reposiciona os feriados** nas semanas de reposição.

É a **fonte única de verdade** do cálculo: usada tanto pela interface de
montagem (via API) quanto pelo gerador do site estático.
"""
from __future__ import annotations

import datetime as dt
import math

WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
DIAS_UTEIS = range(5)  # Monday=0 .. Friday=4


def parse_date(value):
    """Converte 'YYYY-MM-DD'/date/datetime em ``datetime.date`` (ou None)."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value).strip())


def _dias_da_semana(i: int, t: int, f: int) -> int:
    """Port de ``d(i)``: nº de dias (colunas) da semana ``i``."""
    return min(5, 5 * (t - i) + f)


def total_semanas(t: int, f: int) -> int:
    """Port de ``w``: ``t + ceil(f/5)`` (semanas extras para repor feriados)."""
    return t + math.ceil(f / 5)


def feriados_no_calendario(data_inicio: dt.date, t: int, feriados) -> list[dt.date]:
    """Port de ``getHolidaysInCalendar``: feriados úteis dentro da faixa.

    Recalcula o fim da faixa de forma iterativa (o `f` altera o próprio fim),
    até convergir — exatamente como no original.
    """
    dias = sorted(
        {d for d in (parse_date(x) for x in (feriados or [])) if d and d.weekday() in DIAS_UTEIS}
    )
    soma = 0
    prev = None
    fim = data_inicio
    while prev != soma:
        fim = data_inicio + dt.timedelta(days=t * 7 + soma + (soma // 2) * 2)
        prev = soma
        soma = sum(1 for d in dias if data_inicio <= d <= fim)
    return [d for d in dias if data_inicio <= d <= fim]


def calendario_matriz(data_inicio: dt.date, t: int, t1: int, f: int) -> list[list[dict]]:
    """Port de ``calendarMatrix``: grade de células por semana."""
    matriz: list[list[dict]] = []
    atual = data_inicio
    for i in range(total_semanas(t, f)):
        linha = []
        for j in range(_dias_da_semana(i, t, f)):
            linha.append(
                {
                    "date": atual,
                    "week": i,
                    "weekday": j,
                    "part": 1 if i < t1 else 2,
                    "parity": (i + 1) % 2,
                    "free": False,
                    "assigned": False,
                    "old": None,
                }
            )
            atual += dt.timedelta(days=1)
        matriz.append(linha)
        atual += dt.timedelta(days=2)
    return matriz


def date_to_cell(data_inicio: dt.date, date: dt.date, matriz):
    """Port de ``dateToCell``: localiza a célula da data na grade."""
    diff = (date - data_inicio).days
    i = diff // 7
    j = diff % 7
    if i < 0 or i >= len(matriz) or j >= len(matriz[i]) or j > 4:
        return None
    return matriz[i][j]


def melhor_matriz(matriz, feriados_celulas, t: int, f: int):
    """Port de ``betterCalendarMatrix``: marca feriados e redistribui as aulas.

    Retorna a grade final (lista de semanas) ou ``None`` se a redistribuição
    falhar (parâmetros inconsistentes).
    """
    w = len(matriz)
    free_ids = {id(c) for c in feriados_celulas}
    for linha in matriz:
        for celula in linha:
            if id(celula) in free_ids:
                celula["free"] = True

    C = [[dict(celula) for celula in linha] for linha in matriz]

    # A = células das semanas de reposição (i >= t), usadas como destino.
    A = []
    for i in range(t, w):
        for j in range(len(matriz[i])):
            A.append(matriz[i][j])

    def fill(cmp):
        for a1 in A:
            c1 = C[a1["week"]][a1["weekday"]]
            if c1.get("assigned"):
                continue
            for a2 in feriados_celulas:
                c2 = C[a2["week"]][a2["weekday"]]
                if cmp(c1, c2):
                    c1.update(
                        {
                            "old": dict(c1),
                            "parity": c2["parity"],
                            "weekday": c2["weekday"],
                            "week": c2["week"],
                            "date": c2["date"],
                            "assigned": True,
                        }
                    )
                    c2["assigned"] = True
                    break

    fill(lambda c1, c2: c2["parity"] == c1["parity"] and c2["weekday"] == c1["weekday"])
    fill(lambda c1, c2: c2["weekday"] == c1["weekday"])
    fill(lambda c1, c2: c2["parity"] == c1["parity"])
    fill(lambda c1, c2: True)

    # Realoca para a 1ª parte as células de feriado que pertenciam a ela.
    planas = [c for linha in C for c in linha]
    for el in [c for c in feriados_celulas if c["part"] == 1]:
        spares = [
            x
            for x in planas
            if x["weekday"] == el["weekday"]
            and x["parity"] == el["parity"]
            and x["part"] == 2
            and not x["free"]
        ]
        if not spares:
            return None
        spares[0]["part"] = 1

    return C


def _rotulo(col: dict, ridx: int, cidx: int):
    """Port de ``getLabel``: devolve (texto_simples, html) do rótulo da célula."""

    def lbl(c):
        d = c["date"]
        return f"{d.day:02d}.{d.month:02d}"

    texto = lbl(col)
    wd = WEEKDAYS[col["weekday"]] if col["weekday"] < len(WEEKDAYS) else ""
    if col["free"]:
        return "", ""
    if col["weekday"] != cidx:
        lbl2 = lbl(col["old"]) if col.get("old") else ""
        return f"({wd})({texto}) {lbl2}", f'<b class="moved-day">({wd})</b>({texto}) {lbl2}'
    if col["week"] != ridx:
        lbl2 = lbl(col["old"]) if col.get("old") else ""
        return f"({texto}) {lbl2}", f"({texto}) {lbl2}"
    return texto, texto


def _cor_fundo(col: dict) -> str:
    """Port de ``getBckColor``: cor de fundo da célula."""
    if col["free"]:
        return "white"
    if col["parity"]:
        return "#edfaff"
    return "#fff4f4"


def _erro(prop: str, C, matriz) -> int:
    """Port de ``getError``: quantas células divergem do calendário original."""
    total = 0
    for i, linha in enumerate(C):
        for j, celula in enumerate(linha):
            if celula[prop] != matriz[i][j][prop]:
                total += 1
    return total


def build_calendario(data_inicio, total_semanas_valor, semanas_primeira_parte, feriados):
    """Monta o calendário completo a partir dos parâmetros.

    Devolve um dicionário pronto para JSON/template com a grade, métricas,
    validação e a lista de feriados usados.
    """
    data_inicio = parse_date(data_inicio)
    t = int(total_semanas_valor or 0)
    t1 = int(semanas_primeira_parte or 0)
    feriados_norm = [d for d in (parse_date(x) for x in (feriados or [])) if d]

    if data_inicio is None:
        return {
            "parametros": {"data_inicio": "", "total_semanas": t, "semanas_primeira_parte": t1},
            "valido": False,
            "erros": ["Informe a data de início do semestre."],
            "linhas": [],
            "weekdays": WEEKDAYS[:5],
            "metricas": {"parity": 0, "weekday": 0, "part": 0},
            "feriados_calendario": [],
            "feriados_fora": [],
            "f": 0,
            "w": 0,
        }

    erros = []
    if data_inicio.weekday() != 0:
        erros.append("A data de início deve ser uma segunda-feira.")
    if t < 2:
        erros.append("O número de semanas deve ser pelo menos 2.")
    if t1 < 1:
        erros.append("O número de semanas da 1ª parte deve ser pelo menos 1.")
    if t1 > t:
        erros.append("A 1ª parte não pode ter mais semanas que o semestre.")

    feriados_cal = feriados_no_calendario(data_inicio, t, feriados_norm)
    f = len(feriados_cal)
    w = total_semanas(t, f)
    matriz = calendario_matriz(data_inicio, t, t1, f)

    celulas = [c for d in feriados_cal if (c := date_to_cell(data_inicio, d, matriz))]
    C = melhor_matriz(matriz, celulas, t, f)
    if C is None:
        erros.append(
            "Não foi possível redistribuir os feriados; ajuste o número de semanas "
            "ou reduza os feriados."
        )
        C = matriz

    # Validação das semanas por dia (port de isValid).
    totais = [(w - 1) + (1 if _dias_da_semana(w - 1, t, f) > i else 0) for i in range(5)]
    parte1 = [0] * 5
    for i in range(5):
        for linha in C:
            if len(linha) > i and (linha[i]["part"] == 1 or linha[i]["free"]):
                parte1[i] += 1
    for i in range(5):
        if totais[i] - parte1[i] < 0:
            erros.append(f"{WEEKDAYS[i]}: semanas da 1ª parte excedem o total disponível.")

    linhas = []
    for ridx, linha in enumerate(C):
        celulas_out = []
        for cidx, celula in enumerate(linha):
            texto, html = _rotulo(celula, ridx, cidx)
            celulas_out.append(
                {
                    "weekday": cidx,
                    "date": celula["date"].isoformat(),
                    "date_label": f"{celula['date'].day:02d}.{celula['date'].month:02d}",
                    "label": texto,
                    "label_html": html,
                    "color": _cor_fundo(celula),
                    "free": bool(celula["free"]),
                    "part": celula["part"],
                    "parity": celula["parity"],
                    "week": celula["week"],
                }
            )
        linhas.append(
            {
                "week": ridx,
                "week_label": f"s{ridx + 1}",
                "parity": (ridx + 1) % 2,
                "parity_label": f"x{(ridx % 2) + 1}",
                "cells": celulas_out,
                "columns": celulas_out + [None] * (5 - len(celulas_out)),
                "days": len(linha),
            }
        )

    data_fim = matriz[-1][-1]["date"] if matriz and matriz[-1] else data_inicio
    feriados_iso = {d.isoformat() for d in feriados_cal}

    return {
        "parametros": {
            "data_inicio": data_inicio.isoformat(),
            "data_fim": data_fim.isoformat(),
            "total_semanas": t,
            "semanas_primeira_parte": t1,
            "feriados": [d.isoformat() for d in feriados_norm],
        },
        "valido": not erros,
        "erros": erros,
        "f": f,
        "w": w,
        "semanas_extras": w - t,
        "metricas": {
            "parity": _erro("parity", C, matriz),
            "weekday": _erro("weekday", C, matriz),
            "part": _erro("part", C, matriz),
        },
        "semana_dias": [_dias_da_semana(i, t, f) for i in range(w)],
        "linhas": linhas,
        "weekdays": WEEKDAYS[:5],
        "feriados_calendario": [d.isoformat() for d in feriados_cal],
        "feriados_fora": sorted(
            d.isoformat() for d in feriados_norm if d.isoformat() not in feriados_iso
        ),
        "dias_letivos": sum(1 for linha in C for c in linha if not c["free"]),
        "dias_totais": sum(len(linha) for linha in C),
    }

