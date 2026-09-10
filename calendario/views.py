"""Views do calendário acadêmico.

Inclui a interface de montagem (``/editor/``) e a API usada por ela (``/api/``).
O cálculo é feito no servidor (``scheduling.build_calendario``), mantendo o
Python como fonte única de verdade — o JavaScript apenas renderiza o resultado.
"""
from __future__ import annotations

import json

from django.conf import settings
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .data.feriados import feriados_nacionais
from .models import Calendario, Feriado
from .scheduling import build_calendario
from .static_site import print_ctx


def _atual():
    return (
        Calendario.objects.filter(final=True).order_by("-data_inicio", "-etapa").first()
        or Calendario.objects.filter(atual=True).order_by("-data_inicio", "-etapa").first()
        or Calendario.objects.order_by("-data_inicio", "-etapa").first()
    )


def _history(excluir_id=None):
    qs = Calendario.objects.all()
    if excluir_id:
        qs = qs.exclude(id=excluir_id)
    itens = list(qs)
    itens.sort(key=lambda c: (c.data_inicio, c.etapa), reverse=True)
    return itens


def _por_slug(slug):
    for cal in Calendario.objects.all():
        if cal.slug == slug:
            return cal
    return None


def home(request):
    atual = _atual()
    return render(
        request,
        "calendario/home.html",
        {"atual": atual, "history": _history(atual.id if atual else None)},
    )


def versoes(request):
    atual = _atual()
    return render(
        request,
        "calendario/versoes.html",
        {"atual": atual, "history": _history(atual.id if atual else None)},
    )


def calendario_atual(request):
    cal = _atual()
    if cal is None:
        raise Http404("Nenhum calendário cadastrado.")
    titulo = cal.titulo or f"Calendário acadêmico — {cal.versao}"
    return render(
        request,
        "calendario/calendario_detail.html",
        {
            "cal": cal,
            "dados": cal.build(),
            "active": "calendario",
            **print_ctx(titulo, cal.periodo or None),
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
            "active": "calendario",
            **print_ctx(titulo, cal.periodo or None),
        },
    )


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
        "data_inicio": cal.data_inicio.isoformat() if cal else "",
        "total_semanas": cal.total_semanas if cal else settings.CALENDARIO_SEMANAS_PADRAO,
        "semanas_primeira_parte": (
            cal.semanas_primeira_parte if cal else settings.CALENDARIO_SEMANAS_1A_PARTE
        ),
        "etapa": cal.etapa if cal else 1,
        "status": cal.status if cal else "etapa",
        "final": cal.final if cal else False,
        "observacoes": cal.observacoes if cal else "",
        "feriados": cal.feriados_datas if cal else [],
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
    """Aceita lista de strings ou de dicts ``{data, descricao, origem}``."""
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
                }
            )
        else:
            data = str(item).strip()
            if data:
                itens.append({"data": data, "descricao": "", "origem": "manual"})
    return itens


@require_POST
def api_preview(request):
    """Calcula a grade no servidor e devolve o JSON para a interface renderizar."""
    dados = _payload(request)
    resultado = build_calendario(
        dados.get("data_inicio"),
        dados.get("total_semanas"),
        dados.get("semanas_primeira_parte"),
        [f["data"] for f in _normalizar_feriados(dados.get("feriados"))],
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

    cal, criado = Calendario.objects.update_or_create(
        versao=versao,
        defaults={
            "titulo": (dados.get("titulo") or "").strip(),
            "periodo": (dados.get("periodo") or "").strip(),
            "data_inicio": data_inicio,
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
            calendario=cal, data=iso, defaults={"origem": item["origem"]}
        )
        if item["descricao"]:
            obj.descricao = item["descricao"]
        if not obj.descricao and item["origem"]:
            obj.origem = item["origem"]
        obj.save()

    # Versão final/atual é exclusiva.
    if dados.get("final"):
        Calendario.objects.exclude(pk=cal.pk).update(final=False, atual=False)
        cal.final = True
        cal.atual = True
        cal.status = "final"
    else:
        cal.final = False
        cal.atual = False
        cal.status = (dados.get("status") or "etapa").strip() or "etapa"
    cal.save()

    return JsonResponse(
        {
            "ok": True,
            "criado": criado,
            "versao": cal.versao,
            "slug": cal.slug,
            "final": cal.final,
            "dados": resultado,
        }
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

