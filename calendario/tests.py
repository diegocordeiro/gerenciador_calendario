import datetime as dt
import json
import re
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from .agenda import build_agenda
from .data.feriados import feriados_nacionais, pascoa
from .models import Calendario, Evento, Feriado
from .scheduling import (
    build_calendario,
    calendario_matriz,
    date_to_cell,
    feriados_no_calendario,
    parse_date,
    total_semanas,
)
from .slug import url_slug, versao_slug
from .static_site import normalize_base_url


class AlgoritmoTests(TestCase):
    """Valida o port fiel do algoritmo do app original."""

    def test_total_semanas(self):
        self.assertEqual(total_semanas(15, 0), 15)
        self.assertEqual(total_semanas(15, 3), 16)
        self.assertEqual(total_semanas(15, 7), 17)

    def test_parse_date(self):
        self.assertEqual(parse_date("2026-09-14"), dt.date(2026, 9, 14))
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))

    def test_feriados_no_calendario(self):
        # 2026-09-14 é segunda-feira; 2026-11-15 é domingo (excluído).
        feriados = feriados_no_calendario(
            dt.date(2026, 9, 14),
            18,
            ["2026-09-07", "2026-10-12", "2026-11-15", "2026-11-20"],
        )
        self.assertEqual(
            [f.isoformat() for f in feriados], ["2026-10-12", "2026-11-20"]
        )

    def test_calendario_matriz_tamanho(self):
        matriz = calendario_matriz(dt.date(2026, 9, 14), 15, 8, 3)
        self.assertEqual(len(matriz), total_semanas(15, 3))
        # Todas as semanas cheias têm 5 dias; a última pode ter menos.
        for linha in matriz[:-1]:
            self.assertEqual(len(linha), 5)
        self.assertLessEqual(len(matriz[-1]), 5)
        # Paridade alterna (i+1)%2 e parte muda em t1.
        self.assertEqual(matriz[0][0]["parity"], 1)
        self.assertEqual(matriz[1][0]["parity"], 0)
        self.assertEqual(matriz[7][0]["part"], 1)
        self.assertEqual(matriz[8][0]["part"], 2)

    def test_cores_da_grade_por_paridade(self):
        # Cores fortes o suficiente para distinguir x1 (azul) de x2 (pêssego).
        d = build_calendario("2026-09-14", 18, 9, [])
        cores = {c["color"] for linha in d["linhas"] for c in linha["cells"]}
        self.assertIn("#cfe8f7", cores)
        self.assertIn("#ffe6cc", cores)

    def test_build_calendario_sabado_por_semana(self):
        # Cada semana da grade traz o sábado correspondente (segunda + 5 dias).
        d = build_calendario("2026-09-14", 18, 9, [])
        self.assertEqual(d["linhas"][0]["sabado"], "2026-09-19")
        self.assertEqual(d["linhas"][0]["sabado_label"], "19.09")
        self.assertEqual(d["linhas"][1]["sabado"], "2026-09-26")

    def test_date_to_cell(self):
        matriz = calendario_matriz(dt.date(2026, 9, 14), 15, 8, 0)
        self.assertIs(matriz[0][0], date_to_cell(dt.date(2026, 9, 14), dt.date(2026, 9, 14), matriz))
        self.assertIsNone(date_to_cell(dt.date(2026, 9, 14), dt.date(2026, 9, 13), matriz))

    def test_build_calendario_valido(self):
        d = build_calendario("2026-09-14", 18, 9, ["2026-10-12", "2026-11-02"])
        self.assertTrue(d["valido"])
        self.assertEqual(d["erros"], [])
        self.assertEqual(d["f"], 2)
        self.assertEqual(d["w"], 19)
        self.assertEqual(d["parametros"]["data_inicio"], "2026-09-14")
        self.assertEqual(d["parametros"]["data_fim"], "2027-01-19")
        self.assertEqual(len(d["linhas"]), 19)
        for linha in d["linhas"]:
            self.assertEqual(len(linha["columns"]), 5)

    def test_feriado_vira_celula_livre(self):
        d = build_calendario("2026-09-14", 18, 9, ["2026-10-12"])
        livres = [
            c
            for linha in d["linhas"]
            for c in linha["cells"]
            if c and c["free"]
        ]
        self.assertEqual(len(livres), 1)
        self.assertEqual(livres[0]["date"], "2026-10-12")

    def test_parametros_invalidos(self):
        d = build_calendario("2026-09-14", 1, 5, [])
        self.assertFalse(d["valido"])
        self.assertTrue(d["erros"])
        # Data fora de segunda-feira também é inválida.
        d2 = build_calendario("2026-09-15", 18, 9, [])
        self.assertFalse(d2["valido"])
        self.assertTrue(any("segunda" in e for e in d2["erros"]))


class FeriadosNacionaisTests(TestCase):
    def test_pascoa(self):
        self.assertEqual(pascoa(2026), dt.date(2026, 4, 5))
        self.assertEqual(pascoa(2025), dt.date(2025, 4, 20))

    def test_feriados_nacionais_2026(self):
        itens = feriados_nacionais(2026)
        datas = [i["data"] for i in itens]
        self.assertEqual(len(datas), 13)
        self.assertIn(dt.date(2026, 4, 3), datas)  # Sexta-feira Santa
        self.assertIn(dt.date(2026, 2, 17), datas)  # Carnaval (terça)
        self.assertIn(dt.date(2026, 6, 4), datas)  # Corpus Christi
        self.assertIn(dt.date(2026, 11, 20), datas)  # Consciência Negra
        self.assertEqual(datas, sorted(datas))


class SlugETests(TestCase):
    def test_url_slug(self):
        self.assertEqual(url_slug("Calendário Acadêmico 2026.1"), "calendario_academico_2026_1")

    def test_versao_slug(self):
        self.assertEqual(versao_slug("2026.1.Etapa1"), "2026.1.etapa1")

    def test_normalize_base_url(self):
        self.assertEqual(normalize_base_url("https://user.github.io/repo/"), "/repo/")
        self.assertEqual(normalize_base_url("repo"), "/repo/")
        self.assertEqual(normalize_base_url(""), "/")


def _payload(**extra):
    base = {
        "versao": "2026.1.etapa1",
        "titulo": "Calendário 2026.1",
        "periodo": "2026.1",
        "data_inicio": "2026-09-14",
        "total_semanas": 18,
        "semanas_primeira_parte": 9,
        "etapa": 1,
        "final": False,
        "observacoes": "",
        "feriados": [
            {"data": "2026-10-12", "descricao": "N. S. Aparecida", "origem": "nacional"}
        ],
    }
    base.update(extra)
    return base


class ApiTests(TestCase):
    def post(self, url_name, payload):
        return self.client.post(
            reverse(url_name), data=json.dumps(payload), content_type="application/json"
        )

    def test_preview(self):
        resp = self.post("api_preview", _payload())
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertTrue(dados["valido"])
        self.assertEqual(dados["w"], 19)

    def test_salvar_e_promover_a_final(self):
        resposta = self.post("api_salvar", _payload(final=True))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])
        cal = Calendario.objects.get(versao="2026.1.etapa1")
        self.assertTrue(cal.final)
        self.assertTrue(cal.atual)
        self.assertEqual(cal.status, "final")
        self.assertEqual(cal.feriados.count(), 1)

        # Uma nova versão final rebaixa a anterior.
        self.post("api_salvar", _payload(versao="2026.1.etapa2", etapa=2, final=True))
        cal.refresh_from_db()
        self.assertFalse(cal.final)
        self.assertTrue(Calendario.objects.get(versao="2026.1.etapa2").final)

    def test_salvar_remove_feriado_retirado(self):
        self.post("api_salvar", _payload())
        cal = Calendario.objects.get(versao="2026.1.etapa1")
        self.assertEqual(cal.feriados.count(), 1)
        self.post("api_salvar", _payload(feriados=[]))
        self.assertEqual(Feriado.objects.filter(calendario=cal).count(), 0)

    def test_salvar_invalido(self):
        resp = self.post("api_salvar", _payload(total_semanas=1))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    def test_feriados_nacionais_api(self):
        resp = self.client.get(reverse("api_feriados_nacionais") + "?ano=2026")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["feriados"]), 13)

    def test_excluir_versao(self):
        self.post("api_salvar", _payload())
        cal = Calendario.objects.get(versao="2026.1.etapa1")
        self.assertEqual(Feriado.objects.filter(calendario=cal).count(), 1)

        resp = self.post("api_excluir", {"versao": "2026.1.etapa1"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])
        self.assertFalse(Calendario.objects.filter(versao="2026.1.etapa1").exists())
        # A exclusão é em cascata: os feriados da versão também saem.
        self.assertEqual(Feriado.objects.count(), 0)

    def test_excluir_versao_inexistente(self):
        resp = self.post("api_excluir", {"versao": "nao.existe"})
        self.assertEqual(resp.status_code, 404)
        self.assertFalse(resp.json()["ok"])


class ViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cal = Calendario.objects.create(
            versao="2026.1.etapa1",
            titulo="Calendário 2026.1",
            periodo="2026.1",
            data_inicio=dt.date(2026, 9, 14),
            total_semanas=18,
            semanas_primeira_parte=9,
            etapa=1,
            final=True,
            atual=True,
            status="final",
        )
        Feriado.objects.create(
            calendario=cls.cal, data=dt.date(2026, 10, 12), descricao="Padroeira"
        )

    def test_home(self):
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Calendário Acadêmico")
        self.assertContains(resp, "2026.1.etapa1")

    def test_editor(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "Montagem do calendário")
        self.assertContains(resp, "window.CAL_BASE")

    def test_versoes_mostra_opcao_excluir(self):
        resp = self.client.get(reverse("versoes"))
        self.assertContains(resp, "btn-excluir")
        self.assertContains(resp, "versoes/excluir/")
        self.assertContains(resp, "csrfmiddlewaretoken")

    def test_editor_tem_botao_excluir(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "btn-excluir")
        self.assertContains(resp, 'name="destino" value="editor"')

    def test_calendario_atual(self):
        resp = self.client.get(reverse("calendario_atual"))
        self.assertContains(resp, "doc-mes-grid")
        self.assertContains(resp, "data-print-pdf")

    def test_versao_por_slug(self):
        resp = self.client.get(reverse("calendario_versao", kwargs={"slug": self.cal.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.cal.versao)


class ExcluirVersaoFormTests(TestCase):
    """A exclusão pela interface é um POST de formulário (não depende de JS)."""

    @classmethod
    def setUpTestData(cls):
        cls.cal = Calendario.objects.create(
            versao="2026.1.etapa1",
            titulo="Calendário 2026.1",
            periodo="2026.1",
            data_inicio=dt.date(2026, 9, 14),
            total_semanas=18,
            semanas_primeira_parte=9,
            etapa=1,
        )
        Feriado.objects.create(
            calendario=cls.cal, data=dt.date(2026, 10, 12), descricao="Padroeira"
        )

    def test_excluir_via_formulario(self):
        resp = self.client.post(
            reverse("excluir_versao"), {"versao": self.cal.versao, "destino": "versoes"}
        )
        self.assertRedirects(resp, reverse("versoes"))
        self.assertFalse(Calendario.objects.filter(versao=self.cal.versao).exists())
        # A exclusão é em cascata: os feriados da versão também saem.
        self.assertEqual(Feriado.objects.count(), 0)

    def test_excluir_inexistente_avisa(self):
        resp = self.client.post(
            reverse("excluir_versao"),
            {"versao": "nao.existe", "destino": "versoes"},
            follow=True,
        )
        self.assertContains(resp, "não encontrada")

    def test_destino_invalido_cai_para_versoes(self):
        resp = self.client.post(
            reverse("excluir_versao"),
            {"versao": self.cal.versao, "destino": "https://exemplo.com/"},
        )
        self.assertRedirects(resp, reverse("versoes"))

    def test_get_nao_permitido(self):
        self.assertEqual(self.client.get(reverse("excluir_versao")).status_code, 405)

    def test_exige_csrf(self):
        # Sem o token, o Django bloqueia (era o ponto frágil do fluxo via JS).
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(
            cliente.post(reverse("excluir_versao"), {"versao": self.cal.versao}).status_code,
            403,
        )

        # Com o token que o próprio formulário renderiza, funciona.
        pagina = cliente.get(reverse("versoes")).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)
        resp = cliente.post(
            reverse("excluir_versao"),
            {
                "versao": self.cal.versao,
                "destino": "versoes",
                "csrfmiddlewaretoken": token,
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Calendario.objects.filter(versao=self.cal.versao).exists())


class BuildTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.final = Calendario.objects.create(
            versao="2026.1.final",
            titulo="Calendário final 2026.1",
            periodo="2026.1",
            data_inicio=dt.date(2026, 9, 14),
            total_semanas=18,
            semanas_primeira_parte=9,
            etapa=3,
            final=True,
            atual=True,
            status="final",
        )
        Feriado.objects.create(
            calendario=cls.final, data=dt.date(2026, 10, 12), descricao="Padroeira"
        )
        cls.etapa = Calendario.objects.create(
            versao="2026.1.etapa1",
            periodo="2026.1",
            data_inicio=dt.date(2026, 9, 14),
            total_semanas=18,
            semanas_primeira_parte=9,
            etapa=1,
        )
        cls.out = Path(tempfile.mkdtemp(prefix="build_cal_"))
        call_command("render_static_site", output=str(cls.out), base_url="/repo/", verbosity=0)

    def _html(self, *parts):
        return self.out.joinpath(*parts).read_text(encoding="utf-8")

    def test_arquivos_gerados(self):
        self.assertTrue((self.out / "index.html").exists())
        self.assertTrue((self.out / ".nojekyll").exists())
        self.assertTrue((self.out / "calendario" / "index.html").exists())
        self.assertTrue((self.out / "versoes" / "index.html").exists())
        self.assertTrue((self.out / "static" / "css" / "main.css").exists())
        self.assertTrue((self.out / "static" / "js" / "editor.js").exists())
        self.assertTrue((self.out / "static" / "js" / "documento.js").exists())

    def test_build_versionado_por_etapa(self):
        for cal in (self.final, self.etapa):
            caminho = self.out / "versoes" / cal.slug / "index.html"
            self.assertTrue(caminho.exists(), f"faltou {caminho}")

    def test_links_com_base_url(self):
        html = self._html("index.html")
        self.assertIn("/repo/static/css/main.css", html)

    def test_impressao_e_sem_editor_no_build(self):
        html = self._html("calendario", "index.html")
        self.assertIn("data-print-pdf", html)
        self.assertIn("print-head", html)
        self.assertIn("Exportar PDF", html)
        # O editor não é publicado no site estático.
        self.assertNotIn('href="/repo/editor/"', html)

    def test_historico_lista_etapas(self):
        html = self._html("versoes", "index.html")
        self.assertIn("2026.1.final", html)
        self.assertIn("2026.1.etapa1", html)

    def test_build_sem_opcao_excluir(self):
        # O site estático não expõe a ação de excluir (não há API/banco no Pages).
        html = self._html("versoes", "index.html")
        self.assertNotIn("btn-excluir", html)
        self.assertNotIn("csrfmiddlewaretoken", html)
        self.assertNotIn(">Ações<", html)

    def test_documento_no_build(self):
        # A página publicada traz o documento oficial (grades mensais, eventos, legenda).
        html = self._html("calendario", "index.html")
        self.assertIn("Calendário mensal", html)
        self.assertIn("doc-mes", html)
        self.assertIn("doc-table-eventos", html)
        self.assertIn("doc-table-resumo", html)
        self.assertIn("doc-legenda", html)
        self.assertIn("Quantidade de dias letivos por mês", html)
        # Os dias têm tooltip próprio (data/status/eventos) também no build.
        self.assertIn('data-tip="', html)
        self.assertIn("static/js/documento.js", html)
        # A grade x1/x2 (reposição) não é publicada.
        self.assertNotIn("Grade de semanas", html)


class AgendaTests(TestCase):
    """Testa o cálculo da agenda no formato do documento oficial."""

    def _agenda(self, **extra):
        base = dict(
            data_inicio="2026-09-14",
            data_fim="2026-09-25",
            feriados=[
                {"data": "2026-09-16", "tipo": "ponto_facultativo"},
                {"data": "2026-09-24", "tipo": "feriado"},
            ],
            eventos=[
                {
                    "titulo": "Sábado letivo",
                    "tipo": "sabado_letivo",
                    "data_inicio": "2026-09-19",
                    "dia_semana_referencia": 2,
                }
            ],
            dias_letivos_previstos=9,
        )
        base.update(extra)
        return build_agenda(**base)

    def _celula(self, agenda, iso):
        for mes in agenda["meses"]:
            for semana in mes["semanas"]:
                for celula in semana:
                    if not celula.get("vazio") and celula["date"] == iso:
                        return celula
        return None

    def test_dias_letivos_e_status(self):
        ag = self._agenda()
        self.assertEqual(ag["total_letivos"], 9)
        self.assertEqual(self._celula(ag, "2026-09-14")["status"], "letivo")
        self.assertEqual(self._celula(ag, "2026-09-16")["status"], "ponto_facultativo")
        self.assertEqual(self._celula(ag, "2026-09-19")["status"], "letivo_sabado")
        self.assertEqual(self._celula(ag, "2026-09-20")["status"], "nao_letivo")
        self.assertEqual(self._celula(ag, "2026-09-24")["status"], "feriado")
        # Antes do início do período o dia não é considerado.
        self.assertEqual(self._celula(ag, "2026-09-13")["status"], "fora")

    def test_sabados_letivos_com_referencia(self):
        ag = self._agenda()
        self.assertEqual(len(ag["sabados_letivos"]), 1)
        sabado = ag["sabados_letivos"][0]
        self.assertEqual(sabado["date"], "2026-09-19")
        self.assertEqual(sabado["referencia"], "referente à quarta-feira")

    def test_resumo_e_validacao(self):
        ag = self._agenda()
        self.assertEqual(ag["resumo"][0]["label"], "SET/2026")
        self.assertEqual(ag["resumo"][0]["letivos"], 9)
        self.assertTrue(ag["validacao"]["ok"])

        divergente = self._agenda(dias_letivos_previstos=100)
        self.assertFalse(divergente["validacao"]["ok"])
        self.assertTrue(divergente["validacao"]["avisos"])

    def test_eventos_por_mes_e_legenda(self):
        ag = self._agenda()
        self.assertEqual(ag["eventos_por_mes"][0]["label"], "SET/2026")
        self.assertEqual(ag["eventos_por_mes"][0]["itens"][0]["dia"], "19")
        status = {item["status"] for item in ag["legenda"]}
        self.assertTrue(
            {"letivo", "letivo_sabado", "feriado", "ponto_facultativo"} <= status
        )
        # Eventos indexados por data (usados nos tooltips dos dias).
        self.assertEqual(ag["eventos_dia"]["2026-09-19"], ["Sábado letivo"])

    def test_sem_data_inicio(self):
        ag = build_agenda(None, None, [], [])
        self.assertEqual(ag["meses"], [])
        self.assertEqual(ag["total_letivos"], 0)


class Seed20262Tests(TestCase):
    """O seed recria o documento oficial 2026.2 (Administração Integrado PROEJA)."""

    def test_seed_cria_calendario_com_100_dias(self):
        call_command("seed_calendario_2026_2", verbosity=0)
        cal = Calendario.objects.get(versao="2026.2.final")
        self.assertTrue(cal.final)
        self.assertTrue(cal.atual)
        self.assertEqual(cal.curso, "Cursos Técnico em Administração")
        self.assertEqual(cal.dias_letivos_previstos, 100)
        self.assertEqual(cal.feriados.count(), 12)
        self.assertEqual(cal.eventos.count(), 37)

        agenda = cal.agenda()
        self.assertEqual(agenda["total_letivos"], 100)
        self.assertEqual(len(agenda["sabados_letivos"]), 11)
        # O total do documento = seg–sex + sábados letivos.
        self.assertEqual(agenda["sabados_total"], 11)
        self.assertEqual(agenda["letivos_seg_sex"], 89)
        self.assertEqual(
            agenda["letivos_seg_sex"] + agenda["sabados_total"], agenda["total_letivos"]
        )
        # O período vai de agosto/2026 (matrículas) a fevereiro/2027.
        labels = [m["label"] for m in agenda["meses"]]
        self.assertEqual(labels[0], "AGO/2026")
        self.assertEqual(labels[-1], "FEV/2027")
        self.assertEqual(agenda["resumo"][0]["letivos"], 0)

    def test_ferias_coletivas_sem_colisao(self):
        # Dias de férias coletivas não devem ser "roubados" por feriados.
        call_command("seed_calendario_2026_2", verbosity=0)
        cal = Calendario.objects.get(versao="2026.2.final")
        ag = cal.agenda()
        dias = {
            c["date"]: c["status"]
            for m in ag["meses"]
            for s in m["semanas"]
            for c in s
            if not c.get("vazio")
        }
        self.assertEqual(dias["2027-02-13"], "ferias")
        # Colisão legítima e documentada: Natal (feriado) dentro do recesso.
        self.assertEqual(dias["2026-12-25"], "feriado")

    def test_seed_idempotente(self):
        call_command("seed_calendario_2026_2", verbosity=0)
        call_command("seed_calendario_2026_2", verbosity=0)
        self.assertEqual(Calendario.objects.filter(versao="2026.2.final").count(), 1)
        cal = Calendario.objects.get(versao="2026.2.final")
        self.assertEqual(cal.feriados.count(), 12)
        self.assertEqual(cal.eventos.count(), 37)


class EventosApiTests(TestCase):
    """A coleção de eventos é gerenciável pela API."""

    @classmethod
    def setUpTestData(cls):
        cls.cal = Calendario.objects.create(
            versao="2026.2.etapa1",
            data_inicio=dt.date(2026, 9, 14),
        )

    def _post_eventos(self, eventos):
        return self.client.post(
            reverse("api_eventos"),
            data=json.dumps({"versao": "2026.2.etapa1", "eventos": eventos}),
            content_type="application/json",
        )

    def test_post_e_get_eventos(self):
        resp = self._post_eventos(
            [
                {
                    "titulo": "Sábado letivo",
                    "tipo": "sabado_letivo",
                    "data_inicio": "2026-09-19",
                    "dia_semana_referencia": 2,
                },
                {
                    "titulo": "Recesso de Natal",
                    "tipo": "recesso",
                    "data_inicio": "2026-12-22",
                    "data_fim": "2026-12-31",
                },
            ]
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Evento.objects.filter(calendario=self.cal).count(), 2)

        listagem = self.client.get(reverse("api_eventos"), {"versao": "2026.2.etapa1"})
        self.assertEqual(listagem.status_code, 200)
        self.assertEqual(len(listagem.json()["eventos"]), 2)

    def test_post_substitui_a_colecao(self):
        self._post_eventos(
            [
                {"titulo": "A", "tipo": "evento", "data_inicio": "2026-09-15"},
                {"titulo": "B", "tipo": "evento", "data_inicio": "2026-09-16"},
            ]
        )
        self._post_eventos(
            [{"titulo": "C", "tipo": "evento", "data_inicio": "2026-09-17"}]
        )
        titulos = list(
            Evento.objects.filter(calendario=self.cal).values_list("titulo", flat=True)
        )
        self.assertEqual(titulos, ["C"])

    def test_tipo_invalido_vira_evento(self):
        self._post_eventos(
            [{"titulo": "X", "tipo": "inexistente", "data_inicio": "2026-09-15"}]
        )
        self.assertEqual(Evento.objects.get(calendario=self.cal).tipo, "evento")

    def test_versao_inexistente(self):
        self.assertEqual(
            self.client.get(reverse("api_eventos"), {"versao": "nada"}).status_code, 404
        )
        resp = self.client.post(
            reverse("api_eventos"),
            data=json.dumps({"versao": "nada", "eventos": []}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_salvar_persiste_eventos(self):
        payload = _payload(
            versao="2026.2.etapa1",
            curso="Técnico em Administração",
            dias_letivos_previstos=100,
            eventos=[
                {
                    "titulo": "Matrículas",
                    "tipo": "matricula",
                    "data_inicio": "2026-08-10",
                    "data_fim": "2026-08-14",
                }
            ],
        )
        resp = self.client.post(
            reverse("api_salvar"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Evento.objects.filter(calendario=self.cal).count(), 1)
        self.cal.refresh_from_db()
        self.assertEqual(self.cal.curso, "Técnico em Administração")
        self.assertEqual(self.cal.dias_letivos_previstos, 100)
        self.assertIn("agenda", resp.json()["dados"])

    def test_salvar_ponto_facultativo(self):
        payload = _payload(
            feriados=[
                {
                    "data": "2026-10-15",
                    "descricao": "Dia do Professor/TAE",
                    "origem": "institucional",
                    "tipo": "ponto_facultativo",
                }
            ]
        )
        self.client.post(
            reverse("api_salvar"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(
            Feriado.objects.get(calendario__versao="2026.1.etapa1").tipo,
            "ponto_facultativo",
        )


class DocumentoViewTests(TestCase):
    """A página do calendário renderiza o documento oficial completo."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_calendario_2026_2", verbosity=0)

    def test_calendario_atual_renderiza_documento(self):
        resp = self.client.get(reverse("calendario_atual"))
        self.assertEqual(resp.status_code, 200)
        for trecho in (
            "CALENDÁRIO ACADÊMICO 2026.2",
            "Calendário mensal",
            "Quantidade de dias letivos por mês",
            "Feriados e pontos facultativos",
            "Sábados letivos",
            "Legenda",
            "doc-mes",
            "doc-legenda",
            "doc-table-eventos",
        ):
            self.assertContains(resp, trecho)

    def test_calendario_atual_tem_tooltip_nos_dias(self):
        # Os dias das grades levam "data-tip" (tooltip próprio, igual ao da prévia
        # do editor) com data, status e eventos — sem o "title" nativo.
        resp = self.client.get(reverse("calendario_atual"))
        self.assertContains(resp, 'data-tip="')
        self.assertContains(resp, "js/documento.js")
        self.assertNotContains(resp, 'title="Dia letivo"')

    def test_documento_js_tem_tooltip(self):
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "documento.js"
        ).read_text(encoding="utf-8")
        self.assertIn("doc-tooltip", js)
        self.assertIn("data-tip", js)
        self.assertIn("mostrarTooltip", js)

    def test_sem_grade_de_semanas(self):
        # A grade x1/x2 (reposição) não é publicada no documento — fica só na
        # prévia do editor. A legenda do calendário mensal continua na página.
        resp = self.client.get(reverse("calendario_atual"))
        for trecho in (
            "Grade de semanas (reposição)",
            "cal-table",
            "Erros (paridade",
            "cal-sabado-letivo",
            "Feriados considerados",
        ):
            self.assertNotContains(resp, trecho)
        self.assertContains(resp, "doc-legenda")

    def test_editor_tem_painel_de_eventos(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, 'id="eventosBody"')
        self.assertContains(resp, "Dias letivos previstos")
        self.assertContains(resp, "Dia da semana referenciado")

    def test_editor_tem_previa_do_documento(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, 'id="docPreview"')
        self.assertContains(resp, 'id="calPreview"')
        self.assertContains(resp, "Prévia do documento")
        self.assertContains(resp, "Prévia da grade (reposição)")

    def test_editor_js_renderiza_agenda(self):
        # O JS da prévia monta as grades mensais com os eventos e marca a grade x1/x2.
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("renderAgenda", js)
        self.assertIn("docPreview", js)
        self.assertIn("cal-has-evento", js)
        self.assertIn("renderEventosDoc", js)

    def test_editor_js_tem_tooltip_das_previas(self):
        # O tooltip próprio substitui o "title" nativo nas células das prévias.
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("editor-tooltip", js)
        self.assertIn("data-tip", js)
        self.assertIn("mostrarTooltip", js)
        # As células das prévias usam data-tip (tooltip próprio), não o "title" nativo.
        self.assertIn('" data-tip="', js)

    def test_editor_tem_textos_de_ajuda(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "1. Preenchimento")
        self.assertContains(resp, "2. Prévias")
        self.assertContains(resp, "field-hint")
        self.assertContains(resp, "Como utilizar")

    def test_editor_ordena_preenchimento_antes_das_previas(self):
        html = self.client.get(reverse("editor")).content.decode("utf-8")
        self.assertLess(html.index("1. Preenchimento"), html.index("2. Prévias"))
        self.assertLess(html.index("2. Prévias"), html.index("Prévia do documento"))

    def test_editor_tem_toggles_de_navegacao(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, 'data-toggle-block="inputs"')
        self.assertContains(resp, 'data-toggle-block="previews"')
        self.assertContains(resp, 'data-block="inputs"')
        self.assertContains(resp, 'data-block="previews"')

    def test_editor_js_tem_legenda_da_grade(self):
        # A prévia da grade renderiza a legenda de cores (paridade, feriado, parte,
        # evento e aula remanejada).
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("cal-legend", js)
        self.assertIn("swatch-parity1", js)
        self.assertIn("swatch-evento", js)
        self.assertIn("renderLegendaGrade", js)

    def test_editor_js_oculta_blocos(self):
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("editor-hide-inputs", js)
        self.assertIn("editor-hide-previews", js)
        self.assertIn("aplicarBloco", js)

    def test_editor_js_explica_metricas(self):
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("renderAjudaMetricas", js)
        self.assertIn("Como ler", js)
        self.assertIn("ideal: 0 / 0 / 0", js)

    def test_editor_js_feriado_reversivel(self):
        # O dia marcado como feriado continua visível (riscado) e clicável para desfazer.
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("cal-date-free", js)
        self.assertIn("clique para marcar como feriado", js)
        self.assertIn("Feriado — clique para remover", js)

    def test_editor_js_conta_sabados_na_grade(self):
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("sabados_total", js)
        self.assertIn("Dias letivos (seg–sex)", js)
        self.assertIn("Sábados letivos", js)
        self.assertIn("Total de dias letivos", js)

    def test_documento_lista_sabados_letivos(self):
        # Sem a grade x1/x2, os sábados letivos continuam no documento (lista própria).
        resp = self.client.get(reverse("calendario_atual"))
        self.assertContains(resp, "Sábados letivos")
        # 19/09/2026 é um dos sábados letivos do 2026.2.
        self.assertContains(resp, "19/09")
        self.assertContains(resp, "referente à quarta-feira")

    def test_editor_js_coluna_sabado(self):
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn(">Sáb</th>", js)
        self.assertIn("cal-sabado", js)
        self.assertIn("sabados_letivos", js)

    def test_editor_tem_edicao_de_eventos(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, 'id="btnCancelarEvento"')
        self.assertContains(resp, "<th>Ações</th>")
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("editarEvento", js)
        self.assertIn("salvarEvento", js)
        self.assertIn("btnCancelarEvento", js)

    def test_editor_etapas_salvas_primeiro(self):
        html = self.client.get(reverse("editor")).content.decode("utf-8")
        self.assertIn("1.1</span> Etapas salvas", html)
        self.assertLess(html.index("Etapas salvas"), html.index("Parâmetros do calendário"))

    def test_css_ferias_coletivas_em_azul_escuro(self):
        css = (
            Path(__file__).resolve().parent.parent / "static" / "css" / "main.css"
        ).read_text(encoding="utf-8")
        bloco = css[css.index(".doc-dia-ferias {") :]
        bloco = bloco[: bloco.index("}")]
        self.assertIn("30, 58, 138", bloco)
        # O chip da tabela de eventos acompanha a cor da legenda/grade.
        chip = css[css.index(".doc-evento-ferias_coletivas {") :]
        chip = chip[: chip.index("}")]
        self.assertIn("30, 58, 138", chip)
        # O chip de férias coletivas não fica mais agrupado com o recesso.
        self.assertNotIn(".doc-evento-recesso,\n.doc-evento-ferias_coletivas", css)


class PreviewAgendaTests(TestCase):
    """A prévia do editor usa a agenda (eventos por dia) devolvida pela API."""

    def test_preview_traz_eventos_na_agenda(self):
        payload = _payload(
            data_fim="2026-09-25",
            eventos=[
                {
                    "titulo": "Sábado letivo",
                    "tipo": "sabado_letivo",
                    "data_inicio": "2026-09-19",
                    "dia_semana_referencia": 2,
                },
                {
                    "titulo": "Avaliações do 1º Bimestre",
                    "tipo": "avaliacao",
                    "data_inicio": "2026-09-15",
                    "data_fim": "2026-09-16",
                },
            ],
        )
        resp = self.client.post(
            reverse("api_preview"), data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 200)
        agenda = resp.json()["agenda"]

        celulas = {
            c["date"]: c
            for mes in agenda["meses"]
            for semana in mes["semanas"]
            for c in semana
            if c and not c.get("vazio")
        }
        self.assertEqual(celulas["2026-09-19"]["status"], "letivo_sabado")
        self.assertEqual(celulas["2026-09-19"]["eventos"], ["Sábado letivo"])
        self.assertEqual(
            celulas["2026-09-15"]["eventos"], ["Avaliações do 1º Bimestre"]
        )

        grupos = {g["label"]: g for g in agenda["eventos_por_mes"]}
        self.assertIn("SET/2026", grupos)
        titulos = [i["titulo"] for i in grupos["SET/2026"]["itens"]]
        self.assertIn("Sábado letivo", titulos)
        self.assertIn("Avaliações do 1º Bimestre", titulos)




