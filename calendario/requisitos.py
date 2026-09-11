"""Requisitos mínimos do calendário acadêmico (arts. 38, 39 e 40 do regulamento).

Cada modalidade do calendário aponta para a norma aplicável e a norma vira uma
lista de itens verificáveis:

* ``evento``    — exige pelo menos um evento que case por ``tipos`` ou ``palavras``;
* ``calculado`` — derivado da agenda (dias letivos, sábados, feriados, período…);
* ``manual``    — não verificável por regra (sai como *conferir*).

A verificação é **determinística** (não depende de IA): a IA só sugere e ajuda a
interpretar o que a regra não consegue (o :func:`calendario.llm.verificar_eventos`
mescla as duas visões). Nada aqui grava no banco.
"""
from __future__ import annotations

import re
import unicodedata

#: modalidade → norma
NORMA_POR_MODALIDADE = {
    "integrado_medio": "Art. 38",
    "concomitante_subsequente": "Art. 39",
    "graduacao": "Art. 40",
}

#: modalidade usada quando a informada não é reconhecida
MODALIDADE_PADRAO = "integrado_medio"

TITULOS = {
    "Art. 38": "Cursos técnicos integrados ao nível médio",
    "Art. 39": "Cursos técnicos concomitantes/subsequentes",
    "Art. 40": "Cursos de graduação",
}

SITUACAO_ATENDIDO = "atendido"
SITUACAO_FALTANDO = "faltando"
SITUACAO_CONFERIR = "conferir"

STATUS_LABEL = {
    SITUACAO_ATENDIDO: "Atendido",
    SITUACAO_FALTANDO: "Faltando",
    SITUACAO_CONFERIR: "Conferir",
}


def _slug_texto(valor) -> str:
    """Minúsculas sem acentos, para casar palavras-chave com robustez."""
    bruto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in bruto if not unicodedata.combining(c)).lower()


def _texto_evento(e) -> str:
    """Texto pesquisável de um evento (modelo ou dict)."""
    if isinstance(e, dict):
        return _slug_texto(f"{e.get('titulo', '')} {e.get('descricao', '')}")
    return _slug_texto(f"{getattr(e, 'titulo', '')} {getattr(e, 'descricao', '')}")


def _tipo_evento(e) -> str:
    if isinstance(e, dict):
        return str(e.get("tipo") or "")
    return str(getattr(e, "tipo", "") or "")


def _data_evento(e):
    valor = e.get("data_inicio") if isinstance(e, dict) else getattr(e, "data_inicio", None)
    if hasattr(valor, "strftime"):
        return valor
    if valor:
        try:
            from .scheduling import parse_date

            return parse_date(valor)
        except (ValueError, TypeError):
            return None
    return None


def _rotulo_evento(e) -> str:
    data = _data_evento(e)
    titulo = e.get("titulo", "") if isinstance(e, dict) else getattr(e, "titulo", "")
    prefixo = f"{data:%d/%m} — " if data else ""
    return f"{prefixo}{titulo}".strip()


def _item(codigo, descricao, *, modo="evento", tipos=(), palavras=(), calculado=None, dica=""):
    return {
        "codigo": codigo,
        "descricao": descricao,
        "modo": modo,
        "tipos": list(tipos),
        "palavras": list(palavras),
        "calculado": calculado,
        "dica": dica,
    }


#: Referência normativa completa — vai para o prompt da IA, para a interface e para
#: a documentação (RN CONSUP/IFPI 253/2025, Resolução CONSUP 078/2018, LDB 9.394/96
#: e a atualização das normas com os itens acrescentados).
REFERENCIA_NORMAS = (
    "Normas aplicáveis: Resolução Normativa CONSUP/IFPI nº 253, de 22/12/2025 "
    "(Organização Didática do IFPI — arts. 38, 39 e 40); Resolução CONSUP nº 078, de "
    "14/11/2018 (elaboração do calendário acadêmico — art. 10); LDB (Lei nº 9.394/1996) "
    "— art. 24 (carga horária mínima anual distribuída por, no mínimo, 200 dias de "
    "efetivo trabalho escolar, excluído o tempo reservado aos exames finais) e art. 47 "
    "(200 dias de trabalho acadêmico efetivo na educação superior). Atualização das "
    "normas: o calendário deve atender 200 dias no ano letivo, com no mínimo 100 dias de "
    "efetivo trabalho escolar por semestre; além dos arts. 38/39/40 e do art. 10 da "
    "Resolução 078/2018, devem constar: mobilidade acadêmica (transferência interna), "
    "Disciplinas Eletivas Livres, avaliação dos cursos (níveis médio e superior), 20/11 "
    "como Dia Nacional de Zumbi e da Consciência Negra (feriado nacional — Lei nº "
    "14.759/2023), Semana Escolar de Combate à Violência contra a Mulher (março — Lei nº "
    "14.164/2021), Semana Nacional de Ciência e Tecnologia (SNCT — Decreto de 9/6/2004) "
    "e os temas transversais obrigatórios: Educação dos Direitos Humanos (Decreto nº "
    "7.037/2009 e Resolução CNE/CP nº 1/2012), Educação Ambiental (Resolução CNE/CP nº "
    "2/2012) e Educação no Trânsito (Lei nº 9.503/1997) — essas atividades devem ser "
    "descritas no calendário, cadastradas no Módulo Eventos do SUAP e registradas em "
    "foto/vídeo (indicador 1.5 da avaliação externa dos cursos de graduação); férias "
    "coletivas de no máximo 15 dias antes do início das aulas; ano letivo concluído em "
    "no máximo 365 dias corridos."
)


def referencia_normas() -> str:
    """Bloco normativo aplicável (prompt da IA, interface e documentação)."""
    return REFERENCIA_NORMAS


def _romano(numero: int) -> str:
    """Converte 1 → ``I``, 23 → ``XXIII`` (numeração dos artigos)."""
    valores = (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
        (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    )
    saida = ""
    for valor, simbolo in valores:
        while numero >= valor:
            saida += simbolo
            numero -= valor
    return saida


def _itens_atualizacao(primeiro: int) -> list[dict]:
    """Itens acrescentados pela **atualização das normas** (iguais nas 3 modalidades).

    ``primeiro`` é o número romano do primeiro item novo — a numeração continua a da
    norma (arts. 38/39/40), como se os itens fossem apensados ao artigo.
    """
    codigos = [_romano(n) for n in range(primeiro, primeiro + 11)]
    return [
        _item(codigos[0], "Data para solicitação de mobilidade acadêmica (transferência interna)",
              palavras=[r"mobilidade", r"transfer.{0,12}interna"],
              dica="mobilidade acadêmica / transferência interna"),
        _item(codigos[1], "Datas para solicitação de Disciplinas Eletivas Livres",
              palavras=[r"eletiva"], dica="Disciplinas Eletivas Livres"),
        _item(codigos[2], "Datas para avaliação dos cursos (níveis médio e superior)",
              palavras=[r"avalia.{0,18}curso", r"avalia.{0,18}institucional", r"indicador 1\.5"],
              dica="avaliação dos cursos — indicador 1.5 (instrumento de avaliação externa)"),
        _item(codigos[3], "Dia Nacional de Zumbi e da Consciência Negra (20 de novembro)",
              palavras=[r"consci.ncia negra", r"zumbi"],
              dica="evento alusivo de 20/11 — feriado nacional desde 2024 (Lei nº 14.759/2023)"),
        _item(codigos[4], "Semana Escolar de Combate à Violência contra a Mulher (março)",
              palavras=[r"viol.ncia contra a mulher", r"combate.{0,20}viol.ncia"],
              dica="semana de março — Lei nº 14.164/2021"),
        _item(codigos[5], "Semana Nacional de Ciência e Tecnologia (SNCT)",
              palavras=[r"snct", r"ci.ncia e tecnologia"],
              dica="SNCT — Decreto de 9/6/2004"),
        _item(codigos[6], "Temas transversais: Educação dos Direitos Humanos",
              palavras=[r"direitos humanos", r"educa.{0,18}direitos humanos"],
              dica="Decreto nº 7.037/2009 e Resolução CNE/CP nº 1/2012"),
        _item(codigos[7], "Temas transversais: Educação Ambiental",
              palavras=[r"educa.{0,18}ambiental", r"meio ambiente", r"sustentabilidade"],
              dica="Resolução CNE/CP nº 2/2012"),
        _item(codigos[8], "Temas transversais: Educação no Trânsito",
              palavras=[r"tr.nsito", r"contran"],
              dica="Lei nº 9.503/1997 — campanhas educativas do CONTRAN"),
        _item(codigos[9], "Comprovação dos temas transversais (registro foto/vídeo e SUAP)",
              modo="manual",
              dica="descrever as atividades no calendário, cadastrar no Módulo Eventos do "
                   "SUAP e registrar foto/vídeo (comprovação — indicador 1.5)"),
        _item(codigos[10], "Carga horária mínima: 200 dias no ano letivo / 100 por semestre",
              modo="calculado", calculado="carga_minima",
              dica="LDB arts. 24 e 47 — excluído o tempo reservado aos exames finais"),
    ]


# ---------------------------------------------------------------------------
# Art. 38 — cursos técnicos integrados ao nível médio
# ---------------------------------------------------------------------------

ITENS_ART38 = [
    _item("I", "Matrícula dos alunos aprovados no Exame Classificatório",
          tipos=["matricula"], palavras=[r"classificat"],
          dica="matrícula dos aprovados no Exame Classificatório, antes do início do período"),
    _item("II", "Aulas do Programa de Acolhimento ao Estudante Ingressante (PRAEI)",
          palavras=[r"praei", r"acolhimento"], dica="aulas do PRAEI / acolhimento dos ingressantes"),
    _item("III", "Período de Planejamento Bimestral de Ensino",
          tipos=["jornada_pedagogica"], palavras=[r"planejamento", r"bimestral"],
          dica="jornada/planejamento bimestral de ensino, antes do início das aulas"),
    _item("IV", "Datas para eleições de representantes de turma",
          palavras=[r"elei.{0,12}representante", r"representante.{0,12}turma"],
          dica="eleição dos representantes de turma"),
    _item("V", "Datas para realização de provas", tipos=["avaliacao"],
          dica="avaliações bimestrais"),
    _item("VI", "Datas para realização de provas de segunda chamada",
          palavras=[r"segunda chamada", r"2.\s?chamada"], dica="provas de segunda chamada"),
    _item("VII", "Datas para realização da recuperação paralela", tipos=["recuperacao"],
          dica="recuperação paralela"),
    _item("VIII", "Início e fim dos períodos letivos: bimestre e semestre",
          modo="calculado", calculado="periodo", dica="início/término do período letivo"),
    _item("IX", "Início e fim do ano letivo", palavras=[r"ano letivo"],
          dica="início e término do ano letivo"),
    _item("X", "Período de férias docentes", tipos=["ferias_coletivas"], palavras=[r"ferias"],
          dica="férias docentes/coletivas"),
    _item("XI", "Os dias letivos", modo="calculado", calculado="dias_letivos"),
    _item("XII", "Os sábados letivos", modo="calculado", calculado="sabados"),
    _item("XIII", "Os dias para reposição de aulas", tipos=["sabado_reposicao", "sabado_letivo"],
          palavras=[r"reposi"], dica="dias/sábados de reposição de aulas"),
    _item("XIV", "Os dias de feriados", modo="calculado", calculado="feriados"),
    _item("XV", "Os dias de recesso", tipos=["recesso"], dica="recesso escolar"),
    _item("XVI", "Os dias reservados a comemorações cívicas e sociais",
          palavras=[r"civic", r"comemora", r"alusiv"], dica="comemorações cívicas e sociais"),
    _item("XVII", "A quantidade de dias letivos previstos para cada mês",
          modo="calculado", calculado="meses_declarados"),
    _item("XVIII", "Prazos de lançamento de notas no Sistema de Gestão Acadêmica",
          tipos=["administrativo"], palavras=[r"suap", r"lancamento.*nota", r"nota.*sistema"],
          dica="prazo de lançamento de notas no SUAP ao fim de cada bimestre"),
    _item("XIX", "As reuniões de pais dos estudantes",
          palavras=[r"reuni.{0,15}pais", r"pais.{0,10}reuni"], dica="reunião de pais"),
    _item("XX", "Datas para realização do Conselho de Classe", tipos=["conselho_classe"],
          dica="conselho de classe"),
] + _itens_atualizacao(21) + [
    _item("XXXII", "Outros eventos de relevância cultural, científica e institucional",
          tipos=["evento"], dica="eventos culturais/científicos/institucionais"),
]

# ---------------------------------------------------------------------------
# Art. 39 — cursos técnicos concomitantes/subsequentes
# ---------------------------------------------------------------------------

ITENS_ART39 = [
    _item("I", "Matrícula dos alunos aprovados no Exame Classificatório",
          tipos=["matricula"], palavras=[r"classificat"],
          dica="matrícula dos aprovados no Exame Classificatório"),
    _item("II", "Período de Planejamento Semestral de Ensino",
          tipos=["jornada_pedagogica"], palavras=[r"planejamento", r"semestral"],
          dica="planejamento semestral de ensino"),
    _item("III", "Matrícula, trancamento, cancelamento de disciplinas, reabertura, "
                 "reingresso e dispensa de disciplinas",
          tipos=["matricula"],
          palavras=[r"trancamento", r"cancelamento", r"reabertura", r"reingresso", r"dispensa"],
          dica="matrícula/trancamento/cancelamento/reabertura/reingresso/dispensa de disciplinas"),
    _item("IV", "Datas para eleições de representantes de turma",
          palavras=[r"elei.{0,12}representante", r"representante.{0,12}turma"],
          dica="eleição dos representantes de turma"),
    _item("V", "Datas para realização de provas", tipos=["avaliacao"],
          dica="avaliações bimestrais"),
    _item("VI", "Datas para realização de provas de segunda chamada",
          palavras=[r"segunda chamada", r"2.\s?chamada"], dica="provas de segunda chamada"),
    _item("VII", "Datas para a Prova Final", tipos=["avaliacao_final"],
          palavras=[r"prova final"], dica="prova final"),
    _item("VIII", "Datas para realização da recuperação paralela", tipos=["recuperacao"],
          dica="recuperação paralela"),
    _item("IX", "Início e fim dos períodos letivos: bimestre e semestre",
          modo="calculado", calculado="periodo"),
    _item("X", "Início e fim do ano letivo", palavras=[r"ano letivo"]),
    _item("XI", "Período de férias docentes", tipos=["ferias_coletivas"], palavras=[r"ferias"],
          dica="férias docentes/coletivas"),
    _item("XII", "Os dias letivos", modo="calculado", calculado="dias_letivos"),
    _item("XIII", "Os sábados letivos", modo="calculado", calculado="sabados"),
    _item("XIV", "Os dias para reposição de aulas", tipos=["sabado_reposicao", "sabado_letivo"],
          palavras=[r"reposi"], dica="dias/sábados de reposição"),
    _item("XV", "Os dias de feriados", modo="calculado", calculado="feriados"),
    _item("XVI", "Os dias de recesso", tipos=["recesso"], dica="recesso escolar"),
    _item("XVII", "Os dias reservados a comemorações cívicas e sociais",
          palavras=[r"civic", r"comemora", r"alusiv"], dica="comemorações cívicas e sociais"),
    _item("XVIII", "A quantidade de dias letivos previstos para cada mês",
          modo="calculado", calculado="meses_declarados"),
    _item("XIX", "Prazos de lançamento de notas no Sistema de Gestão Acadêmica",
          tipos=["administrativo"], palavras=[r"suap", r"lancamento.*nota", r"nota.*sistema"],
          dica="prazo de lançamento de notas no SUAP ao fim de cada bimestre/semestre"),
    _item("XX", "Datas para realização do Conselho de Classe", tipos=["conselho_classe"],
          dica="conselho de classe"),
] + _itens_atualizacao(21) + [
    _item("XXXII", "Outros eventos de relevância cultural, científica e institucional",
          tipos=["evento"], dica="eventos culturais/científicos/institucionais"),
]


# ---------------------------------------------------------------------------
# Art. 40 — cursos de graduação
# ---------------------------------------------------------------------------

ITENS_ART40 = [
    _item("I", "Período de Planejamento Semestral de Ensino",
          tipos=["jornada_pedagogica"], palavras=[r"planejamento", r"semestral"],
          dica="planejamento semestral de ensino"),
    _item("II", "Matrícula, trancamento, cancelamento de disciplinas, reabertura, "
                "reingresso e dispensa de disciplinas",
          tipos=["matricula"],
          palavras=[r"trancamento", r"cancelamento", r"reabertura", r"reingresso", r"dispensa"],
          dica="matrícula/trancamento/cancelamento/reabertura/reingresso/dispensa de disciplinas"),
    _item("III", "Datas para realização de provas", tipos=["avaliacao"]),
    _item("IV", "Datas para realização de provas de segunda chamada",
          palavras=[r"segunda chamada", r"2.\s?chamada"], dica="provas de segunda chamada"),
    _item("V", "Datas para a Prova Final", tipos=["avaliacao_final"], palavras=[r"prova final"],
          dica="prova final"),
    _item("VI", "Início e fim dos períodos letivos: bimestre e semestre",
          modo="calculado", calculado="periodo"),
    _item("VII", "Início e fim do ano letivo", palavras=[r"ano letivo"]),
    _item("VIII", "Período de férias docentes", tipos=["ferias_coletivas"], palavras=[r"ferias"],
          dica="férias docentes/coletivas"),
    _item("IX", "Os dias letivos", modo="calculado", calculado="dias_letivos"),
    _item("X", "Os sábados letivos", modo="calculado", calculado="sabados"),
    _item("XI", "Os dias para reposição de aulas", tipos=["sabado_reposicao", "sabado_letivo"],
          palavras=[r"reposi"], dica="dias/sábados de reposição"),
    _item("XII", "Os dias de feriados", modo="calculado", calculado="feriados"),
    _item("XIII", "Os dias de recesso", tipos=["recesso"], dica="recesso escolar"),
    _item("XIV", "Os dias reservados a comemorações cívicas e sociais",
          palavras=[r"civic", r"comemora", r"alusiv"], dica="comemorações cívicas e sociais"),
    _item("XV", "A quantidade de dias letivos previstos para cada mês",
          modo="calculado", calculado="meses_declarados"),
    _item("XVI", "Prazos de lançamento de notas no Sistema de Gestão Acadêmica",
          tipos=["administrativo"], palavras=[r"suap", r"lancamento.*nota", r"nota.*sistema"],
          dica="prazo de lançamento de notas no SUAP ao fim de cada bimestre/semestre"),
    _item("XVII", "Período de planejamento semestral de ensino (item repetido — equivale a I)",
          tipos=["jornada_pedagogica"], palavras=[r"planejamento", r"semestral"]),
    _item("XVIII", "Data para ambientação dos calouros",
          palavras=[r"ambienta", r"calouro"], dica="ambientação dos calouros"),
    _item("XIX", "Data da divulgação de relação dos prováveis concludentes",
          palavras=[r"concludente"], dica="divulgação dos prováveis concludentes"),
    _item("XX", "Data de solicitação de colação de grau pelos prováveis concluintes",
          palavras=[r"colacao de grau", r"cola.{0,3}o de grau"],
          dica="solicitação de colação de grau"),
    _item("XXI", "Validação de Atividades Complementares, PCCS e ATPA",
          palavras=[r"atpa", r"pccs", r"atividades complementares", r"praticas curriculares"],
          dica="validação de ACC/PCCS/ATPA"),
] + _itens_atualizacao(22) + [
    _item("XXXIII", "Outros eventos de relevância cultural, científica e institucional",
          tipos=["evento"], dica="eventos culturais/científicos/institucionais"),
]

#: norma → itens
ITENS_POR_NORMA = {
    "Art. 38": ITENS_ART38,
    "Art. 39": ITENS_ART39,
    "Art. 40": ITENS_ART40,
}


# ---------------------------------------------------------------------------
# Verificação determinística
# ---------------------------------------------------------------------------


def modalidade_valida(modalidade) -> str:
    """Devolve uma modalidade conhecida (cai no padrão quando desconhecida)."""
    valor = (modalidade or "").strip().lower()
    return valor if valor in NORMA_POR_MODALIDADE else MODALIDADE_PADRAO


def norma_da_modalidade(modalidade) -> str:
    """Norma aplicável à modalidade (ex.: ``"Art. 38"``)."""
    return NORMA_POR_MODALIDADE[modalidade_valida(modalidade)]


def itens_da_modalidade(modalidade) -> list[dict]:
    """Itens exigidos pela norma da modalidade."""
    return [dict(i) for i in ITENS_POR_NORMA[norma_da_modalidade(modalidade)]]


def info_da_modalidade(modalidade) -> dict:
    """Norma + itens da modalidade (usado no prompt e na interface)."""
    valor = modalidade_valida(modalidade)
    norma = NORMA_POR_MODALIDADE[valor]
    return {
        "modalidade": valor,
        "norma": norma,
        "titulo": TITULOS[norma],
        "referencia": REFERENCIA_NORMAS,
        "itens": [dict(i) for i in ITENS_POR_NORMA[norma]],
    }


def formatar_para_prompt(modalidade) -> str:
    """Lista os itens da norma em texto, para embutir no prompt da LLM."""
    linhas = []
    for item in itens_da_modalidade(modalidade):
        dica = f" — {item['dica']}" if item["dica"] else ""
        linhas.append(f"- {item['codigo']}) {item['descricao']}{dica}")
    return "\n".join(linhas)


def _match_item(item, eventos) -> list:
    """Eventos que satisfazem um item (por tipo ou por palavra-chave)."""
    achados = []
    for e in eventos:
        if item["tipos"] and _tipo_evento(e) in item["tipos"]:
            achados.append(e)
            continue
        if item["palavras"]:
            texto = _texto_evento(e)
            if any(re.search(p, texto) for p in item["palavras"]):
                achados.append(e)
    return achados


def _checar_calculado(chave, agenda, dias_letivos_por_mes) -> tuple[str, str]:
    """Avalia um item derivado da agenda: ``(situacao, evidencia)``."""
    ag = agenda or {}
    if chave == "periodo":
        params = ag.get("parametros") or {}
        if params.get("data_inicio") and params.get("data_fim"):
            return (
                SITUACAO_ATENDIDO,
                f"período letivo de {params['data_inicio']} a {params['data_fim']}",
            )
        if params.get("data_inicio"):
            return SITUACAO_FALTANDO, "informe o término do período letivo (bloco 1.2)"
        return SITUACAO_FALTANDO, "informe o início do semestre (bloco 1.2)"
    if chave == "dias_letivos":
        total = int(ag.get("total_letivos") or 0)
        if total:
            return SITUACAO_ATENDIDO, f"{total} dias letivos no período"
        return SITUACAO_FALTANDO, "nenhum dia letivo calculado no período"
    if chave == "sabados":
        total = int(ag.get("sabados_total") or 0)
        if total:
            return SITUACAO_ATENDIDO, f"{total} sábado(s) letivo(s)/de reposição"
        return SITUACAO_FALTANDO, "nenhum sábado letivo lançado"
    if chave == "feriados":
        total = len(ag.get("feriados") or [])
        if total:
            return SITUACAO_ATENDIDO, f"{total} feriado(s)/ponto(s) facultativo(s) no documento"
        return SITUACAO_FALTANDO, "nenhum feriado/ponto facultativo lançado"
    if chave == "carga_minima":
        dados = ag.get("carga_minima") or {}
        total = int(dados.get("total") if dados.get("total") is not None else ag.get("total_letivos") or 0)
        aplicado = int(dados.get("aplicado") or 0)
        if not aplicado:
            return (
                SITUACAO_CONFERIR,
                "informe o período e os dias letivos previstos (bloco 1.2) para conferir "
                "o mínimo legal",
            )
        unidade = "no ano letivo" if dados.get("ano") else "por semestre"
        texto = f"{total} dias letivos (mínimo legal: {aplicado} {unidade})"
        return (SITUACAO_ATENDIDO if total >= aplicado else SITUACAO_FALTANDO), texto
    if chave == "meses_declarados":
        if dias_letivos_por_mes:
            return (
                SITUACAO_ATENDIDO,
                f"{len(dias_letivos_por_mes)} mês(es) com total declarado para conferência",
            )
        return (
            SITUACAO_CONFERIR,
            "os totais por mês não foram declarados; o documento publica o total "
            "calculado — confira o resumo mensal",
        )
    return SITUACAO_CONFERIR, "verificação não implementada para este item"


def verificar_requisitos(
    modalidade,
    eventos=None,
    feriados=None,
    agenda=None,
    dias_letivos_por_mes=None,
    extras=None,
) -> dict:
    """Confere os itens da norma da modalidade contra eventos, feriados e agenda.

    ``extras`` mescla itens avaliados externamente (ex.: pela LLM) no formato
    ``{codigo: {"situacao", "motivo", "evento_sugerido"}}``. A regra local **nunca**
    é rebaixada pela IA: quando a IA vê evidência que a regra não viu, o item vira
    *conferir* (com o motivo da IA). Devolve
    ``{modalidade, norma, titulo, itens, resumo, avisos}``.
    """
    valor = modalidade_valida(modalidade)
    info = info_da_modalidade(valor)
    eventos = list(eventos or [])
    avisos = []
    informada = (modalidade or "").strip()
    if informada and informada.lower() != valor:
        avisos.append(
            f'Modalidade "{informada}" não reconhecida — usando "{valor}" ({info["norma"]}).'
        )
    if agenda is None:
        avisos.append(
            "A agenda não foi calculada: os itens derivados do período saem como “conferir”."
        )

    itens = []
    for item in info["itens"]:
        registro = {
            "codigo": item["codigo"],
            "descricao": item["descricao"],
            "dica": item["dica"],
            "modo": item["modo"],
            "evidencias": [],
            "situacao": SITUACAO_CONFERIR,
            "motivo": "",
            "evento_sugerido": None,
        }
        if item["modo"] == "manual":
            registro["motivo"] = "Item não verificável automaticamente — confira manualmente."
        elif item["modo"] == "calculado":
            situacao, evidencia = _checar_calculado(
                item["calculado"], agenda, dias_letivos_por_mes
            )
            registro["situacao"] = situacao
            if evidencia:
                registro["evidencias"] = [evidencia]
                if situacao != SITUACAO_ATENDIDO:
                    registro["motivo"] = evidencia
        else:
            achados = _match_item(item, eventos)
            if achados:
                registro["situacao"] = SITUACAO_ATENDIDO
                registro["evidencias"] = [_rotulo_evento(e) for e in achados[:4]]
            else:
                registro["situacao"] = SITUACAO_FALTANDO
                registro["motivo"] = "Nenhum evento do calendário atende a este item."

        externo = (extras or {}).get(str(item["codigo"]))
        if isinstance(externo, dict) and registro["situacao"] != SITUACAO_ATENDIDO:
            # Evidência local manda: se a regra já achou o item, a IA não rebaixa
            # nem substitui a evidência. Nos demais casos, a análise da IA entra
            # como motivo e a sugestão fica disponível para o usuário marcar.
            externa = str(externo.get("situacao") or "").lower()
            motivo_externo = str(externo.get("motivo") or "")[:400]
            sugestao = externo.get("evento_sugerido")
            if registro["situacao"] == SITUACAO_FALTANDO and externa == SITUACAO_ATENDIDO:
                registro["situacao"] = SITUACAO_CONFERIR
                if not registro["evidencias"]:
                    registro["evidencias"] = ["apontado pela IA — confirme o evento/data"]
                if motivo_externo:
                    registro["motivo"] = motivo_externo
            elif motivo_externo:
                registro["motivo"] = motivo_externo
            if sugestao and registro["situacao"] != SITUACAO_ATENDIDO:
                registro["evento_sugerido"] = sugestao

        registro["situacao_label"] = STATUS_LABEL[registro["situacao"]]
        itens.append(registro)

    resumo = {
        "total": len(itens),
        "atendidos": sum(1 for i in itens if i["situacao"] == SITUACAO_ATENDIDO),
        "faltando": sum(1 for i in itens if i["situacao"] == SITUACAO_FALTANDO),
        "conferir": sum(1 for i in itens if i["situacao"] == SITUACAO_CONFERIR),
    }
    resumo["ok"] = resumo["faltando"] == 0
    return {
        "modalidade": valor,
        "norma": info["norma"],
        "titulo": info["titulo"],
        "itens": itens,
        "resumo": resumo,
        "avisos": avisos,
    }






