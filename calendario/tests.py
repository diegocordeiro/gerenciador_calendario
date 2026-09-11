import datetime as dt
import json
import re
import tempfile
from pathlib import Path
from unittest import mock

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from . import llm, requisitos
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

    def test_salvar_versao(self):
        resposta = self.post("api_salvar", _payload())
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.json()["ok"])
        cal = Calendario.objects.get(versao="2026.1.etapa1")
        self.assertEqual(cal.feriados.count(), 1)
        self.assertEqual(cal.etapa, 1)

        # Salvar uma segunda versão não altera a primeira.
        self.post("api_salvar", _payload(versao="2026.1.etapa2", etapa=2))
        self.assertEqual(Calendario.objects.count(), 2)

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

    def test_indice_mostra_opcao_excluir(self):
        resp = self.client.get(reverse("indice"))
        self.assertContains(resp, "btn-excluir")
        self.assertContains(resp, "versoes/excluir/")
        self.assertContains(resp, "csrfmiddlewaretoken")

    def test_editor_tem_botao_excluir(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "btn-excluir")
        self.assertContains(resp, 'name="destino" value="editor"')

    def test_indice_lista_versoes(self):
        resp = self.client.get(reverse("indice"))
        self.assertContains(resp, "Calendário acadêmico")
        self.assertContains(resp, self.cal.versao)

    def test_versoes_redireciona_para_indice(self):
        self.assertRedirects(self.client.get(reverse("versoes")), reverse("indice"))

    def test_documento_versionado(self):
        resp = self.client.get(
            reverse("calendario_versionado", kwargs={"slug": self.cal.slug})
        )
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
            reverse("excluir_versao"), {"versao": self.cal.versao, "destino": "calendario"}
        )
        self.assertRedirects(resp, reverse("indice"))
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

    def test_destino_invalido_cai_para_o_indice(self):
        resp = self.client.post(
            reverse("excluir_versao"),
            {"versao": self.cal.versao, "destino": "https://exemplo.com/"},
        )
        self.assertRedirects(resp, reverse("indice"))

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
        pagina = cliente.get(reverse("indice")).content.decode()
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', pagina).group(1)
        resp = cliente.post(
            reverse("excluir_versao"),
            {
                "versao": self.cal.versao,
                "destino": "calendario",
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
        html = self._html("versoes", self.final.slug, "index.html")
        self.assertIn("data-print-pdf", html)
        self.assertIn("print-head", html)
        self.assertIn("Exportar PDF", html)
        # O editor não é publicado no site estático.
        self.assertNotIn('href="/repo/editor/"', html)

    def test_indice_lista_versoes(self):
        html = self._html("calendario", "index.html")
        self.assertIn("2026.1.final", html)
        self.assertIn("2026.1.etapa1", html)

    def test_versoes_redireciona_no_build(self):
        html = self._html("versoes", "index.html")
        self.assertIn("url=../calendario/", html)

    def test_build_sem_opcao_excluir(self):
        # O site estático não expõe a ação de excluir (não há API/banco no Pages).
        html = self._html("calendario", "index.html")
        self.assertNotIn("btn-excluir", html)
        self.assertNotIn("csrfmiddlewaretoken", html)
        self.assertNotIn(">Ações<", html)

    def test_documento_no_build(self):
        # A página publicada traz o documento oficial (grades mensais, eventos, legenda).
        html = self._html("versoes", self.final.slug, "index.html")
        self.assertIn("Calendário mensal", html)
        self.assertIn("doc-mes", html)
        self.assertIn("doc-table-eventos", html)
        self.assertIn("doc-table-resumo", html)
        self.assertIn("doc-table-dias", html)
        self.assertIn("Dias letivos por dia da semana", html)
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

    def test_contagem_por_dia_da_semana_separada(self):
        # A meta do semestre é dividida pelos 5 dias úteis: 9/5 -> 2 por dia.
        ag = self._agenda()
        self.assertEqual(ag["meta_por_dia"], 2)
        # 2026-09-14(seg) a 2026-09-25(sex): seg 2, ter 2, qua 1, qui 1, sex 2.
        self.assertEqual(ag["letivos_seg_sex_por_dia"], [2, 2, 1, 1, 2])
        # O sábado letivo (19/09) é referente à quarta-feira (dia_semana_referencia=2).
        self.assertEqual(ag["sabados_por_dia"], [0, 0, 1, 0, 0])
        # Total por dia = seg–sex + sábados (pela Referência).
        self.assertEqual(ag["letivos_por_dia"], [2, 2, 2, 1, 2])
        self.assertEqual(len(ag["dias_por_dia"]), 5)
        self.assertEqual(ag["dias_por_dia"][0]["label"], "Segunda-feira")

        por_dia = {d["weekday"]: d for d in ag["dias_por_dia"]}
        self.assertEqual(por_dia[2]["letivos"], 2)  # 1 seg–sex + 1 sábado
        self.assertEqual(por_dia[2]["seg_sex"], 1)
        self.assertEqual(por_dia[2]["sabados"], 1)
        self.assertTrue(por_dia[2]["ok"])  # quarta: 2 >= 2
        self.assertFalse(por_dia[3]["ok"])  # quinta: 1 < 2
        self.assertEqual(por_dia[3]["falta"], 1)
        self.assertFalse(ag["validacao"]["por_dia_ok"])
        avisos = "".join(ag["validacao"]["avisos"])
        self.assertIn("Quinta-feira: 1 dia(s) letivo(s)", avisos)
        # A soma por dia confere com o total (seg–sex + sábados).
        self.assertEqual(sum(ag["letivos_por_dia"]), ag["total_letivos"])

    def test_sabado_sem_referencia_nao_conta_por_dia(self):
        ag = self._agenda(
            eventos=[
                {
                    "titulo": "Sábado letivo",
                    "tipo": "sabado_letivo",
                    "data_inicio": "2026-09-19",
                }
            ]
        )
        self.assertEqual(ag["sabados_total"], 1)
        self.assertEqual(ag["sabados_sem_referencia"], 1)
        self.assertEqual(ag["sabados_por_dia"], [0, 0, 0, 0, 0])
        # Sem Referência, o sábado não é somado a nenhum dia da semana.
        self.assertEqual(ag["letivos_por_dia"], [2, 2, 1, 1, 2])
        self.assertIn("sem dia da semana", "".join(ag["validacao"]["avisos"]))

    def test_sem_meta_por_dia_quando_sem_previsto(self):
        ag = self._agenda(dias_letivos_previstos=0)
        self.assertEqual(ag["meta_por_dia"], 0)
        self.assertTrue(ag["validacao"]["por_dia_ok"])
        self.assertTrue(all(d["ok"] for d in ag["dias_por_dia"]))

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
        self.assertEqual(cal.curso, "Cursos Técnico em Administração")
        self.assertEqual(cal.dias_letivos_previstos, 100)
        self.assertEqual(cal.feriados.count(), 12)
        self.assertEqual(cal.eventos.count(), 37)

        agenda = cal.agenda()
        # Jornada pedagógica e conselho de classe NÃO contam: o Conselho de Classe
        # (12/02/2027, sexta) remove aquele dia letivo e as férias de 13/02 ficam
        # fora do período declarado (12/02) — o cálculo fecha nos 100 do documento.
        self.assertEqual(agenda["total_letivos"], 100)
        self.assertEqual(len(agenda["sabados_letivos"]), 11)
        # O total do documento = seg–sex + sábados letivos.
        self.assertEqual(agenda["sabados_total"], 11)
        self.assertEqual(agenda["letivos_seg_sex"], 89)
        self.assertEqual(
            agenda["letivos_seg_sex"] + agenda["sabados_total"], agenda["total_letivos"]
        )
        # Contagem por dia da semana, em separado (meta 100/5 = 20 por dia),
        # somando os sábados letivos ao dia informado no campo Referência.
        self.assertEqual(agenda["meta_por_dia"], 20)
        self.assertEqual(agenda["letivos_seg_sex_por_dia"], [17, 18, 18, 18, 18])
        self.assertEqual(agenda["sabados_por_dia"], [3, 0, 4, 2, 2])
        self.assertEqual(agenda["letivos_por_dia"], [20, 18, 22, 20, 20])
        self.assertEqual(agenda["sabados_sem_referencia"], 0)
        self.assertFalse(agenda["validacao"]["por_dia_ok"])
        self.assertEqual(
            [d["falta"] for d in agenda["dias_por_dia"]], [0, 2, 0, 0, 0]
        )
        # A soma por dia confere com o total de dias letivos do documento.
        self.assertEqual(sum(agenda["letivos_por_dia"]), agenda["total_letivos"])
        # O período vai de agosto/2026 (matrículas) a fevereiro/2027.
        labels = [m["label"] for m in agenda["meses"]]
        self.assertEqual(labels[0], "AGO/2026")
        self.assertEqual(labels[-1], "FEV/2027")
        self.assertEqual(agenda["resumo"][0]["letivos"], 0)
        # Férias coletivas começam depois do término: ficam fora do cálculo.
        self.assertIn("2027-02-13", agenda["eventos_fora"])
        self.assertEqual(agenda["reposicoes_total"], 0)

    def test_ferias_coletivas_sem_colisao(self):
        # As férias coletivas começam em 13/02/2027, depois do término declarado
        # (12/02/2027): continuam no documento, mas o dia fica "fora" e não entra na
        # carga horária.
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
        self.assertEqual(dias["2027-02-13"], "fora")
        self.assertFalse(
            next(
                c
                for m in ag["meses"]
                for s in m["semanas"]
                for c in s
                if not c.get("vazio") and c["date"] == "2027-02-13"
            )["letivo"]
        )
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

    def _doc(self):
        cal = Calendario.objects.get(versao="2026.2.final")
        return self.client.get(
            reverse("calendario_versionado", kwargs={"slug": cal.slug})
        )

    def test_documento_renderiza_documento(self):
        resp = self._doc()
        self.assertEqual(resp.status_code, 200)
        for trecho in (
            "CALENDÁRIO ACADÊMICO 2026.2",
            "Calendário mensal",
            "Quantidade de dias letivos por mês",
            "Dias letivos por dia da semana",
            "Feriados e pontos facultativos",
            "Sábados letivos",
            "Legenda",
            "doc-mes",
            "doc-legenda",
            "doc-table-eventos",
            "doc-table-dias",
        ):
            self.assertContains(resp, trecho)

    def test_documento_tem_tooltip_nos_dias(self):
        # Os dias das grades levam "data-tip" (tooltip próprio, igual ao da prévia
        # do editor) com data, status e eventos — sem o "title" nativo.
        resp = self._doc()
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
        resp = self._doc()
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

    def test_editor_js_tabela_por_dia_da_semana(self):
        # A elaboração traz a tabela com a contagem SEPARADA por dia da semana
        # (seg–sex) e o mínimo de 100/5 = 20 por dia.
        js = (
            Path(__file__).resolve().parent.parent / "static" / "js" / "editor.js"
        ).read_text(encoding="utf-8")
        self.assertIn("renderResumoDias", js)
        self.assertIn("doc-table-dias", js)
        self.assertIn("Letivos por dia (seg–sex + sábados)", js)
        self.assertIn("por_dia_ok", js)
        self.assertIn("Dias letivos por dia da semana", js)
        self.assertIn("sabados_por_dia", js)

    def test_documento_lista_sabados_letivos(self):
        # Sem a grade x1/x2, os sábados letivos continuam no documento (lista própria).
        resp = self._doc()
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


class ClonarVersaoTests(TestCase):
    """Clonar uma versão como base para o calendário de outra modalidade."""

    @classmethod
    def setUpTestData(cls):
        cls.cal = Calendario.objects.create(
            versao="2026.2.integrado",
            titulo="Calendário 2026.2 — Administração",
            periodo="2026.2",
            curso="Técnico em Administração",
            modalidade="integrado_medio",
            semestre="2º Semestre",
            data_inicio=dt.date(2026, 9, 14),
            data_fim=dt.date(2027, 2, 12),
            total_semanas=22,
            semanas_primeira_parte=11,
            dias_letivos_previstos=100,
            dias_letivos_por_mes=[{"mes": "SET/2026", "letivos": 13}],
            etapa=1,
            observacoes="Base do integrado.",
        )

        Feriado.objects.create(
            calendario=cls.cal,
            data=dt.date(2026, 11, 20),
            descricao="Consciência Negra",
            origem="nacional",
            tipo="feriado",
        )
        Evento.objects.create(
            calendario=cls.cal,
            titulo="Avaliações do 1º Bimestre",
            tipo="avaliacao",
            data_inicio=dt.date(2026, 11, 4),
            data_fim=dt.date(2026, 11, 7),
        )
        Evento.objects.create(
            calendario=cls.cal,
            titulo="Sábado letivo",
            tipo="sabado_letivo",
            data_inicio=dt.date(2026, 11, 7),
            dia_semana_referencia=2,
        )

    # ---- núcleo (modelo) ----
    def test_clonar_copia_parametros_feriados_e_eventos(self):
        novo = self.cal.clonar(
            "2026.2.subsequente",
            modalidade="concomitante_subsequente",
            curso="Técnico em Administração Subsequente",
        )
        self.assertEqual(novo.modalidade, "concomitante_subsequente")
        self.assertEqual(novo.curso, "Técnico em Administração Subsequente")
        # Cabeçalho/período herdados.
        self.assertEqual(novo.titulo, self.cal.titulo)
        self.assertEqual(novo.periodo, "2026.2")
        self.assertEqual(novo.data_inicio, self.cal.data_inicio)
        self.assertEqual(novo.total_semanas, 22)
        self.assertEqual(
            novo.dias_letivos_por_mes, [{"mes": "SET/2026", "letivos": 13}]
        )
        # Feriados e eventos copiados.
        self.assertEqual(novo.feriados.count(), 1)
        self.assertEqual(novo.eventos.count(), 2)
        # A origem permanece intacta.
        self.assertEqual(self.cal.feriados.count(), 1)
        self.assertEqual(self.cal.eventos.count(), 2)

    def test_clonar_cria_versao_independente(self):
        novo = self.cal.clonar("2026.2.copia")
        self.assertEqual(novo.versao, "2026.2.copia")
        self.assertEqual(Calendario.objects.count(), 2)
        # A origem permanece intacta.
        self.cal.refresh_from_db()
        self.assertEqual(self.cal.versao, "2026.2.integrado")

    def test_clonar_nome_repetido_falha(self):
        with self.assertRaises(ValidationError):
            self.cal.clonar("2026.2.integrado")
        self.assertEqual(Calendario.objects.count(), 1)

    def test_clonar_nome_vazio_falha(self):
        with self.assertRaises(ValidationError):
            self.cal.clonar("   ")

    # ---- formulário (funciona sem JS) ----
    def test_clonar_via_formulario_redireciona_para_editor(self):
        resp = self.client.post(
            reverse("clonar_versao"),
            {
                "versao": "2026.2.integrado",
                "nova_versao": "2026.2.subsequente",
                "modalidade": "concomitante_subsequente",
                "curso": "Administração Subsequente",
                "destino": "editor",
            },
        )
        novo = Calendario.objects.get(versao="2026.2.subsequente")
        self.assertRedirects(resp, reverse("editor") + f"?versao={novo.slug}")
        self.assertEqual(novo.modalidade, "concomitante_subsequente")
        self.assertEqual(novo.eventos.count(), 2)

    def test_clonar_formulario_origem_inexistente_avisa(self):
        resp = self.client.post(
            reverse("clonar_versao"),
            {"versao": "nao.existe", "nova_versao": "x", "destino": "versoes"},
            follow=True,
        )
        self.assertContains(resp, "não encontrada")
        self.assertFalse(Calendario.objects.filter(versao="x").exists())

    def test_clonar_formulario_nome_igual_avisa(self):
        resp = self.client.post(
            reverse("clonar_versao"),
            {"versao": "2026.2.integrado", "nova_versao": "2026.2.integrado"},
            follow=True,
        )
        self.assertContains(resp, "diferente")
        self.assertEqual(Calendario.objects.count(), 1)

    def test_clonar_formulario_modalidade_invalida_mantem_base(self):
        self.client.post(
            reverse("clonar_versao"),
            {
                "versao": "2026.2.integrado",
                "nova_versao": "2026.2.x",
                "modalidade": "inexistente",
                "destino": "versoes",
            },
        )
        novo = Calendario.objects.get(versao="2026.2.x")
        self.assertEqual(novo.modalidade, "integrado_medio")

    def test_clonar_get_nao_permitido(self):
        self.assertEqual(self.client.get(reverse("clonar_versao")).status_code, 405)

    def test_clonar_exige_csrf(self):
        cliente = Client(enforce_csrf_checks=True)
        self.assertEqual(
            cliente.post(
                reverse("clonar_versao"), {"versao": "2026.2.integrado"}
            ).status_code,
            403,
        )

    # ---- API ----
    def test_api_clonar(self):
        resp = self.client.post(
            reverse("api_clonar"),
            data=json.dumps(
                {
                    "versao": "2026.2.integrado",
                    "nova_versao": "2026.2.superior",
                    "modalidade": "graduacao",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["versao"], "2026.2.superior")
        self.assertEqual(len(dados["eventos"]), 2)

    def test_api_clonar_origem_inexistente(self):
        resp = self.client.post(
            reverse("api_clonar"),
            data=json.dumps({"versao": "nada", "nova_versao": "x"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_api_clonar_duplicado(self):
        resp = self.client.post(
            reverse("api_clonar"),
            data=json.dumps(
                {"versao": "2026.2.integrado", "nova_versao": "2026.2.integrado"}
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["ok"])

    # ---- página ----
    def test_indice_tem_painel_de_clone(self):
        resp = self.client.get(reverse("indice"))
        self.assertContains(resp, "versoes/clonar/")
        self.assertContains(resp, "Clonar uma versão")
        self.assertContains(resp, 'name="nova_versao"')
        self.assertContains(resp, "Manter a da versão base")

    def test_editor_carrega_versao_clonada(self):
        novo = self.cal.clonar("2026.2.subsequente")
        resp = self.client.get(reverse("editor") + f"?versao={novo.slug}")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2026.2.subsequente")





# ===========================================================================
# Requisitos das normas (arts. 38, 39 e 40)
# ===========================================================================


class RequisitosTests(TestCase):
    """Conferência determinística dos itens exigidos por norma."""

    def test_modalidade_aponta_para_a_norma(self):
        self.assertEqual(requisitos.norma_da_modalidade("integrado_medio"), "Art. 38")
        self.assertEqual(
            requisitos.norma_da_modalidade("concomitante_subsequente"), "Art. 39"
        )
        self.assertEqual(requisitos.norma_da_modalidade("graduacao"), "Art. 40")

    def test_modalidade_desconhecida_cai_no_padrao(self):
        self.assertEqual(requisitos.norma_da_modalidade("inexistente"), "Art. 38")

    def test_quantidade_de_itens_por_norma(self):
        self.assertEqual(len(requisitos.itens_da_modalidade("integrado_medio")), 22)
        self.assertEqual(len(requisitos.itens_da_modalidade("concomitante_subsequente")), 21)
        self.assertEqual(len(requisitos.itens_da_modalidade("graduacao")), 23)

    def test_prompt_lista_os_itens_da_norma(self):
        texto = requisitos.formatar_para_prompt("graduacao")
        self.assertIn("I)", texto)
        self.assertIn("ATPA", texto)

    def _itens(self, modalidade, eventos, agenda=None, **extra):
        return {
            i["codigo"]: i
            for i in requisitos.verificar_requisitos(
                modalidade, eventos=eventos, agenda=agenda, **extra
            )["itens"]
        }

    def test_detecta_por_tipo(self):
        itens = self._itens(
            "integrado_medio",
            [
                {"titulo": "Recuperação paralela", "tipo": "recuperacao",
                 "data_inicio": "2026-11-23"},
                {"titulo": "Conselho de Classe", "tipo": "conselho_classe",
                 "data_inicio": "2026-11-30"},
            ],
        )
        self.assertEqual(itens["VII"]["situacao"], requisitos.SITUACAO_ATENDIDO)
        self.assertEqual(itens["XX"]["situacao"], requisitos.SITUACAO_ATENDIDO)
        self.assertEqual(itens["VII"]["evidencias"], ["23/11 — Recuperação paralela"])

    def test_detecta_por_palavra_mesmo_com_outro_titulo(self):
        itens = self._itens(
            "integrado_medio",
            [{"titulo": "Eleição dos representantes de turma", "tipo": "evento",
              "data_inicio": "2026-09-22"}],
        )
        self.assertEqual(itens["IV"]["situacao"], requisitos.SITUACAO_ATENDIDO)

    def test_detecta_por_calculo_da_agenda(self):
        agenda = {
            "parametros": {"data_inicio": "2026-09-14", "data_fim": "2027-02-12"},
            "total_letivos": 100,
            "sabados_total": 11,
            "feriados": [{"data": "2026-10-12"}],
        }
        itens = self._itens("integrado_medio", [], agenda=agenda)
        for codigo in ("VIII", "XI", "XII", "XIV"):
            self.assertEqual(
                itens[codigo]["situacao"], requisitos.SITUACAO_ATENDIDO, codigo
            )
        # Dias letivos por mês não declarados → conferir
        self.assertEqual(itens["XVII"]["situacao"], requisitos.SITUACAO_CONFERIR)

    def test_dias_por_mes_declarado_e_atendido(self):
        agenda = {
            "parametros": {"data_inicio": "2026-09-14", "data_fim": "2027-02-12"},
            "total_letivos": 100,
            "sabados_total": 11,
            "feriados": [],
        }
        itens = self._itens(
            "integrado_medio", [], agenda=agenda,
            dias_letivos_por_mes=[{"mes": "SET/2026", "letivos": 13}],
        )
        self.assertEqual(itens["XVII"]["situacao"], requisitos.SITUACAO_ATENDIDO)

    def test_item_manual_fica_como_conferir(self):
        itens = self._itens("integrado_medio", [])
        self.assertEqual(itens["XXI"]["situacao"], requisitos.SITUACAO_CONFERIR)
        self.assertIn("manualmente", itens["XXI"]["motivo"])

    def test_sem_agenda_os_itens_calculados_nao_afirmam_atendido(self):
        resultado = requisitos.verificar_requisitos("integrado_medio", eventos=[])
        itens = {i["codigo"]: i for i in resultado["itens"]}
        self.assertNotEqual(itens["XI"]["situacao"], requisitos.SITUACAO_ATENDIDO)
        self.assertTrue(resultado["avisos"])

    def test_ia_nao_rebaixa_evidencia_local(self):
        eventos = [
            {"titulo": "Recuperação paralela", "tipo": "recuperacao",
             "data_inicio": "2026-11-23"}
        ]
        extras = {"VII": {"situacao": "faltando", "motivo": "a IA não encontrou"}}
        itens = {
            i["codigo"]: i
            for i in requisitos.verificar_requisitos(
                "integrado_medio", eventos=eventos, extras=extras
            )["itens"]
        }
        self.assertEqual(itens["VII"]["situacao"], requisitos.SITUACAO_ATENDIDO)
        self.assertEqual(itens["VII"]["evidencias"], ["23/11 — Recuperação paralela"])

    def test_ia_sem_prova_local_vira_conferir(self):
        extras = {"IV": {"situacao": "atendido", "motivo": "consta na ata"}}
        itens = {
            i["codigo"]: i
            for i in requisitos.verificar_requisitos(
                "integrado_medio", eventos=[], extras=extras
            )["itens"]
        }
        self.assertEqual(itens["IV"]["situacao"], requisitos.SITUACAO_CONFERIR)
        self.assertEqual(itens["IV"]["motivo"], "consta na ata")

    def test_sugestao_da_ia_nao_entra_em_item_atendido(self):
        eventos = [
            {"titulo": "Recuperação paralela", "tipo": "recuperacao",
             "data_inicio": "2026-11-23"}
        ]
        extras = {
            "VII": {
                "situacao": "faltando",
                "evento_sugerido": {"titulo": "Recuperação", "data_inicio": "2026-11-24"},
            }
        }
        itens = {
            i["codigo"]: i
            for i in requisitos.verificar_requisitos(
                "integrado_medio", eventos=eventos, extras=extras
            )["itens"]
        }
        self.assertEqual(itens["VII"]["situacao"], requisitos.SITUACAO_ATENDIDO)
        self.assertIsNone(itens["VII"]["evento_sugerido"])

    def test_calendario_oficial_2026_2_atende_o_art_38(self):
        call_command("seed_calendario_2026_2")
        cal = Calendario.objects.get(versao="2026.2.final")
        resultado = requisitos.verificar_requisitos(
            cal.modalidade,
            eventos=cal.eventos.all(),
            feriados=cal.feriados.all(),
            agenda=cal.agenda(),
            dias_letivos_por_mes=cal.dias_letivos_por_mes,
        )
        self.assertEqual(resultado["norma"], "Art. 38")
        self.assertEqual(resultado["resumo"]["total"], 22)
        self.assertGreaterEqual(resultado["resumo"]["atendidos"], 15)
        itens = {i["codigo"]: i for i in resultado["itens"]}
        for codigo in ("V", "VII", "XI", "XII", "XIV", "XV", "XX"):
            self.assertEqual(
                itens[codigo]["situacao"], requisitos.SITUACAO_ATENDIDO, codigo
            )


# ===========================================================================
# LLM: configuração, leitura da resposta e carga horária
# ===========================================================================

PROVEDOR_FAKE = {
    "deepseek": {
        "label": "DeepSeek",
        "dialeto": "openai",
        "url": "https://exemplo.invalido/chat",
        "model": "deepseek-chat",
        "api_key": "chave-fake",
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "dialeto": "anthropic",
        "url": "https://exemplo.invalido/messages",
        "model": "claude-sonnet-4-5",
        "api_key": "",
    },
}


class LlmConfigTests(TestCase):
    """Apelidos de provedor e disponibilidade conforme as chaves."""

    def test_resolve_apelidos(self):
        self.assertEqual(llm.resolver_provedor("chatgpt"), "openai")
        self.assertEqual(llm.resolver_provedor("claude"), "anthropic")
        self.assertEqual(llm.resolver_provedor("claudecode"), "anthropic")
        self.assertEqual(llm.resolver_provedor("google"), "gemini")
        self.assertEqual(llm.resolver_provedor("DeepSeek"), "deepseek")

    @override_settings(LLM_PROVIDERS=PROVEDOR_FAKE)
    def test_provedores_disponiveis_so_com_chave(self):
        itens = {p["valor"]: p for p in llm.provedores_disponiveis()}
        self.assertTrue(itens["deepseek"]["disponivel"])
        self.assertFalse(itens["anthropic"]["disponivel"])
        self.assertEqual(itens["deepseek"]["modelo"], "deepseek-chat")

    @override_settings(LLM_PROVIDERS=PROVEDOR_FAKE)
    def test_tem_provedor_configurado(self):
        self.assertTrue(llm.tem_provedor_configurado())

    @override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=False)
    def test_desativado_por_flag(self):
        self.assertFalse(llm.tem_provedor_configurado())
        with self.assertRaises(llm.LlmConfigError):
            llm.gerar_eventos({"data_inicio": "2026-09-14", "data_fim": "2027-02-12"})

    def test_provedor_desconhecido(self):
        with self.assertRaises(llm.LlmConfigError):
            llm.config_provedor("inexistente")

    @override_settings(LLM_PROVIDERS=PROVEDOR_FAKE)
    def test_config_provedor_resolve_apelido(self):
        cfg = llm.config_provedor("claude")
        self.assertEqual(cfg["chave"], "anthropic")
        self.assertEqual(cfg["dialeto"], "anthropic")

    @override_settings(LLM_PROVIDERS=PROVEDOR_FAKE)
    def test_config_provedor_usa_padrao_quando_vazio(self):
        cfg = llm.config_provedor("")
        self.assertIn(cfg["chave"], PROVEDOR_FAKE)

    def test_sem_chave_nenhuma_avisa(self):
        somente_sem_chave = {
            "deepseek": {
                "label": "DeepSeek",
                "dialeto": "openai",
                "url": "https://exemplo.invalido",
                "model": "deepseek-chat",
                "api_key": "",
            }
        }
        with override_settings(LLM_PROVIDERS=somente_sem_chave):
            with self.assertRaises(llm.LlmConfigError) as ctx:
                llm.gerar_eventos({"data_inicio": "2026-09-14", "data_fim": "2027-02-12"})
            self.assertIn("chave", str(ctx.exception).lower())


class LlmLeituraRespostaTests(TestCase):
    """Leitura tolerante e normalização da resposta da IA."""

    def test_parse_json_puro(self):
        self.assertEqual(llm.parse_resposta('{"eventos": []}'), {"eventos": []})

    def test_parse_com_cerca_e_texto_em_volta(self):
        texto = 'Claro! ```json\n{"eventos": [{"titulo": "X"}]}\n``` Fim.'
        self.assertEqual(llm.parse_resposta(texto)["eventos"][0]["titulo"], "X")

    def test_parse_invalido(self):
        with self.assertRaises(llm.LlmProviderError):
            llm.parse_resposta("nada de json aqui")

    def test_normalizar_tipo_com_apelidos(self):
        self.assertEqual(llm.normalizar_tipo("Recuperação"), "recuperacao")
        self.assertEqual(llm.normalizar_tipo("Sábado letivo"), "sabado_letivo")
        self.assertEqual(llm.normalizar_tipo("feriado_municipal"), "feriado")
        self.assertEqual(llm.normalizar_tipo("qualquer"), "evento")

    def test_normalizar_dia_semana(self):
        self.assertEqual(llm.normalizar_dia_semana("quarta"), 2)
        self.assertEqual(llm.normalizar_dia_semana("2"), 2)
        self.assertEqual(llm.normalizar_dia_semana(4), 4)
        self.assertIsNone(llm.normalizar_dia_semana(9))
        self.assertIsNone(llm.normalizar_dia_semana(None))
        self.assertIsNone(llm.normalizar_dia_semana(True))

    def test_normalizar_origem_do_feriado(self):
        self.assertEqual(llm.normalizar_feriado_origem(None, "municipal"), "municipal")
        self.assertEqual(llm.normalizar_feriado_origem(None, "estadual"), "estadual")
        self.assertEqual(llm.normalizar_feriado_origem(None, "outra"), "institucional")

    def test_validar_normalizar_mantem_evento_antes_do_inicio(self):
        inicio, fim = dt.date(2026, 9, 14), dt.date(2027, 2, 12)
        dados = {
            "eventos": [
                {"titulo": "Matrículas", "tipo": "matricula", "data_inicio": "2026-08-10",
                 "data_fim": "2026-08-14"},
                {"titulo": "Fora da janela", "tipo": "evento", "data_inicio": "2020-01-10"},
                {"titulo": "Sem data", "tipo": "evento"},
            ],
            "feriados": [
                {"data": "2026-09-07", "esfera": "federal", "descricao": "Independência"}
            ],
        }
        resultado = llm.validar_normalizar(dados, inicio, fim)
        titulos = [e["titulo"] for e in resultado["eventos"]]
        self.assertIn("Matrículas", titulos)
        self.assertNotIn("Fora da janela", titulos)
        self.assertEqual(resultado["feriados"][0]["data"], "2026-09-07")
        self.assertEqual(resultado["feriados"][0]["origem"], "federal")
        self.assertTrue(resultado["avisos"])

    def test_validar_normalizar_deduplica(self):
        inicio, fim = dt.date(2026, 9, 14), dt.date(2027, 2, 12)
        dados = {
            "eventos": [
                {"titulo": "Avaliação", "tipo": "avaliacao", "data_inicio": "2026-11-04"},
                {"titulo": "avaliação", "tipo": "avaliacao", "data_inicio": "2026-11-04"},
            ],
            "feriados": [
                {"data": "2026-10-12", "descricao": "A"},
                {"data": "2026-10-12", "descricao": ""},
            ],
        }
        resultado = llm.validar_normalizar(dados, inicio, fim)
        self.assertEqual(len(resultado["eventos"]), 1)
        self.assertEqual(len(resultado["feriados"]), 1)

    def test_mesclar_feriados_nacionais_inclui_federal(self):
        feriados = llm.mesclar_feriados_nacionais(
            [], dt.date(2026, 9, 14), dt.date(2027, 2, 12)
        )
        datas = {f["data"] for f in feriados}
        self.assertIn("2026-09-07", datas)  # véspera do início (margem)
        self.assertIn("2026-10-12", datas)
        self.assertTrue(all(f["origem"] == "nacional" for f in feriados))


class CompletarSabadosTests(TestCase):
    """Distribuição determinística dos sábados para fechar a carga horária."""

    INICIO = dt.date(2026, 9, 14)
    FIM = dt.date(2027, 2, 12)

    def _agenda(self, eventos, feriados=(), previsto=100):
        return build_agenda(
            data_inicio=self.INICIO,
            data_fim=self.FIM,
            feriados=list(feriados),
            eventos=list(eventos),
            dias_letivos_previstos=previsto,
        )

    def test_fecha_a_meta_de_cada_dia_da_semana(self):
        # meta = ceil(120/5) = 24 por dia: o semestre sozinho não alcança, então
        # os sábados precisam ser distribuídos.
        resultado = llm.completar_sabados([], [], self.INICIO, self.FIM, 120)
        self.assertGreater(resultado["criados"], 0)
        self.assertEqual(resultado["faltando"], [0, 0, 0, 0, 0])
        self.assertEqual(resultado["avisos"], [])
        agenda = self._agenda(resultado["eventos"], previsto=120)
        self.assertEqual(agenda["meta_por_dia"], 24)
        for dia in agenda["dias_por_dia"]:
            self.assertGreaterEqual(dia["letivos"], dia["meta"], dia["label"])

    def test_sabados_tem_referencia_valida_e_nao_repetem_data(self):
        resultado = llm.completar_sabados([], [], self.INICIO, self.FIM, 120)
        sabados = [e for e in resultado["eventos"] if e["tipo"] == "sabado_letivo"]
        self.assertTrue(sabados)
        for s in sabados:
            self.assertIsNotNone(s["dia_semana_referencia"])
            self.assertTrue(0 <= s["dia_semana_referencia"] <= 4)
            self.assertEqual(dt.date.fromisoformat(s["data_inicio"]).weekday(), 5)
        datas = [s["data_inicio"] for s in sabados]
        self.assertEqual(len(datas), len(set(datas)))

    def test_nao_usa_sabado_ja_lancado_nem_feriado(self):
        eventos = [
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-19", "dia_semana_referencia": 0}
        ]
        feriados = [{"data": "2026-09-26", "tipo": "feriado", "descricao": "Municipal"}]
        resultado = llm.completar_sabados(eventos, feriados, self.INICIO, self.FIM, 120)
        datas = [
            e["data_inicio"]
            for e in resultado["eventos"]
            if e["tipo"] == "sabado_letivo"
        ]
        self.assertIn("2026-09-19", datas)
        self.assertNotIn("2026-09-26", datas)
        self.assertEqual(len(datas), len(set(datas)))

    def test_sem_previsto_nao_cria_sabados(self):
        resultado = llm.completar_sabados([], [], self.INICIO, self.FIM, 0)
        self.assertEqual(resultado["criados"], 0)
        self.assertEqual(resultado["eventos"], [])
        self.assertEqual(resultado["avisos"], [])

    def test_avisa_quando_faltam_sabados(self):
        inicio = dt.date(2026, 9, 14)
        fim = dt.date(2026, 10, 9)  # janela curta
        resultado = llm.completar_sabados([], [], inicio, fim, 100)
        self.assertGreater(sum(resultado["faltando"]), 0)
        self.assertTrue(resultado["avisos"])
        self.assertIn("sábados", resultado["avisos"][0])


# ===========================================================================
# Endpoints da IA (com o provedor simulado — nenhum teste toca a rede)
# ===========================================================================


def resposta_ia_gerar() -> str:
    """Resposta simulada do provedor para o modo *gerar*."""
    return json.dumps(
        {
            "feriados": [
                {"data": "2026-09-24", "tipo": "feriado", "esfera": "municipal",
                 "descricao": "Aniversário de Barras-PI", "confianca": "alta"}
            ],
            "eventos": [
                {"titulo": "Matrículas", "tipo": "matricula", "data_inicio": "2026-08-10",
                 "data_fim": "2026-08-14"},
                {"titulo": "Aulas do PRAEI", "tipo": "evento", "data_inicio": "2026-09-10"},
                {"titulo": "Avaliações do 1º Bimestre", "tipo": "avaliacao",
                 "data_inicio": "2026-11-04", "data_fim": "2026-11-07"},
                {"titulo": "Recuperação paralela", "tipo": "recuperacao",
                 "data_inicio": "2026-11-23"},
                {"titulo": "Conselho de Classe", "tipo": "conselho_classe",
                 "data_inicio": "2026-11-30"},
            ],
        },
        ensure_ascii=False,
    )


def resposta_ia_verificar() -> str:
    """Resposta simulada do provedor para o modo *verificar* (com cerca de código)."""
    dados = {
        "requisitos": [
            {
                "codigo": "IV",
                "situacao": "faltando",
                "motivo": "não há evento de eleição de representantes",
                "evento_sugerido": {
                    "titulo": "Eleição de representantes de turma",
                    "tipo": "evento",
                    "data_inicio": "2026-09-22",
                },
            }
        ],
        "observacoes": ["Conferir o recesso de dezembro."],
    }
    return "```json\n" + json.dumps(dados, ensure_ascii=False) + "\n```"


class IaApiTestsBase(TestCase):
    """Base dos testes de IA: payload padrão e POST JSON."""

    def _post(self, url_name, payload):
        return self.client.post(
            reverse(url_name), data=json.dumps(payload), content_type="application/json"
        )

    def _payload(self, **extra):
        base = {
            "cidade": "Barras",
            "estado": "PI",
            "pais": "Brasil",
            "instituicao": "IFPI — Campus Barras",
            "curso": "Técnico em Administração",
            "modalidade": "integrado_medio",
            "data_inicio": "2026-09-14",
            "data_fim": "2027-02-12",
            "total_semanas": 22,
            "semanas_primeira_parte": 11,
            "dias_letivos_previstos": 100,
            "feriados": [],
            "eventos": [],
            "completar_sabados": True,
            "provedor": "deepseek",
        }
        base.update(extra)
        return base


@override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True)
class IaEventosApiTests(IaApiTestsBase):
    """``POST /api/ia/eventos/`` — prévia gerada pela IA, sem gravar nada."""

    def test_previa_gera_sem_persistir(self):
        with mock.patch.object(llm, "chamar_provedor", lambda *a, **k: resposta_ia_gerar()):
            resp = self._post("api_ia_eventos", self._payload())
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["provedor"], "deepseek")
        self.assertEqual(dados["modelo"], "deepseek-chat")
        self.assertEqual(dados["requisitos"]["norma"], "Art. 38")
        self.assertTrue(dados["requisitos"]["resumo"]["atendidos"] > 0)
        # sábados letivos distribuídos pelo cálculo (não pela IA)
        self.assertTrue(any(e["tipo"] == "sabado_letivo" for e in dados["eventos"]))
        self.assertIn("dias_por_dia", dados["agenda"])
        # NADA foi gravado
        self.assertEqual(Evento.objects.count(), 0)
        self.assertEqual(Feriado.objects.count(), 0)

    def test_feriado_municipal_com_esfera(self):
        with mock.patch.object(llm, "chamar_provedor", lambda *a, **k: resposta_ia_gerar()):
            resp = self._post("api_ia_eventos", self._payload())
        feriados = resp.json()["feriados"]
        municipal = [f for f in feriados if f["data"] == "2026-09-24"][0]
        self.assertEqual(municipal["origem"], "municipal")
        self.assertEqual(municipal["esfera"], "municipal")
        # federais entram sempre, pelo cálculo local
        self.assertTrue(any(f["origem"] == "nacional" for f in feriados))

    def test_exige_cidade_e_estado(self):
        resp = self._post("api_ia_eventos", self._payload(cidade="", estado=""))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("cidade", resp.json()["erros"][0].lower())

    def test_exige_periodo(self):
        resp = self._post("api_ia_eventos", self._payload(data_fim=""))
        self.assertEqual(resp.status_code, 400)

    def test_provedor_sem_chave(self):
        sem_chave = {
            "deepseek": {
                "label": "DeepSeek",
                "dialeto": "openai",
                "url": "https://exemplo.invalido",
                "model": "deepseek-chat",
                "api_key": "",
            }
        }
        with override_settings(LLM_PROVIDERS=sem_chave):
            resp = self._post("api_ia_eventos", self._payload())
        self.assertEqual(resp.status_code, 400)
        self.assertIn("chave", resp.json()["erros"][0].lower())

    def test_falha_do_provedor_retorna_502(self):
        erro = llm.LlmProviderError("O provedor respondeu HTTP 500.")
        with mock.patch.object(llm, "chamar_provedor", side_effect=erro):
            resp = self._post("api_ia_eventos", self._payload())
        self.assertEqual(resp.status_code, 502)
        self.assertFalse(resp.json()["ok"])

    def test_modalidade_desconhecida_cai_no_padrao(self):
        with mock.patch.object(llm, "chamar_provedor", lambda *a, **k: resposta_ia_gerar()):
            resp = self._post("api_ia_eventos", self._payload(modalidade="inexistente"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["requisitos"]["norma"], "Art. 38")

    def test_get_nao_permitido(self):
        self.assertEqual(self.client.get(reverse("api_ia_eventos")).status_code, 405)


@override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True)
class IaVerificarApiTests(IaApiTestsBase):
    """``POST /api/ia/verificar/`` — auditoria dos eventos lançados."""

    def _resposta(self):
        return mock.patch.object(
            llm, "chamar_provedor", lambda *a, **k: resposta_ia_verificar()
        )

    def test_relatorio_com_sugestao_sem_persistir(self):
        payload = self._payload(
            eventos=[
                {"titulo": "Matrículas", "tipo": "matricula", "data_inicio": "2026-08-10"},
                {"titulo": "Avaliações", "tipo": "avaliacao", "data_inicio": "2026-11-04"},
            ]
        )
        with self._resposta():
            resp = self._post("api_ia_verificar", payload)
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(dados["norma"], "Art. 38")
        itens = {i["codigo"]: i for i in dados["requisitos"]["itens"]}
        self.assertEqual(itens["IV"]["situacao"], "faltando")
        self.assertEqual(
            itens["IV"]["evento_sugerido"]["titulo"], "Eleição de representantes de turma"
        )
        self.assertEqual(itens["IV"]["situacao_label"], "Faltando")
        self.assertEqual(dados["observacoes"], ["Conferir o recesso de dezembro."])
        self.assertEqual(Evento.objects.count(), 0)

    def test_nao_exige_cidade(self):
        with self._resposta():
            resp = self._post(
                "api_ia_verificar",
                {"modalidade": "graduacao", "data_inicio": "2026-09-14",
                 "data_fim": "2027-02-12", "eventos": [], "provedor": "deepseek"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["norma"], "Art. 40")

    def test_exige_periodo(self):
        resp = self._post("api_ia_verificar", {"modalidade": "graduacao"})
        self.assertEqual(resp.status_code, 400)

    def test_falha_do_provedor_retorna_502(self):
        erro = llm.LlmProviderError("timeout")
        with mock.patch.object(llm, "chamar_provedor", side_effect=erro):
            resp = self._post("api_ia_verificar", self._payload())
        self.assertEqual(resp.status_code, 502)


class ContagemDiasLetivosTests(TestCase):
    """Quais tipos contam na carga horária — e só dentro do período declarado."""

    INICIO = dt.date(2026, 9, 14)  # segunda-feira
    FIM = dt.date(2026, 9, 25)     # sexta-feira
    QUARTA = "2026-09-16"
    SABADO = "2026-09-19"

    def _agenda(self, eventos, feriados=(), fim_=None, inicio=None):
        return build_agenda(
            data_inicio=inicio or self.INICIO,
            data_fim=self.FIM if fim_ is None else fim_,
            feriados=list(feriados),
            eventos=list(eventos),
            dias_letivos_previstos=0,
        )

    def _celula(self, agenda, iso):
        for m in agenda["meses"]:
            for s in m["semanas"]:
                for c in s:
                    if not c.get("vazio") and c["date"] == iso:
                        return c
        raise AssertionError(f"célula {iso} não encontrada")

    def _evento(self, tipo, data=None):
        return {"titulo": f"Evento {tipo}", "tipo": tipo, "data_inicio": data or self.QUARTA}

    def test_base_do_periodo(self):
        # 14/09 a 25/09/2026 sem eventos: 10 dias úteis.
        ag = self._agenda([])
        self.assertEqual(ag["total_letivos"], 10)
        self.assertEqual(ag["letivos_seg_sex"], 10)

    def test_tipos_que_contam(self):
        # Num dia útil o dia já é letivo; o que importa é que o evento do tipo que
        # conta mantém o dia contabilizado.
        for tipo in ("letivo", "avaliacao", "recuperacao", "evento"):
            with self.subTest(tipo=tipo):
                ag = self._agenda([self._evento(tipo)])
                self.assertEqual(ag["total_letivos"], 10, tipo)
                self.assertTrue(self._celula(ag, self.QUARTA)["letivo"], tipo)

    def test_conselho_remove_o_dia_letivo(self):
        # Conselho de classe NÃO conta: o dia útil deixa de ser letivo (fica com o
        # status do tipo, em cor e legenda).
        ag = self._agenda([self._evento("conselho_classe")])
        celula = self._celula(ag, self.QUARTA)
        self.assertEqual(celula["status"], "conselho")
        self.assertFalse(celula["letivo"])
        self.assertEqual(ag["total_letivos"], 9)
        self.assertEqual(ag["letivos_seg_sex"], 9)

    def test_jornada_pedagogica_e_neutra(self):
        # Jornada pedagógica é marcador (como administrativo): o dia continua sendo
        # "Dia letivo" e entra na carga horária.
        ag = self._agenda([self._evento("jornada_pedagogica")])
        celula = self._celula(ag, self.QUARTA)
        self.assertEqual(celula["status"], "letivo")
        self.assertTrue(celula["letivo"])
        self.assertEqual(ag["total_letivos"], 10)
        self.assertEqual(ag["letivos_seg_sex"], 10)

    def test_tipos_que_nao_contam(self):
        for tipo in (
            "feriado",
            "ponto_facultativo",
            "recesso",
            "ferias_coletivas",
            "avaliacao_final",
            "conselho_classe",
        ):
            with self.subTest(tipo=tipo):
                ag = self._agenda([self._evento(tipo)])
                self.assertEqual(ag["total_letivos"], 9, tipo)
                self.assertFalse(self._celula(ag, self.QUARTA)["letivo"], tipo)

    def test_marcadores_sao_neutros(self):
        # Matrícula, administrativo e jornada pedagógica são avisos: o dia continua
        # sendo "Dia letivo" e conta.
        for tipo in ("matricula", "administrativo", "jornada_pedagogica"):
            with self.subTest(tipo=tipo):
                ag = self._agenda([self._evento(tipo)])
                self.assertEqual(ag["total_letivos"], 10, tipo)
                celula = self._celula(ag, self.QUARTA)
                self.assertEqual(celula["status"], "letivo", tipo)
                self.assertTrue(celula["letivo"], tipo)

    def test_sabado_letivo_conta_e_reposicao_nao(self):
        letivo = self._agenda([self._evento("sabado_letivo", self.SABADO)])
        self.assertEqual(letivo["total_letivos"], 11)
        self.assertEqual(letivo["sabados_total"], 1)
        self.assertTrue(self._celula(letivo, self.SABADO)["letivo"])

        reposicao = self._agenda([self._evento("sabado_reposicao", self.SABADO)])
        self.assertEqual(reposicao["total_letivos"], 10)
        self.assertEqual(reposicao["sabados_total"], 0)
        self.assertEqual(reposicao["reposicoes_total"], 1)
        self.assertFalse(self._celula(reposicao, self.SABADO)["letivo"])

    def test_tipo_que_conta_depois_do_fim_nao_conta(self):
        # Avaliação em 28/09/2026 (depois do término declarado).
        ag = self._agenda([self._evento("avaliacao", "2026-09-28")])
        self.assertEqual(ag["total_letivos"], 10)
        self.assertEqual(self._celula(ag, "2026-09-28")["status"], "fora")
        self.assertIn("2026-09-28", ag["eventos_fora"])
        self.assertTrue(any("fora do período letivo" in n for n in ag["notas"]))

    def test_tipo_que_conta_antes_do_inicio_nao_conta(self):
        # Avaliação em 10/09/2026 (antes do início declarado).
        ag = self._agenda([self._evento("avaliacao", "2026-09-10")])
        self.assertEqual(ag["total_letivos"], 10)
        self.assertEqual(self._celula(ag, "2026-09-10")["status"], "fora")

    def test_tipo_que_conta_em_sabado_nao_conta(self):
        # Avaliação num sábado dentro do período: aparece no documento, mas o sábado
        # não entra na carga horária (só sábado letivo conta).
        ag = self._agenda([self._evento("avaliacao", self.SABADO)])
        self.assertEqual(ag["total_letivos"], 10)
        celula = self._celula(ag, self.SABADO)
        self.assertEqual(celula["status"], "nao_letivo")
        self.assertFalse(celula["letivo"])

    def test_sem_termino_informado_estima_a_faixa(self):
        ag = self._agenda([self._evento("avaliacao", "2026-09-30")], fim_="")
        self.assertEqual(ag["total_letivos"], 13)  # até 30/09 (quarta)
        self.assertEqual(self._celula(ag, "2026-09-30")["status"], "letivo")
        self.assertTrue(any("estimada" in n for n in ag["notas"]))

    def test_legenda_traz_quem_conta(self):
        ag = self._agenda([self._evento("conselho_classe")])
        conta = {l["status"]: l["conta"] for l in ag["legenda"]}
        self.assertFalse(conta["conselho"])  # conselho não conta
        self.assertTrue(ag["status_conta"]["letivo"])
        self.assertFalse(ag["status_conta"]["reposicao"])
        self.assertIn("avaliacao", ag["tipos_que_contam"])
        self.assertNotIn("conselho_classe", ag["tipos_que_contam"])
        self.assertIn("conselho_classe", ag["tipos_que_removem"])
        self.assertIn("jornada_pedagogica", ag["tipos_neutros"])
        self.assertIn("matricula", ag["tipos_neutros"])


class SabadosLetivosTests(TestCase):
    """Sábado letivo conta; sábado de reposição **não** conta na carga horária."""

    INICIO = dt.date(2026, 9, 14)
    FIM = dt.date(2027, 2, 12)

    def _agenda(self, eventos, feriados=(), previsto=100):
        return build_agenda(
            data_inicio=self.INICIO,
            data_fim=self.FIM,
            feriados=list(feriados),
            eventos=list(eventos),
            dias_letivos_previstos=previsto,
        )

    def _celula(self, agenda, iso):
        for mes in agenda["meses"]:
            for semana in mes["semanas"]:
                for c in semana:
                    if not c.get("vazio") and c["date"] == iso:
                        return c
        raise AssertionError(f"célula {iso} não encontrada")

    def _invariantes(self, agenda):
        """O rodapé da tabela precisa ser, sempre, a soma das colunas."""
        t = agenda["totais_tabela"]
        self.assertEqual(t["seg_sex"], sum(d["seg_sex"] for d in agenda["dias_por_dia"]))
        self.assertEqual(t["sabados"], sum(d["sabados"] for d in agenda["dias_por_dia"]))
        self.assertEqual(t["total"], sum(d["letivos"] for d in agenda["dias_por_dia"]))
        self.assertEqual(
            agenda["sabados_contabilizados"],
            sum(d["sabados"] for d in agenda["dias_por_dia"]),
        )
        self.assertEqual(
            agenda["total_letivos"], agenda["letivos_seg_sex"] + agenda["sabados_total"]
        )
        self.assertEqual(
            t["total"] + agenda["sabados_sem_referencia"], agenda["total_letivos"]
        )

    def test_reposicao_nao_conta_na_carga_horaria(self):
        eventos = [
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-19", "dia_semana_referencia": 0},
            {"titulo": "Sábado de reposição", "tipo": "sabado_reposicao",
             "data_inicio": "2026-09-26", "dia_semana_referencia": 2},
        ]
        com = self._agenda(eventos)
        sem = self._agenda([e for e in eventos if e["tipo"] != "sabado_reposicao"])

        self.assertEqual(com["total_letivos"], sem["total_letivos"])
        self.assertEqual(com["sabados_total"], sem["sabados_total"])
        self.assertEqual(com["letivos_por_dia"], sem["letivos_por_dia"])
        self.assertEqual(com["letivos_seg_sex"], sem["letivos_seg_sex"])
        self._invariantes(com)

        self.assertEqual(com["reposicoes_total"], 1)
        self.assertEqual([r["date"] for r in com["dias_reposicao"]], ["2026-09-26"])
        self.assertFalse(com["dias_reposicao"][0]["conta"])
        celula = self._celula(com, "2026-09-26")
        self.assertEqual(celula["status"], "reposicao")
        self.assertFalse(celula["letivo"])
        self.assertTrue(any("reposição" in n for n in com["notas"]))

    def test_sabado_letivo_sem_referencia_nao_quebra_o_rodape(self):
        eventos = [
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-19", "dia_semana_referencia": 0},
            {"titulo": "Sábado letivo sem referência", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-26", "dia_semana_referencia": None},
        ]
        agenda = self._agenda(eventos)
        self._invariantes(agenda)
        self.assertEqual(agenda["sabados_sem_referencia"], 1)
        self.assertEqual(agenda["sabados_total"], 2)
        self.assertEqual(agenda["totais_tabela"]["sabados"], 1)
        self.assertTrue(
            any("sem dia da semana" in a for a in agenda["validacao"]["avisos"])
        )

    def test_sabado_letivo_em_dia_util_nao_rouba_o_dia(self):
        # 15/09/2026 é uma terça-feira
        com = self._agenda(
            [{"titulo": "Sábado letivo", "tipo": "sabado_letivo",
              "data_inicio": "2026-09-15", "dia_semana_referencia": 2}]
        )
        sem = self._agenda([])
        self.assertEqual(com["total_letivos"], sem["total_letivos"])
        self.assertEqual(com["sabados_total"], 0)
        self.assertEqual(self._celula(com, "2026-09-15")["status"], "letivo")
        self.assertTrue(any("fora do sábado" in a for a in com["validacao"]["avisos"]))

    def test_sabado_letivo_com_intervalo_conta_os_sabados(self):
        # 19/09 a 26/09: dois sábados (os dias úteis do meio são ignorados)
        agenda = self._agenda(
            [{"titulo": "Sábado letivo", "tipo": "sabado_letivo",
              "data_inicio": "2026-09-19", "data_fim": "2026-09-26",
              "dia_semana_referencia": 0}]
        )
        self.assertEqual(agenda["sabados_total"], 2)
        self.assertEqual(agenda["sabados_por_dia"][0], 2)
        self.assertEqual(
            [s["date"] for s in agenda["sabados_letivos"]],
            ["2026-09-19", "2026-09-26"],
        )
        self.assertEqual(self._celula(agenda, "2026-09-22")["status"], "letivo")
        self._invariantes(agenda)
        self.assertTrue(any("intervalo" in a for a in agenda["validacao"]["avisos"]))

    def test_sabado_letivo_que_cai_em_feriado_nao_conta(self):
        agenda = self._agenda(
            [{"titulo": "Sábado letivo", "tipo": "sabado_letivo",
              "data_inicio": "2026-09-19", "dia_semana_referencia": 0}],
            feriados=[
                {"data": "2026-09-19", "tipo": "feriado", "descricao": "Municipal"}
            ],
        )
        self.assertEqual(agenda["sabados_total"], 0)
        self.assertEqual(self._celula(agenda, "2026-09-19")["status"], "feriado")
        self.assertEqual(len(agenda["sabados_letivos"]), 1)
        self.assertFalse(agenda["sabados_letivos"][0]["conta"])
        self._invariantes(agenda)
        self.assertTrue(
            any("caíram em feriado" in a for a in agenda["validacao"]["avisos"])
        )

    def test_calendario_oficial_mantem_as_invariantes(self):
        call_command("seed_calendario_2026_2")
        cal = Calendario.objects.get(versao="2026.2.final")
        agenda = cal.agenda()
        self._invariantes(agenda)
        # Jornada e conselho não contam: o cálculo fecha nos 100 do documento.
        self.assertEqual(agenda["total_letivos"], 100)
        self.assertEqual(agenda["reposicoes_total"], 0)


class AtribuirReferenciasTests(TestCase):
    """Sábado letivo sem Referência recebe o dia de maior déficit automaticamente."""

    def test_atribui_por_deficit(self):
        eventos = [
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-19", "dia_semana_referencia": None},
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-26", "dia_semana_referencia": None},
        ]
        preenchidos = llm._atribuir_referencias_faltantes(
            eventos, [], dt.date(2026, 9, 14), dt.date(2027, 2, 12), 120
        )
        self.assertEqual(preenchidos, 2)
        for e in eventos:
            self.assertIsNotNone(e["dia_semana_referencia"])
            self.assertTrue(0 <= e["dia_semana_referencia"] <= 4)

    def test_nao_mexe_em_sabado_de_reposicao(self):
        eventos = [
            {"titulo": "Sábado de reposição", "tipo": "sabado_reposicao",
             "data_inicio": "2026-09-19", "dia_semana_referencia": None}
        ]
        self.assertEqual(
            llm._atribuir_referencias_faltantes(
                eventos, [], dt.date(2026, 9, 14), dt.date(2027, 2, 12), 100
            ),
            0,
        )
        self.assertIsNone(eventos[0]["dia_semana_referencia"])

    def test_sem_previsto_nao_atribui(self):
        eventos = [
            {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
             "data_inicio": "2026-09-19", "dia_semana_referencia": None}
        ]
        self.assertEqual(
            llm._atribuir_referencias_faltantes(
                eventos, [], dt.date(2026, 9, 14), dt.date(2027, 2, 12), 0
            ),
            0,
        )

    def test_gerar_eventos_atribui_referencia_e_ignora_reposicao(self):
        resposta = {
            "feriados": [],
            "eventos": [
                {"titulo": "Sábado letivo", "tipo": "sabado_letivo",
                 "data_inicio": "2026-09-19", "dia_semana_referencia": None},
                {"titulo": "Sábado de reposição", "tipo": "sabado_reposicao",
                 "data_inicio": "2026-09-26", "dia_semana_referencia": None},
            ],
        }

        def transporte(url, corpo, headers, timeout):
            return {
                "choices": [
                    {"message": {"content": json.dumps(resposta, ensure_ascii=False)}}
                ]
            }

        with override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True):
            resultado = llm.gerar_eventos(
                {
                    "modalidade": "integrado_medio",
                    "data_inicio": "2026-09-14",
                    "data_fim": "2027-02-12",
                    "dias_letivos_previstos": 120,
                    "provedor": "deepseek",
                    "completar_sabados": False,
                },
                transporte=transporte,
            )

        letivos = [e for e in resultado["eventos"] if e["tipo"] == "sabado_letivo"]
        reposicao = [e for e in resultado["eventos"] if e["tipo"] == "sabado_reposicao"]
        self.assertEqual(len(letivos), 1)
        self.assertIsNotNone(letivos[0]["dia_semana_referencia"])
        self.assertEqual(len(reposicao), 1)
        self.assertIsNone(reposicao[0]["dia_semana_referencia"])
        self.assertEqual(resultado["estatisticas"]["referencias_atribuidas"], 1)
        self.assertTrue(
            any("Referência" in a for a in resultado["avisos"])
        )
        agenda = resultado["agenda"]
        self.assertEqual(agenda["reposicoes_total"], 1)
        self.assertEqual(
            agenda["totais_tabela"]["total"],
            sum(d["letivos"] for d in agenda["dias_por_dia"]),
        )


class LlmFeriadosTests(TestCase):
    """Extração da lista colada + veredito determinístico dos feriados."""

    INICIO = dt.date(2027, 3, 1)
    FIM = dt.date(2027, 7, 2)

    def _cadastrados(self):
        return [
            {"data": "2027-03-26", "descricao": "Sexta-feira Santa", "tipo": "feriado",
             "origem": "nacional"},
            {"data": "2027-04-21", "descricao": "Tiradentes", "tipo": "feriado",
             "origem": "nacional"},
            {"data": "2027-05-01", "descricao": "Dia do Trabalho",
             "tipo": "ponto_facultativo", "origem": "nacional"},
            {"data": "2027-06-13", "descricao": "Aniversário do Município de Barras",
             "tipo": "feriado", "origem": "municipal"},
        ]

    def test_normaliza_linhas_da_lista(self):
        dados = {
            "feriados": [
                {"original": "➡️24(sexta-feira)- Aniversário de Barras-PI", "marcador": "➡️",
                 "data": "2027-09-24", "descricao": "Aniversário de Barras-PI",
                 "tipo": "feriado", "esfera": "municipal"},
                {"original": "➡️19( terça-feira)- Dia do Piauí", "data": "2027-10-19",
                 "descricao": "Dia do Piauí", "tipo": "ponto facultativo", "esfera": "estadual"},
                {"original": "duplicado", "data": "2027-09-24", "descricao": "Outro"},
                {"original": "ano errado", "data": "2019-09-24", "descricao": "Antigo"},
            ]
        }
        itens, avisos = llm._ler_itens_feriados(dados, {2027})
        self.assertEqual(len(itens), 2)
        self.assertEqual(itens[0]["data"], "2027-09-24")
        self.assertEqual(itens[0]["origem"], "municipal")
        self.assertEqual(itens[0]["marcador"], "➡️")
        self.assertEqual(itens[1]["tipo"], "ponto_facultativo")
        self.assertEqual(itens[1]["tipo_label"], "Ponto facultativo")
        self.assertEqual(itens[1]["origem"], "estadual")
        self.assertTrue(any("lidas" in a for a in avisos))

    def test_mesmo_feriado_por_nome(self):
        # Nomes diferentes do mesmo feriado casam; nomes que só compartilham uma
        # palavra genérica não casam.
        self.assertTrue(
            llm._mesmo_feriado("Aniversário de Barras-PI", "Aniversário do Município de Barras")
        )
        self.assertTrue(llm._mesmo_feriado("Finados", "Finados"))
        self.assertFalse(llm._mesmo_feriado("Dia do Piauí", "Padroeira do Piauí"))
        self.assertFalse(llm._mesmo_feriado("Dia do Professor", "Dia do Trabalho"))

    def test_veredito_mapeado_faltando_divergente(self):
        atuais = llm._feriados_atuais_normalizados(self._cadastrados())
        por_data = {a["data"]: a for a in atuais}

        def avaliar(data, descricao, tipo="feriado", origem="nacional"):
            return llm._avaliar_item_feriado(
                {"data": data, "descricao": descricao, "tipo": tipo, "origem": origem},
                por_data, atuais, self.INICIO, self.FIM,
            )

        mapeado = avaliar("2027-04-21", "Tiradentes")
        self.assertEqual(mapeado["situacao"], "mapeado")
        self.assertIsNone(mapeado["sugestao"])
        self.assertIn("Tiradentes", mapeado["registro"])

        divergente_tipo = avaliar("2027-05-01", "Dia Mundial do Trabalho")
        self.assertEqual(divergente_tipo["situacao"], "divergente")
        self.assertEqual(divergente_tipo["sugestao"]["acao"], "ajustar_tipo")
        self.assertIn("Ponto facultativo", divergente_tipo["motivo"])

        divergente_data = avaliar("2027-09-24", "Aniversário de Barras-PI", origem="municipal")
        self.assertEqual(divergente_data["situacao"], "divergente")
        self.assertEqual(divergente_data["sugestao"]["acao"], "adicionar")
        self.assertIn("13/06/2027", divergente_data["motivo"])
        self.assertTrue(divergente_data["fora_do_periodo"])

        faltando = avaliar("2027-05-27", "Corpus Christi")
        self.assertEqual(faltando["situacao"], "faltando")
        self.assertEqual(faltando["sugestao"]["acao"], "adicionar")
        self.assertFalse(faltando["fora_do_periodo"])

    def test_prompt_tem_a_lista_o_ano_e_os_cadastrados(self):
        lista = "➡️27(quinta) - Corpus Christi"
        prompt = llm.montar_prompt_feriados(
            {"lista": lista}, self.INICIO, self.FIM, self._cadastrados()
        )
        self.assertIn(lista, prompt)
        self.assertIn("2027", prompt)
        self.assertIn("Sexta-feira Santa", prompt)
        self.assertIn("Ano(s) de referência", prompt)


@override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True)
class IaFeriadosFluxoTests(TestCase):
    """Fluxo completo de ``verificar_feriados`` (provedor simulado)."""

    CADASTRADOS = [
        {"data": "2027-03-26", "descricao": "Sexta-feira Santa", "tipo": "feriado",
         "origem": "nacional"},
        {"data": "2027-05-01", "descricao": "Dia do Trabalho", "tipo": "ponto_facultativo",
         "origem": "nacional"},
        {"data": "2027-06-13", "descricao": "Aniversário do Município de Barras",
         "tipo": "feriado", "origem": "municipal"},
    ]

    EXTRAIDO = {
        "feriados": [
            {"original": "✅março - 26 de março: Paixão de Cristo", "data": "2027-03-26",
             "descricao": "Paixão de Cristo", "tipo": "feriado", "esfera": "federal"},
            {"original": "➡️27(quinta) - Corpus Christi", "marcador": "➡️",
             "data": "2027-05-27", "descricao": "Corpus Christi", "tipo": "feriado"},
            {"original": "➡️24(sexta-feira)- Aniversário de Barras-PI", "marcador": "➡️",
             "data": "2027-09-24", "descricao": "Aniversário de Barras-PI",
             "tipo": "feriado", "esfera": "municipal"},
        ]
    }

    def _transporte(self, url, corpo, headers, timeout):
        return {
            "choices": [
                {"message": {"content": json.dumps(self.EXTRAIDO, ensure_ascii=False)}}
            ]
        }

    def _verificar(self, **extra):
        entrada = {
            "lista": "lista qualquer",
            "provedor": "deepseek",
            "data_inicio": "2027-03-01",
            "data_fim": "2027-07-02",
            "feriados": self.CADASTRADOS,
        }
        entrada.update(extra)
        return llm.verificar_feriados(entrada, transporte=self._transporte)

    def test_fluxo_completo(self):
        resultado = self._verificar()
        situacoes = {i["data"]: i["situacao"] for i in resultado["itens"]}
        self.assertEqual(situacoes["2027-03-26"], "mapeado")
        self.assertEqual(situacoes["2027-05-27"], "faltando")
        self.assertEqual(situacoes["2027-09-24"], "divergente")
        self.assertEqual(resultado["resumo"]["mapeados"], 1)
        self.assertEqual(resultado["resumo"]["faltando"], 1)
        self.assertEqual(resultado["resumo"]["divergentes"], 1)
        self.assertEqual(resultado["resumo"]["fora_do_periodo"], 1)
        self.assertFalse(resultado["resumo"]["ok"])
        extras = {e["data"] for e in resultado["extras_no_calendario"]}
        self.assertIn("2027-05-01", extras)

    def test_exige_lista(self):
        with self.assertRaises(llm.LlmConfigError):
            self._verificar(lista="   ")

    def test_exige_periodo(self):
        with self.assertRaises(llm.LlmConfigError):
            self._verificar(data_inicio="", data_fim="")


@override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True)
class IaFeriadosApiTests(IaApiTestsBase):
    """``POST /api/ia/feriados/`` — confere a lista e **não grava nada**."""

    def test_confere_a_lista_sem_persistir(self):
        resposta = {
            "feriados": [
                {"original": "➡️27(quinta) - Corpus Christi", "data": "2027-05-27",
                 "descricao": "Corpus Christi", "tipo": "feriado"},
                {"original": "➡️15(sexta-feira)- Dia do Professor", "data": "2027-10-15",
                 "descricao": "Dia do Professor", "tipo": "ponto_facultativo"},
            ]
        }
        with mock.patch.object(
            llm, "chamar_provedor", lambda *a, **k: json.dumps(resposta, ensure_ascii=False)
        ):
            resp = self._post(
                "api_ia_feriados",
                self._payload(
                    lista="➡️27(quinta) - Corpus Christi\n➡️15 - Dia do Professor",
                    data_inicio="2027-03-01",
                    data_fim="2027-07-02",
                ),
            )
        self.assertEqual(resp.status_code, 200)
        dados = resp.json()
        self.assertTrue(dados["ok"])
        self.assertEqual(len(dados["itens"]), 2)
        self.assertEqual(dados["resumo"]["faltando"], 2)
        self.assertEqual(dados["resumo"]["fora_do_periodo"], 1)
        self.assertEqual(dados["anos"], [2027])
        # Nada foi gravado
        self.assertEqual(Feriado.objects.count(), 0)
        self.assertEqual(Evento.objects.count(), 0)

    def test_divergente_quando_o_tipo_difere(self):
        resposta = {
            "feriados": [{"data": "2027-05-01", "descricao": "Dia do Trabalho",
                          "tipo": "feriado"}]
        }
        with mock.patch.object(
            llm, "chamar_provedor", lambda *a, **k: json.dumps(resposta)
        ):
            resp = self._post(
                "api_ia_feriados",
                self._payload(
                    lista="01/05 - Dia do Trabalho",
                    data_inicio="2027-03-01",
                    data_fim="2027-07-02",
                    feriados=[
                        {"data": "2027-05-01", "descricao": "Dia do Trabalho",
                         "tipo": "ponto_facultativo", "origem": "nacional"}
                    ],
                ),
            )
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["itens"][0]
        self.assertEqual(item["situacao"], "divergente")
        self.assertEqual(item["sugestao"]["acao"], "ajustar_tipo")

    def test_exige_lista(self):
        resp = self._post("api_ia_feriados", self._payload(lista="  "))
        self.assertEqual(resp.status_code, 400)
        self.assertIn("lista", resp.json()["erros"][0].lower())

    def test_exige_periodo(self):
        resp = self._post("api_ia_feriados", self._payload(lista="x", data_fim=""))
        self.assertEqual(resp.status_code, 400)

    def test_falha_do_provedor_retorna_502(self):
        with mock.patch.object(
            llm, "chamar_provedor", side_effect=llm.LlmProviderError("timeout")
        ):
            resp = self._post("api_ia_feriados", self._payload(lista="x"))
        self.assertEqual(resp.status_code, 502)


@override_settings(LLM_PROVIDERS=PROVEDOR_FAKE, LLM_ENABLED=True)
class IaEditorTests(TestCase):
    """O editor expõe o preenchimento/verificação por IA sem vazar chaves."""

    def test_editor_tem_os_botoes_e_o_modal(self):
        resp = self.client.get(reverse("editor"))
        self.assertEqual(resp.status_code, 200)
        for marcador in (
            'id="btnIA"',
            'id="btnIAVerificar"',
            'id="iaModal"',
            'id="iaRequisitos"',
            'id="iaAplicarSelecionados"',
            "Preencher com IA",
            "Verificar com IA",
        ):
            self.assertContains(resp, marcador)

    def test_editor_nao_vaza_chave_de_api(self):
        resp = self.client.get(reverse("editor"))
        self.assertNotContains(resp, "chave-fake")
        self.assertNotContains(resp, "DEEPSEEK_API_KEY")

    def test_editor_traz_as_normas_das_modalidades(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "Art. 38")
        self.assertContains(resp, "integrado_medio")
        self.assertContains(resp, "concomitante_subsequente")
        self.assertContains(resp, "graduacao")

    def test_editor_mostra_modalidades_atuais(self):
        resp = self.client.get(reverse("editor"))
        self.assertContains(resp, "Cursos técnicos integrados ao nível médio")
        self.assertContains(resp, "Cursos técnicos concomitantes/subsequentes")
        self.assertContains(resp, "Graduação")

    def test_editor_sem_provedor_marca_desabilitado(self):
        sem_chave = {
            "deepseek": {
                "label": "DeepSeek",
                "dialeto": "openai",
                "url": "https://exemplo.invalido",
                "model": "deepseek-chat",
                "api_key": "",
            }
        }
        with override_settings(LLM_PROVIDERS=sem_chave):
            resp = self.client.get(reverse("editor"))
        self.assertContains(resp, '"habilitado": false')







