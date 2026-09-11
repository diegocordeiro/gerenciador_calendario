"""Cálculo da agenda do calendário no formato do documento oficial.

Diferente de ``scheduling`` (que produz a grade de semanas x1/x2 com
remanejamento de feriados), aqui o calendário é montado **mês a mês**, como no
documento publicado pelo campus: grade mensal com o status de cada dia, resumo
de dias letivos por mês, sábados letivos com o dia da semana referenciado,
tabela de eventos e feriados/pontos facultativos.

Regra de dia letivo (documentada e coberta por testes):

* a **faixa do cálculo** é o período **declarado** (``data_inicio`` → ``data_fim``):
  registros fora dela aparecem no documento (o grid começa no primeiro registro),
  ficam com status ``fora`` e **não entram em nenhum cálculo**;
* **segunda a sexta** dentro da faixa é *letivo*, exceto em feriado, ponto
  facultativo, recesso, férias coletivas e avaliação final;
* **contam** na carga horária os dias de: *dia letivo*, *sábado letivo*,
  *avaliação*, *recuperação paralela* e *evento institucional* (ver
  :data:`TIPOS_QUE_CONTAM`);
* **removem** o dia letivo — mesmo caindo num dia útil dentro do período — os tipos
  de feriado, ponto facultativo, recesso, férias coletivas, avaliação final,
  **conselho de classe** e sábado de reposição (ver :data:`TIPOS_QUE_REMOVEM`);
* *matrícula*, *administrativo* e **jornada pedagógica** são **marcadores/avisos**
  (:data:`TIPOS_NEUTROS`): não criam dia letivo nem o removem — o dia segue a regra
  normal (útil dentro do período = letivo e contabilizado);
* **sábado** conta somente com evento do tipo *sábado letivo*; *sábado de
  reposição* aparece na grade (e na legenda) mas **não** conta (nem entra no total
  de sábados letivos). **domingo** nunca conta;
* eventos de *sábado letivo/de reposição* só têm efeito quando caem no sábado: em
  dia útil o dia segue a regra normal (letivo) e, se o evento tiver intervalo,
  cada sábado do intervalo conta — os dias úteis do meio são ignorados.
"""
from __future__ import annotations

import datetime as dt
import math

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
#: rótulo de cada dia útil (índice = ``date.weekday()``: 0=segunda … 4=sexta),
#: usado na contagem dos dias letivos **por dia da semana**.
DIAS_SEMANA_LABEL = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
]

#: status possíveis de um dia na agenda
STATUS_LETIVO = "letivo"
STATUS_LETIVO_SABADO = "letivo_sabado"
STATUS_REPOSICAO = "reposicao"
STATUS_FERIADO = "feriado"
STATUS_PONTO = "ponto_facultativo"
STATUS_RECESSO = "recesso"
STATUS_FERIAS = "ferias"
STATUS_AVALIACAO_FINAL = "avaliacao_final"
STATUS_CONSELHO = "conselho"
STATUS_NAO_LETIVO = "nao_letivo"
STATUS_FORA = "fora"

#: status que contam como dia letivo (dentro do período declarado) e só em dia útil
#: — o sábado conta apenas como *sábado letivo* e o domingo nunca conta.
STATUS_LETIVOS = {
    STATUS_LETIVO,
    STATUS_LETIVO_SABADO,
}

#: Tipos de evento (``Evento.TIPO_CHOICES``) cujos dias entram na carga horária:
#:
#: * ``letivo`` e ``sabado_letivo`` são o próprio dia letivo;
#: * ``avaliacao``, ``recuperacao`` e ``evento`` (institucional) são dias de
#:   atividade que **contam**.
TIPOS_QUE_CONTAM = (
    "letivo",
    "sabado_letivo",
    "avaliacao",
    "recuperacao",
    "evento",
)

#: Tipos que **removem** o dia letivo: se caírem num dia útil dentro do período
#: declarado, aquele dia deixa de ser contabilizado (fica com o status próprio do
#: tipo, em cor e legenda, mas fora da carga horária). ``sabado_reposicao`` também
#: não conta (é atividade de sábado, fora da carga horária).
TIPOS_QUE_REMOVEM = (
    "feriado",
    "ponto_facultativo",
    "recesso",
    "ferias_coletivas",
    "avaliacao_final",
    "conselho_classe",
    "sabado_reposicao",
)

#: Tipos **neutros** (marcadores/avisos): não criam dia letivo nem o removem — o dia
#: segue a regra normal (útil dentro do período = letivo).
TIPOS_NEUTROS = (
    "matricula",
    "administrativo",
    "jornada_pedagogica",
)

#: tipos de evento que só valem quando caem no sábado (nos demais dias o dia é
#: tratado pela regra normal de dia letivo/feriado).
TIPOS_SABADO = ("sabado_letivo", "sabado_reposicao")

#: Pisos e limites da **atualização das normas** (LDB arts. 24 e 47 e orientação do
#: calendário): 200 dias no ano letivo, no mínimo 100 dias de efetivo trabalho
#: escolar por semestre, até 15 dias de férias coletivas antes do início das aulas
#: e ano letivo concluído em no máximo 365 dias corridos (incluindo as férias).
CARGA_MINIMA_SEMESTRE = 100
CARGA_MINIMA_ANO = 200
LIMITE_FERIAS_ANTES = 15
LIMITE_DIAS_ANO_LETIVO = 365

STATUS_LABEL = {
    STATUS_LETIVO: "Dia letivo",
    STATUS_LETIVO_SABADO: "Sábado letivo",
    STATUS_REPOSICAO: "Sábado de reposição (não conta)",
    STATUS_FERIADO: "Feriado",
    STATUS_PONTO: "Ponto facultativo",
    STATUS_RECESSO: "Recesso escolar",
    STATUS_FERIAS: "Férias coletivas",
    STATUS_AVALIACAO_FINAL: "Avaliação final",
    STATUS_CONSELHO: "Conselho de classe",
    STATUS_NAO_LETIVO: "Não letivo",
    STATUS_FORA: "Fora do período",
}

#: prioridade dos eventos por tipo (o primeiro que casar define o status do dia).
#: Tipos ausentes daqui são **neutros** (marcadores/avisos): ``matricula``,
#: ``administrativo`` e ``jornada_pedagogica`` — o dia segue a regra normal
#: (útil dentro do período = letivo) e continua contando.
PRIORIDADE_TIPOS = [
    ("feriado", STATUS_FERIADO),
    ("ponto_facultativo", STATUS_PONTO),
    ("recesso", STATUS_RECESSO),
    ("ferias_coletivas", STATUS_FERIAS),
    ("avaliacao_final", STATUS_AVALIACAO_FINAL),
    ("conselho_classe", STATUS_CONSELHO),
    ("sabado_reposicao", STATUS_REPOSICAO),
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
        # Eventos de sábado letivo/reposição só valem no sábado: se o evento tem
        # intervalo (ex.: 19/09 a 26/09), os dias úteis do meio **não** viram sábado
        # — cada sábado do intervalo conta como um sábado próprio.
        so_sabados = item["tipo"] in TIPOS_SABADO
        d = ini
        while d <= fim:
            if not so_sabados or d.weekday() == 5:
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
    # Sábado letivo/de reposição só vale no sábado: em dia útil o dia segue a regra
    # normal (letivo) e no domingo continua não letivo.
    if d.weekday() != 5:
        tipos -= set(TIPOS_SABADO)
    for tipo, status in PRIORIDADE_TIPOS:
        if tipo in tipos:
            return status
    if d.weekday() >= 5:
        return STATUS_NAO_LETIVO
    return STATUS_LETIVO


def _conta_dia(status: str, d: dt.date) -> bool:
    """O dia entra na carga horária?

    Só **dias úteis** (seg–sex) contam; o sábado conta apenas como *sábado letivo* e
    o domingo nunca conta. Eventos fora da faixa declarada nem chegam aqui — o dia
    fica com status ``fora``.
    """
    if status == STATUS_LETIVO_SABADO:
        return d.weekday() == 5
    if d.weekday() >= 5:
        return False
    return status in STATUS_LETIVOS


def _referencia_sabado(evs) -> int | None:
    """Dia da semana (0..4) referenciado por um **sábado letivo**.

    O ``Evento`` do tipo *sábado letivo* é somado ao dia da semana informado no
    campo ``dia_semana_referencia`` (ex.: um sábado referente à quarta-feira conta
    como uma **quarta letiva**). O tipo *sábado de reposição* fica de fora: ele
    aparece na grade, mas **não** entra na carga horária.
    """
    for e in evs or []:
        if e.get("tipo") != "sabado_letivo":
            continue
        ref = e.get("dia_semana_referencia")
        if ref is not None and 0 <= int(ref) < 5:
            return int(ref)
    return None


def _sabados_do_periodo(eventos_norm, tipo, ini: dt.date, fim: dt.date) -> list[tuple]:
    """``(data, evento)`` de cada **sábado** do período com evento do ``tipo`` dado.

    Um evento com intervalo (ex.: 19/09 a 26/09) gera uma entrada por sábado do
    intervalo; os dias úteis do meio são ignorados.
    """
    itens = []
    for e in eventos_norm or []:
        if e["tipo"] != tipo:
            continue
        d = e["data_inicio"]
        while d <= e["data_fim"]:
            if d.weekday() == 5 and ini <= d <= fim:
                itens.append((d, e))
            d += dt.timedelta(days=1)
    itens.sort(key=lambda par: (par[0], par[1]["titulo"]))
    return itens


def _mes(primeiro: dt.date, ini: dt.date, fim: dt.date, feriados_map, eventos_por_dia) -> dict:
    """Monta a grade de um mês (domingo primeiro), como no documento."""
    ultimo = _fim_do_mes(primeiro)
    offset = (primeiro.weekday() + 1) % 7  # segunda=0 → domingo primeiro
    inicio_grid = primeiro - dt.timedelta(days=offset)
    fim_grid = ultimo + dt.timedelta(days=6 - ((ultimo.weekday() + 1) % 7))

    celulas = []
    letivos = feriados = sabados = 0
    letivos_seg_sex = 0         # dias letivos de segunda a sexta (contagem própria)
    reposicoes = 0              # sábados de reposição (não contam na carga horária)
    letivos_por_dia = [0] * 5   # letivos de segunda a sexta
    sabados_por_dia = [0] * 5   # sábados letivos, pelo dia da semana referenciado
    sabados_sem_referencia = 0
    d = inicio_grid
    while d <= fim_grid:
        if d.month != primeiro.month:
            celulas.append({"vazio": True})
        else:
            status = _status_dia(d, ini, fim, feriados_map, eventos_por_dia)
            evs = eventos_por_dia.get(d, [])
            conta = _conta_dia(status, d)
            if conta:
                letivos += 1
                if status == STATUS_LETIVO_SABADO:
                    sabados += 1
                    ref = _referencia_sabado(evs)
                    if ref is None:
                        sabados_sem_referencia += 1
                    else:
                        sabados_por_dia[ref] += 1
                else:
                    # Dias úteis que contam (letivo, avaliação, recuperação,
                    # evento institucional).
                    letivos_seg_sex += 1
                    letivos_por_dia[d.weekday()] += 1
            if status == STATUS_REPOSICAO:
                reposicoes += 1
            if status in (STATUS_FERIADO, STATUS_PONTO):
                feriados += 1
            celulas.append(
                {
                    "vazio": False,
                    "dia": d.day,
                    "date": d.isoformat(),
                    "status": status,
                    "status_label": STATUS_LABEL.get(status, status),
                    "letivo": conta,
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
        "letivos_seg_sex": letivos_seg_sex,
        "letivos_por_dia": letivos_por_dia,
        "sabados_por_dia": sabados_por_dia,
        "sabados_sem_referencia": sabados_sem_referencia,
        "feriados": feriados,
        "sabados": sabados,
        "reposicoes": reposicoes,
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
        "letivos_por_dia": [0, 0, 0, 0, 0],
        "letivos_seg_sex_por_dia": [0, 0, 0, 0, 0],
        "sabados_por_dia": [0, 0, 0, 0, 0],
        "sabados_contabilizados": 0,
        "sabados_sem_referencia": 0,
        "meta_por_dia": 0,
        "dias_por_dia": [],
        "sabados_total": 0,
        "sabados_letivos": [],
        "dias_reposicao": [],
        "reposicoes_total": 0,
        "totais_tabela": {
            "seg_sex": 0,
            "sabados": 0,
            "total": 0,
            "minimo_por_dia": 0,
            "minimo_semestre": 0,
            "sabados_sem_referencia": 0,
            "reposicoes": 0,
            "total_documento": 0,
        },
        "carga_minima": {
            "semestre": CARGA_MINIMA_SEMESTRE,
            "ano": None,
            "aplicado": 0,
            "total": 0,
            "atende": True,
        },
        "notas": [],
        "status_conta": {st: st in STATUS_LETIVOS for st in STATUS_LABEL},
        "tipos_que_contam": list(TIPOS_QUE_CONTAM),
        "tipos_que_removem": list(TIPOS_QUE_REMOVEM),
        "tipos_neutros": list(TIPOS_NEUTROS),
        "eventos_fora": [],
        "eventos_por_mes": [],
        "eventos_dia": {},
        "feriados": [],
        "legenda": [],
        "dias_cabecalho": DIAS_CABECALHO,
        "status_label": STATUS_LABEL,
        "validacao": {
            "total_letivos": 0,
            "previsto": 0,
            "letivos_seg_sex": 0,
            "por_dia_ok": True,
            "dias_por_dia": [],
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

    # Faixa do cálculo: manda o período **declarado** (`Início do semestre` →
    # `Término do período letivo`). Registros fora dessa faixa continuam aparecendo
    # no documento (o grid começa no primeiro registro), mas o dia fica "fora" e
    # **não entra em nenhum cálculo**. Sem o término informado, a faixa é estimada
    # pelo último registro — e isso é avisado nas notas.
    fim_informado = parse_date(data_fim)
    fim_estimado = fim_informado is None
    if fim_estimado:
        fim = max([ini] + [e["data_fim"] for e in eventos_norm] + list(feriados_map))
    else:
        fim = fim_informado
    if fim < ini:
        ini, fim = fim, ini

    # Eventos que ficaram totalmente fora do período (não contam para nada).
    eventos_fora = [
        e for e in eventos_norm if e["data_fim"] < ini or e["data_inicio"] > fim
    ]

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

    # Sábados letivos (com o dia da semana referenciado) e sábados de reposição.
    # Um evento com intervalo gera uma entrada por sábado; havendo mais de um
    # evento no mesmo sábado, a lista fica com uma entrada por data (preferindo a
    # que tem Referência).
    sabados = []
    vistos = set()
    for data, e in _sabados_do_periodo(eventos_norm, "sabado_letivo", ini, fim):
        if data in vistos:
            continue
        ref = e["dia_semana_referencia"]
        if ref is None and any(
            outra == data and outro["dia_semana_referencia"] is not None
            for outra, outro in _sabados_do_periodo(eventos_norm, "sabado_letivo", ini, fim)
        ):
            continue
        vistos.add(data)
        sabados.append(
            {
                "date": data.isoformat(),
                "label": f"{data.day:02d}/{data.month:02d}",
                "titulo": e["titulo"],
                "tipo": e["tipo"],
                # Sábado que cai em feriado/ponto facultativo aparece na lista mas
                # não entra na contagem (o feriado tem precedência).
                "conta": data not in feriados_map,
                "referencia": (
                    f"referente à {NOMES_SEMANA[ref]}"
                    if ref is not None and 0 <= ref < len(NOMES_SEMANA)
                    else ""
                ),
            }
        )
    sabados_em_feriado = [s for s in sabados if not s["conta"]]

    reposicoes = []
    vistas = set()
    for data, e in _sabados_do_periodo(eventos_norm, "sabado_reposicao", ini, fim):
        if data in vistas:
            continue
        vistas.add(data)
        reposicoes.append(
            {
                "date": data.isoformat(),
                "label": f"{data.day:02d}/{data.month:02d}",
                "titulo": e["titulo"],
                "tipo": e["tipo"],
                "conta": False,
                "referencia": "",
            }
        )

    # Totais do documento. O **sábado de reposição não entra na carga horária**:
    # ele aparece na grade/legenda, mas não conta como dia letivo.
    sabados_total = sum(m["sabados"] for m in meses)
    letivos_seg_sex = sum(m["letivos_seg_sex"] for m in meses)
    reposicoes_total = sum(m["reposicoes"] for m in meses)

    # Contagem dos dias letivos **por dia da semana, em separado**: soma os dias
    # de segunda a sexta e **acrescenta os sábados letivos** ao dia da semana
    # informado no campo ``Referência`` do evento (``dia_semana_referencia``).
    # A meta do semestre dividida pelos 5 dias úteis (ex.: 100/5 = 20) define o
    # mínimo esperado em cada dia da semana.
    previsto = int(dias_letivos_previstos or 0)
    letivos_seg_sex_por_dia = [
        sum(m["letivos_por_dia"][k] for m in meses) for k in range(5)
    ]
    sabados_por_dia = [sum(m["sabados_por_dia"][k] for m in meses) for k in range(5)]
    sabados_sem_referencia = sum(m["sabados_sem_referencia"] for m in meses)
    letivos_por_dia = [
        letivos_seg_sex_por_dia[k] + sabados_por_dia[k] for k in range(5)
    ]
    meta_por_dia = math.ceil(previsto / 5) if previsto else 0
    dias_por_dia = [
        {
            "weekday": k,
            "label": DIAS_SEMANA_LABEL[k],
            "seg_sex": letivos_seg_sex_por_dia[k],
            "sabados": sabados_por_dia[k],
            "letivos": letivos_por_dia[k],
            "meta": meta_por_dia,
            "falta": max(meta_por_dia - letivos_por_dia[k], 0),
            "ok": (meta_por_dia == 0) or letivos_por_dia[k] >= meta_por_dia,
        }
        for k in range(5)
    ]
    por_dia_ok = all(d["ok"] for d in dias_por_dia)

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
    # Status que contam na carga horária (em dia útil) — usado pela interface para
    # marcar os dias e explicar a legenda.
    status_conta = {st: st in STATUS_LETIVOS for st in STATUS_LABEL}
    legenda = [
        {"status": k, "label": v, "conta": status_conta.get(k, False)}
        for k, v in usados.items()
    ]

    # Validação: total calculado × previsto, calculado × declarado por mês e a
    # contagem de cada dia da semana (mínimo de ``previsto/5`` por dia).
    avisos = []
    if previsto and total != previsto:
        avisos.append(
            f"Total de dias letivos calculado ({total}) difere do previsto ({previsto})."
        )
    for d in dias_por_dia:
        if not d["ok"]:
            avisos.append(
                f"{d['label']}: {d['letivos']} dia(s) letivo(s) — mínimo "
                f"{d['meta']} ({previsto}/5)."
            )
    if sabados_sem_referencia:
        avisos.append(
            f"{sabados_sem_referencia} sábado(s) letivo(s) sem dia da semana "
            "referenciado (campo Referência) — não contabilizados por dia."
        )
    for r in resumo:
        if r["diferenca"]:
            avisos.append(
                f"{r['label']}: calculado {r['letivos']} × declarado {r['declarado']}."
            )

    # Sábados cadastrados fora do sábado (o dia segue a regra normal: não vira
    # sábado letivo) e eventos de sábado com intervalo.
    for e in eventos_norm:
        if e["tipo"] not in TIPOS_SABADO:
            continue
        if e["data_inicio"].weekday() != 5:
            avisos.append(
                f"{e['titulo']} ({e['data_inicio']:%d/%m/%Y}) é um evento de sábado "
                "cadastrado fora do sábado — esse dia NÃO entra como sábado letivo."
            )
        elif e["data_fim"] > e["data_inicio"]:
            qtd = len(_sabados_do_periodo([e], e["tipo"], ini, fim))
            avisos.append(
                f"{e['titulo']} tem intervalo de "
                f"{e['data_inicio']:%d/%m/%Y} a {e['data_fim']:%d/%m/%Y}: considerados "
                f"{qtd} sábado(s) do intervalo (os dias úteis do meio são ignorados)."
            )
    if sabados_em_feriado:
        datas = ", ".join(s["label"] for s in sabados_em_feriado)
        avisos.append(
            f"{len(sabados_em_feriado)} sábado(s) letivo(s) caíram em feriado/ponto "
            f"facultativo ({datas}) — não entram na contagem de dias letivos."
        )

    # --- Atualização das normas: carga horária mínima, férias e duração do ano ---
    # 200 dias no ano letivo e, no mínimo, 100 dias de efetivo trabalho escolar por
    # semestre (LDB arts. 24 e 47, excluído o tempo reservado aos exames finais). O
    # ano letivo é reconhecido pelo período declarado (mais de 180 dias corridos) ou
    # pela meta declarada de 200 dias ou mais.
    periodo_dias = (fim - ini).days + 1
    ano_letivo = periodo_dias > 180 or previsto >= CARGA_MINIMA_ANO
    piso = CARGA_MINIMA_ANO if ano_letivo else CARGA_MINIMA_SEMESTRE
    carga_minima = {
        "semestre": CARGA_MINIMA_SEMESTRE,
        "ano": CARGA_MINIMA_ANO if ano_letivo else None,
        "aplicado": piso,
        "total": total,
        "atende": total >= piso,
    }
    if total < piso:
        avisos.append(
            f"Total de dias letivos ({total}) abaixo do mínimo legal ({piso} dias "
            f"{'no ano letivo' if ano_letivo else 'por semestre'}) — LDB arts. 24 e 47."
        )

    # Férias coletivas antes do início das aulas: no máximo ``LIMITE_FERIAS_ANTES``.
    dias_ferias_antes = set()
    ultimo_dia_antes = ini - dt.timedelta(days=1)
    for e in eventos_norm:
        if e["tipo"] != "ferias_coletivas" or e["data_inicio"] >= ini:
            continue
        dia = e["data_inicio"]
        limite = min(e["data_fim"] or e["data_inicio"], ultimo_dia_antes)
        while dia <= limite:
            dias_ferias_antes.add(dia)
            dia += dt.timedelta(days=1)
    if len(dias_ferias_antes) > LIMITE_FERIAS_ANTES:
        avisos.append(
            f"{len(dias_ferias_antes)} dia(s) de férias coletivas antes do início das "
            f"aulas — o planejamento orienta no máximo {LIMITE_FERIAS_ANTES} dias."
        )

    # Duração do ano letivo: no máximo ``LIMITE_DIAS_ANO_LETIVO`` dias corridos,
    # contando as férias coletivas que antecedem as aulas.
    inicio_ano = min([ini] + [d for d in dias_ferias_antes]) if dias_ferias_antes else ini
    duracao_ano = (fim - inicio_ano).days + 1
    if duracao_ano > LIMITE_DIAS_ANO_LETIVO:
        avisos.append(
            f"Período de {duracao_ano} dias corridos (de {inicio_ano:%d/%m/%Y} a "
            f"{fim:%d/%m/%Y}) — o ano letivo deve ser concluído em no máximo "
            f"{LIMITE_DIAS_ANO_LETIVO} dias corridos, incluindo as férias coletivas."
        )

    # Notas informativas (não são problemas): reposição fora da carga horária e os
    # registros que ficaram fora do período declarado.
    notas = []
    if reposicoes_total:
        datas = ", ".join(r["label"] for r in reposicoes)
        notas.append(
            f"{reposicoes_total} sábado(s) de reposição ({datas}) — o tipo "
            "“Sábado de reposição” não entra na carga horária nem no total de "
            "sábados letivos."
        )
    if fim_estimado:
        notas.append(
            "Término do período letivo não informado — a faixa usada no cálculo foi "
            f"estimada pelo último registro ({fim:%d/%m/%Y})."
        )
    if eventos_fora:
        datas = ", ".join(f"{e['data_inicio']:%d/%m/%Y}" for e in eventos_fora[:6])
        complemento = "…" if len(eventos_fora) > 6 else ""
        notas.append(
            f"{len(eventos_fora)} evento(s) fora do período letivo ({datas}{complemento}) — "
            "aparecem no documento, mas não entram na carga horária."
        )

    # Totais do rodapé da tabela "Dias letivos por dia da semana": são exatamente a
    # **soma das colunas**, garantindo que o rodapé sempre feche com as linhas.
    sabados_contabilizados = sum(sabados_por_dia)
    totais_tabela = {
        "seg_sex": sum(letivos_seg_sex_por_dia),
        "sabados": sabados_contabilizados,
        "total": sum(letivos_por_dia),
        "minimo_por_dia": meta_por_dia,
        "minimo_semestre": meta_por_dia * 5,
        "sabados_sem_referencia": sabados_sem_referencia,
        "reposicoes": reposicoes_total,
        "total_documento": total,
    }

    return {
        "parametros": {"data_inicio": ini.isoformat(), "data_fim": fim.isoformat()},
        "meses": meses,
        "resumo": resumo,
        "total_letivos": total,
        "letivos_seg_sex": letivos_seg_sex,
        "letivos_por_dia": letivos_por_dia,
        "letivos_seg_sex_por_dia": letivos_seg_sex_por_dia,
        "sabados_por_dia": sabados_por_dia,
        "sabados_contabilizados": sabados_contabilizados,
        "sabados_sem_referencia": sabados_sem_referencia,
        "meta_por_dia": meta_por_dia,
        "dias_por_dia": dias_por_dia,
        "sabados_total": sabados_total,
        "sabados_letivos": sabados,
        "dias_reposicao": reposicoes,
        "reposicoes_total": reposicoes_total,
        "totais_tabela": totais_tabela,
        "carga_minima": carga_minima,
        "notas": notas,
        "status_conta": status_conta,
        "tipos_que_contam": list(TIPOS_QUE_CONTAM),
        "tipos_que_removem": list(TIPOS_QUE_REMOVEM),
        "tipos_neutros": list(TIPOS_NEUTROS),
        "eventos_fora": [e["data_inicio"].isoformat() for e in eventos_fora],
        "eventos_por_mes": eventos_por_mes,
        "eventos_dia": eventos_dia,
        "feriados": feriados_lista,
        "legenda": legenda,
        "dias_cabecalho": DIAS_CABECALHO,
        "status_label": STATUS_LABEL,
        "validacao": {
            "total_letivos": total,
            "previsto": previsto,
            "letivos_seg_sex": letivos_seg_sex,
            "letivos_por_dia": letivos_por_dia,
            "letivos_seg_sex_por_dia": letivos_seg_sex_por_dia,
            "sabados_por_dia": sabados_por_dia,
            "sabados_sem_referencia": sabados_sem_referencia,
            "sabados_contabilizados": sabados_contabilizados,
            "reposicoes_total": reposicoes_total,
            "totais_tabela": totais_tabela,
            "notas": notas,
            "meta_por_dia": meta_por_dia,
            "por_dia_ok": por_dia_ok,
            "dias_por_dia": dias_por_dia,
            "diferenca": (total - previsto) if previsto else None,
            "ok": (not previsto) or total == previsto,
            "avisos": avisos,
        },
    }


