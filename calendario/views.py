"""Views do calendário acadêmico.

Inclui a interface de montagem (``/editor/``) e a API usada por ela (``/api/``).
O cálculo é feito no servidor (``scheduling.build_calendario``), mantendo o
Python como fonte única de verdade — o JavaScript apenas renderiza o resultado.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import llm, requisitos
from .agenda import build_agenda
from .data.feriados import feriados_nacionais
from .models import Calendario, Evento, Feriado
from .scheduling import build_calendario
from .static_site import print_ctx


def _versoes():
    """Todas as versões cadastradas, da mais recente para a mais antiga."""
    itens = list(Calendario.objects.all())
    itens.sort(key=lambda c: (c.data_inicio, c.etapa), reverse=True)
    return itens


def _por_slug(slug):
    for cal in Calendario.objects.all():
        if cal.slug == slug:
            return cal
    return None


def home(request):
    return render(
        request,
        "calendario/home.html",
        {"versoes": _versoes(), "active": "inicio"},
    )


def versoes(request):
    """A lista de versões vive na raiz do calendário; aqui só redirecionamos."""
    return redirect("indice")


def indice(request):
    """Índice do calendário: lista todas as versões cadastradas."""
    return render(
        request,
        "calendario/indice.html",
        {
            "versoes": _versoes(),
            "modalidades": [
                {"valor": v, "label": lbl} for v, lbl in Calendario.MODALIDADE_CHOICES
            ],
            "active": "calendario",
        },
    )


def calendario_versionado(request, slug):
    cal = _por_slug(slug)
    if cal is None:
        raise Http404("Versão não encontrada.")
    titulo = cal.titulo or f"Calendário acadêmico — {cal.versao}"
    return render(
        request,
        "calendario/calendario_detail.html",
        {
            "cal": cal,
            "dados": cal.build(),
            "agenda": cal.agenda(),
            "active": "calendario",
            **print_ctx(titulo, cal.periodo or None),
        },
    )


def _llm_contexto() -> dict:
    """Contexto da IA para o editor — **nunca** inclui chaves de API."""
    normas = {}
    for valor, _ in Calendario.MODALIDADE_CHOICES:
        info = requisitos.info_da_modalidade(valor)
        normas[valor] = {
            "norma": info["norma"],
            "titulo": info["titulo"],
            "total_itens": len(info["itens"]),
        }
    return {
        "habilitado": llm.tem_provedor_configurado(),
        "padrao": llm.resolver_provedor(None),
        "provedores": llm.provedores_disponiveis(),
        "cidade": settings.LLM_CIDADE_PADRAO,
        "estado": settings.LLM_ESTADO_PADRAO,
        "pais": settings.LLM_PAIS_PADRAO,
        "timeout": settings.LLM_TIMEOUT,
        "normas": normas,
    }


def editor(request):
    """Interface de montagem do calendário (mesmo visual do painel de horários)."""
    versao = request.GET.get("versao")
    cal = _por_slug(versao) if versao else None
    etapas = list(Calendario.objects.all())
    etapas.sort(key=lambda c: (c.data_inicio, c.etapa), reverse=True)

    inicial = {
        "versao": cal.versao if cal else "",
        "titulo": cal.titulo if cal else "",
        "periodo": cal.periodo if cal else "",
        "instituicao": cal.instituicao if cal else Calendario.INSTITUICAO_PADRAO,
        "curso": cal.curso if cal else "",
        "modalidade": cal.modalidade if cal else "integrado_medio",
        "semestre": cal.semestre if cal else "",
        "data_inicio": cal.data_inicio.isoformat() if cal else "",
        "data_fim": cal.data_fim.isoformat() if cal and cal.data_fim else "",
        "total_semanas": cal.total_semanas if cal else settings.CALENDARIO_SEMANAS_PADRAO,
        "semanas_primeira_parte": (
            cal.semanas_primeira_parte if cal else settings.CALENDARIO_SEMANAS_1A_PARTE
        ),
        "dias_letivos_previstos": cal.dias_letivos_previstos if cal else 0,
        "dias_letivos_por_mes": cal.dias_letivos_por_mes if cal else [],
        "etapa": cal.etapa if cal else 1,
        "observacoes": cal.observacoes if cal else "",
        "feriados": (
            [
                {
                    "data": f.data.isoformat(),
                    "descricao": f.descricao,
                    "origem": f.origem,
                    "tipo": f.tipo,
                }
                for f in cal.feriados.all()
            ]
            if cal
            else []
        ),
        "eventos": _eventos_para_json(cal) if cal else [],
        "tipos_evento": [{"valor": t, "label": lbl} for t, lbl in Evento.TIPO_CHOICES],
        "dias_semana": [{"valor": v, "label": lbl} for v, lbl in Evento.DIAS_SEMANA_CHOICES],
        "modalidades": [
            {"valor": v, "label": lbl} for v, lbl in Calendario.MODALIDADE_CHOICES
        ],
        "llm": _llm_contexto(),
    }
    return render(
        request,
        "calendario/editor.html",
        {"inicial": inicial, "etapas": etapas, "active": "editor"},
    )


# ---------- API ----------


def _payload(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


def _normalizar_feriados(raw) -> list[dict]:
    """Aceita lista de strings ou de dicts ``{data, descricao, origem, tipo}``."""
    itens = []
    for item in raw or []:
        if isinstance(item, dict):
            data = (item.get("data") or "").strip()
            if not data:
                continue
            itens.append(
                {
                    "data": data,
                    "descricao": (item.get("descricao") or "").strip(),
                    "origem": (item.get("origem") or "manual").strip() or "manual",
                    "tipo": (item.get("tipo") or "feriado").strip() or "feriado",
                }
            )
        else:
            data = str(item).strip()
            if data:
                itens.append(
                    {"data": data, "descricao": "", "origem": "manual", "tipo": "feriado"}
                )
    return itens


_TIPOS_EVENTO = {t for t, _ in Evento.TIPO_CHOICES}


def _normalizar_eventos(raw) -> list[dict]:
    """Normaliza a lista de eventos enviada pela interface/API."""
    itens = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        ini = (item.get("data_inicio") or "").strip()
        if not ini:
            continue
        tipo = (item.get("tipo") or "evento").strip() or "evento"
        if tipo not in _TIPOS_EVENTO:
            tipo = "evento"
        fim = (item.get("data_fim") or "").strip() or None
        ref = item.get("dia_semana_referencia")
        try:
            ref = int(ref) if ref not in (None, "") else None
        except (TypeError, ValueError):
            ref = None
        itens.append(
            {
                "titulo": (item.get("titulo") or "").strip() or "Evento",
                "tipo": tipo,
                "data_inicio": ini,
                "data_fim": fim,
                "dia_semana_referencia": ref,
                "descricao": (item.get("descricao") or "").strip(),
                "destaque": bool(item.get("destaque")),
            }
        )
    return itens


def _eventos_para_json(cal):
    return [
        {
            "titulo": e.titulo,
            "tipo": e.tipo,
            "data_inicio": e.data_inicio.isoformat(),
            "data_fim": e.data_fim.isoformat() if e.data_fim else "",
            "dia_semana_referencia": e.dia_semana_referencia,
            "descricao": e.descricao,
            "destaque": e.destaque,
        }
        for e in cal.eventos.all()
    ]


def _iso_ou_none(valor):
    """Converte uma string vazia em ``None`` (para campos de data opcionais)."""
    if isinstance(valor, str):
        valor = valor.strip()
    return valor or None


def _normalizar_resumo_meses(raw) -> list[dict]:
    """Normaliza ``dias_letivos_por_mes`` (``[{'mes', 'letivos'}]``)."""
    itens = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        mes = (item.get("mes") or "").strip()
        if not mes:
            continue
        try:
            letivos = int(item.get("letivos") or 0)
        except (TypeError, ValueError):
            letivos = 0
        itens.append({"mes": mes, "letivos": letivos})
    return itens




def _overrides_clone(dados) -> dict:
    """Lê os *overrides* opcionais do clone (``None`` mantém o valor da origem)."""
    modalidade = (dados.get("modalidade") or "").strip()
    if modalidade and modalidade not in dict(Calendario.MODALIDADE_CHOICES):
        modalidade = ""
    try:
        etapa = int(dados.get("etapa") or 0)
    except (TypeError, ValueError):
        etapa = 0
    return {
        "titulo": (dados.get("titulo") or "").strip() or None,
        "curso": (dados.get("curso") or "").strip() or None,
        "modalidade": modalidade or None,
        "semestre": (dados.get("semestre") or "").strip() or None,
        "periodo": (dados.get("periodo") or "").strip() or None,
        "etapa": etapa if etapa > 0 else 1,
    }


@require_POST
def api_preview(request):
    """Calcula a grade e a agenda no servidor e devolve o JSON para a interface."""
    dados = _payload(request)
    feriados = _normalizar_feriados(dados.get("feriados"))
    eventos = _normalizar_eventos(dados.get("eventos"))
    resultado = build_calendario(
        dados.get("data_inicio"),
        dados.get("total_semanas"),
        dados.get("semanas_primeira_parte"),
        [f["data"] for f in feriados],
    )
    resultado["agenda"] = build_agenda(
        data_inicio=dados.get("data_inicio"),
        data_fim=dados.get("data_fim"),
        feriados=feriados,
        eventos=eventos,
        dias_letivos_previstos=dados.get("dias_letivos_previstos") or 0,
        dias_letivos_por_mes=_normalizar_resumo_meses(dados.get("dias_letivos_por_mes")),
    )
    return JsonResponse(resultado)


@require_POST
def api_salvar(request):
    """Grava/atualiza uma versão/etapa do calendário no banco."""
    dados = _payload(request)
    versao = (dados.get("versao") or "").strip()
    data_inicio = (dados.get("data_inicio") or "").strip()
    erros = []
    if not versao:
        erros.append("Informe o nome da versão (ex.: 2026.1.etapa1).")
    if not data_inicio:
        erros.append("Informe a data de início do semestre.")
    if erros:
        return JsonResponse({"ok": False, "erros": erros}, status=400)

    feriados = _normalizar_feriados(dados.get("feriados"))
    eventos = _normalizar_eventos(dados.get("eventos"))
    resultado = build_calendario(
        data_inicio,
        dados.get("total_semanas"),
        dados.get("semanas_primeira_parte"),
        [f["data"] for f in feriados],
    )
    if not resultado["valido"]:
        return JsonResponse(
            {"ok": False, "erros": resultado["erros"], "dados": resultado}, status=400
        )

    try:
        etapa = int(dados.get("etapa") or 1)
    except (TypeError, ValueError):
        etapa = 1
    try:
        previstos = int(dados.get("dias_letivos_previstos") or 0)
    except (TypeError, ValueError):
        previstos = 0

    cal, criado = Calendario.objects.update_or_create(
        versao=versao,
        defaults={
            "titulo": (dados.get("titulo") or "").strip(),
            "periodo": (dados.get("periodo") or "").strip(),
            "instituicao": (dados.get("instituicao") or "").strip()
            or Calendario.INSTITUICAO_PADRAO,
            "curso": (dados.get("curso") or "").strip(),
            "modalidade": (dados.get("modalidade") or "").strip() or "integrado_medio",
            "semestre": (dados.get("semestre") or "").strip(),
            "data_inicio": data_inicio,
            "data_fim": _iso_ou_none(dados.get("data_fim")),
            "dias_letivos_previstos": previstos,
            "dias_letivos_por_mes": _normalizar_resumo_meses(dados.get("dias_letivos_por_mes")),
            "total_semanas": int(dados.get("total_semanas") or 0),
            "semanas_primeira_parte": int(dados.get("semanas_primeira_parte") or 0),
            "etapa": etapa,
            "observacoes": (dados.get("observacoes") or "").strip(),
        },
    )

    # Sincroniza os feriados (adiciona/atualiza, remove os que saíram).
    entradas = {f["data"]: f for f in feriados}
    for existente in list(cal.feriados.all()):
        if existente.data.isoformat() not in entradas:
            existente.delete()
    for iso, item in entradas.items():
        obj, _ = Feriado.objects.get_or_create(
            calendario=cal,
            data=iso,
            defaults={"origem": item["origem"], "tipo": item["tipo"]},
        )
        if item["descricao"]:
            obj.descricao = item["descricao"]
        if not obj.descricao and item["origem"]:
            obj.origem = item["origem"]
        obj.tipo = item["tipo"]
        obj.save()

    # Sincroniza os eventos (substitui a coleção pela enviada).
    cal.eventos.all().delete()
    Evento.objects.bulk_create(
        [
            Evento(
                calendario=cal,
                titulo=item["titulo"],
                tipo=item["tipo"],
                data_inicio=item["data_inicio"],
                data_fim=_iso_ou_none(item["data_fim"]),
                dia_semana_referencia=item["dia_semana_referencia"],
                descricao=item["descricao"],
                destaque=item["destaque"],
            )
            for item in eventos
        ]
    )

    resultado["agenda"] = cal.agenda()
    return JsonResponse(
        {
            "ok": True,
            "criado": criado,
            "versao": cal.versao,
            "slug": cal.slug,
            "eventos": _eventos_para_json(cal),
            "dados": resultado,
        }
    )


def api_eventos(request):
    """Lista (GET) ou salva (POST) os eventos de uma versão.

    GET  ``?versao=<versao>`` → ``{ok, versao, eventos}``
    POST ``{versao, eventos: [...]}`` → substitui a coleção de eventos.
    """
    if request.method == "GET":
        versao = (request.GET.get("versao") or "").strip()
        cal = Calendario.objects.filter(versao=versao).first()
        if cal is None:
            return JsonResponse({"ok": False, "erros": ["Versão não encontrada."]}, status=404)
        return JsonResponse({"ok": True, "versao": cal.versao, "eventos": _eventos_para_json(cal)})

    if request.method != "POST":
        return JsonResponse({"ok": False, "erros": ["Método não permitido."]}, status=405)

    dados = _payload(request)
    versao = (dados.get("versao") or "").strip()
    cal = Calendario.objects.filter(versao=versao).first()
    if cal is None:
        return JsonResponse({"ok": False, "erros": ["Versão não encontrada."]}, status=404)

    eventos = _normalizar_eventos(dados.get("eventos"))
    cal.eventos.all().delete()
    Evento.objects.bulk_create(
        [
            Evento(
                calendario=cal,
                titulo=item["titulo"],
                tipo=item["tipo"],
                data_inicio=item["data_inicio"],
                data_fim=_iso_ou_none(item["data_fim"]),
                dia_semana_referencia=item["dia_semana_referencia"],
                descricao=item["descricao"],
                destaque=item["destaque"],
            )
            for item in eventos
        ]
    )
    return JsonResponse(
        {"ok": True, "versao": cal.versao, "eventos": _eventos_para_json(cal)}
    )


@require_POST
def api_excluir(request):
    """Remove uma versão/etapa do banco."""
    dados = _payload(request)
    versao = (dados.get("versao") or "").strip()
    cal = Calendario.objects.filter(versao=versao).first()
    if cal is None:
        return JsonResponse({"ok": False, "erros": ["Versão não encontrada."]}, status=404)
    cal.delete()
    return JsonResponse({"ok": True, "versao": versao})


@require_POST
def api_clonar(request):
    """Clona uma versão/etapa (feriados e eventos) como base de outra modalidade.

    POST ``{versao, nova_versao, titulo?, curso?, modalidade?, semestre?,
    periodo?, etapa?}`` → ``{ok, versao, slug, origem, eventos}``.
    """
    dados = _payload(request)
    versao = (dados.get("versao") or "").strip()
    nova = (dados.get("nova_versao") or dados.get("versao_nova") or "").strip()

    origem = Calendario.objects.filter(versao=versao).first()
    if origem is None:
        return JsonResponse(
            {"ok": False, "erros": ["Versão de origem não encontrada."]}, status=404
        )

    try:
        novo = origem.clonar(nova, **_overrides_clone(dados))
    except ValidationError as exc:
        return JsonResponse({"ok": False, "erros": list(exc.messages)}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "versao": novo.versao,
            "slug": novo.slug,
            "origem": origem.versao,
            "modalidade": novo.modalidade,
            "eventos": _eventos_para_json(novo),
        }
    )


# Destinos válidos após excluir (evita redirecionamento aberto). A lista vive na
# raiz do calendário (``indice``); ``versoes`` é mantido por compatibilidade.
_EXCLUIR_DESTINOS = {"versoes": "indice", "calendario": "indice", "editor": "editor"}


@require_POST
def excluir_versao(request):
    """Exclui uma versão/etapa via formulário HTML e volta para a listagem.

    Funciona sem JavaScript (form POST + redirect), então o token CSRF vai no
    próprio corpo da requisição e a página é recarregada pelo navegador.
    """
    versao = (request.POST.get("versao") or "").strip()
    destino = _EXCLUIR_DESTINOS.get(request.POST.get("destino"), "indice")

    cal = Calendario.objects.filter(versao=versao).first()
    if cal is None:
        messages.error(request, f'Versão "{versao}" não encontrada.')
    else:
        cal.delete()
        messages.success(request, f'Versão "{versao}" excluída.')
    return redirect(destino)


# Destinos válidos após clonar (evita redirecionamento aberto).
_CLONAR_DESTINOS = {"editor": "editor", "versoes": "indice", "calendario": "indice"}


@require_POST
def clonar_versao(request):
    """Clona uma versão via formulário HTML e abre o editor da cópia.

    Funciona sem JavaScript (form POST + redirect PRG): o token CSRF vai no corpo
    e o navegador recarrega a página. A nova versão herda feriados e eventos da
    origem e fica pronta para virar o calendário de outra modalidade/curso.
    """
    versao = (request.POST.get("versao") or "").strip()
    nova = (request.POST.get("nova_versao") or "").strip()
    destino = _CLONAR_DESTINOS.get(request.POST.get("destino"), "editor")

    origem = Calendario.objects.filter(versao=versao).first()
    if origem is None:
        messages.error(request, f'Versão "{versao}" não encontrada.')
        return redirect("indice")

    try:
        novo = origem.clonar(nova, **_overrides_clone(request.POST.dict()))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("indice")

    messages.success(
        request,
        f'Versão "{novo.versao}" criada a partir de "{origem.versao}" — '
        "ajuste os dados e salve.",
    )
    if destino == "editor":
        return redirect(f"{reverse('editor')}?versao={novo.slug}")
    return redirect(destino)


def api_feriados_nacionais(request):
    """Devolve os feriados nacionais de um ano (?ano=YYYY) para a interface."""
    try:
        ano = int(request.GET.get("ano") or 0)
    except (TypeError, ValueError):
        ano = 0
    if not ano:
        return JsonResponse({"ok": False, "erros": ["Informe ?ano=YYYY."]}, status=400)
    return JsonResponse(
        {
            "ok": True,
            "ano": ano,
            "feriados": [
                {"data": f["data"].isoformat(), "descricao": f["descricao"]}
                for f in feriados_nacionais(ano)
            ],
        }
    )


# ---------- IA (LLM) ----------


def _agenda_resumida(agenda: dict) -> dict:
    """Recorte da agenda usado na prévia do modal (carga horária + validação)."""
    return {
        "dias_por_dia": agenda["dias_por_dia"],
        "meta_por_dia": agenda["meta_por_dia"],
        "letivos_por_dia": agenda["letivos_por_dia"],
        "letivos_seg_sex_por_dia": agenda["letivos_seg_sex_por_dia"],
        "sabados_por_dia": agenda["sabados_por_dia"],
        "sabados_total": agenda["sabados_total"],
        "sabados_contabilizados": agenda["sabados_contabilizados"],
        "sabados_letivos": agenda["sabados_letivos"],
        "dias_reposicao": agenda["dias_reposicao"],
        "reposicoes_total": agenda["reposicoes_total"],
        "total_letivos": agenda["total_letivos"],
        "letivos_seg_sex": agenda["letivos_seg_sex"],
        "totais_tabela": agenda["totais_tabela"],
        "notas": agenda["notas"],
        "validacao": agenda["validacao"],
    }


@require_POST
def api_ia_eventos(request):
    """Gera feriados/eventos com a LLM a partir da cidade/UF/país da unidade.

    **Prévia: nada é gravado.** A persistência acontece só quando o usuário confirma
    no editor e clica em *Salvar versão* (``api_salvar``).

    POST ``{cidade, estado, pais?, provedor?, modelo?, data_inicio, data_fim,
    total_semanas?, semanas_primeira_parte?, dias_letivos_previstos?, feriados?,
    eventos?, completar_sabados?}`` → ``{ok, feriados, eventos, avisos, agenda}``.
    """
    dados = _payload(request)
    entrada, erro = _entrada_ia(dados, exigir_local=True)
    if erro is not None:
        return erro

    try:
        resultado = llm.gerar_eventos(entrada)
    except llm.LlmConfigError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)
    except llm.LlmProviderError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=502)
    except llm.LlmError as exc:  # salvaguarda
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)

    agenda = resultado["agenda"]

    return JsonResponse(
        {
            "ok": True,
            "provedor": resultado["provedor"],
            "provedor_label": resultado["provedor_label"],
            "modelo": resultado["modelo"],
            "feriados": resultado["feriados"],
            "eventos": resultado["eventos"],
            "avisos": resultado["avisos"],
            "estatisticas": resultado["estatisticas"],
            "requisitos": resultado["requisitos"],
            "agenda": _agenda_resumida(agenda),
        }
    )


def _entrada_ia(dados: dict, *, exigir_local: bool) -> tuple[dict, JsonResponse | None]:
    """Monta a entrada da IA a partir do payload (com validações comuns)."""
    entrada = {
        "cidade": (dados.get("cidade") or "").strip(),
        "estado": (dados.get("estado") or "").strip(),
        "pais": (dados.get("pais") or "").strip() or "Brasil",
        "instituicao": (dados.get("instituicao") or "").strip(),
        "curso": (dados.get("curso") or "").strip(),
        "modalidade": (dados.get("modalidade") or "").strip(),
        "data_inicio": dados.get("data_inicio"),
        "data_fim": dados.get("data_fim"),
        "total_semanas": dados.get("total_semanas"),
        "semanas_primeira_parte": dados.get("semanas_primeira_parte"),
        "dias_letivos_previstos": dados.get("dias_letivos_previstos") or 0,
        "dias_letivos_por_mes": _normalizar_resumo_meses(dados.get("dias_letivos_por_mes")),
        "feriados": _normalizar_feriados(dados.get("feriados")),
        "eventos": _normalizar_eventos(dados.get("eventos")),
        "provedor": dados.get("provedor"),
        "completar_sabados": dados.get("completar_sabados"),
    }
    if exigir_local and (not entrada["cidade"] or not entrada["estado"]):
        return entrada, JsonResponse(
            {"ok": False, "erros": ["Informe a cidade e o estado (UF) da unidade."]},
            status=400,
        )
    if not (dados.get("data_inicio") or "").strip() or not (dados.get("data_fim") or "").strip():
        return entrada, JsonResponse(
            {
                "ok": False,
                "erros": [
                    "Informe o início e o término do período letivo (bloco 1.2) "
                    "antes de usar a IA."
                ],
            },
            status=400,
        )
    return entrada, None


@require_POST
def api_ia_feriados(request):
    """Confere a **lista de feriados colada** contra o calendário (Art. 38–40 não; só feriados).

    A IA converte cada linha da lista em data/nome/tipo; o veredito
    (mapeado / faltando / divergente) é calculado no servidor. **Nada é gravado** —
    as sugestões voltam para o modal e só entram no editor quando o usuário marca os
    itens e aplica (a gravação é o “Salvar versão”).

    POST ``{lista, data_inicio, data_fim, feriados?, modalidade?, cidade?, estado?,
    pais?, provedor?, modelo?}`` → ``{ok, itens, resumo, extras_no_calendario, avisos}``.
    """
    dados = _payload(request)
    lista = (dados.get("lista") or "").strip()
    if not lista:
        return JsonResponse(
            {"ok": False, "erros": ["Cole a lista de feriados para conferir."]}, status=400
        )

    entrada, erro = _entrada_ia(dados, exigir_local=False)
    if erro is not None:
        return erro
    entrada["lista"] = lista

    try:
        resultado = llm.verificar_feriados(entrada)
    except llm.LlmConfigError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)
    except llm.LlmProviderError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=502)
    except llm.LlmError as exc:  # salvaguarda
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)

    return JsonResponse({"ok": True, **resultado})


@require_POST
def api_ia_verificar(request):
    """Audita os eventos lançados contra a norma da modalidade (Art. 38/39/40).

    Combina a conferência determinística com a análise da LLM. **Nada é gravado**:
    as sugestões voltam para o modal e só entram no editor quando o usuário marca
    os itens e clica em “Aplicar selecionados” (a gravação é o “Salvar versão”).

    POST ``{modalidade, data_inicio, data_fim, eventos?, feriados?,
    dias_letivos_previstos?, cidade?, estado?, pais?, provedor?}``
    → ``{ok, norma, requisitos, observacoes, avisos}``.
    """
    dados = _payload(request)
    entrada, erro = _entrada_ia(dados, exigir_local=False)
    if erro is not None:
        return erro

    try:
        resultado = llm.verificar_eventos(entrada)
    except llm.LlmConfigError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)
    except llm.LlmProviderError as exc:
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=502)
    except llm.LlmError as exc:  # salvaguarda
        return JsonResponse({"ok": False, "erros": [str(exc)]}, status=400)

    return JsonResponse(
        {
            "ok": True,
            "provedor": resultado["provedor"],
            "provedor_label": resultado["provedor_label"],
            "modelo": resultado["modelo"],
            "norma": resultado["norma"],
            "requisitos": resultado["requisitos"],
            "observacoes": resultado["observacoes"],
            "avisos": resultado["avisos"],
        }
    )

