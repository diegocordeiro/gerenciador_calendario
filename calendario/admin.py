"""Admin do calendário acadêmico.

Diferente do painel de horários, aqui o banco é a **fonte da verdade**: o admin
grava de verdade (é uma via de edição ao lado da interface de montagem).
"""
from django.contrib import admin

from .models import Calendario, Feriado


class FeriadoInline(admin.TabularInline):
    model = Feriado
    extra = 1
    fields = ("data", "descricao", "origem")


@admin.register(Calendario)
class CalendarioAdmin(admin.ModelAdmin):
    list_display = (
        "versao",
        "titulo",
        "periodo",
        "data_inicio",
        "total_semanas",
        "semanas_primeira_parte",
        "etapa",
        "status",
        "final",
        "atual",
    )
    list_filter = ("status", "final", "atual", "periodo")
    search_fields = ("versao", "titulo", "observacoes")
    inlines = [FeriadoInline]


@admin.register(Feriado)
class FeriadoAdmin(admin.ModelAdmin):
    list_display = ("calendario", "data", "descricao", "origem")
    list_filter = ("origem", "calendario")
    search_fields = ("descricao",)
    date_hierarchy = "data"
