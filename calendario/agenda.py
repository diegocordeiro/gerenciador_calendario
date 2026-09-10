"""Cálculo da agenda do calendário no formato do documento oficial.

Diferente de ``scheduling`` (que produz a grade de semanas x1/x2 com
remanejamento de feriados), aqui o calendário é montado **mês a mês**, como no
documento publicado pelo campus: grade mensal com o status de cada dia, resumo
de dias letivos por mês, sábados letivos com o dia da semana referenciado,
tabela de eventos e feriados/pontos facultativos.

Regra de dia letivo (documentada e coberta por testes):

* **segunda a sexta** dentro do período do semestre é *letivo*, exceto em
  feriado, ponto facultativo, recesso, férias coletivas, jornada pedagógica,
  conselho de classe e avaliação final;
* **sábado** é letivo somente quando há evento do tipo *sábado letivo* ou
  *sábado de reposição*;
* **domingo** nunca é letivo.
"""
from __future__ import annotations

import datetime as dt

from .scheduling import parse_date

MESES_ABREV = [
    "", "JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
    "JUL", "AGO", "SET", "OUT", "NOV", "DEZ",
]
DIAS_CABECALHO = ["D", "S", "T", "Q", "Q", "S", "S"]
NOMES_SEMANA = [
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
]

#: status possíveis de um dia na agenda
STATUS_LETIVO = "letivo"
STATUS_LETIVO_SABADO = "letivo_sabado"
STATUS_FERIADO = "feriado"
STATUS_PONTO = "ponto_facultativo"
STATUS_RECESSO = "recesso"
STATUS_FERIAS = "ferias"
STATUS_JORNADA = "jornada"
STATUS_AVALIACAO_FINAL = "avaliacao_final"
STATUS_CONSELHO = "conselho"
STATUS_NAO_LETIVO = "nao_letivo"
STATUS_FORA = "fora"

#: status que contam como dia letivo
STATUS_LETIVOS = {STATUS_LETIVO, STATUS_LETIVO_SABADO}

STATUS_LABEL = {
    STATUS_LETIVO: "Dia letivo",
    STATUS_LETIVO_SABADO: "Sábado letivo",
    STATUS_FERIADO: "Feriado",
    STATUS_PONTO: "Ponto facultativo",
    STATUS_RECESSO: "Recesso escolar",
    STATUS_FERIAS: "Férias coletivas",
    STATUS_JORNADA: "Jornada pedagógica",
    STATUS_AVALIACAO_FINAL: "Avaliação final",
    STATUS_CONSELHO: "Conselho de classe",
    STATUS_NAO_LETIVO: "Não letivo",
    STATUS_FORA: "Fora do período",
}

#: prioridade dos eventos por tipo (o primeiro que casar define o status do dia)
PRIORIDADE_TIPOS = [
    ("feriado", STATUS_FERIADO),
    ("ponto_facultativo", STATUS_PONTO),
    ("recesso", STATUS_RECESSO),
    ("ferias_coletivas", STATUS_FERIAS),
    ("avaliacao_final", STATUS_AVALIACAO_FINAL),
    ("conselho_classe", STATUS_CONSELHO),
    ("jornada_pedagogica", STATUS_JORNADA),
    ("sabado_reposicao", STATUS_LETIVO_SABADO),
    ("sabado_letivo", STATUS_LETIVO_SABADO),
]


def _attr(obj, nome, default=None):
    """Lê um campo de um objeto (modelo) ou de um dicionário."""
    if isinstance(obj, dict):
        return obj.get(nome, default)
    return getattr(obj, nome, default)


def mes_label(d: dt.date) -> str:
    """Rótulo do mês no formato do documento (ex.: ``SET/2026``)."""
    return f"{MESES_ABREV[d.month]}/{d.year}"


def _fim_do_mes(d: dt.date) -> dt.date:
    if d.month == 12:
        proximo = dt.date(d.year + 1, 1, 1)
    else:
        proximo = dt.date(d.year, d.month + 1, 1)
    return proximo - dt.timedelta(days=1)


def dia_label(ini: dt.date, fim: dt.date) -> str:
    """Rótulo do intervalo de dias (ex.: ``10``, ``10 a 14``, ``22/12 a 02/01``)."""
    if ini == fim:
        return f"{ini.day:02d}"
    if ini.month == fim.month and ini.year == fim.year:
        return f"{ini.day:02d} a {fim.day:02d}"
    return f"{ini.day:02d}/{ini.month:02d} a {fim.day:02d}/{fim.month:02d}"


def _normalizar(feriados, eventos):
    """Normaliza feriados/eventos em mapas indexados por data."""
    feriados_map = {}
    for f in feriados or []:
        d = parse_date(_attr(f, "data"))
        if not d:
            continue
        feriados_map[d] = {
            "descricao": (_attr(f, "descricao", "") or "").strip(),
            "tipo": (_attr(f, "tipo", "feriado") or "feriado"),
        }

    eventos_norm = []
    eventos_por_dia = {}
    for e in eventos or []:
        ini = parse_date(_attr(e, "data_inicio"))
        if not ini:
            continue
        fim = parse_date(_attr(e, "data_fim")) or ini
        if fim < ini:
            ini, fim = fim, ini
        item = {
            "titulo": (_attr(e, "titulo", "") or "").strip(),
            "tipo": (_attr(e, "tipo", "evento") or "evento"),
            "data_inicio": ini,
            "data_fim": fim,
            "dia_semana_referencia": _attr(e, "dia_semana_referencia"),
            "descricao": (_attr(e, "descricao", "") or ""),
            "destaque": bool(_attr(e, "destaque", False)),
        }
        eventos_norm.append(item)
        d = ini
        while d <= fim:
            eventos_por_dia.setdefault(d, []).append(item)
            d += dt.timedelta(days=1)

    eventos_norm.sort(key=lambda x: (x["data_inicio"], x["titulo"]))
    return feriados_map, eventos_norm, eventos_por_dia


def _status_dia(d: dt.date, ini: dt.date, fim: dt.date, feriados_map, eventos_por_dia) -> str:
    """Define o status de um dia conforme a regra documentada do módulo."""
    if d < ini or d > fim:
        return STATUS_FORA
    if d in feriados_map:
        if feriados_map[d]["tipo"] == "ponto_facultativo":
            return STATUS_PONTO
        return STATUS_FERIADO
    tipos = {e["tipo"] for e in eventos_por_dia.get(d, [])}
    for tipo, status in PRIORIDADE_TIPOS:
        if tipo in tipos:
            return status
    if d.weekday() >= 5:
        return STATUS_NAO_LETIVO
    return STATUS_LETIVO


def _mes(primeiro: dt.date, ini: dt.date, fim: dt.date, feriados_map, eventos_por_dia) -> dict:
    """Monta a grade de um mês (domingo primeiro), como no documento."""
    ultimo = _fim_do_mes(primeiro)
    offset = (primeiro.weekday() + 1) % 7  # segunda=0 → domingo primeiro
    inicio_grid = primeiro - dt.timedelta(days=offset)
    fim_grid = ultimo + dt.timedelta(days=6 - ((ultimo.weekday() + 1) % 7))

    celulas = []
    letivos = feriados = sabados = 0
    d = inicio_grid
    while d <= fim_grid:
        if d.month != primeiro.month:
            celulas.append({"vazio": True})
        else:
            status = _status_dia(d, ini, fim, feriados_map, eventos_por_dia)
            if status in STATUS_LETIVOS:
                letivos += 1
            if status == STATUS_LETIVO_SABADO:
                sabados += 1
            if status in (STATUS_FERIADO, STATUS_PONTO):
                feriados += 1
            evs = eventos_por_dia.get(d, [])
            celulas.append(
                {
                    "vazio": False,
                    "dia": d.day,
                    "date": d.isoformat(),
                    "status": status,
                    "status_label": STATUS_LABEL.get(status, status),
                    "letivo": status in STATUS_LETIVOS,
                    "destaque": any(e["destaque"] for e in evs),
                    "eventos": [e["titulo"] for e in evs],
                }
            )
        d += dt.timedelta(days=1)

    return {
        "label": mes_label(primeiro),
        "ano": primeiro.year,
        "mes": primeiro.month,
        "letivos": letivos,
        "feriados": feriados,
        "sabados": sabados,
        "semanas": [celulas[i:i + 7] for i in range(0, len(celulas), 7)],
    }


#: rótulos dos tipos de evento (espelha ``Evento.TIPO_CHOICES``)
TIPO_LABEL = {
    "letivo": "Dia letivo",
    "sabado_letivo": "Sábado letivo",
    "sabado_reposicao": "Sábado de reposição",
    "feriado": "Feriado",
    "ponto_facultativo": "Ponto facultativo",
    "jornada_pedagogica": "Jornada pedagógica",
    "recesso": "Recesso escolar",
    "ferias_coletivas": "Férias coletivas",
    "avaliacao": "Avaliação",
    "avaliacao_final": "Avaliação final",
    "recuperacao": "Recuperação paralela",
    "conselho_classe": "Conselho de classe",
    "matricula": "Matrícula",
    "administrativo": "Administrativo",
    "evento": "Evento institucional",
}


def _vazio() -> dict:
    return {
        "parametros": {"data_inicio": "", "data_fim": ""},
        "meses": [],
        "resumo": [],
        "total_letivos": 0,
        "letivos_seg_sex": 0,
        "sabados_total": 0,
        "sabados_letivos": [],
        "eventos_por_mes": [],
        "eventos_dia": {},
        "feriados": [],
        "legenda": [],
        "dias_cabecalho": DIAS_CABECALHO,
        "status_label": STATUS_LABEL,
        "validacao": {
            "total_letivos": 0,
            "previsto": 0,
            "diferenca": None,
            "ok": True,
            "avisos": [],
        },
    }


def build_agenda(
    data_inicio,
    data_fim=None,
    feriados=None,
    eventos=None,
    dias_letivos_previstos=0,
    dias_letivos_por_mes=None,
) -> dict:
    """Monta a agenda do documento oficial a partir dos parâmetros.

    Devolve um dicionário pronto para template/JSON com as grades mensais, o
    resumo de dias letivos (calculado × declarado), os sábados letivos, a tabela
    de eventos, a lista de feriados/pontos facultativos, a legenda e a validação.
    """
    ini = parse_date(data_inicio)
    if ini is None:
        return _vazio()

    feriados_map, eventos_norm, eventos_por_dia = _normalizar(feriados, eventos)

    candidatos = [ini]
    fim = parse_date(data_fim)
    if fim:
        candidatos.append(fim)
    candidatos += [e["data_fim"] for e in eventos_norm]
    candidatos += list(feriados_map)
    fim = max(candidatos)
    if fim < ini:
        ini, fim = fim, ini

    # Grades mensais: do mês do primeiro registro do documento (ex.: matrículas
    # de agosto aparecem antes do início do período letivo) até o mês final.
    marcos = [ini, fim]
    marcos += [e["data_inicio"] for e in eventos_norm]
    marcos += list(feriados_map)
    grid_ini = min(marcos)

    meses = []
    cursor = dt.date(grid_ini.year, grid_ini.month, 1)
    while cursor <= fim:
        meses.append(_mes(cursor, ini, fim, feriados_map, eventos_por_dia))
        cursor = _fim_do_mes(cursor) + dt.timedelta(days=1)

    # Números declarados no documento (opcional) para conferência.
    declarado = {}
    for item in dias_letivos_por_mes or []:
        if not isinstance(item, dict):
            continue
        chave = (item.get("mes") or "").strip().upper()
        if not chave:
            continue
        try:
            declarado[chave] = int(item.get("letivos") or 0)
        except (TypeError, ValueError):
            declarado[chave] = 0

    resumo = []
    total = 0
    for m in meses:
        total += m["letivos"]
        dec = declarado.get(m["label"].upper())
        resumo.append(
            {
                "label": m["label"],
                "letivos": m["letivos"],
                "feriados": m["feriados"],
                "sabados": m["sabados"],
                "declarado": dec,
                "tem_declarado": dec is not None,
                "diferenca": (None if dec is None else m["letivos"] - dec),
            }
        )

    # Sábados letivos com o dia da semana referenciado.
    sabados = []
    for e in eventos_norm:
        if e["tipo"] not in ("sabado_letivo", "sabado_reposicao"):
            continue
        ref = e["dia_semana_referencia"]
        sabados.append(
            {
                "date": e["data_inicio"].isoformat(),
                "label": f"{e['data_inicio'].day:02d}/{e['data_inicio'].month:02d}",
                "titulo": e["titulo"],
                "tipo": e["tipo"],
                "referencia": (
                    f"referente à {NOMES_SEMANA[ref]}"
                    if ref is not None and 0 <= ref < len(NOMES_SEMANA)
                    else ""
                ),
            }
        )

    # Total de sábados efetivamente letivos dentro do período (contagem por mês)
    # e o total de dias letivos de segunda a sexta (sem os sábados).
    sabados_total = sum(r["sabados"] for r in resumo)
    letivos_seg_sex = total - sabados_total

    # Tabela de eventos agrupada por mês (MÊS · DIA · EVENTO).
    eventos_por_mes = []
    for m in meses:
        itens = [
            e
            for e in eventos_norm
            if e["data_inicio"].year == m["ano"] and e["data_inicio"].month == m["mes"]
        ]
        if not itens:
            continue
        eventos_por_mes.append(
            {
                "label": m["label"],
                "itens": [
                    {
                        "dia": dia_label(e["data_inicio"], e["data_fim"]),
                        "titulo": e["titulo"],
                        "tipo": e["tipo"],
                        "tipo_label": TIPO_LABEL.get(e["tipo"], e["tipo"]),
                        "referencia": (
                            f"referente à {NOMES_SEMANA[e['dia_semana_referencia']]}"
                            if e["dia_semana_referencia"] is not None
                            and 0 <= e["dia_semana_referencia"] < len(NOMES_SEMANA)
                            else ""
                        ),
                        "descricao": e["descricao"],
                    }
                    for e in itens
                ],
            }
        )

    # Feriados/pontos facultativos (o documento lista inclusive datas fora do
    # período, como 07/SET — véspera do início do semestre).
    feriados_lista = [
        {
            "date": d.isoformat(),
            "label": f"{d.day:02d}/{d.month:02d}",
            "descricao": info["descricao"],
            "tipo": info["tipo"],
            "tipo_label": TIPO_LABEL.get(info["tipo"], info["tipo"]),
        }
        for d, info in sorted(feriados_map.items())
    ]

    # Eventos por data (ISO → títulos), usado nos tooltips dos dias das grades.
    eventos_dia = {
        d.isoformat(): [e["titulo"] for e in evs]
        for d, evs in eventos_por_dia.items()
        if evs
    }

    # Legenda: apenas os status efetivamente usados nas grades.
    usados = {}
    for m in meses:
        for semana in m["semanas"]:
            for c in semana:
                if c.get("vazio"):
                    continue
                st = c["status"]
                if st != STATUS_FORA and st not in usados:
                    usados[st] = STATUS_LABEL.get(st, st)
    legenda = [{"status": k, "label": v} for k, v in usados.items()]

    # Validação: total calculado × previsto e calculado × declarado por mês.
    previsto = int(dias_letivos_previstos or 0)
    avisos = []
    if previsto and total != previsto:
        avisos.append(
            f"Total de dias letivos calculado ({total}) difere do previsto ({previsto})."
        )
    for r in resumo:
        if r["diferenca"]:
            avisos.append(
                f"{r['label']}: calculado {r['letivos']} × declarado {r['declarado']}."
            )

    return {
        "parametros": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()},
        "meses": meses,
        "resumo": resumo,
        "total_letivos": total,
        "letivos_seg_sex": letivos_seg_sex,
        "sabados_total": sabados_total,
        "sabados_letivos": sabados,
        "eventos_por_mes": eventos_por_mes,
        "eventos_dia": eventos_dia,
        "feriados": feriados_lista,
        "legenda": legenda,
        "dias_cabecalho": DIAS_CABECALHO,
        "status_label": STATUS_LABEL,
        "validacao": {
            "total_letivos": total,
            "previsto": previsto,
            "diferenca": (total - previsto) if previsto else None,
            "ok": (not previsto) or total == previsto,
            "avisos": avisos,
        },
    }


