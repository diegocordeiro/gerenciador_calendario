# Calendário Acadêmico — IFPI Campus Barras

Sistema em **Python + Django** para **montar, versionar e publicar** o calendário
acadêmico do campus. Reaproveita a metodologia de publicação do projeto de
horários (`barras_horarios`): interface de montagem → banco de dados → **build
estático** → **GitHub Pages**.

A lógica de cálculo é um **port fiel** do app original
[`academic-callendar-scheduler`](https://github.com/rsusik/academic-callendar-scheduler)
(Quasar/Vue), reimplementado em Python (`calendario/scheduling.py`). A partir da
data de início do semestre, do total de semanas e das semanas da 1ª parte, o
sistema distribui os dias letivos e **reposiciona os feriados** nas semanas de
reposição.

## Como funciona

```
Editor (/editor/) → banco (db.sqlite3) → render_static_site → build/ → GitHub Pages
```

1. **Montagem na interface** — em `/editor/` você define os parâmetros, marca os
   feriados clicando na grade e salva cada **etapa**. O cálculo é feito no
   servidor (`POST /api/preview/`), então o Python é a **fonte única de verdade**.
2. **Banco é a fonte da verdade** — cada etapa salva vira um registro
   (`Calendario` + `Feriado`) no `db.sqlite3` (local, fora do git).
3. **Build estático** — `render_static_site` gera `build/` com um HTML **por
   etapa** (`versoes/<slug>/`) e a **versão final** (`calendario/`).
4. **Publicação** — a pasta `build/` é **commitada** e o workflow do GitHub
   Actions apenas a publica no **GitHub Pages**.

> Diferente do painel de horários (onde o banco é recriado a partir de CSVs), aqui
> **o banco é a fonte da verdade** e **o que é versionado no git é o `build/`
> renderizado**. Assim cada etapa fica registrada no histórico de commits da
> pasta `build/`.

## Estrutura

```
calendario_academico/
├── calendario/                  # Aplicação Django
│   ├── scheduling.py            # Port fiel do algoritmo (cálculo da grade)
│   ├── models.py                # Calendario (versão/etapa) + Feriado
│   ├── static_site.py           # Gerador do site estático (build/)
│   ├── views.py                 # Home, /editor/, /versoes/, API (/api/…)
│   ├── admin.py                 # Admin editável (o banco é a fonte da verdade)
│   ├── data/feriados.py         # Feriados nacionais (BR) por ano
│   ├── management/commands/     # seed_feriados, seed_exemplo, render_static_site
│   ├── templates/calendario/    # base, home, editor, versões, detalhe, grade
│   └── tests.py
├── config/                      # Settings/urls do projeto Django
├── static/                      # CSS/JS/imagens (mesmo visual dos horários)
├── build/                       # HTML VERSIONADO por etapa + versão final (publicado)
├── .github/workflows/deploy.yml # Publica build/ no GitHub Pages
├── Makefile
├── manage.py
└── requirements.txt
```

## Recursos

- **Grade do semestre** com semanas (`x1`/`x2`), dias úteis, feriados e
  **reposição** (redistribuição) das aulas perdidas — com cores por paridade;
- **Métricas** de erro (paridade / dia da semana / parte do semestre) e validação
  em tempo real;
- **Feriados nacionais brasileiros** calculados por ano (inclui móveis: Carnaval,
  Sexta-feira Santa e Corpus Christi) e feriados manuais/institucionais;
- **Versionamento de cada etapa** (`2026.1.etapa1`, `2026.1.etapa2`, …) e uma
  **versão final publicável**;
- **Interface no mesmo padrão visual** do painel de horários (tema claro/escuro,
  cabeçalho, banner de versão, cards);
- **Exportação para PDF** pela impressão do navegador (A4 paisagem).

## Pré-requisitos

- **Python 3.13+** (versão usada no CI);
- **Django 5.2.13** (`requirements.txt`).

## Desenvolvimento local

```bash
make configurar        # cria .venv e instala as dependências
make banco             # migrate
make exemplo           # (opcional) cria calendários de exemplo 2026.1
make rodar             # runserver → monte em http://127.0.0.1:8000/editor/
make gerar             # gera build/ com BASE_URL=/ (prévia local)
make ver               # prévia local do build/ em http://127.0.0.1:8000
make publicar          # gera build/ com PAGES_BASE e commita a pasta
```

Ou, manualmente:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## Comandos de gestão

| Comando              | Descrição                                              | Argumentos                          |
| -------------------- | ------------------------------------------------------ | ----------------------------------- |
| `seed_feriados`      | Adiciona feriados **nacionais** aos calendários        | `--versao`, `--ano`                 |
| `seed_exemplo`       | Cria calendários de exemplo (etapas + final)           | —                                   |
| `render_static_site` | Gera o site estático em `build/`                       | `--output`, `--base-url`            |

### Importar os feriados nacionais

```bash
python manage.py seed_feriados                 # todos os calendários existentes
python manage.py seed_feriados --versao 2026.1.final
```

## Versionamento de etapas e versão final

- Cada salvamento no editor grava/atualiza uma **etapa** (`Calendario.etapa`,
  `status`). Salvar com **“Marcar como versão final”** deixa aquela versão como
  **final/atual** (exclusiva) — é a página publicada em `calendario/`.
- O `build/` guarda **todas as etapas** em `versoes/<slug>/`, então a evolução da
  produção fica versionada no git e navegável em `/versoes/`.

## Publicação (GitHub Pages)

1. Ajuste a base do Pages no `Makefile` (`PAGES_BASE`) conforme o nome do
   repositório (project pages → `/nome-do-repo/`).
2. Gere e commite o build:

   ```bash
   make publicar     # render_static_site --base-url $(PAGES_BASE) + git add build/
   ```

3. Envie para o repositório (`git push`). O workflow
   `.github/workflows/deploy.yml` publica a pasta `build/` no GitHub Pages.
   Habilite em **Settings → Pages → Build and deployment → Source: GitHub Actions**.

> Como o `build/` é commitado com caminhos absolutos, se o nome do repositório
> mudar rode `make publicar PAGES_BASE=/novo-nome/` para regerar com a base certa.

## Testes

```bash
python manage.py test
```

A suíte cobre o **algoritmo** (semana/feriados/remanejamento/validação), os
**feriados nacionais** (Páscoa e feriados móveis), a **API** (preview/salvar),
as **views** e o **build estático versionado**.

## Observações

- O `db.sqlite3` é **local** (ignorado pelo git): é a sua fonte de trabalho no
  editor/admin. O que se compartilha é o **`build/`**.
- Para reproduzir o ambiente do zero, `make exemplo` recria os calendários de
  demonstração de 2026.1.
- O link **Editor** aparece apenas no `runserver`; ele **não** é publicado no
  site estático.

