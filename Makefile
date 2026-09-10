# ============================================================================
# Calendário Acadêmico — IFPI Campus Barras
# Comandos locais amigáveis.
#
# Fluxo rápido:
#   make configurar  -> cria .venv e instala dependências
#   make banco       -> migrate + seed dos feriados nacionais
#   make rodar       -> sobe o servidor (use /editor/ para montar o calendário)
#   make gerar       -> gera o site estático versionado em build/
#   make ver         -> python -m http.server -d build 8000
#   make publicar    -> gera o build/ e faz commit (o CI só publica a pasta)
#   make limpar      -> apaga o build/ (rode 'make gerar' antes de commitar)
#
# Atalhos compatíveis: help, setup, migrate, data, render, build, serve,
# dev, test e clean.
# ============================================================================

# ---- Configuração ---------------------------------------------------------
VENV     ?= .venv
PYTHON   ?= $(VENV)/bin/python
MANAGE    = $(PYTHON) manage.py
PORT     ?= 8000
# Base local: o site é servido na raiz do http.server.
BASE_URL   ?= /
# Base usada no build publicado (project pages: /nome-do-repo/).
PAGES_BASE ?= /calendario_academico/

.PHONY: ajuda configurar banco importar semear exemplo oficial gerar site ver rodar publicar testar limpar
.PHONY: help setup migrate data render build serve dev test clean

ajuda: ## mostra todos os comandos disponíveis
	@echo "Comandos disponíveis:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

configurar: ## cria o ambiente virtual e instala as dependências
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -r requirements.txt
	@echo "Pronto! Ative o venv com:  source $(VENV)/bin/activate"

banco: ## prepara o banco de dados (migrate)
	$(MANAGE) migrate

importar: banco ## alias de 'banco' (compatibilidade)

semear: banco ## adiciona os feriados nacionais aos calendários existentes
	$(MANAGE) seed_feriados

exemplo: banco ## cria calendários de exemplo (para demonstração/prévia)
	$(MANAGE) seed_exemplo

oficial: banco ## cria o calendário oficial 2026.2 (Administração Integrado PROEJA)
	$(MANAGE) seed_calendario_2026_2

gerar: ## gera o site em build/ para prévia local (BASE_URL, padrão /)
	$(MANAGE) render_static_site --base-url $(BASE_URL)

site: banco gerar ## monta o site do zero (banco + gerar) e abre a prévia
	@echo "OK: build/ pronto. Rode 'make ver' para conferir."

ver: ## sobe o servidor local em http://127.0.0.1:PORT (use após 'make gerar')
	$(PYTHON) -m http.server -d build $(PORT)

rodar: banco ## sobe o servidor de desenvolvimento (use /editor/ para montar)
	$(MANAGE) runserver $(PORT)

publicar: banco ## gera o build/ para o GitHub Pages (PAGES_BASE) e commita a pasta
	$(MANAGE) render_static_site --base-url $(PAGES_BASE)
	git add build/
	git commit -m "build: atualiza calendário acadêmico versionado" || true
	@echo "OK: build/ commitado. Faça o push para publicar no GitHub Pages."

testar: banco ## roda a suíte de testes
	$(MANAGE) test

limpar: ## remove o diretório build/ gerado (rode 'make gerar' antes de commitar)
	rm -rf build
	@echo "build/ apagado."

# ---- Atalhos (compatibilidade) --------------------------------------------
help: ajuda
setup: configurar
migrate: banco
data: importar
render: gerar
build: site
serve: ver
dev: rodar
test: testar
clean: limpar
