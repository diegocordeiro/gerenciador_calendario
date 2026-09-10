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
│   ├── scheduling.py            # Port fiel do algoritmo (cálculo da grade x1/x2)
│   ├── agenda.py                # Documento oficial: grade mensal, eventos, dias letivos
│   ├── models.py                # Calendario (versão/etapa) + Feriado + Evento
│   ├── static_site.py           # Gerador do site estático (build/)
│   ├── views.py                 # Home, /editor/, /versoes/, API (/api/…)
│   ├── admin.py                 # Admin editável (o banco é a fonte da verdade)
│   ├── data/feriados.py         # Feriados nacionais (BR) por ano
│   ├── management/commands/     # seed_feriados, seed_exemplo, seed_calendario_2026_2, render_static_site
│   ├── templates/calendario/    # base, home, editor, versões, detalhe + parciais do documento
│   └── tests.py
├── config/                      # Settings/urls do projeto Django
├── static/                      # CSS/JS/imagens (mesmo visual dos horários)
├── build/                       # HTML VERSIONADO por etapa + versão final (publicado)
├── .github/workflows/deploy.yml # Publica build/ no GitHub Pages
├── Makefile
├── manage.py
└── requirements.txt
```

## Documento oficial (estrutura do PDF)

Além da grade x1/x2, o sistema monta a página no **formato do calendário oficial
publicado pelo campus** (`CALENDÁRIO ACADÊMICO 2026.2 — Técnico em Administração
Integrado PROEJA`), com:

- **Cabeçalho** com instituição, curso, modalidade, semestre, início, término e o
  total de dias letivos (calculado × previsto);
- **Grade mensal** de AGO/2026 a FEV/2027 (domingo primeiro) com o **status de
  cada dia**: dia letivo, sábado letivo, feriado, ponto facultativo, recesso,
  férias coletivas, jornada pedagógica, avaliação final, conselho de classe e
  não letivo;
- **Quantidade de dias letivos por mês** (calculado × declarado no documento) e
  o **total**, usado para conferir a meta (ex.: 100 dias);
- **Tabela de eventos** (`MÊS · DIA · EVENTO`): matrículas, jornada pedagógica,
  PSAD, avaliações (1º/2º bimestre e 2ª chamada), recuperação paralela, fim de
  bimestre/entrega de notas no SUAP, conselho de classe, recessos, semanas
  temáticas e eventos institucionais;
- **Sábados letivos** com o **dia da semana referenciado** (ex.: “referente à
  quarta-feira”);
- **Feriados e pontos facultativos** e a **legenda** das categorias.

### Regra de dia letivo

- **segunda a sexta**, dentro do período, é *letivo* — exceto feriado, ponto
  facultativo, recesso, férias coletivas, jornada pedagógica, conselho de classe
  e avaliação final;
- **sábado** só é letivo quando há evento *sábado letivo* / *sábado de reposição*;
- **domingo** nunca é letivo.

> O código-fonte da regra e dos cálculos está em `calendario/agenda.py`
> (`build_agenda`) e é coberto por testes.

### Recriar o calendário 2026.2 do documento

```bash
python manage.py seed_calendario_2026_2   # ou: make oficial
```

O comando é idempotente e cria a versão `2026.2.final` com 12 feriados/pontos
facultativos, 37 eventos e 11 sábados letivos — resultando em **100 dias
letivos** (13/14 conferem com o documento; mês a mês, o documento distribui 21
dias em NOV e 17 em DEZ, enquanto o cálculo por regra resulta 21 e 16 — a
divergência é exibida na página como conferência).

## Recursos

- **Documento oficial** (vide acima): grade mensal, eventos, sábados letivos,
  dias letivos por mês, feriados/pontos facultativos e legenda;
- **Grade do semestre** com semanas (`x1`/`x2`), dias úteis, feriados e
  **reposição** (redistribuição) das aulas perdidas — com cores por paridade;
- **Métricas** de erro (paridade / dia da semana / parte do semestre) e validação
  em tempo real, com explicação na página de como lê-las (quanto menor, melhor —
  `0 / 0 / 0` é o ideal);
- **Feriados nacionais brasileiros** calculados por ano (inclui móveis: Carnaval,
  Sexta-feira Santa e Corpus Christi), feriados/pontos facultativos
  institucionais e manuais;
- **Eventos acadêmicos** com intervalo de datas, tipo (categoria da legenda) e
  dia da semana referenciado (sábados letivos/de reposição);
- **Versionamento de cada etapa** (`2026.1.etapa1`, `2026.1.etapa2`, …) e uma
  **versão final publicável**;
- **Interface no mesmo padrão visual** do painel de horários (tema claro/escuro,
  cabeçalho, banner de versão, cards);
- **Editor organizado em etapas** — todo o preenchimento (parâmetros, feriados e
  eventos) vem primeiro, com **texto de ajuda em cada campo**, e as prévias ficam
  no fim; ao passar o mouse sobre um dia, um tooltip mostra data, status e eventos;
- **Navegação no editor** — botões para **ocultar o preenchimento** ou as
  **prévias** (a escolha é lembrada no navegador) e **legenda de cores** na prévia
  da grade (paridade x1/x2, feriado sem aula, 1ª parte, dia com evento e aula
  remanejada);
- **Exportação para PDF** pela impressão do navegador (A4 paisagem).

## Pré-requisitos

- **Python 3.13+** (versão usada no CI);
- **Django 5.2.13** (`requirements.txt`).

## Desenvolvimento local

```bash
make configurar        # cria .venv e instala as dependências
make banco             # migrate
make exemplo           # (opcional) cria calendários de exemplo 2026.1
make oficial           # (opcional) cria o calendário oficial 2026.2 do documento
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

| Comando                    | Descrição                                              | Argumentos                          |
| -------------------------- | ------------------------------------------------------ | ----------------------------------- |
| `seed_feriados`            | Adiciona feriados **nacionais** aos calendários        | `--versao`, `--ano`                 |
| `seed_exemplo`             | Cria calendários de exemplo (etapas + final)           | —                                   |
| `seed_calendario_2026_2`   | Recria o **calendário oficial 2026.2** do documento    | —                                   |
| `render_static_site`       | Gera o site estático em `build/`                       | `--output`, `--base-url`            |

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
- **Excluir versões** — em `/versoes/` (coluna *Ações*) e na lista **Etapas salvas**
  do `/editor/` há o botão **Excluir** para cada versão, com confirmação. É um **POST
  de formulário** para `/versoes/excluir/` (funciona sem JavaScript) que remove a
  versão do banco — e os feriados dela, em cascata — e volta para a listagem com uma
  mensagem de retorno. A ação é **permanente** e **não** aparece no site estático (o
  Pages não tem banco). A API `POST /api/excluir/` segue disponível para integrações.

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
>
> Após **excluir** uma versão, rode `make gerar` (ou `make publicar`) para o `build/`
> deixar de conter o HTML da versão removida — o gerador recria a pasta do zero.

## Testes

```bash
python manage.py test
```

A suíte cobre o **algoritmo** (semana/feriados/remanejamento/validação), a
**agenda do documento** (status por dia, dias letivos por mês, sábados letivos e
validação de 100 dias), os **feriados nacionais** (Páscoa e feriados móveis), a
**API** (preview/salvar/eventos), o **seed 2026.2**, as **views** e o **build
estático versionado**.

## Observações

- O `db.sqlite3` é **local** (ignorado pelo git): é a sua fonte de trabalho no
  editor/admin. O que se compartilha é o **`build/`**.
- Para reproduzir o ambiente do zero, `make exemplo` recria os calendários de
  demonstração de 2026.1 e `make oficial` recria o calendário oficial 2026.2 do
  documento (Administração Integrado PROEJA).
- O link **Editor** aparece apenas no `runserver`; ele **não** é publicado no
  site estático.

