"""Preenchimento assistido dos eventos por LLM (DeepSeek, ChatGPT, Gemini, Claude).

O fluxo é sempre o mesmo, independente do provedor:

1. :func:`montar_prompt` monta o pedido em texto com o contexto do calendário, a
   lista fechada de tipos de evento e o esquema JSON esperado;
2. :func:`chamar_provedor` conversa com a API do provedor (via ``urllib``, sem
   dependência externa) e devolve o texto bruto;
3. :func:`parse_resposta` extrai o JSON da resposta (tolerante a cercas de código);
4. :func:`validar_normalizar` descarta o que não é válido e normaliza os campos;
5. :func:`completar_sabados` **fecha a carga horária** de cada dia da semana com
   sábados letivos — cálculo determinístico, feito em Python, e não pelo modelo.

A LLM só sugere; quem garante as regras é este módulo. Nada aqui grava no banco.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
import unicodedata
import urllib.error
import urllib.request

from django.conf import settings

from . import requisitos
from .agenda import DIAS_SEMANA_LABEL
from .data.feriados import feriados_nacionais
from .models import Evento
from .scheduling import parse_date

DIALETOS = ("openai", "gemini", "anthropic")
MAX_DESCRICAO = 500

#: Margem (em dias) aceita **antes** do início do período letivo. Matrículas,
#: jornada pedagógica (planejamento) e feriados da véspera fazem parte do
#: calendário oficial mesmo caindo antes do primeiro dia de aula.
MARGEM_ANTES = 120
#: Margem depois do término (recesso, férias docentes, conselho final). Mantida
#: curta de propósito: a agenda vai até o último registro, então datas muito
#: posteriores ao término inflariam o total de dias letivos calculado.
MARGEM_DEPOIS = 10

TIPOS_EVENTO = [t for t, _ in Evento.TIPO_CHOICES]
_TIPOS_LABEL = {t: lbl for t, lbl in Evento.TIPO_CHOICES}
TIPOS_SABADO = ("sabado_letivo", "sabado_reposicao")

#: aliases de tipo aceitos vindos do modelo (além dos valores de ``TIPO_CHOICES``)
_ALIASES_TIPO = {
    "feriado_municipal": "feriado",
    "feriado_estadual": "feriado",
    "feriado_nacional": "feriado",
    "facultativo": "ponto_facultativo",
    "sabado": "sabado_letivo",
    "sábado": "sabado_letivo",
    "sabado letivo": "sabado_letivo",
    "sabado_reposicao": "sabado_reposicao",
    "sábado de reposição": "sabado_reposicao",
    "reposicao": "sabado_reposicao",
    "reposição": "sabado_reposicao",
    "avaliacoes": "avaliacao",
    "avaliações": "avaliacao",
    "recuperacao": "recuperacao",
    "recuperação": "recuperacao",
    "conselho": "conselho_classe",
    "matriculas": "matricula",
    "matrículas": "matricula",
    "institucional": "evento",
    "evento_institucional": "evento",
}


def _sem_acento(valor: str) -> str:
    """Minúsculas sem acentos (para casar apelidos de tipo com robustez)."""
    bruto = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in bruto if not unicodedata.combining(c)).lower()


#: apelidos indexados pela forma normalizada (sem acentos)
_ALIASES_TIPO_NORM = {_sem_acento(k): v for k, v in _ALIASES_TIPO.items()}

#: ``dia_semana_referencia`` escrito por extenso → índice (0=segunda … 4=sexta)
_DIAS_POR_NOME = {
    "segunda": 0, "segunda-feira": 0, "seg": 0,
    "terca": 1, "terça": 1, "terca-feira": 1, "terça-feira": 1, "ter": 1,
    "quarta": 2, "quarta-feira": 2, "qua": 2,
    "quinta": 3, "quinta-feira": 3, "qui": 3,
    "sexta": 4, "sexta-feira": 4, "sex": 4,
}

_ESFERAS = ("municipal", "estadual", "federal", "institucional", "manual")


class LlmError(Exception):
    """Erro no uso da IA (mensagem amigável para o usuário)."""


class LlmConfigError(LlmError):
    """Configuração/entrada inválida (chave ausente, período ausente…) → HTTP 400."""


class LlmProviderError(LlmError):
    """Falha do provedor (HTTP, timeout, JSON ilegível) → HTTP 502."""


# ---------------------------------------------------------------------------
# Configuração / provedores
# ---------------------------------------------------------------------------


def resolver_provedor(nome=None) -> str:
    """Resolve o nome do provedor aceitando apelidos (``chatgpt`` → ``openai``)."""
    bruto = (nome or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")
    if not bruto:
        bruto = (settings.LLM_DEFAULT_PROVIDER or "deepseek").strip().lower()
    provedores = settings.LLM_PROVIDERS or {}
    if bruto in provedores:
        return bruto
    return (settings.LLM_PROVIDER_ALIASES or {}).get(bruto, bruto)


def config_provedor(nome=None) -> dict:
    """Devolve a configuração (label, dialeto, url, modelo, chave) do provedor."""
    chave = resolver_provedor(nome)
    cfg = (settings.LLM_PROVIDERS or {}).get(chave)
    if not cfg:
        raise LlmConfigError(f'Provedor de IA desconhecido: "{nome}".')
    dialeto = (cfg.get("dialeto") or "openai").lower()
    if dialeto not in DIALETOS:
        raise LlmConfigError(f'Dialeto "{dialeto}" não suportado pelo provedor "{chave}".')
    return {"chave": chave, **cfg, "dialeto": dialeto}


def provedores_disponiveis() -> list[dict]:
    """Lista os provedores para o modal: ``[{valor, label, modelo, disponivel}]``."""
    itens = []
    for valor, cfg in (settings.LLM_PROVIDERS or {}).items():
        itens.append(
            {
                "valor": valor,
                "label": cfg.get("label") or valor,
                "modelo": cfg.get("model") or "",
                "disponivel": bool(
                    settings.LLM_ENABLED and (cfg.get("api_key") or "").strip()
                ),
            }
        )
    return itens


def tem_provedor_configurado() -> bool:
    """Há pelo menos um provedor habilitado com chave de API?"""
    return bool(settings.LLM_ENABLED) and any(
        p["disponivel"] for p in provedores_disponiveis()
    )


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def _json_dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def _feriados_nacionais_iso(inicio: dt.date, fim: dt.date) -> list[dict]:
    """Feriados federais calculados localmente (anos cobertos pelo período)."""
    itens = []
    for ano in range(inicio.year, fim.year + 1):
        itens += feriados_nacionais(ano)
    janela_ini = inicio - dt.timedelta(days=MARGEM_ANTES)
    janela_fim = fim + dt.timedelta(days=MARGEM_DEPOIS)
    return [
        {"data": f["data"].isoformat(), "descricao": f["descricao"]}
        for f in itens
        if janela_ini <= f["data"] <= janela_fim
    ]


def _meses_do_periodo(inicio: dt.date, fim: dt.date) -> list[str]:
    meses = []
    cursor = dt.date(inicio.year, inicio.month, 1)
    while cursor <= fim:
        meses.append(f"{cursor.month:02d}/{cursor.year}")
        cursor = dt.date(cursor.year + 1, 1, 1) if cursor.month == 12 else dt.date(
            cursor.year, cursor.month + 1, 1
        )
    return meses


def prompt_sistema() -> str:
    return (
        "Você responde sempre com um único objeto JSON válido, sem comentários e sem "
        "texto fora do JSON. Nunca inventa datas de feriados municipais/estaduais: "
        "quando não tiver certeza, omite o item."
    )


def prompt_sistema_verificacao() -> str:
    return (
        "Você é um auditor de calendários acadêmicos. Responde sempre com um único "
        "objeto JSON válido, sem texto fora do JSON, e nunca afirma que um item está "
        "atendido sem apontar o evento que o cumpre."
    )


def montar_prompt_verificacao(
    entrada: dict,
    inicio: dt.date,
    fim: dt.date,
    eventos: list[dict],
    feriados: list[dict],
    agenda: dict,
    conferencia: dict,
) -> str:
    """Monta o pedido de **auditoria** dos eventos já lançados contra a norma."""
    norma_info = requisitos.info_da_modalidade(entrada.get("modalidade"))
    previsto = int(entrada.get("dias_letivos_previstos") or 0)
    meta = math.ceil(previsto / 5) if previsto else 0
    janela_sug_ini = inicio - dt.timedelta(days=MARGEM_ANTES)
    janela_sug_fim = fim + dt.timedelta(days=MARGEM_DEPOIS)
    checklist = "\n".join(
        f"- {i['codigo']}) [{i['situacao']}] {i['descricao']}"
        + (f" — evidência: {'; '.join(i['evidencias'])}" if i["evidencias"] else "")
        for i in conferencia.get("itens", [])
    )
    eventos_txt = _json_dump(
        [
            {
                "titulo": e.get("titulo"),
                "tipo": e.get("tipo"),
                "data_inicio": e.get("data_inicio"),
                "data_fim": e.get("data_fim") or None,
                "dia_semana_referencia": e.get("dia_semana_referencia"),
            }
            for e in eventos
        ]
    )
    feriados_txt = _json_dump(
        [
            {
                "data": f.get("data"),
                "tipo": f.get("tipo"),
                "descricao": f.get("descricao"),
            }
            for f in feriados
        ]
    )

    return f"""Audite o calendário acadêmico abaixo contra a norma {norma_info['norma']} \
({norma_info['titulo']}) e aponte o que falta.

# Unidade
- Cidade: {entrada.get('cidade') or '-'} | Estado (UF): {entrada.get('estado') or '-'} | País: {entrada.get('pais') or 'Brasil'}
- Instituição: {entrada.get('instituicao') or '-'} | Curso: {entrada.get('curso') or '-'} | Modalidade: {norma_info['titulo']}

# Período
- De {inicio.isoformat()} a {fim.isoformat()}
- Sugestões podem usar datas de {janela_sug_ini.isoformat()} a {janela_sug_fim.isoformat()}
  (matrículas e planejamento antes do início; recesso/férias depois do término)
- Meta de dias letivos: {previsto} (mínimo {meta} por dia da semana)

# Resumo calculado do calendário
{_json_dump({
    'total_letivos': agenda.get('total_letivos'),
    'letivos_seg_sex': agenda.get('letivos_seg_sex'),
    'sabados_letivos': agenda.get('sabados_total'),
    'letivos_por_dia': agenda.get('letivos_por_dia'),
    'meta_por_dia': agenda.get('meta_por_dia'),
})}

# Eventos lançados
{eventos_txt}

# Feriados/pontos facultativos lançados
{feriados_txt}

# Atividades exigidas pela norma (código, item)
{requisitos.formatar_para_prompt(entrada.get('modalidade'))}

# Conferência automática já feita (pode discordar, mas sempre com motivo e evidência)
{checklist}

# Tarefas
1. Para CADA código acima, informe a situação: "atendido", "faltando" ou "conferir".
   Só marque "atendido" citando em "motivo" o evento (título e data) que cumpre o item.
2. Nos itens "faltando", sugira UM evento em "evento_sugerido" (com título, tipo da lista
   permitida e data plausível dentro do período) OU null quando não for aplicável.
3. Aponte em "observacoes" incoerências de datas (ex.: avaliação antes do início das aulas,
   recesso sobre feriado, sábado letivo em data que já é feriado).

# Formato da resposta
{{
  "requisitos": [
    {{"codigo": "IV", "situacao": "faltando", "motivo": "não há evento de eleição de representantes",
      "evento_sugerido": {{"titulo": "Eleição de representantes de turma", "tipo": "evento",
                          "data_inicio": "YYYY-MM-DD", "data_fim": null,
                          "dia_semana_referencia": null}}}}
  ],
  "observacoes": ["..."]
}}
"""



def montar_prompt(entrada: dict, inicio: dt.date, fim: dt.date) -> str:
    """Monta o texto do pedido (o mesmo para todos os provedores)."""
    tipos = "\n".join(f'  - "{t}" = {_TIPOS_LABEL[t]}' for t in TIPOS_EVENTO)
    sabados = [
        d.isoformat()
        for d in (inicio + dt.timedelta(days=i) for i in range((fim - inicio).days + 1))
        if d.weekday() == 5
    ]
    previsto = int(entrada.get("dias_letivos_previstos") or 0)
    meta = math.ceil(previsto / 5) if previsto else 0
    cidade = entrada.get("cidade")
    uf = entrada.get("estado")
    norma_info = requisitos.info_da_modalidade(entrada.get("modalidade"))
    norma = norma_info["norma"]
    norma_titulo = norma_info["titulo"]
    itens_norma = requisitos.formatar_para_prompt(entrada.get("modalidade"))
    janela_ini = inicio - dt.timedelta(days=MARGEM_ANTES)
    janela_fim = fim + dt.timedelta(days=MARGEM_DEPOIS)

    return f"""Você é um assistente especialista em calendários acadêmicos de Institutos Federais brasileiros.

# Unidade
- Cidade: {cidade}
- Estado (UF): {uf}
- País: {entrada.get('pais') or 'Brasil'}
- Instituição: {entrada.get('instituicao') or '-'}
- Curso: {entrada.get('curso') or '-'} | Modalidade: {entrada.get('modalidade') or '-'}

# Período
- Início do período letivo: {inicio.isoformat()} (segunda-feira)
- Término: {fim.isoformat()}
- Semanas: {entrada.get('total_semanas')} (1ª parte com {entrada.get('semanas_primeira_parte')} semanas; o restante é reposição)
- Meta de dias letivos do semestre: {previsto} (equivale a {meta} por dia da semana)
- Meses no período: {', '.join(_meses_do_periodo(inicio, fim))}

# Feriados FEDERAIS já confirmados (não repita com outro texto)
{_json_dump(_feriados_nacionais_iso(inicio, fim))}

# Feriados e pontos facultativos já lançados no documento (não repita)
{_json_dump(entrada.get('feriados') or [])}

# Eventos já lançados (não repita; complemente o calendário)
{_json_dump(entrada.get('eventos') or [])}

# Tipos de evento permitidos (use exatamente esta string em "tipo")
{tipos}

Observação importante sobre sábados:
- "sabado_letivo" É um dia letivo: entra na carga horária somado ao dia da semana
  informado em "dia_semana_referencia" (0 = segunda … 4 = sexta).
- "sabado_reposicao" aparece no documento mas **não** entra na carga horária.
- Nos dois casos use **uma data só** ("data_fim": null) e **sempre** informe
  "dia_semana_referencia".

# Atividades exigidas pela norma {norma} — {norma_titulo}
# O calendário DEVE contemplar TODAS as atividades abaixo:
{itens_norma}

# Tarefas
1. Feriados/pontos facultativos **municipais** (de {cidade}) e **estaduais** ({uf}) dentro do
   período (ex.: aniversário do município, padroeira, datas estaduais). NÃO invente datas:
   se não tiver certeza, omita o item.
2. Gere um evento para CADA atividade exigida pela norma acima, com data plausível dentro do
   período e o tipo adequado ("tipo" da lista permitida). Não invente atividades inaplicáveis.
3. Sábados letivos: os sábados disponíveis no período são {', '.join(sabados)}.
   Use "sabado_letivo" com "dia_semana_referencia" = 0 (segunda) a 4 (sexta), indicando qual
   dia da semana o sábado repõe. NÃO use sábado que seja feriado/ponto facultativo.

# Regras de saída
- Responda **somente** com JSON válido (sem texto antes ou depois, sem cercas de código).
- Datas no formato YYYY-MM-DD, dentro de {janela_ini.isoformat()} a {janela_fim.isoformat()}.
  Eventos preparatórios (matrículas, planejamento/jornada pedagógica) e feriados da véspera
  PODEM ser anteriores a {inicio.isoformat()}; recesso/férias podem passar de {fim.isoformat()}.
- Em "dia_semana_referencia" use o número 0–4 ou null.
- Seja conservador: prefira menos itens a inventar datas erradas.

# Formato da resposta
{{
  "feriados": [
    {{"data": "YYYY-MM-DD", "tipo": "feriado", "esfera": "municipal",
      "descricao": "Aniversário do Município de {cidade}", "confianca": "alta"}}
  ],
  "eventos": [
    {{"titulo": "Matrículas", "tipo": "matricula", "data_inicio": "YYYY-MM-DD",
      "data_fim": "YYYY-MM-DD", "dia_semana_referencia": null, "descricao": "", "destaque": false}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Comunicação HTTP (stdlib — sem dependência externa)
# ---------------------------------------------------------------------------


def _http_post_json(url: str, corpo: dict, headers: dict, timeout: int) -> dict:
    """POST JSON e devolve a resposta decodificada (erros viram ``LlmError``)."""
    dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=dados,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        try:
            detalhe = exc.read().decode("utf-8", "replace")[:400]
        except Exception:  # pragma: no cover - corpo ilegível
            detalhe = ""
        raise LlmProviderError(
            f"O provedor respondeu HTTP {exc.code}."
            + (f" {detalhe}" if detalhe else "")
        ) from exc
    except urllib.error.URLError as exc:
        raise LlmProviderError(
            f"Não foi possível falar com o provedor: {exc.reason}."
        ) from exc
    except TimeoutError as exc:  # pragma: no cover - depende da rede
        raise LlmProviderError(
            "O provedor demorou demais para responder (timeout)."
        ) from exc

    try:
        return json.loads(bruto or "{}")
    except json.JSONDecodeError as exc:
        raise LlmProviderError(
            "O provedor devolveu uma resposta que não é JSON."
        ) from exc


def _extrair_texto(dialeto: str, resposta: dict) -> str:
    """Recorta o texto gerado da resposta de cada dialeto."""
    if dialeto == "openai":
        escolhas = resposta.get("choices") or []
        if escolhas:
            return (escolhas[0].get("message") or {}).get("content") or ""
    elif dialeto == "gemini":
        candidatos = resposta.get("candidates") or []
        if candidatos:
            partes = (candidatos[0].get("content") or {}).get("parts") or []
            return "\n".join(p.get("text") or "" for p in partes)
    elif dialeto == "anthropic":
        blocos = resposta.get("content") or []
        return "\n".join(b.get("text") or "" for b in blocos if b.get("type") == "text")
    return ""


def _mensagem_de_erro(resposta: dict) -> str:
    erro = resposta.get("error")
    if isinstance(erro, dict):
        return erro.get("message") or erro.get("status") or ""
    return str(erro or "")


def _corpo_e_headers(prompt: str, sistema: str, cfg: dict, api_key: str) -> tuple[dict, dict]:
    """Monta o corpo/headers conforme o dialeto do provedor."""
    modelo = cfg.get("model") or ""
    dialeto = cfg["dialeto"]
    max_tokens = int(getattr(settings, "LLM_MAX_TOKENS", 8000))
    temperatura = float(getattr(settings, "LLM_TEMPERATURE", 0.2))

    if dialeto == "openai":
        corpo = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperatura,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        return corpo, {"Authorization": f"Bearer {api_key}"}
    if dialeto == "gemini":
        corpo = {
            "systemInstruction": {"parts": [{"text": sistema}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperatura,
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        return corpo, {"x-goog-api-key": api_key}
    corpo = {
        "model": modelo,
        "system": sistema,
        "max_tokens": max_tokens,
        "temperature": temperatura,
        "messages": [{"role": "user", "content": prompt}],
    }
    return corpo, {"x-api-key": api_key, "anthropic-version": "2023-06-01"}


def chamar_provedor(prompt: str, sistema: str, cfg: dict, transporte=None) -> str:
    """Chama o provedor e devolve o texto bruto (o JSON interno é parseado depois).

    ``transporte`` permite injetar um ``callable(url, corpo, headers, timeout)``
    nos testes, evitando acesso à rede.
    """
    enviar = transporte or _http_post_json
    api_key = (cfg.get("api_key") or "").strip()
    if not api_key and transporte is None:
        raise LlmConfigError(
            f'A chave de API do provedor "{cfg.get("label") or cfg["chave"]}" não está '
            "configurada (variável de ambiente)."
        )

    modelo = cfg.get("model") or ""
    url = (cfg.get("url") or "").replace("{model}", modelo)
    corpo, headers = _corpo_e_headers(prompt, sistema, cfg, api_key)
    resposta = enviar(url, corpo, headers, int(getattr(settings, "LLM_TIMEOUT", 120)))

    if not isinstance(resposta, dict):
        raise LlmProviderError("O provedor devolveu uma resposta inesperada.")

    if _mensagem_de_erro(resposta) and not _extrair_texto(cfg["dialeto"], resposta):
        raise LlmProviderError(f"O provedor reportou um erro: {_mensagem_de_erro(resposta)}")

    texto = _extrair_texto(cfg["dialeto"], resposta)
    if not texto.strip():
        raise LlmProviderError("O provedor não devolveu conteúdo utilizável.")
    return texto


# ---------------------------------------------------------------------------
# Leitura e normalização da resposta
# ---------------------------------------------------------------------------


def parse_resposta(texto: str) -> dict:
    """Extrai o objeto JSON da resposta do modelo (tolerante a cercas/texto)."""
    bruto = (texto or "").strip()
    if not bruto:
        raise LlmProviderError("A resposta do provedor veio vazia.")

    cerca = re.search(r"```(?:json)?\s*(.+?)```", bruto, re.S | re.I)
    if cerca:
        bruto = cerca.group(1).strip()

    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError:
        ini, fim = bruto.find("{"), bruto.rfind("}")
        if ini == -1 or fim <= ini:
            raise LlmProviderError(
                "Não foi possível ler o JSON devolvido pelo provedor "
                "(a resposta não contém um objeto JSON)."
            )
        try:
            dados = json.loads(bruto[ini : fim + 1])
        except json.JSONDecodeError as exc:
            raise LlmProviderError(
                f"O JSON devolvido pelo provedor é inválido: {exc.msg}."
            ) from exc

    if not isinstance(dados, dict):
        raise LlmProviderError("O provedor devolveu um JSON que não é um objeto.")
    return dados


def _texto(valor, limite: int = 200) -> str:
    return ("" if valor is None else str(valor)).strip()[:limite]


def _data(valor):
    try:
        return parse_date(valor)
    except (ValueError, TypeError):
        return None


def normalizar_tipo(valor) -> str:
    """Normaliza o tipo do evento para um valor válido de ``Evento.TIPO_CHOICES``."""
    bruto = _texto(valor, 60).lower()
    if not bruto:
        return "evento"
    if bruto in TIPOS_EVENTO:
        return bruto
    chave = _sem_acento(bruto).replace("-", "_")
    # aceita a forma escrita com espaços (ex.: "ponto facultativo")
    variantes = [chave, chave.replace(" ", "_").replace("  ", "_")]
    for variante in variantes:
        if variante in TIPOS_EVENTO:
            return variante
    for variante in variantes:
        if variante in _ALIASES_TIPO_NORM:
            return _ALIASES_TIPO_NORM[variante]
    return "evento"


def normalizar_feriado_origem(valor, esfera) -> str:
    """Define ``Feriado.origem`` a partir da esfera informada pelo modelo."""
    bruto = _texto(valor, 20).lower()
    if bruto in ("nacional", "estadual", "municipal", "institucional", "manual"):
        return bruto
    esfera_bruta = _texto(esfera, 20).lower()
    return esfera_bruta if esfera_bruta in _ESFERAS else "institucional"


def normalizar_dia_semana(valor):
    """Normaliza ``dia_semana_referencia`` (número, nome do dia ou ``null``)."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        numero = int(valor)
        return numero if 0 <= numero <= 4 else None
    texto = _texto(valor, 30).lower()
    if texto.isdigit():
        numero = int(texto)
        return numero if 0 <= numero <= 4 else None
    return _DIAS_POR_NOME.get(texto)


def validar_normalizar(dados: dict, inicio: dt.date, fim: dt.date) -> dict:
    """Valida e normaliza a saída do modelo; devolve ``{feriados, eventos, avisos}``.

    Regras: datas fora da janela são descartadas; tipos desconhecidos viram
    ``evento``; feriados repetidos (mesma data) são unificados; eventos repetidos
    (mesma data inicial e título) são unificados.

    A janela aceita começa :data:`MARGEM_ANTES` dias antes do início do período
    (matrículas, planejamento, feriado da véspera) e termina :data:`MARGEM_DEPOIS`
    dias depois (recesso, férias docentes, conselho final).
    """
    janela_ini = inicio - dt.timedelta(days=MARGEM_ANTES)
    janela_fim = fim + dt.timedelta(days=MARGEM_DEPOIS)
    feriados: dict[str, dict] = {}
    eventos: list[dict] = []
    vistos = set()
    avisos: list[str] = []
    descartados = 0

    for item in dados.get("feriados") or []:
        if not isinstance(item, dict):
            continue
        data = _data(item.get("data") or item.get("data_inicio"))
        if data is None or not (janela_ini <= data <= janela_fim):
            descartados += 1
            continue
        iso = data.isoformat()
        tipo = normalizar_tipo(item.get("tipo"))
        if tipo not in ("feriado", "ponto_facultativo"):
            tipo = "feriado"
        descricao = _texto(item.get("descricao") or item.get("titulo"), 200)
        if iso not in feriados:
            feriados[iso] = {
                "data": iso,
                "descricao": descricao,
                "tipo": tipo,
                "origem": normalizar_feriado_origem(item.get("origem"), item.get("esfera")),
                "esfera": _texto(item.get("esfera") or "", 20).lower(),
                "confianca": _texto(item.get("confianca") or "", 20).lower(),
                "sugerido_ia": True,
            }
        elif descricao and not feriados[iso]["descricao"]:
            feriados[iso]["descricao"] = descricao

    for item in dados.get("eventos") or []:
        if not isinstance(item, dict):
            continue
        ini = _data(item.get("data_inicio") or item.get("data"))
        if ini is None or not (janela_ini <= ini <= janela_fim):
            descartados += 1
            continue
        fim_ev = _data(item.get("data_fim")) or ini
        if fim_ev < ini:
            ini, fim_ev = fim_ev, ini
        if fim_ev > janela_fim:
            fim_ev = janela_fim
        tipo = normalizar_tipo(item.get("tipo"))
        titulo = _texto(item.get("titulo") or item.get("descricao"), 200) or (
            _TIPOS_LABEL.get(tipo) or "Evento"
        )
        assinatura = (ini.isoformat(), titulo.lower())
        if assinatura in vistos:
            continue
        vistos.add(assinatura)
        ref = item.get("dia_semana_referencia")
        if ref is None:
            ref = item.get("referencia")
        eventos.append(
            {
                "titulo": titulo,
                "tipo": tipo,
                "data_inicio": ini.isoformat(),
                "data_fim": fim_ev.isoformat() if fim_ev != ini else "",
                "dia_semana_referencia": normalizar_dia_semana(ref),
                "descricao": _texto(item.get("descricao"), MAX_DESCRICAO),
                "destaque": bool(item.get("destaque")),
                "sugerido_ia": True,
            }
        )

    if descartados:
        avisos.append(
            f"{descartados} item(ns) sugerido(s) pela IA foram descartados por data "
            f"fora da janela aceita ({janela_ini.isoformat()} a {janela_fim.isoformat()})."
        )
    eventos.sort(key=lambda e: (e["data_inicio"], e["titulo"]))
    return {"feriados": list(feriados.values()), "eventos": eventos, "avisos": avisos}


def mesclar_feriados_nacionais(feriados: list[dict], inicio: dt.date, fim: dt.date) -> list[dict]:
    """Garante os feriados federais (calculados localmente) na lista."""
    existentes = {f["data"] for f in feriados}
    itens = list(feriados)
    for f in _feriados_nacionais_iso(inicio, fim):
        if f["data"] in existentes:
            continue
        itens.append(
            {
                "data": f["data"],
                "descricao": f["descricao"],
                "tipo": "feriado",
                "origem": "nacional",
                "esfera": "federal",
                "confianca": "alta",
                "sugerido_ia": False,
            }
        )
    itens.sort(key=lambda f: f["data"])
    return itens


# ---------------------------------------------------------------------------
# Carga horária: distribuição determinística dos sábados letivos
# ---------------------------------------------------------------------------


def _sabados_usados(eventos: list[dict]) -> set[str]:
    return {
        e["data_inicio"]
        for e in eventos
        if e.get("tipo") in TIPOS_SABADO and e.get("data_inicio")
    }


def _atribuir_referencias_faltantes(
    eventos: list[dict], feriados: list[dict], inicio: dt.date, fim: dt.date, previsto: int
) -> int:
    """Preenche a Referência dos **sábados letivos** que vieram sem ``dia_semana_referencia``.

    Usa o dia da semana com maior déficit (``meta - letivos``), na mesma heurística
    do :func:`completar_sabados`, e altera a lista **in place**. Devolve quantos
    foram preenchidos. Sábados de reposição ficam de fora: eles não entram na
    carga horária, então não precisam de Referência.
    """
    from .agenda import build_agenda

    pendentes = [
        e
        for e in eventos
        if e.get("tipo") == "sabado_letivo" and e.get("dia_semana_referencia") is None
    ]
    if not pendentes:
        return 0

    meta = math.ceil(int(previsto) / 5) if previsto else 0
    if meta <= 0:
        return 0

    agenda = build_agenda(
        data_inicio=inicio,
        data_fim=fim,
        feriados=feriados,
        eventos=eventos,
        dias_letivos_previstos=previsto,
    )
    contagem = list(agenda.get("letivos_por_dia") or [0, 0, 0, 0, 0])
    ordem: list[int] = []
    preenchidos = 0
    for e in pendentes:
        deficit = [max(meta - contagem[k], 0) for k in range(5)]
        if sum(deficit) == 0:
            break
        elegiveis = [k for k in range(5) if deficit[k] > 0]
        escolhido = min(elegiveis, key=lambda k: (-deficit[k], ordem.count(k), k))
        e["dia_semana_referencia"] = escolhido
        contagem[escolhido] += 1
        ordem.append(escolhido)
        preenchidos += 1
    return preenchidos


def completar_sabados(
    eventos: list[dict],
    feriados: list[dict],
    inicio: dt.date,
    fim: dt.date,
    previsto: int,
) -> dict:
    """Acrescenta sábados letivos até cada dia da semana atingir ``ceil(previsto/5)``.

    A meta por dia sai do próprio semestre (``previsto / 5``). Cada sábado escolhido
    recebe em ``dia_semana_referencia`` o dia da semana com maior déficit, de modo
    que a soma por dia feche a carga horária. É determinístico: depende apenas dos
    parâmetros e dos itens já lançados (nada é decidido pelo modelo).
    """
    from .agenda import build_agenda

    base = [dict(e) for e in eventos]
    meta = math.ceil(int(previsto) / 5) if previsto else 0
    resultado = {
        "eventos": base,
        "meta_por_dia": meta,
        "deficit_inicial": [0] * 5,
        "faltando": [0] * 5,
        "criados": 0,
        "sabados_disponiveis": 0,
        "avisos": [],
    }
    if meta <= 0:
        return resultado

    agenda = build_agenda(
        data_inicio=inicio,
        data_fim=fim,
        feriados=feriados,
        eventos=base,
        dias_letivos_previstos=previsto,
    )
    por_dia = list(agenda.get("letivos_seg_sex_por_dia") or [0, 0, 0, 0, 0])
    deficit = [max(meta - por_dia[k], 0) for k in range(5)]
    resultado["deficit_inicial"] = list(deficit)
    if sum(deficit) == 0:
        return resultado

    # Sábados candidatos: dentro do período, sem feriado/ponto facultativo e ainda
    # não usados como letivos/reposição.
    feriados_iso = {f["data"] for f in feriados if f.get("data")}
    usados = _sabados_usados(base)
    candidatos = []
    d = inicio
    while d <= fim:
        if d.weekday() == 5 and d.isoformat() not in feriados_iso and d.isoformat() not in usados:
            candidatos.append(d)
        d += dt.timedelta(days=1)
    resultado["sabados_disponiveis"] = len(candidatos)

    # Distribui os sábados pelos dias com maior déficit, alternando para equilibrar.
    ordem: list[int] = []
    for sabado in candidatos:
        if sum(deficit) == 0:
            break
        elegiveis = [k for k in range(5) if deficit[k] > 0]
        escolhido = min(elegiveis, key=lambda k: (-deficit[k], ordem.count(k), k))
        base.append(
            {
                "titulo": "Sábado letivo",
                "tipo": "sabado_letivo",
                "data_inicio": sabado.isoformat(),
                "data_fim": "",
                "dia_semana_referencia": escolhido,
                "descricao": (
                    "Gerado automaticamente para completar a carga horária — "
                    f"referente à {DIAS_SEMANA_LABEL[escolhido]}."
                ),
                "destaque": False,
                "sugerido_ia": True,
            }
        )
        deficit[escolhido] -= 1
        ordem.append(escolhido)
        resultado["criados"] += 1

    base.sort(key=lambda e: (e["data_inicio"], e["titulo"]))
    resultado["eventos"] = base
    resultado["faltando"] = list(deficit)
    if sum(deficit):
        pendentes = ", ".join(
            f"{DIAS_SEMANA_LABEL[k]} (faltam {deficit[k]})" for k in range(5) if deficit[k]
        )
        resultado["avisos"].append(
            "Não há sábados suficientes para fechar a carga horária: "
            f"{pendentes}. Aumente o nº de semanas, reduza feriados ou ajuste os dias "
            "letivos previstos."
        )
    return resultado


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------


def _normalizar_sugestao(ev, inicio: dt.date, fim: dt.date):
    """Normaliza um ``evento_sugerido`` da IA (ou devolve ``None`` se inválido)."""
    if not isinstance(ev, dict):
        return None
    normalizado = validar_normalizar({"eventos": [ev]}, inicio, fim)
    itens = normalizado["eventos"]
    return itens[0] if itens else None


def _ler_requisitos_ia(dados: dict, inicio: dt.date, fim: dt.date) -> tuple[dict, list]:
    """Lê a lista ``requisitos`` da resposta: ``(extras, observacoes)``."""
    extras: dict[str, dict] = {}
    observacoes = []
    for item in dados.get("requisitos") or []:
        if not isinstance(item, dict):
            continue
        codigo = _texto(item.get("codigo"), 8).upper().rstrip(").").strip()
        if not codigo:
            continue
        situacao = _texto(item.get("situacao"), 20).lower()
        if situacao not in ("atendido", "faltando", "conferir"):
            situacao = "conferir"
        registro = {
            "situacao": situacao,
            "motivo": _texto(item.get("motivo"), 400),
            "evento_sugerido": _normalizar_sugestao(item.get("evento_sugerido"), inicio, fim),
        }
        extras[codigo] = registro
    for obs in dados.get("observacoes") or []:
        texto = _texto(obs, 300)
        if texto:
            observacoes.append(texto)
    return extras, observacoes


def verificar_eventos(entrada: dict, transporte=None) -> dict:
    """Audita os eventos **já lançados** contra a norma da modalidade.

    Combina a conferência determinística (:mod:`calendario.requisitos`) com a
    análise da LLM. Devolve ``{provedor, provedor_label, modelo, norma, requisitos,
    observacoes, avisos}``. **Não grava nada** — as sugestões só entram no editor
    quando o usuário marca os itens e confirma.
    """
    from .agenda import build_agenda

    if not settings.LLM_ENABLED:
        raise LlmConfigError(
            "O preenchimento por IA está desativado (LLM_ENABLED=0)."
        )
    if not tem_provedor_configurado():
        raise LlmConfigError(
            "Nenhum provedor de IA está configurado. Defina a chave de API numa "
            "variável de ambiente (ex.: DEEPSEEK_API_KEY, OPENAI_API_KEY, "
            "GEMINI_API_KEY ou ANTHROPIC_API_KEY)."
        )

    cfg = config_provedor(entrada.get("provedor"))
    inicio = _data(entrada.get("data_inicio"))
    fim = _data(entrada.get("data_fim"))
    if inicio is None or fim is None:
        raise LlmConfigError(
            "Informe o período (data de início e término) antes de verificar."
        )
    if fim < inicio:
        raise LlmConfigError("A data de término é anterior à data de início.")

    eventos = list(entrada.get("eventos") or [])
    feriados = list(entrada.get("feriados") or [])
    dias_letivos_por_mes = entrada.get("dias_letivos_por_mes") or []
    agenda = build_agenda(
        data_inicio=inicio,
        data_fim=fim,
        feriados=feriados,
        eventos=eventos,
        dias_letivos_previstos=entrada.get("dias_letivos_previstos") or 0,
        dias_letivos_por_mes=dias_letivos_por_mes,
    )
    conferencia = requisitos.verificar_requisitos(
        entrada.get("modalidade"),
        eventos=eventos,
        feriados=feriados,
        agenda=agenda,
        dias_letivos_por_mes=dias_letivos_por_mes,
    )

    contexto = {
        "cidade": _texto(entrada.get("cidade"), 120),
        "estado": _texto(entrada.get("estado"), 60),
        "pais": _texto(entrada.get("pais"), 60) or "Brasil",
        "instituicao": _texto(entrada.get("instituicao"), 200),
        "curso": _texto(entrada.get("curso"), 200),
        "modalidade": entrada.get("modalidade"),
        "dias_letivos_previstos": int(entrada.get("dias_letivos_previstos") or 0),
    }

    texto = chamar_provedor(
        montar_prompt_verificacao(
            contexto, inicio, fim, eventos, feriados, agenda, conferencia
        ),
        prompt_sistema_verificacao(),
        cfg,
        transporte=transporte,
    )
    extras, observacoes = _ler_requisitos_ia(parse_resposta(texto), inicio, fim)

    # Sábados letivos sugeridos sem Referência recebem o dia de maior déficit, para
    # que o item aplicado no editor já nasça contabilizável.
    sugeridos = [
        ex["evento_sugerido"] for ex in extras.values() if ex.get("evento_sugerido")
    ]
    if sugeridos:
        _atribuir_referencias_faltantes(
            eventos + sugeridos,
            feriados,
            inicio,
            fim,
            int(entrada.get("dias_letivos_previstos") or 0),
        )

    final = requisitos.verificar_requisitos(
        entrada.get("modalidade"),
        eventos=eventos,
        feriados=feriados,
        agenda=agenda,
        dias_letivos_por_mes=dias_letivos_por_mes,
        extras=extras,
    )
    final["observacoes"] = observacoes
    return {
        "provedor": cfg["chave"],
        "provedor_label": cfg.get("label") or cfg["chave"],
        "modelo": cfg.get("model") or "",
        "norma": final["norma"],
        "requisitos": final,
        "observacoes": observacoes,
        "avisos": list(conferencia.get("avisos") or []),
    }


def gerar_eventos(entrada: dict, transporte=None) -> dict:
    """Executa o fluxo completo: prompt → provedor → parse → validação → sábados.

    Devolve ``{provedor, provedor_label, modelo, feriados, eventos, avisos,
    estatisticas, requisitos}``. **Não grava nada no banco** — a persistência
    acontece apenas quando o usuário confirma no editor.
    """
    if not settings.LLM_ENABLED:
        raise LlmConfigError(
            "O preenchimento por IA está desativado (LLM_ENABLED=0)."
        )
    if not tem_provedor_configurado():
        raise LlmConfigError(
            "Nenhum provedor de IA está configurado. Defina a chave de API numa "
            "variável de ambiente (ex.: DEEPSEEK_API_KEY, OPENAI_API_KEY, "
            "GEMINI_API_KEY ou ANTHROPIC_API_KEY)."
        )

    cfg = config_provedor(entrada.get("provedor"))

    inicio = _data(entrada.get("data_inicio"))
    fim = _data(entrada.get("data_fim"))
    if inicio is None or fim is None:
        raise LlmConfigError(
            "Informe o período (data de início e término) antes de usar a IA."
        )
    if fim < inicio:
        raise LlmConfigError("A data de término é anterior à data de início.")

    contexto = {
        "cidade": _texto(entrada.get("cidade"), 120),
        "estado": _texto(entrada.get("estado"), 60),
        "pais": _texto(entrada.get("pais"), 60) or "Brasil",
        "instituicao": _texto(entrada.get("instituicao"), 200),
        "curso": _texto(entrada.get("curso"), 200),
        "modalidade": _texto(entrada.get("modalidade"), 60),
        "data_inicio": inicio.isoformat(),
        "data_fim": fim.isoformat(),
        "total_semanas": entrada.get("total_semanas"),
        "semanas_primeira_parte": entrada.get("semanas_primeira_parte"),
        "dias_letivos_previstos": int(entrada.get("dias_letivos_previstos") or 0),
        "feriados": entrada.get("feriados") or [],
        "eventos": entrada.get("eventos") or [],
    }

    texto = chamar_provedor(
        montar_prompt(contexto, inicio, fim), prompt_sistema(), cfg, transporte=transporte
    )
    normalizado = validar_normalizar(parse_resposta(texto), inicio, fim)

    feriados = mesclar_feriados_nacionais(normalizado["feriados"], inicio, fim)
    avisos = list(normalizado["avisos"])

    completar = entrada.get("completar_sabados")
    completar = True if completar is None else bool(completar)
    eventos = normalizado["eventos"]

    # Sábado letivo sem Referência não entra na contagem por dia: aqui ele recebe
    # automaticamente o dia da semana com maior déficit.
    atribuidos = _atribuir_referencias_faltantes(
        eventos, feriados, inicio, fim, contexto["dias_letivos_previstos"]
    )
    if atribuidos:
        avisos.append(
            f"{atribuidos} sábado(s) letivo(s) sem Referência receberam automaticamente "
            "o dia da semana com maior déficit."
        )

    estatisticas = {"sabados_criados": 0, "sabados_disponiveis": 0, "referencias_atribuidas": atribuidos}
    if completar:
        resultado = completar_sabados(
            eventos, feriados, inicio, fim, contexto["dias_letivos_previstos"]
        )
        eventos = resultado["eventos"]
        avisos += resultado["avisos"]
        estatisticas = {
            "sabados_criados": resultado["criados"],
            "sabados_disponiveis": resultado["sabados_disponiveis"],
            "meta_por_dia": resultado["meta_por_dia"],
            "deficit_inicial": resultado["deficit_inicial"],
            "faltando": resultado["faltando"],
        }

    if any(f.get("confianca") == "baixa" for f in feriados):
        avisos.append(
            "A IA sinalizou feriados municipais/estaduais com confiança baixa — "
            "confirme as datas na legislação antes de publicar."
        )

    # Conferência da norma da modalidade sobre o que foi gerado (para a prévia já
    # sair com o checklist dos arts. 38/39/40).
    from .agenda import build_agenda

    agenda = build_agenda(
        data_inicio=inicio,
        data_fim=fim,
        feriados=feriados,
        eventos=eventos,
        dias_letivos_previstos=contexto["dias_letivos_previstos"],
        dias_letivos_por_mes=entrada.get("dias_letivos_por_mes") or [],
    )
    conferencia = requisitos.verificar_requisitos(
        entrada.get("modalidade"),
        eventos=eventos,
        feriados=feriados,
        agenda=agenda,
        dias_letivos_por_mes=entrada.get("dias_letivos_por_mes") or [],
    )

    return {
        "provedor": cfg["chave"],
        "provedor_label": cfg.get("label") or cfg["chave"],
        "modelo": cfg.get("model") or "",
        "feriados": feriados,
        "eventos": eventos,
        "avisos": avisos,
        "estatisticas": estatisticas,
        "requisitos": conferencia,
        "agenda": agenda,
    }










# ---------------------------------------------------------------------------
# Verificação da lista de feriados (texto colado × calendário)
# ---------------------------------------------------------------------------

SITUACAO_FERIADO_LABEL = {
    "mapeado": "Mapeado",
    "faltando": "Faltando",
    "divergente": "Divergente",
}
SITUACAO_FERIADO_ICONE = {"mapeado": "✅", "faltando": "➡️", "divergente": "⚠"}


def prompt_sistema_feriados() -> str:
    return (
        "Você extrai listas de feriados em texto livre e responde sempre com um único "
        "objeto JSON válido, sem comentários e sem texto fora do JSON. Você não "
        "inventa feriados: converte apenas as linhas recebidas."
    )


def _marcador_linha(original: str) -> str:
    """Marcador opcional no início da linha (``✅``, ``➡️``, ``⚠️``…)."""
    achado = re.match(r"^([^\w\s(]+)", (original or "").strip())
    return achado.group(1) if achado else ""


def _sem_marcador(texto: str) -> str:
    """Remove o marcador do início da linha (mantém o resto)."""
    return re.sub(r"^[^\w(]+", "", (texto or "").strip()).strip()


def _chave_nome(texto: str) -> str:
    """Chave de comparação de nomes (sem acento, só letras/números/espaços)."""
    limpo = re.sub(r"[^a-z0-9 ]+", " ", _sem_acento(texto or ""))
    return " ".join(limpo.split())


#: palavras que não distinguem um feriado de outro (usadas no casamento por nome)
_STOPWORDS_NOME = {
    "a", "as", "o", "os", "e", "de", "da", "das", "do", "dos",
    "dia", "nacional", "municipal", "municipio", "estadual", "federal",
    "feriado", "ponto", "facultativo", "santo", "santa", "sao",
    "senhor", "senhora", "n", "s",
}


def _radicais_nome(texto: str) -> set:
    """Palavras significativas do nome do feriado (sem conectivos)."""
    return {p for p in _chave_nome(texto).split() if p not in _STOPWORDS_NOME}


def _mesmo_feriado(descricao_a: str, descricao_b: str) -> bool:
    """Dois nomes se referem ao mesmo feriado?

    Regra conservadora: se o nome mais curto tem **uma só** palavra significativa,
    ele só casa com outro de uma palavra (``Finados`` × ``Finados``); caso contrário,
    todas as palavras do menor precisam estar presentes no outro. Assim
    ``Aniversário do Município de Barras`` casa com ``Aniversário de Barras-PI``,
    mas ``Dia do Piauí`` **não** casa com ``Padroeira do Piauí``.
    """
    ra, rb = _radicais_nome(descricao_a), _radicais_nome(descricao_b)
    if not ra or not rb:
        return False
    comuns = ra & rb
    if not comuns:
        return False
    menor, maior = (ra, rb) if len(ra) <= len(rb) else (rb, ra)
    if len(menor) == 1:
        return len(maior) == 1
    return len(comuns) >= len(menor)


def _mesmo_feriado_em_outra_data(descricao: str, atuais, data_iso: str):
    """Procura o mesmo feriado cadastrado em outra data."""
    for a in atuais:
        if a["data"] != data_iso and _mesmo_feriado(descricao, a["descricao"]):
            return a
    return None


def montar_prompt_feriados(entrada: dict, inicio: dt.date, fim: dt.date, cadastrados) -> str:
    """Monta o pedido de extração/conferência da lista de feriados."""
    anos = ", ".join(str(a) for a in sorted({inicio.year, fim.year}))
    nacionais = _feriados_nacionais_iso(inicio, fim)
    return f"""Você vai converter a LISTA DE FERIADOS abaixo (texto livre, possivelmente com
emojis, meses por extenso e o dia da semana entre parênteses) em itens estruturados
para conferência contra o calendário acadêmico.

# Contexto
- Instituição: {entrada.get('instituicao') or '-'} | Curso: {entrada.get('curso') or '-'}
- Cidade: {entrada.get('cidade') or '-'} | Estado (UF): {entrada.get('estado') or '-'} | País: {entrada.get('pais') or 'Brasil'}
- Período do calendário: {inicio.isoformat()} a {fim.isoformat()}
- Ano(s) de referência: {anos} — use este ano quando a linha não tiver ano

# Feriados FEDERAIS do período (referência confiável — use para conferir nomes/datas)
{_json_dump(nacionais)}

# Feriados já cadastrados no calendário (use para eu conferir o que já existe)
{_json_dump(cadastrados)}

# LISTA DE FERIADOS (uma linha por item; ✅/➡️/etc. são apenas marcadores)
<<<LISTA
{entrada.get('lista')}
LISTA

# Tarefas
1. Converta CADA linha de feriado em um item com "data" (YYYY-MM-DD), "descricao" e
   "tipo" ("feriado" ou "ponto_facultativo" — use ponto facultativo apenas quando a
   linha indicar ponto facultativo; "Dia do Professor", "Dia do Piauí" e
   "Dia do Servidor Público" costumam ser ponto facultativo).
2. Em "esfera" informe "municipal", "estadual" ou "federal" quando der para inferir
   (ex.: aniversário da cidade/padroeira = municipal; datas nacionais = federal).
3. Preserve em "original" o texto da linha e em "marcador" o emoji inicial (se houver).
4. Use o dia da semana entre parênteses (ex.: "(terça-feira)") para confirmar a data
   no ano de referência.
5. NÃO crie itens que não estejam na lista e ignore cabeçalhos soltos
   (ex.: "Feriados", "março:", "✅ setembro:").

# Formato da resposta
{{
  "feriados": [
    {{"original": "➡️24(sexta-feira)- Aniversário de Barras-PI", "marcador": "➡️",
      "data": "YYYY-MM-DD", "descricao": "Aniversário de Barras-PI",
      "tipo": "feriado", "esfera": "municipal", "confianca": "alta"}}
  ]
}}
"""


def _ler_itens_feriados(dados: dict, anos_validos: set) -> tuple[list[dict], list[str]]:
    """Normaliza as linhas da lista que a IA devolveu (``(itens, avisos)``)."""
    itens: list[dict] = []
    avisos: list[str] = []
    vistos = set()
    descartados = 0

    for bruto in dados.get("feriados") or []:
        if not isinstance(bruto, dict):
            continue
        data = _data(bruto.get("data") or bruto.get("data_inicio"))
        if data is None or data.year not in anos_validos:
            descartados += 1
            continue
        iso = data.isoformat()
        if iso in vistos:
            avisos.append(
                f"A lista tem mais de um item em {data:%d/%m/%Y} — mantido apenas o primeiro."
            )
            continue
        vistos.add(iso)

        tipo = normalizar_tipo(bruto.get("tipo"))
        if tipo not in ("feriado", "ponto_facultativo"):
            tipo = "feriado"
        original = _texto(bruto.get("original"), 300)
        descricao = _texto(
            bruto.get("descricao") or bruto.get("titulo") or _sem_marcador(original), 200
        )
        itens.append(
            {
                "data": iso,
                "data_label": f"{data.day:02d}/{data.month:02d}/{data.year}",
                "descricao": descricao,
                "tipo": tipo,
                "tipo_label": "Ponto facultativo" if tipo == "ponto_facultativo" else "Feriado",
                "origem": normalizar_feriado_origem(bruto.get("origem"), bruto.get("esfera")),
                "esfera": _texto(bruto.get("esfera") or "", 20).lower(),
                "confianca": _texto(bruto.get("confianca") or "", 20).lower(),
                "marcador": _texto(bruto.get("marcador"), 4) or _marcador_linha(original),
                "original": original,
            }
        )

    itens.sort(key=lambda i: i["data"])
    if descartados:
        avisos.append(
            f"{descartados} linha(s) da lista não puderam ser lidas (sem data válida ou "
            "fora do ano de referência)."
        )
    return itens, avisos


def _feriados_atuais_normalizados(feriados) -> list[dict]:
    """Normaliza os feriados já cadastrados (modelo ou dict) para a conferência."""
    itens = []
    for f in feriados or []:
        if isinstance(f, dict):
            data, descricao = f.get("data"), f.get("descricao")
            tipo, origem = f.get("tipo"), f.get("origem")
        else:
            data, descricao = getattr(f, "data", None), getattr(f, "descricao", "")
            tipo, origem = getattr(f, "tipo", None), getattr(f, "origem", None)
        d = _data(data)
        if d is None:
            continue
        tipo_norm = tipo if tipo in ("feriado", "ponto_facultativo") else "feriado"
        itens.append(
            {
                "data": d.isoformat(),
                "data_label": f"{d.day:02d}/{d.month:02d}/{d.year}",
                "descricao": _texto(descricao, 200),
                "tipo": tipo_norm,
                "tipo_label": "Ponto facultativo" if tipo_norm == "ponto_facultativo" else "Feriado",
                "origem": origem or "manual",
            }
        )
    itens.sort(key=lambda i: i["data"])
    return itens


def _avaliar_item_feriado(item, atuais_por_data, atuais, inicio, fim) -> dict:
    """Veredito **determinístico** de um item da lista contra o calendário."""
    item.setdefault(
        "tipo_label",
        "Ponto facultativo" if item.get("tipo") == "ponto_facultativo" else "Feriado",
    )
    registro = atuais_por_data.get(item["data"])
    situacao = "faltando"
    motivo = "Não há feriado/ponto facultativo cadastrado nesta data."
    acao = "adicionar"

    if registro is not None:
        if registro["tipo"] == item["tipo"]:
            situacao = "mapeado"
            motivo = "Já cadastrado com o mesmo tipo."
            acao = ""
        else:
            situacao = "divergente"
            motivo = (
                f"No calendário está como “{registro['tipo_label']}”; a lista indica "
                f"“{item['tipo_label']}”."
            )
            acao = "ajustar_tipo"
    else:
        antigo = _mesmo_feriado_em_outra_data(item["descricao"], atuais, item["data"])
        if antigo is not None:
            situacao = "divergente"
            motivo = (
                f"O mesmo feriado parece cadastrado em outra data: "
                f"{antigo['data_label']} — {antigo['descricao']}."
            )
            acao = "adicionar"

    data = dt.date.fromisoformat(item["data"])
    item.update(
        {
            "situacao": situacao,
            "situacao_label": SITUACAO_FERIADO_LABEL[situacao],
            "situacao_icone": SITUACAO_FERIADO_ICONE[situacao],
            "motivo": motivo,
            "fora_do_periodo": not (inicio <= data <= fim),
            "registro": (
                f"{registro['data_label']} — {registro['descricao']} ({registro['tipo_label']})"
                if registro
                else ""
            ),
            "sugestao": (
                {
                    "acao": acao,
                    "data": item["data"],
                    "descricao": item["descricao"],
                    "tipo": item["tipo"],
                    "origem": item["origem"],
                }
                if acao
                else None
            ),
        }
    )
    return item


def verificar_feriados(entrada: dict, transporte=None) -> dict:
    """Confere a **lista de feriados colada** contra o calendário.

    A LLM apenas converte o texto em itens (data/nome/tipo/esfera); o veredito
    (``mapeado`` / ``faltando`` / ``divergente``) é calculado aqui, comparando com os
    feriados já cadastrados. **Nada é gravado.**
    """
    if not settings.LLM_ENABLED:
        raise LlmConfigError("O preenchimento por IA está desativado (LLM_ENABLED=0).")
    if not tem_provedor_configurado():
        raise LlmConfigError(
            "Nenhum provedor de IA está configurado. Defina a chave de API numa "
            "variável de ambiente (ex.: DEEPSEEK_API_KEY, OPENAI_API_KEY, "
            "GEMINI_API_KEY ou ANTHROPIC_API_KEY)."
        )

    cfg = config_provedor(entrada.get("provedor"))
    lista = (entrada.get("lista") or "").strip()
    if not lista:
        raise LlmConfigError("Cole a lista de feriados para conferir.")

    inicio = _data(entrada.get("data_inicio"))
    fim = _data(entrada.get("data_fim"))
    if inicio is None or fim is None:
        raise LlmConfigError(
            "Informe o período (início e término) antes de conferir os feriados."
        )
    if fim < inicio:
        raise LlmConfigError("A data de término é anterior à data de início.")

    anos_validos = {inicio.year, fim.year}
    atuais = _feriados_atuais_normalizados(entrada.get("feriados"))
    atuais_por_data = {a["data"]: a for a in atuais}

    contexto = {
        "cidade": _texto(entrada.get("cidade"), 120),
        "estado": _texto(entrada.get("estado"), 60),
        "pais": _texto(entrada.get("pais"), 60) or "Brasil",
        "instituicao": _texto(entrada.get("instituicao"), 200),
        "curso": _texto(entrada.get("curso"), 200),
        "lista": lista,
        "feriados": atuais,
    }

    texto = chamar_provedor(
        montar_prompt_feriados(contexto, inicio, fim, atuais),
        prompt_sistema_feriados(),
        cfg,
        transporte=transporte,
    )
    itens, avisos = _ler_itens_feriados(parse_resposta(texto), anos_validos)
    if not itens:
        avisos.append("A IA não conseguiu extrair nenhuma linha da lista de feriados.")

    avaliados = [
        _avaliar_item_feriado(dict(i), atuais_por_data, atuais, inicio, fim)
        for i in itens
    ]
    datas_lista = {i["data"] for i in avaliados}
    extras = [a for a in atuais if a["data"] not in datas_lista]

    resumo = {
        "total": len(avaliados),
        "mapeados": sum(1 for i in avaliados if i["situacao"] == "mapeado"),
        "faltando": sum(1 for i in avaliados if i["situacao"] == "faltando"),
        "divergentes": sum(1 for i in avaliados if i["situacao"] == "divergente"),
        "fora_do_periodo": sum(1 for i in avaliados if i["fora_do_periodo"]),
        "extras_no_calendario": len(extras),
    }
    resumo["ok"] = resumo["faltando"] == 0 and resumo["divergentes"] == 0

    return {
        "provedor": cfg["chave"],
        "provedor_label": cfg.get("label") or cfg["chave"],
        "modelo": cfg.get("model") or "",
        "anos": sorted(anos_validos),
        "periodo": {"data_inicio": inicio.isoformat(), "data_fim": fim.isoformat()},
        "itens": avaliados,
        "resumo": resumo,
        "extras_no_calendario": extras,
        "avisos": avisos,
    }


