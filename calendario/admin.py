"""Admin do calendário acadêmico.

Diferente do painel de horários, aqui o banco é a **fonte da verdade**: o admin
grava de verdade (é uma via de edição ao lado da interface de montagem).
"""
from django.contrib import admin

from .models import Calendario, Evento, Feriado


class FeriadoInline(admin.TabularInline):
    model = Feriado
    extra = 1
    fields = ("data", "descricao", "tipo", "origem")


class EventoInline(admin.TabularInline):
    model = Evento
    extra = 1
    fields = (
        "titulo",
        "tipo",
        "data_inicio",
        "data_fim",
        "dia_semana_referencia",
        "destaque",
    )
    ordering = ("data_inicio",)
    show_change_link = True


@admin.register(Calendario)
class CalendarioAdmin(admin.ModelAdmin):
    list_display = (
        "versao",
        "titulo",
        "curso",
        "periodo",
        "data_inicio",
        "data_fim",
        "dias_letivos_previstos",
        "total_semanas",
        "semanas_primeira_parte",
        "etapa",
    )
    list_filter = ("periodo", "modalidade")
    search_fields = ("versao", "titulo", "curso", "observacoes")
    inlines = [EventoInline, FeriadoInline]
    fieldsets = (
        (
            "Identificação",
            {
                "fields": (
                    "versao",
                    "titulo",
                    "periodo",
                    "etapa",
                )
            },
        ),
        (
            "Documento",
            {
                "fields": (
                    "instituicao",
                    "curso",
                    "modalidade",
                    "semestre",
                )
            },
        ),
        (
            "Período",
            {
                "fields": (
                    "data_inicio",
                    "data_fim",
                    "total_semanas",
                    "semanas_primeira_parte",
                )
            },
        ),
        (
            "Dias letivos",
            {
                "fields": (
                    "dias_letivos_previstos",
                    "dias_letivos_por_mes",
                )
            },
        ),
        ("Observações", {"fields": ("observacoes",)}),
    )


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("calendario", "data", "descricao", "tipo", "origem")
    list_filter = ("tipo", "origem", "calendario")
    search_fields = ("descricao",)
    date_hierarchy = "data"


@admin.register(Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = (
        "calendario",
        "data_inicio",
        "data_fim",
        "titulo",
        "tipo",
        "dia_semana_referencia",
        "destaque",
    )
    list_filter = ("tipo", "calendario", "destaque")
    search_fields = ("titulo", "descricao")
    date_hierarchy = "data_inicio"
    autocomplete_fields = ("calendario",)

