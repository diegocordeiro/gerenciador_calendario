"""Modelos do calendário acadêmico.

O banco (``db.sqlite3``) é a **fonte da verdade**: a interface de montagem e o
admin gravam cada versão/etapa aqui. O HTML final é gerado a partir do banco
pelo comando ``render_static_site`` e publicado no GitHub Pages.

Além da grade de semanas (``scheduling``), o documento oficial do campus é
composto por **eventos** (matrículas, avaliações, recessos, sábados letivos…)
e por **feriados/pontos facultativos** — representados por :class:`Evento` e
:class:`Feriado`.
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

    MODALIDADE_CHOICES = [
        ("integrado", "Integrado"),
        ("integrado_proeja", "Integrado PROEJA"),
        ("subsequente", "Subsequente"),
        ("proeja", "PROEJA"),
        ("superior", "Superior"),
        ("outro", "Outro"),
    ]

    INSTITUICAO_PADRAO = (
        "Instituto Federal de Educação, Ciência e Tecnologia do Piauí — IFPI — "
        "Campus Barras"
    )

    # ---- Identificação ----
    versao = models.CharField("Versão", max_length=60, unique=True)
    titulo = models.CharField("Título", max_length=200, blank=True)
    periodo = models.CharField("Período", max_length=40, blank=True)

    # ---- Cabeçalho do documento oficial ----
    instituicao = models.CharField(
        "Instituição", max_length=200, blank=True, default=INSTITUICAO_PADRAO
    )
    curso = models.CharField("Curso", max_length=200, blank=True)
    modalidade = models.CharField(
        "Modalidade",
        max_length=30,
        choices=MODALIDADE_CHOICES,
        blank=True,
        default="integrado_proeja",
    )
    semestre = models.CharField("Semestre", max_length=20, blank=True)

    # ---- Período ----
    data_inicio = models.DateField("Início do semestre")
    data_fim = models.DateField("Término do período letivo", null=True, blank=True)
    total_semanas = models.PositiveIntegerField("Nº de semanas", default=18)
    semanas_primeira_parte = models.PositiveIntegerField("Semanas na 1ª parte", default=9)

    # ---- Metas de dias letivos ----
    dias_letivos_previstos = models.PositiveIntegerField("Dias letivos previstos", default=0)
    dias_letivos_por_mes = models.JSONField(
        "Dias letivos declarados por mês",
        default=list,
        blank=True,
        help_text="Lista de {'mes': 'SET/2026', 'letivos': 13} para conferência.",
    )

    # ---- Versionamento ----
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

    @property
    def periodo_letivo_label(self) -> str:
        """Rótulo curto do período letivo (ex.: ``2026.2`` ou ``2º Semestre``)."""
        return " — ".join(p for p in (self.periodo, self.semestre) if p)

    def build(self) -> dict:
        """Monta o calendário calculado (delega para ``scheduling``)."""
        from .scheduling import build_calendario

        return build_calendario(
            self.data_inicio,
            self.total_semanas,
            self.semanas_primeira_parte,
            self.feriados_datas,
        )

    def agenda(self) -> dict:
        """Monta a agenda no formato do documento oficial (delega para ``agenda``)."""
        from .agenda import build_agenda

        return build_agenda(
            data_inicio=self.data_inicio,
            data_fim=self.data_fim,
            feriados=self.feriados.all(),
            eventos=self.eventos.all(),
            dias_letivos_previstos=self.dias_letivos_previstos,
            dias_letivos_por_mes=self.dias_letivos_por_mes,
        )

    def __str__(self) -> str:
        return self.versao


class Feriado(models.Model):
    """Um dia não letivo (feriado ou ponto facultativo) de uma versão."""

    ORIGEM_CHOICES = [
        ("nacional", "Nacional"),
        ("institucional", "Institucional"),
        ("manual", "Manual"),
    ]
    TIPO_CHOICES = [
        ("feriado", "Feriado"),
        ("ponto_facultativo", "Ponto facultativo"),
    ]

    calendario = models.ForeignKey(
        Calendario, related_name="feriados", on_delete=models.CASCADE
    )
    data = models.DateField("Data")
    descricao = models.CharField("Descrição", max_length=200, blank=True)
    origem = models.CharField(
        "Origem", max_length=20, choices=ORIGEM_CHOICES, default="manual"
    )
    tipo = models.CharField(
        "Tipo", max_length=20, choices=TIPO_CHOICES, default="feriado"
    )

    class Meta:
        ordering = ["data"]
        unique_together = ("calendario", "data")
        verbose_name = "Feriado"
        verbose_name_plural = "Feriados"

    def __str__(self) -> str:
        return f"{self.data:%d/%m/%Y} — {self.descricao or 'feriado'}"


class Evento(models.Model):
    """Um evento/atividade acadêmica do documento do calendário.

    Cada item da tabela ``MÊS · DIA · EVENTO`` do calendário oficial — matrículas,
    jornada pedagógica, avaliações, recuperação, recesso, férias coletivas,
    conselho de classe, sábados letivos/de reposição e eventos institucionais —
    é um :class:`Evento`.
    """

    TIPO_CHOICES = [
        ("letivo", "Dia letivo"),
        ("sabado_letivo", "Sábado letivo"),
        ("sabado_reposicao", "Sábado de reposição"),
        ("feriado", "Feriado"),
        ("ponto_facultativo", "Ponto facultativo"),
        ("jornada_pedagogica", "Jornada pedagógica"),
        ("recesso", "Recesso escolar"),
        ("ferias_coletivas", "Férias coletivas"),
        ("avaliacao", "Avaliação"),
        ("avaliacao_final", "Avaliação final"),
        ("recuperacao", "Recuperação paralela"),
        ("conselho_classe", "Conselho de classe"),
        ("matricula", "Matrícula"),
        ("administrativo", "Administrativo"),
        ("evento", "Evento institucional"),
    ]

    DIAS_SEMANA_CHOICES = [
        (0, "Segunda-feira"),
        (1, "Terça-feira"),
        (2, "Quarta-feira"),
        (3, "Quinta-feira"),
        (4, "Sexta-feira"),
    ]

    NOMES_SEMANA = [
        "segunda-feira",
        "terça-feira",
        "quarta-feira",
        "quinta-feira",
        "sexta-feira",
    ]

    calendario = models.ForeignKey(
        Calendario, related_name="eventos", on_delete=models.CASCADE
    )
    titulo = models.CharField("Título", max_length=200)
    tipo = models.CharField("Tipo", max_length=30, choices=TIPO_CHOICES, default="evento")
    data_inicio = models.DateField("Data inicial")
    data_fim = models.DateField("Data final", null=True, blank=True)
    dia_semana_referencia = models.PositiveSmallIntegerField(
        "Dia da semana referenciado",
        choices=DIAS_SEMANA_CHOICES,
        null=True,
        blank=True,
        help_text="Usado em sábados letivos/de reposição (qual dia da semana é reposto).",
    )
    descricao = models.TextField("Descrição", blank=True)
    destaque = models.BooleanField("Destaque", default=False)

    class Meta:
        ordering = ["data_inicio", "titulo"]
        verbose_name = "Evento"
        verbose_name_plural = "Eventos"

    @property
    def data_final_efetiva(self):
        return self.data_fim or self.data_inicio

    @property
    def referencia_label(self) -> str:
        """Rótulo do dia da semana referenciado (ex.: ``referente à quarta-feira``)."""
        if self.dia_semana_referencia is None:
            return ""
        return f"referente à {self.NOMES_SEMANA[self.dia_semana_referencia]}"

    def __str__(self) -> str:
        return f"{self.data_inicio:%d/%m/%Y} — {self.titulo}"
