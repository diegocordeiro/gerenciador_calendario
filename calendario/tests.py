import datetime as dt
import json
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .data.feriados import feriados_nacionais, pascoa
from .models import Calendario, Feriado
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

    def test_calendario_atual(self):
        resp = self.client.get(reverse("calendario_atual"))
        self.assertContains(resp, "cal-table")
        self.assertContains(resp, "data-print-pdf")

    def test_versao_por_slug(self):
        resp = self.client.get(reverse("calendario_versao", kwargs={"slug": self.cal.slug}))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.cal.versao)


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


