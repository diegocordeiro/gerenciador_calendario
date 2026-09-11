# Calendário Acadêmico — IFPI Campus Barras

Sistema em **Python + Django** para **montar, versionar e publicar** o calendário
acadêmico.

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
   versão** (`versoes/<slug>/`) e o **índice** (`calendario/`): **todas as versões**
   cadastradas são publicadas.
4. **Publicação** — a pasta `build/` é **commitada** e o workflow do GitHub
   Actions apenas a publica no **GitHub Pages**.

## Estrutura

```
calendario_academico/
├── calendario/                  # Aplicação Django
│   ├── scheduling.py            # Port fiel do algoritmo (cálculo da grade x1/x2)
│   ├── agenda.py                # Documento oficial: grade mensal, eventos, dias letivos
│   ├── models.py                # Calendario (versão/etapa) + Feriado + Evento
│   ├── static_site.py           # Gerador do site estático (build/)
│   ├── views.py                 # Home, /calendario/ (índice), /editor/, API (/api/…)
│   ├── admin.py                 # Admin editável (o banco é a fonte da verdade)
│   ├── data/feriados.py         # Feriados nacionais (BR) por ano
│   ├── management/commands/     # seed_feriados, seed_exemplo, seed_calendario_2026_2, render_static_site
│   ├── templates/calendario/    # base, home, editor, índice, detalhe + parciais do documento
│   └── tests.py
├── config/                      # Settings/urls do projeto Django
├── static/                      # CSS/JS/imagens (mesmo visual dos horários)
├── build/                       # HTML VERSIONADO por versão + índice (publicado)
├── .github/workflows/deploy.yml # Publica build/ no GitHub Pages
├── Makefile
├── manage.py
└── requirements.txt
```

## Documento oficial (estrutura do PDF)

A raiz `/calendario/` é o **índice** (lista todas as versões). Cada versão tem sua
página em `/versoes/<slug>/` com o **documento no formato do calendário oficial do
campus** (`CALENDÁRIO ACADÊMICO 2026.2 — Técnico em Administração Integrado
PROEJA`) — a **grade x1/x2 de reposição fica restrita à prévia do editor** —, com:

- **Cabeçalho** com instituição, curso, modalidade, semestre, início, término e o
  total de dias letivos (calculado × previsto);
- **Grade mensal** de AGO/2026 a FEV/2027 (domingo primeiro) com o **status de
  cada dia**: dia letivo, sábado letivo, feriado, ponto facultativo, recesso,
  férias coletivas, jornada pedagógica, avaliação final, conselho de classe e
  não letivo;
- **Quantidade de dias letivos por mês** (calculado × declarado no documento) e
  o **total**, usado para conferir a meta (ex.: 100 dias);
- **Dias letivos por dia da semana** — a contagem **em separado** de segunda a
  sexta (seg–sex + sábados) com o **mínimo de `100/5 = 20` por dia** e a situação
  de cada dia (OK / Faltam N). Os **sábados letivos/de reposição** entram somados
  ao **dia da semana do campo “Referência”** do evento. Também aparece na
  **elaboração** (`/editor/`), recalculada dinamicamente a cada alteração de
  feriado/evento, e como métrica da prévia da grade;
- **Tabela de eventos** (`MÊS · DIA · EVENTO`): matrículas, jornada pedagógica,
  PSAD, avaliações (1º/2º bimestre e 2ª chamada), recuperação paralela, fim de
  bimestre/entrega de notas no SUAP, conselho de classe, recessos, semanas
  temáticas e eventos institucionais;
- **Sábados letivos** com o **dia da semana referenciado** (ex.: “referente à
  quarta-feira”);
- **Feriados e pontos facultativos** e a **legenda** das categorias;
- **Tooltip nos dias** da grade mensal: ao passar o mouse — ou focar pelo
  teclado — aparecem a **data**, o **status** e os **eventos** do dia, sem
  depender do `title` nativo do navegador.

### Regra de dia letivo

**Faixa do cálculo:** só entra o que está dentro do período **declarado**
(`Início do semestre` → `Término do período letivo`). Registros fora dessa faixa
continuam aparecendo no documento (matrículas, 07/SET, férias depois do término…),
mas ficam com o status **“Fora do período”** e **não entram em nenhum cálculo**.
Se o término não for informado, a faixa é estimada pelo último registro (com nota
de aviso no documento).

**Tipos que contam** na carga horária (`calendario.TIPOS_QUE_CONTAM`):

| Contam | Removem o dia letivo (`TIPOS_QUE_REMOVEM`) | Neutros (`TIPOS_NEUTROS`) |
| --- | --- | --- |
| Dia letivo, Sábado letivo, Avaliação, Recuperação paralela, Evento institucional | Feriado, Ponto facultativo, Recesso escolar, Férias coletivas, Avaliação final, **Conselho de classe**, **Sábado de reposição** | Matrícula, Administrativo e **Jornada pedagógica** — *não criam dia letivo nem o removem*: o dia segue a regra normal (útil dentro do período = letivo **e contabilizado**) |

- **segunda a sexta**, dentro da faixa, é *letivo* — os tipos da primeira coluna
  mantêm o dia contabilizado; os da segunda **removem** o dia letivo (inclusive
  **conselho de classe**, que aparece na grade com cor e legenda próprias, mas o dia
  sai da conta);
- **matrícula**, **administrativo** e **jornada pedagógica** são avisos: o dia
  continua sendo “Dia letivo”, com a faixa verde e contando na carga horária (o
  evento aparece no tooltip/tabela de eventos);
- **sábado** conta somente com evento *sábado letivo*; **domingo** nunca conta;
- os tipos que contam somam **apenas em dia útil** — uma avaliação em sábado/domingo
  aparece na grade, mas não entra na carga horária;
- o dia que conta recebe uma **faixa verde** na grade mensal (`doc-dia-conta`) e a
  legenda indica “conta na carga horária” / “não conta”.

Além do total, os dias letivos são contados **por dia da semana, em separado**
(segunda, terça, quarta, quinta, sexta). A meta de dias letivos do semestre é
dividida pelos 5 dias úteis — **`100/5 = 20`** — e cada dia da semana deve
atingir esse mínimo; os dias abaixo da meta são destacados na tabela e nos avisos
de conferência. Os **sábados letivos** são somados ao **dia da semana informado no
campo “Referência”** do evento (ex.: um sábado referente à quarta-feira conta como
uma quarta letiva), de modo que
`Σ(seg–sex + sábados) = total de dias letivos`.

O tipo **“Sábado de reposição” NÃO entra na carga horária**: ele aparece na grade
mensal e na legenda (em cor própria), mas não conta como dia letivo, não soma no
total de sábados letivos e não precisa de Referência. Regras dos sábados:

- evento de sábado só vale **no sábado** — se for cadastrado em dia útil, o dia
  segue a regra normal (letivo) e o editor avisa;
- se o evento tiver **intervalo** (ex.: 19/09 a 26/09), cada **sábado** do intervalo
  conta e os dias úteis do meio são ignorados;
- se o sábado letivo cair em **feriado/ponto facultativo**, o feriado prevalece e o
  dia não entra na contagem (com aviso);
- **sábado letivo sem Referência** aparece no documento, mas não entra na coluna de
  nenhum dia — nesse caso o rodapé mostra a soma das colunas e o texto explica a
  diferença para o total do documento. O editor oferece o botão **Corrigir
  Referência dos sábados** (no quadro *Eventos*) e a IA já preenche a Referência
  automaticamente ao gerar os eventos.

> O rodapé da tabela **“Dias letivos por dia da semana”** é sempre a **soma das
> colunas** (`agenda.totais_tabela`), então a conta fecha linha a linha; a coluna
> “Mínimo” mostra a meta **por dia** e o rodapé dela o mínimo do semestre
> (`meta × 5`).

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

- **Documento oficial** (vide acima): grades mensais com **tooltip nos dias**,
  dias letivos por mês, eventos, sábados letivos, feriados/pontos facultativos e
  legenda — é o que a página publicada exibe;
- **Grade do semestre** com semanas (`x1`/`x2`), dias úteis, feriados e
  **reposição** (redistribuição) das aulas perdidas — **restrita à prévia do
  editor** (não é publicada no documento), com cores por paridade e a **legenda
  de cores** (x1/x2, feriado sem aula, sábado letivo, 1ª parte, dia com evento e
  aula remanejada);
- **Métricas** de erro (paridade / dia da semana / parte do semestre) e validação
  em tempo real, com explicação na **prévia do editor** de como lê-las (quanto
  menor, melhor — `0 / 0 / 0` é o ideal);
- **Coluna “Sáb” na grade** (prévia do editor) com os **sábados letivos/de
  reposição** (e o dia da semana referenciado) — no documento publicado eles
  aparecem na lista **Sábados letivos**;
- **Feriados nacionais brasileiros** calculados por ano (inclui móveis: Carnaval,
  Sexta-feira Santa e Corpus Christi), feriados/pontos facultativos
  institucionais e manuais;
- **Eventos acadêmicos** com intervalo de datas, tipo (categoria da legenda) e
  dia da semana referenciado (sábados letivos/de reposição);
- **Preenchimento e verificação por IA** (DeepSeek, ChatGPT, Gemini e Claude) a
  partir da cidade/UF/país da unidade: sugere feriados municipais/estaduais, os
  eventos exigidos pela **norma da modalidade** (arts. 38/39/40) e **distribui os
  sábados letivos** para fechar a carga horária — sempre com prévia, edição e
  confirmação antes de gravar (veja a seção específica);
- **Versionamento de cada etapa** (`2026.1.etapa1`, `2026.1.etapa2`, …) — **todas as
  versões** cadastradas são publicadas no build;
- **Interface no mesmo padrão visual** do painel de horários (tema claro/escuro,
  cabeçalho, banner de versão, cards);
- **Editor organizado em etapas** — começa por **Etapas salvas** (carregar uma versão
  existente) e segue com parâmetros, feriados e eventos, com **texto de ajuda em cada
  campo**; os **eventos podem ser editados** na própria tabela (Editar/Excluir) e as
  **prévias** ficam no fim. Ao passar o mouse sobre um dia, um tooltip mostra data,
  status e eventos;
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
| `seed_exemplo`             | Cria calendários de exemplo (etapas + publicada)   | —                                   |
| `seed_calendario_2026_2`   | Recria o **calendário oficial 2026.2** do documento    | —                                   |
| `render_static_site`       | Gera o site estático em `build/`                       | `--output`, `--base-url`            |

### Importar os feriados nacionais

```bash
python manage.py seed_feriados                 # todos os calendários existentes
python manage.py seed_feriados --versao 2026.1.final
```

## Preenchimento e verificação por IA (LLM)

O quadro de **Eventos** do editor tem dois botões que usam um provedor de LLM para
acelerar a montagem **sem gravar nada por conta própria**:

| Botão | O que faz |
| --- | --- |
| **Preencher com IA** | a partir da **cidade/UF/país** da unidade, sugere **feriados municipais/estaduais** e os eventos exigidos pela norma da modalidade, e **distribui os sábados letivos** para fechar a carga horária de cada dia da semana (sábados letivos sem Referência recebem o dia de maior déficit automaticamente) |
| **Verificar com IA** | audita os eventos **já lançados** (preenchimento manual) contra a norma e lista o que falta, com evidências, motivo e um evento sugerido por item |
| **Corrigir Referência dos sábados** | preenche a Referência dos **sábados letivos** sem dia da semana (pelo maior déficit). Não se aplica a *sábados de reposição*, que **não entram na carga horária** |

### Modalidade → norma (arts. 38, 39 e 40)

| Modalidade | Norma | Itens |
| --- | --- | --- |
| `integrado_medio` — Cursos técnicos integrados ao nível médio | **Art. 38** | 22 |
| `concomitante_subsequente` — Cursos técnicos concomitantes/subsequentes | **Art. 39** | 21 |
| `graduacao` — Graduação | **Art. 40** | 23 |

O checklist é **determinístico** (regras em `calendario/requisitos.py`, casando o tipo do
evento, palavras-chave e cálculos da agenda). A IA só **sugere** e interpreta; a regra
local nunca é rebaixada por ela — quando a IA vê uma evidência que a regra não viu, o item
vira **“a conferir”**, nunca “atendido” sem prova. Itens não automatizáveis (ex.: “temas
transversais obrigatórios por lei”) aparecem sempre como **a conferir**.

### Carga horária e sábados letivos

A meta por dia é `ceil(dias_letivos_previstos / 5)` e quem **fecha** essa conta é o
cálculo do projeto, não o modelo: `calendario/llm.py::completar_sabados` escolhe sábados
livres (dentro do período, sem feriado/ponto facultativo e sem reutilizar sábados já
lançados), gravando sempre em **Dia da semana referenciado** o dia com maior déficit. Se
não houver sábados suficientes, o editor avisa o que falta em cada dia.

### Configuração (chaves por variável de ambiente)

As chaves **nunca** ficam no banco, no build estático nem no HTML do editor.

| Provedor | Chave (env) | Modelo padrão (env) |
| --- | --- | --- |
| DeepSeek *(padrão)* | `DEEPSEEK_API_KEY` | `deepseek-chat` (`DEEPSEEK_MODEL`) |
| ChatGPT (OpenAI) | `OPENAI_API_KEY` | `gpt-4o-mini` (`OPENAI_MODEL`) |
| Gemini (Google) | `GEMINI_API_KEY` | `gemini-2.0-flash` (`GEMINI_MODEL`) |
| Claude (Anthropic) | `ANTHROPIC_API_KEY` | `claude-sonnet-4-5` (`ANTHROPIC_MODEL`) |

```bash
export DEEPSEEK_API_KEY="sk-..."   # ou OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY
export LLM_PROVIDER="deepseek"     # padrão do modal (aceita chatgpt, claude, claudecode, google)
export LLM_TIMEOUT=120             # segundos
make rodar                         # reinicie o servidor após definir as variáveis
```

Outras variáveis: `LLM_ENABLED` (`0` desliga), `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`,
`LLM_CIDADE_PADRAO`/`LLM_ESTADO_PADRAO`/`LLM_PAIS_PADRAO` e os overrides de URL/modelo
(`DEEPSEEK_API_URL`, `OPENAI_MODEL`, …). Veja o `.env.example`.

### Fluxo (nada é gravado antes da sua confirmação)

1. **Preencher/Verificar**: a chamada é síncrona e o modal mostra “Consultando …”;
2. o modal devolve a **prévia**: métricas, tabela **Dias letivos por dia da semana**,
   eventos editáveis, feriados em chips e o **checklist da norma**;
3. **Aplicar ao editor** (modo *preencher*) ou **Aplicar selecionados ao editor** (modo
   *verificar*, marcando os itens faltantes) leva os itens para o editor — **nada foi
   salvo ainda** (o editor avisa isso em destaque);
4. só o botão **Salvar versão** grava no banco.

### Endpoints

| Rota | Método | Descrição |
| --- | --- | --- |
| `/api/ia/eventos/` | POST | prévia de feriados/eventos/sábados + checklist — **não grava** |
| `/api/ia/verificar/` | POST | auditoria da norma sobre os eventos lançados — **não grava** |
| `/api/preview/` | POST | recalcula a carga horária no servidor (usado pelas prévias) |

Erros: **400** para uso/configuração inválida (faltou cidade/UF ou período, provedor sem
chave) e **502** quando o provedor falha (HTTP, timeout ou resposta ilegível).

### Limitações

- Feriados **municipais/estaduais** sugeridos pela IA podem estar errados: confira na
  legislação (o checklist marca “confiança baixa”);
- A chamada é **síncrona** (pode levar até `LLM_TIMEOUT`); não há streaming.

## Versionamento

- Cada salvamento no editor grava/atualiza uma **versão** (`Calendario.etapa`). **Não
  existe “versão final”**: todas as versões cadastradas são equivalentes e **todas vão
  para o build**.
- A raiz **`/calendario/` é o índice** — lista todas as versões. Cada versão tem sua
  página em **`/versoes/<slug>/`** com o documento completo. O path legado
  **`/versoes/` redireciona** para o índice (`/calendario/`).
- **Excluir versões** — no índice `/calendario/` (coluna *Ações*) e na lista **Etapas
  salvas** do `/editor/` há o botão **Excluir** para cada versão, com confirmação. É um
  **POST de formulário** para `/versoes/excluir/` (funciona sem JavaScript) que remove a
  versão do banco — e os feriados dela, em cascata — e volta para o índice com uma
  mensagem de retorno. A ação é **permanente** e **não** aparece no site estático (o
  Pages não tem banco). A API `POST /api/excluir/` segue disponível para integrações.
- **Clonar versões** — o painel **“Clonar uma versão”** no índice usa uma versão
  existente como **base** para elaborar o calendário de **outra modalidade/curso**
  (ex.: partir do Integrado PROEJA e adaptar para o Subsequente). O clone copia o
  cabeçalho, o período, as metas de dias letivos, os **feriados** e os **eventos**.
  Informe o **nome da nova versão** e, se quiser, troque a **modalidade** e o **curso**;
  o botão *Clonar e editar* abre a nova versão no editor. É um **POST de formulário**
  para `/versoes/clonar/` (funciona sem JavaScript) e **não** aparece no site estático.
  A API `POST /api/clonar/` segue disponível para integrações.

## Publicação (GitHub Pages)

1. A base do Pages já está configurada no `Makefile` (`PAGES_BASE`), apontando
   para o nome do repositório (project pages → `/nome-do-repo/`). Neste projeto:
   `PAGES_BASE ?= /gerenciador_calendario/`.
2. Gere e commite o build:

   ```bash
   make publicar     # render_static_site --base-url $(PAGES_BASE) + git add build/
   ```

3. Envie para o repositório (`git push`). O workflow
   `.github/workflows/deploy.yml` publica a pasta `build/` no GitHub Pages.
   Habilite em **Settings → Pages → Build and deployment → Source: GitHub Actions**.

> O CI **valida a base do build** antes de publicar: se o `build/` estiver com links
> a partir da raiz (`/static/...`, típico de `make gerar`), o deploy falha com erro
> claro em vez de publicar um site sem CSS/imagens. Publique sempre com `make publicar`.
>
> Como o `build/` é commitado com caminhos absolutos, se o nome do repositório
> mudar rode `make publicar PAGES_BASE=/novo-nome/` para regerar com a base certa.
>
> Após **excluir** ou **clonar** uma versão, rode `make gerar` (ou `make publicar`)
> para o `build/` refletir a lista atual — o gerador recria a pasta do zero e publica
> **todas** as versões em `versoes/<slug>/`.

## Testes

```bash
python manage.py test
```

A suíte cobre o **algoritmo** (semana/feriados/remanejamento/validação), a
**agenda do documento** (status por dia, dias letivos por mês, sábados letivos e
validação de 100 dias), os **feriados nacionais** (Páscoa e feriados móveis), a
**API** (preview/salvar/eventos/clonar/excluir), a **clonagem de versão** (cópia de
parâmetros, feriados e eventos; nome único), o **índice/redirect** de versões, o
**seed 2026.2**, as **views** e o **build estático versionado**.

A IA tem cobertura própria, **sem nenhuma chamada de rede** (o provedor é
simulado): **requisitos** (as 3 normas, detecção por tipo/palavra/cálculo, merge
conservador com a IA, calendário oficial 2026.2), **configuração** de provedores e
apelidos, **leitura/normalização** da resposta (JSON puro, com cerca, inválido),
**carga horária** (`completar_sabados`) e os **endpoints** `/api/ia/eventos/` e
`/api/ia/verificar/` — inclusive o teste que garante que **nada é gravado** antes
do “Salvar versão”.

## Observações

- O `db.sqlite3` é **local** (ignorado pelo git): é a sua fonte de trabalho no
  editor/admin. O que se compartilha é o **`build/`**.
- Para reproduzir o ambiente do zero, `make exemplo` recria os calendários de
  demonstração de 2026.1 e `make oficial` recria o calendário oficial 2026.2 do
  documento (Administração Integrado PROEJA).
- O link **Editor** aparece apenas no `runserver`; ele **não** é publicado no
  site estático (por isso as chaves de IA ficam fora do que vai para o Pages).
- As **modalidades** do calendário são apenas três — `integrado_medio`,
  `concomitante_subsequente` e `graduacao` — e cada uma aponta para a norma
  correspondente (arts. 38, 39 e 40). A migração `0005` converte automaticamente os
  valores antigos (`integrado`, `integrado_proeja`, `subsequente`, `superior`, `outro`).

