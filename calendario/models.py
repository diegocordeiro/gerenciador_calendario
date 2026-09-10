"""Modelos do calendário acadêmico.

O banco (``db.sqlite3``) é a **fonte da verdade**: a interface de montagem e o
admin gravam cada versão/etapa aqui. O HTML final é gerado a partir do banco
pelo comando ``render_static_site`` e publicado no GitHub Pages.
"""
from django.db import models

from .slug import versao_slug


class Calendario(models.Model):
    """Uma versão/etapa do calendário acadêmico."""

    STATUS_CHOICES = [
        ("rascunho", "Rascunho"),
        ("etapa", "Etapa"),
        ("final", "Final"),
    ]

    versao = models.CharField("Versão", max_length=60, unique=True)
    titulo = models.CharField("Título", max_length=200, blank=True)
    periodo = models.CharField("Período", max_length=40, blank=True)
    data_inicio = models.DateField("Início do semestre")
    total_semanas = models.PositiveIntegerField("Nº de semanas", default=18)
    semanas_primeira_parte = models.PositiveIntegerField("Semanas na 1ª parte", default=9)
    etapa = models.PositiveIntegerField("Etapa", default=1)
    status = models.CharField("Status", max_length=20, choices=STATUS_CHOICES, default="etapa")
    final = models.BooleanField("Versão final", default=False)
    atual = models.BooleanField("Versão atual", default=False)
    observacoes = models.TextField("Observações", blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-data_inicio", "-etapa", "versao"]
        verbose_name = "Calendário"
        verbose_name_plural = "Calendários"

    @property
    def slug(self) -> str:
        return versao_slug(self.versao)

    @property
    def feriados_datas(self) -> list[str]:
        return [f.data.isoformat() for f in self.feriados.all()]

    def build(self) -> dict:
        """Monta o calendário calculado (delega para ``scheduling``)."""
        from .scheduling import build_calendario

        return build_calendario(
            self.data_inicio,
            self.total_semanas,
            self.semanas_primeira_parte,
            self.feriados_datas,
        )

    def __str__(self) -> str:
        return self.versao


class Feriado(models.Model):
    """Um dia não letivo (feriado) de uma versão do calendário."""

    ORIGEM_CHOICES = [
        ("nacional", "Nacional"),
        ("institucional", "Institucional"),
        ("manual", "Manual"),
    ]

    calendario = models.ForeignKey(
        Calendario, related_name="feriados", on_delete=models.CASCADE
    )
    data = models.DateField("Data")
    descricao = models.CharField("Descrição", max_length=200, blank=True)
    origem = models.CharField(
        "Origem", max_length=20, choices=ORIGEM_CHOICES, default="manual"
    )

    class Meta:
        ordering = ["data"]
        unique_together = ("calendario", "data")
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"

    def __str__(self) -> str:
        return f"{self.data:%d/%m/%Y} — {self.descricao or 'feriado'}"
