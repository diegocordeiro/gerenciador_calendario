/* Interface de montagem do calendário acadêmico.
 * O cálculo é feito no servidor (/api/preview/ e /api/salvar/); este arquivo
 * apenas coleta os parâmetros, renderiza a grade devolvida e envia os dados.
 */
(function () {
  "use strict";

  var inicialEl = document.getElementById("inicial-data");
  if (!inicialEl) return;
  var inicial = JSON.parse(inicialEl.textContent || "{}");
  var BASE = window.CAL_BASE || "/";

  var csrfInput = document.querySelector("#editorForm input[name=csrfmiddlewaretoken]");
  var CSRF = csrfInput ? csrfInput.value : "";

  function $(id) {
    return document.getElementById(id);
  }

  var state = {
    feriados: (inicial.feriados || []).map(function (f) {
      if (typeof f === "string") {
        return { data: f, descricao: "", origem: "manual", tipo: "feriado" };
      }
      return {
        data: f.data,
        descricao: f.descricao || "",
        origem: f.origem || "manual",
        tipo: f.tipo || "feriado"
      };
    }),
    eventos: (inicial.eventos || []).map(function (e) {
      return {
        titulo: e.titulo || "",
        tipo: e.tipo || "evento",
        data_inicio: e.data_inicio || "",
        data_fim: e.data_fim || "",
        dia_semana_referencia:
          e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
            ? null
            : e.dia_semana_referencia,
        descricao: e.descricao || "",
        destaque: !!e.destaque
      };
    }),
    eventoEditandoIdx: null
  };

  var TIPOS_EVENTO = {};
  (inicial.tipos_evento || []).forEach(function (t) {
    TIPOS_EVENTO[t.valor] = t.label;
  });
  var DIAS_SEMANA = {};
  (inicial.dias_semana || []).forEach(function (d) {
    DIAS_SEMANA[d.valor] = d.label;
  });

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function postJSON(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
      body: JSON.stringify(data)
    }).then(function (resp) {
      return resp.json().catch(function () {
        return {};
      });
    });
  }

  function msg(texto, tipo) {
    var el = $("editorMsg");
    if (!el) return;
    el.textContent = texto;
    el.className = "editor-msg " + (tipo === "ok" ? "editor-msg-ok" : "editor-msg-erro");
  }

  function fmtData(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(iso);
  }

  // ---- Tooltip das prévias ------------------------------------------------
  // As células das prévias (mensal e grade x1/x2) levam "data-tip". O tooltip
  // nativo do navegador é lento/instável, então exibimos uma caixa própria.
  var tooltipEl = null;

  function tooltip() {
    if (!tooltipEl) {
      tooltipEl = document.createElement("div");
      tooltipEl.className = "editor-tooltip";
      tooltipEl.setAttribute("role", "tooltip");
      document.body.appendChild(tooltipEl);
    }
    return tooltipEl;
  }

  function alvoComDica(node) {
    return node && node.closest ? node.closest("[data-tip]") : null;
  }

  function posicionarTooltip(x, y) {
    if (!tooltipEl || !tooltipEl.classList.contains("is-visible")) return;
    var margem = 14;
    var box = tooltipEl.getBoundingClientRect();
    var px = x + margem;
    var py = y + margem;
    if (px + box.width > window.innerWidth - 8) px = window.innerWidth - box.width - 8;
    if (px < 8) px = 8;
    if (py + box.height > window.innerHeight - 8) py = y - box.height - margem;
    if (py < 8) py = 8;
    tooltipEl.style.left = px + "px";
    tooltipEl.style.top = py + "px";
  }

  function mostrarTooltip(alvo, x, y) {
    var texto = alvo.getAttribute("data-tip");
    if (!texto) return;
    var el = tooltip();
    el.textContent = texto;
    el.classList.add("is-visible");
    posicionarTooltip(x, y);
  }

  function esconderTooltip() {
    if (tooltipEl) tooltipEl.classList.remove("is-visible");
  }

  document.addEventListener("mouseover", function (ev) {
    var alvo = alvoComDica(ev.target);
    if (alvo) mostrarTooltip(alvo, ev.clientX, ev.clientY);
  });
  document.addEventListener("mousemove", function (ev) {
    if (alvoComDica(ev.target)) posicionarTooltip(ev.clientX, ev.clientY);
  });
  document.addEventListener("mouseout", function (ev) {
    var alvo = alvoComDica(ev.target);
    if (alvo && !alvo.contains(ev.relatedTarget)) esconderTooltip();
  });
  document.addEventListener("focusin", function (ev) {
    var alvo = alvoComDica(ev.target);
    if (!alvo) return;
    var box = alvo.getBoundingClientRect();
    mostrarTooltip(alvo, box.left, box.bottom);
  });
  document.addEventListener("focusout", esconderTooltip);
  window.addEventListener("scroll", esconderTooltip, true);
  window.addEventListener("blur", esconderTooltip);

  // ---- Formulário --------------------------------------------------------
  function fill() {
    $("fVersao").value = inicial.versao || "";
    $("fTitulo").value = inicial.titulo || "";
    $("fPeriodo").value = inicial.periodo || "";
    $("fInstituicao").value = inicial.instituicao || "";
    $("fCurso").value = inicial.curso || "";
    $("fModalidade").value = inicial.modalidade || "integrado_medio";
    $("fSemestre").value = inicial.semestre || "";
    $("fInicio").value = inicial.data_inicio || "";
    $("fDataFim").value = inicial.data_fim || "";
    $("fPrevistos").value = inicial.dias_letivos_previstos || 0;
    $("fSemanas").value = inicial.total_semanas || 18;
    $("fSemanas1").value = inicial.semanas_primeira_parte || 9;
    $("fEtapa").value = inicial.etapa || 1;
    $("fObs").value = inicial.observacoes || "";
  }

  function payload() {
    return {
      versao: $("fVersao").value.trim(),
      titulo: $("fTitulo").value.trim(),
      periodo: $("fPeriodo").value.trim(),
      instituicao: $("fInstituicao").value.trim(),
      curso: $("fCurso").value.trim(),
      modalidade: $("fModalidade").value,
      semestre: $("fSemestre").value.trim(),
      data_inicio: $("fInicio").value,
      data_fim: $("fDataFim").value,
      dias_letivos_previstos: parseInt($("fPrevistos").value || "0", 10),
      dias_letivos_por_mes: inicial.dias_letivos_por_mes || [],
      total_semanas: parseInt($("fSemanas").value || "0", 10),
      semanas_primeira_parte: parseInt($("fSemanas1").value || "0", 10),
      etapa: parseInt($("fEtapa").value || "1", 10),
      observacoes: $("fObs").value,
      feriados: state.feriados,
      eventos: state.eventos
    };
  }

  // ---- Feriados ----------------------------------------------------------
  function temFeriado(iso) {
    return state.feriados.some(function (f) {
      return f.data === iso;
    });
  }

  function addFeriado(iso, descricao, origem, tipo) {
    if (!iso || temFeriado(iso)) return;
    state.feriados.push({
      data: iso,
      descricao: descricao || "",
      origem: origem || "manual",
      tipo: tipo || "feriado"
    });
  }

  function toggleFeriado(iso) {
    if (temFeriado(iso)) {
      state.feriados = state.feriados.filter(function (f) {
        return f.data !== iso;
      });
    } else {
      addFeriado(iso, "", "manual", "feriado");
    }
    renderChips();
    agendarPreview();
  }

  function renderChips() {
    var ul = $("holidayChips");
    if (!ul) return;
    var ordenados = state.feriados.slice().sort(function (a, b) {
      return a.data < b.data ? -1 : 1;
    });
    ul.innerHTML = ordenados
      .map(function (f) {
        var rotulo = f.data.split("-").reverse().join("/");
        var tipo = f.tipo === "ponto_facultativo" ? "Ponto facultativo" : "Feriado";
        return (
          '<li class="chip chip-removable" data-date="' +
          esc(f.data) +
          '">' +
          esc(rotulo) +
          " <small>(" +
          esc(tipo) +
          ")</small>" +
          ' <button type="button" class="chip-remove" aria-label="Remover">&times;</button></li>'
        );
      })
      .join("");
    Array.prototype.forEach.call(ul.querySelectorAll(".chip-remove"), function (btn) {
      btn.addEventListener("click", function () {
        toggleFeriado(btn.parentNode.getAttribute("data-date"));
      });
    });
  }

  // ---- Eventos -----------------------------------------------------------
  function renderEventos() {
    var tbody = $("eventosBody");
    if (!tbody) return;
    if (state.eventoEditandoIdx !== null && !state.eventos[state.eventoEditandoIdx]) {
      state.eventoEditandoIdx = null;
    }
    var ordenados = state.eventos.slice().sort(function (a, b) {
      return a.data_inicio < b.data_inicio ? -1 : 1;
    });
    tbody.innerHTML = ordenados
      .map(function (e) {
        var i = state.eventos.indexOf(e);
        var editando = i === state.eventoEditandoIdx;
        var ref =
          e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
            ? ""
            : DIAS_SEMANA[e.dia_semana_referencia] || "";
        return (
          "<tr" +
          (editando ? ' class="row-editando"' : "") +
          ">" +
          "<td>" +
          esc(e.data_inicio.split("-").reverse().join("/")) +
          "</td>" +
          "<td>" +
          (e.data_fim ? esc(e.data_fim.split("-").reverse().join("/")) : "—") +
          "</td>" +
          "<td>" +
          esc(e.titulo) +
          "</td>" +
          "<td>" +
          esc(TIPOS_EVENTO[e.tipo] || e.tipo) +
          "</td>" +
          "<td>" +
          esc(ref) +
          "</td>" +
          '<td class="evento-acoes">' +
          '<button type="button" class="btn-editar" data-edit="' +
          i +
          '" title="Editar evento" aria-label="Editar evento">&#9998;</button>' +
          '<button type="button" class="chip-remove" data-idx="' +
          i +
          '" aria-label="Remover">&times;</button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    Array.prototype.forEach.call(tbody.querySelectorAll(".btn-editar"), function (btn) {
      btn.addEventListener("click", function () {
        editarEvento(parseInt(btn.getAttribute("data-edit"), 10));
      });
    });
    Array.prototype.forEach.call(tbody.querySelectorAll(".chip-remove"), function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-idx"), 10);
        state.eventos.splice(idx, 1);
        if (state.eventoEditandoIdx === idx) state.eventoEditandoIdx = null;
        else if (state.eventoEditandoIdx !== null && state.eventoEditandoIdx > idx) {
          state.eventoEditandoIdx -= 1;
        }
        atualizarBotaoEvento();
        renderEventos();
        agendarPreview();
      });
    });
  }

  function limparFormEvento() {
    $("evTitulo").value = "";
    $("evInicio").value = "";
    $("evFim").value = "";
    $("evReferencia").value = "";
    $("evDestaque").checked = false;
  }

  function atualizarBotaoEvento() {
    var btn = $("btnAddEvento");
    var cancelar = $("btnCancelarEvento");
    var editando = state.eventoEditandoIdx !== null;
    if (btn) btn.textContent = editando ? "Salvar alterações" : "Adicionar evento";
    if (cancelar) cancelar.hidden = !editando;
  }

  function editarEvento(idx) {
    var e = state.eventos[idx];
    if (!e) return;
    $("evTitulo").value = e.titulo || "";
    $("evTipo").value = e.tipo || "evento";
    $("evInicio").value = e.data_inicio || "";
    $("evFim").value = e.data_fim || "";
    $("evReferencia").value =
      e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
        ? ""
        : String(e.dia_semana_referencia);
    $("evDestaque").checked = !!e.destaque;
    state.eventoEditandoIdx = idx;
    atualizarBotaoEvento();
    renderEventos();
    msg("Editando o evento selecionado — ajuste os campos e clique em “Salvar alterações”.", "ok");
    $("evTitulo").focus();
  }

  function cancelarEdicaoEvento() {
    state.eventoEditandoIdx = null;
    limparFormEvento();
    atualizarBotaoEvento();
    renderEventos();
  }

  function salvarEvento() {
    var titulo = $("evTitulo").value.trim();
    var inicio = $("evInicio").value;
    if (!titulo || !inicio) {
      msg("Informe o título e a data inicial do evento.", "erro");
      return;
    }
    var ref = $("evReferencia").value;
    var idx = state.eventoEditandoIdx;
    var anterior = idx !== null ? state.eventos[idx] : null;
    var evento = {
      titulo: titulo,
      tipo: $("evTipo").value,
      data_inicio: inicio,
      data_fim: $("evFim").value || "",
      dia_semana_referencia: ref === "" ? null : parseInt(ref, 10),
      descricao: anterior ? anterior.descricao || "" : "",
      destaque: $("evDestaque").checked
    };
    if (idx !== null) {
      state.eventos[idx] = evento;
      state.eventoEditandoIdx = null;
      msg("Evento atualizado.", "ok");
    } else {
      state.eventos.push(evento);
      msg("Evento adicionado.", "ok");
    }
    limparFormEvento();
    atualizarBotaoEvento();
    renderEventos();
    preview();
  }

  // ---- Prévia da grade ---------------------------------------------------
  function metric(rotulo, valor, sub, dica) {
    return (
      '<div class="cal-metric"' +
      (dica ? ' data-tip="' + esc(dica) + '"' : "") +
      '><span class="cal-metric-label">' +
      esc(rotulo) +
      "</span><strong>" +
      esc(valor) +
      "</strong><small>" +
      esc(sub) +
      "</small></div>"
    );
  }

  // Explicação da métrica "Erros (paridade / dia / parte)" com a leitura dos
  // valores atuais do calendário.
  function renderAjudaMetricas(d) {
    var m = (d && d.metricas) || { parity: 0, weekday: 0, part: 0 };
    return (
      '<div class="cal-help">' +
      '<strong>Como ler “Erros (paridade / dia / parte)”</strong>' +
      "<p>Ao remanejar as aulas interrompidas por feriados, o sistema tenta recolocá-las na " +
      "<strong>mesma semana (paridade x1/x2)</strong>, no <strong>mesmo dia da semana</strong> e na " +
      "<strong>mesma parte do semestre</strong>. Cada número conta quantas aulas <em>não</em> " +
      "conseguiram manter essas condições — por isso <strong>quanto menor, melhor</strong> e " +
      "<code>0 / 0 / 0</code> é o ideal.</p>" +
      "<ul>" +
      "<li><strong>Paridade (x1/x2):</strong> aulas que caíram em uma semana de paridade diferente da original.</li>" +
      "<li><strong>Dia:</strong> aulas que caíram em outro dia da semana (ex.: uma quarta no lugar de uma terça).</li>" +
      "<li><strong>Parte:</strong> aulas que mudaram da 1ª para a 2ª parte do semestre (ou o contrário).</li>" +
      "</ul>" +
      "<p>Neste calendário: <strong>" +
      esc(m.parity) +
      "</strong> aula(s) em paridade diferente, <strong>" +
      esc(m.weekday) +
      "</strong> em dia diferente e <strong>" +
      esc(m.part) +
      "</strong> em outra parte.</p>" +
      "</div>"
    );
  }

  // Eventos indexados por data (a matriz x1/x2 é seg–sex, então usamos o
  // índice derivado da agenda para marcar as células com evento).
  function eventosPorData(agenda) {
    var mapa = {};
    ((agenda && agenda.meses) || []).forEach(function (mes) {
      (mes.semanas || []).forEach(function (semana) {
        (semana || []).forEach(function (c) {
          if (c && !c.vazio && c.eventos && c.eventos.length) mapa[c.date] = c.eventos;
        });
      });
    });
    return mapa;
  }

  function renderMensalAgenda(agenda) {
    var html = '<div class="doc-meses">';
    agenda.meses.forEach(function (mes) {
      html +=
        '<div class="doc-mes"><h3 class="doc-mes-titulo">MÊS: ' + esc(mes.label) + "</h3>";
      html += '<table class="doc-mes-grid"><thead><tr>';
      (agenda.dias_cabecalho || []).forEach(function (d) {
        html += "<th>" + esc(d) + "</th>";
      });
      html += "</tr></thead><tbody>";
      (mes.semanas || []).forEach(function (semana) {
        html += "<tr>";
        (semana || []).forEach(function (c) {
          if (!c || c.vazio) {
            html += '<td class="doc-dia doc-dia-vazio"></td>';
            return;
          }
          var rotulo = fmtData(c.date);
          var clicavel =
            ["fora", "nao_letivo", "letivo_sabado"].indexOf(c.status) === -1;
          var titulo = rotulo + " — " + (c.status_label || "");
          if (c.eventos && c.eventos.length) titulo += " — " + c.eventos.join("; ");
          if (clicavel) titulo += " · Clique para marcar/desmarcar feriado";
          html +=
            '<td class="doc-dia doc-dia-' +
            esc(c.status) +
            (c.destaque ? " doc-dia-destaque" : "") +
            (c.eventos && c.eventos.length ? " doc-dia-com-evento" : "") +
            '" data-tip="' +
            esc(titulo) +
            '" aria-label="' +
            esc(titulo) +
            '"' +
            (clicavel ? ' data-date="' + esc(c.date) + '"' : "") +
            '><span class="doc-dia-num">' +
            esc(c.dia) +
            "</span></td>";
        });
        html += "</tr>";
      });
      html += "</tbody></table>";
      html +=
        '<p class="doc-mes-resumo">Dias letivos: <strong>' +
        esc(mes.letivos) +
        "</strong>" +
        (mes.sabados ? " • Sábados letivos: " + esc(mes.sabados) : "") +
        "</p></div>";
    });
    return html + "</div>";
  }

  function renderResumoDoc(agenda) {
    var linhas = (agenda.resumo || [])
      .map(function (r) {
        return (
          "<tr><th>" +
          esc(r.label) +
          "</th><td>" +
          esc(r.letivos) +
          "</td><td>" +
          (r.tem_declarado ? esc(r.declarado) : "—") +
          "</td><td>" +
          esc(r.sabados) +
          "</td><td>" +
          esc(r.feriados) +
          '</td><td class="' +
          (r.diferenca ? "doc-dif" : "") +
          '">' +
          (r.tem_declarado ? esc(r.diferenca) : "—") +
          "</td></tr>"
        );
      })
      .join("");
    if (!linhas) {
      linhas = '<tr><td colspan="6" class="muted">Sem meses no período informado.</td></tr>';
    }
    var previsto =
      agenda.validacao && agenda.validacao.previsto ? esc(agenda.validacao.previsto) : "—";
    return (
      "<h3>Quantidade de dias letivos por mês</h3>" +
      '<table class="doc-table doc-table-resumo"><thead><tr>' +
      "<th>Mês</th><th>Dias letivos</th><th>Declarado</th><th>Sábados</th>" +
      "<th>Feriados/Pontos</th><th>Diferença</th></tr></thead><tbody>" +
      linhas +
      '</tbody><tfoot><tr><th>Total</th><td>' +
      esc(agenda.total_letivos) +
      "</td><td>" +
      previsto +
      '</td><td colspan="3"></td></tr></tfoot></table>'
    );
  }

  // Tabela "Dias letivos por dia da semana" — contagem SEPARADA de cada dia
  // útil (seg–sex) somada aos SÁBADOS LETIVOS pelo dia da semana informado no
  // campo "Referência" (dia_semana_referencia). A meta do semestre é dividida
  // pelos 5 dias (ex.: 100/5 = 20). Recalculada a cada prévia (dinâmica).
  function renderResumoDias(agenda) {
    var itens = agenda.dias_por_dia || [];
    if (!itens.length) return "";
    var previsto =
      agenda.validacao && agenda.validacao.previsto ? agenda.validacao.previsto : 0;
    var linhas = itens
      .map(function (d) {
        var situacao = !d.meta ? "—" : d.ok ? "OK" : "Faltam " + esc(d.falta);
        return (
          '<tr class="' +
          (d.ok ? "" : "doc-dif") +
          '"><th>' +
          esc(d.label) +
          "</th><td>" +
          esc(d.seg_sex) +
          "</td><td>" +
          esc(d.sabados) +
          "</td><td>" +
          esc(d.letivos) +
          "</td><td>" +
          (d.meta ? esc(d.meta) : "—") +
          "</td><td>" +
          situacao +
          "</td></tr>"
        );
      })
      .join("");
    var porDiaOk = !agenda.validacao || agenda.validacao.por_dia_ok !== false;
    return (
      "<h3>Dias letivos por dia da semana</h3>" +
      '<p class="muted">Contagem de <strong>segunda a sexta, em separado</strong>. Os ' +
      "<strong>sábados letivos/de reposição</strong> entram somados ao " +
      "<strong>dia da semana do campo “Referência”</strong> do evento. A meta é " +
      "distribuída pelos 5 dias úteis (ex.: 100/5 = 20 por dia).</p>" +
      '<table class="doc-table doc-table-dias"><thead><tr>' +
      "<th>Dia da semana</th><th>Seg–sex</th><th>Sábados</th><th>Total</th><th>Mínimo" +
      (previsto ? " (" + esc(previsto) + "/5)" : "") +
      "</th><th>Situação</th></tr></thead><tbody>" +
      linhas +
      '</tbody><tfoot><tr><th>Total</th><td>' +
      esc(agenda.letivos_seg_sex) +
      "</td><td>" +
      esc(agenda.sabados_total) +
      "</td><td>" +
      esc(agenda.total_letivos) +
      "</td><td>" +
      (previsto ? esc(previsto) : "—") +
      "</td><td>" +
      (porDiaOk ? "OK" : "Abaixo da meta") +
      "</td></tr></tfoot></table>" +
      (agenda.sabados_sem_referencia
        ? '<p class="muted"><strong>' +
          esc(agenda.sabados_sem_referencia) +
          " sábado(s) letivo(s) sem Referência — não contabilizados por dia.</strong></p>"
        : "") +
      '<p class="muted">Total geral do documento: <strong>' +
      esc(agenda.total_letivos) +
      "</strong> dias (" +
      esc(agenda.letivos_seg_sex) +
      " seg–sex + " +
      esc(agenda.sabados_total) +
      " sábados letivos).</p>"
    );
  }

  function renderEventosDoc(agenda) {
    var grupos = agenda.eventos_por_mes || [];
    if (!grupos.length) {
      return '<h3>Eventos</h3><p class="muted">Nenhum evento cadastrado.</p>';
    }
    var html =
      '<h3>Eventos</h3><table class="doc-table doc-table-eventos"><thead><tr>' +
      "<th>Mês</th><th>Dia</th><th>Eventos</th></tr></thead><tbody>";
    grupos.forEach(function (g) {
      (g.itens || []).forEach(function (it, i) {
        html += "<tr>";
        if (i === 0) {
          html +=
            '<th rowspan="' + g.itens.length + '" class="doc-mes-cel">' + esc(g.label) + "</th>";
        }
        html +=
          '<td class="doc-dia-cel">' +
          esc(it.dia) +
          '</td><td><span class="doc-evento doc-evento-' +
          esc(it.tipo) +
          '">' +
          esc(it.titulo) +
          "</span>";
        if (it.referencia) html += ' <em class="muted">(' + esc(it.referencia) + ")</em>";
        html += "</td></tr>";
      });
    });
    return html + "</tbody></table>";
  }

  function renderLegendaDoc(agenda) {
    var itens = agenda.legenda || [];
    if (!itens.length) return "";
    return (
      "<h3>Legenda</h3><ul class=\"doc-legenda\">" +
      itens
        .map(function (l) {
          return (
            '<li><span class="doc-dia-swatch doc-dia-' +
            esc(l.status) +
            '"></span> ' +
            esc(l.label) +
            "</li>"
          );
        })
        .join("") +
      "</ul>"
    );
  }

  function renderAgenda(agenda) {
    var alvo = $("docPreview");
    if (!alvo) return;
    if (!agenda || !agenda.meses || !agenda.meses.length) {
      alvo.innerHTML = '<p class="muted">Informe a data de início para ver o documento.</p>';
      return;
    }
    alvo.innerHTML =
      renderMensalAgenda(agenda) +
      '<div class="doc-section">' +
      renderResumoDoc(agenda) +
      renderResumoDias(agenda) +
      renderEventosDoc(agenda) +
      renderLegendaDoc(agenda) +
      "</div>";

    // Clicar em um dia útil da prévia do documento também marca/desmarca feriado.
    Array.prototype.forEach.call(alvo.querySelectorAll(".doc-dia[data-date]"), function (td) {
      td.addEventListener("click", function () {
        toggleFeriado(td.getAttribute("data-date"));
      });
    });
  }

  function renderLegendaGrade() {
    return (
      '<div class="cal-legend">' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-parity1"></span> Semana x1</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-parity2"></span> Semana x2</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-free"></span> Feriado (sem aula)</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-sabado"></span> Sábado letivo/reposição</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-part1">01</span> 1ª parte (data em negrito)</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-evento"></span> Dia com evento</span>' +
      '<span class="cal-legend-item"><span class="moved-day">(dia)</span> Aula remanejada</span>' +
      "</div>"
    );
  }

  function renderPreview(d) {
    var html = "";
    var ag = d.agenda || {};
    var sabados = ag.sabados_total;
    if (typeof sabados !== "number") sabados = (ag.sabados_letivos || []).length;
    var totalDoc = ag.total_letivos || 0;
    var segSex =
      typeof ag.letivos_seg_sex === "number"
        ? ag.letivos_seg_sex
        : Math.max(totalDoc - sabados, 0);
    html +=
      '<div class="cal-metrics">' +
      metric(
        "Semanas",
        d.w,
        (d.parametros ? d.parametros.total_semanas : "") + " + " + d.semanas_extras + " reposição",
        "Grade x1/x2 (seg–sex) com " + d.dias_totais + " dias no total."
      ) +
      metric("Feriados na faixa", d.f, "dias úteis") +
      metric(
        "Dias letivos (seg–sex)",
        segSex,
        "sem sábados",
        "Dias letivos de segunda a sexta no período, sem contar os sábados letivos."
      ) +
      metric(
        "Letivos por dia (seg–sex + sábados)",
        (ag.letivos_por_dia || []).join(" / ") || "0 / 0 / 0 / 0 / 0",
        "mínimo " + (ag.meta_por_dia || 0) + " por dia (100/5)",
        "Contagem separada por dia da semana (Seg / Ter / Qua / Qui / Sex), somando " +
          "os sábados letivos ao dia informado no campo Referência. " +
          "Seg–sex: " +
          ((ag.letivos_seg_sex_por_dia || []).join(" / ") || "0 / 0 / 0 / 0 / 0") +
          " + sábados: " +
          ((ag.sabados_por_dia || []).join(" / ") || "0 / 0 / 0 / 0 / 0") +
          ". Cada dia deve ter pelo menos 100/5 = " +
          (ag.meta_por_dia || 0) +
          " dias letivos."
      ) +
      metric(
        "Sábados letivos",
        sabados,
        "referentes a dias úteis",
        "Sábados usados como dia letivo/de reposição; cada um referencia um dia da semana."
      ) +
      metric(
        "Total de dias letivos",
        totalDoc,
        "seg–sex + sábados · igual ao documento",
        "Total do documento oficial: " + segSex + " dias (seg–sex) + " + sabados + " sábados letivos."
      ) +
      metric(
        "Erros (paridade / dia / parte)",
        d.metricas.parity + " / " + d.metricas.weekday + " / " + d.metricas.part,
        "ideal: 0 / 0 / 0 — quanto menor, melhor",
        "Cada número conta aulas remanejadas que perderam a paridade (x1/x2), o dia da semana ou a parte do semestre. Menor é melhor."
      ) +
      "</div>";

    html += renderAjudaMetricas(d);

    if (d.erros && d.erros.length) {
      html +=
        '<div class="cal-alert"><strong>Ajustes necessários:</strong><ul>' +
        d.erros.map(function (e) {
          return "<li>" + esc(e) + "</li>";
        }).join("") +
        "</ul></div>";
    }

    var evPorData = eventosPorData(d.agenda);
    // Sábado de cada semana (eventos de sábado letivo/reposição), casado por data.
    var sabPorData = {};
    ((d.agenda && d.agenda.sabados_letivos) || []).forEach(function (s) {
      sabPorData[s.date] = s;
    });

    html += '<table class="cal-table"><thead><tr><th class="cal-corner">Semana</th>';
    (d.weekdays || []).forEach(function (dia) {
      html += '<th class="cal-day">' + esc(dia) + "</th>";
    });
    html += '<th class="cal-day">Sáb</th>';
    html += "</tr></thead><tbody>";
    (d.linhas || []).forEach(function (linha) {
      html +=
        '<tr><th class="cal-week">' +
        esc(linha.week_label) +
        '<span class="cal-parity">/' +
        esc(linha.parity_label) +
        "</span></th>";
      (linha.columns || []).forEach(function (cell) {
        if (!cell) {
          html += '<td class="cal-cell cal-empty"></td>';
          return;
        }
        var evs = evPorData[cell.date] || [];
        var cls =
          "cal-cell" +
          (cell.free ? " cal-free" : "") +
          (cell.part === 1 ? " cal-part1" : "") +
          (evs.length ? " cal-has-evento" : "");
        var rotuloData = fmtData(cell.date);
        var acao = cell.free
          ? "Feriado — clique para remover"
          : "clique para marcar como feriado";
        var dica = evs.length
          ? rotuloData + " — " + evs.join("; ") + " · " + acao
          : rotuloData + " · " + acao;
        var conteudo = cell.label_html || "";
        if (!conteudo && cell.free) {
          conteudo =
            '<span class="cal-date-free">' +
            esc(cell.date_label || rotuloData) +
            "</span>";
        }
        html +=
          '<td class="' +
          cls +
          '" data-tip="' +
          esc(dica) +
          '" aria-label="' +
          esc(dica) +
          '" style="background:' +
          esc(cell.color) +
          ';" data-date="' +
          esc(cell.date) +
          '"><span class="cal-date">' +
          conteudo +
          "</span></td>";
      });
      var sab = sabPorData[linha.sabado];
      var sabDica = sab
        ? sab.titulo + (sab.referencia ? " — " + sab.referencia : "")
        : "Sábado sem aula";
      html +=
        '<td class="cal-cell cal-sabado' +
        (sab ? " cal-sabado-letivo" : "") +
        '" data-tip="' +
        esc(sabDica) +
        '" aria-label="' +
        esc(sabDica) +
        '"><span class="cal-date">' +
        (sab
          ? esc(sab.label)
          : '<span class="cal-date-vazio">' +
            esc(linha.sabado_label || "") +
            "</span>") +
        "</span></td>";
      html += "</tr>";
    });
    html += "</tbody></table>";
    html += renderLegendaGrade();

    var alvo = $("calPreview");
    alvo.innerHTML = html;
    Array.prototype.forEach.call(alvo.querySelectorAll(".cal-cell[data-date]"), function (td) {
      td.addEventListener("click", function () {
        toggleFeriado(td.getAttribute("data-date"));
      });
    });

    renderAgenda(d.agenda);
  }

  var timer = null;
  function agendarPreview() {
    clearTimeout(timer);
    timer = setTimeout(preview, 180);
  }

  function preview() {
    postJSON(BASE + "api/preview/", payload()).then(function (d) {
      if (d && (d.linhas || d.agenda)) renderPreview(d);
    });
  }

  // ---- Feriados nacionais ------------------------------------------------
  function anosDoPeriodo() {
    var inicio = $("fInicio").value;
    if (!inicio) return [];
    var semanas = parseInt($("fSemanas").value || "0", 10);
    var d = new Date(inicio + "T00:00:00");
    var fim = new Date(d.getTime() + semanas * 7 * 86400000);
    var anos = [];
    for (var y = d.getFullYear(); y <= fim.getFullYear(); y++) anos.push(y);
    return anos;
  }

  function carregarNacionais() {
    var anos = anosDoPeriodo();
    if (!anos.length) {
      msg("Informe a data de início antes de carregar os feriados nacionais.", "erro");
      return;
    }
    Promise.all(
      anos.map(function (ano) {
        return fetch(BASE + "api/feriados-nacionais/?ano=" + ano).then(function (r) {
          return r.json();
        });
      })
    ).then(function (respostas) {
      var total = 0;
      respostas.forEach(function (r) {
        (r.feriados || []).forEach(function (f) {
          if (!temFeriado(f.data)) total++;
          addFeriado(f.data, f.descricao, "nacional");
        });
      });
      renderChips();
      preview();
      msg(total + " feriado(s) nacional(is) adicionado(s).", "ok");
    });
  }

  // ---- Salvar / nova versão ---------------------------------------------
  function marcarPendenteIA(pendente) {
    var el = $("iaPendente");
    if (el) el.hidden = !pendente;
  }

  function salvar() {
    postJSON(BASE + "api/salvar/", payload())
      .then(function (res) {
        if (res && res.ok) {
          msg("Versão " + res.versao + " salva.", "ok");
          marcarPendenteIA(false);
          if (res.dados) renderPreview(res.dados);
        } else {
          msg(((res && res.erros) || ["Erro ao salvar."]).join(" "), "erro");
        }
      })
      .catch(function () {
        msg("Falha de comunicação ao salvar.", "erro");
      });
  }

  function novaVersao() {
    inicial = {};
    state.feriados = [];
    state.eventos = [];
    state.eventoEditandoIdx = null;
    fill();
    limparFormEvento();
    atualizarBotaoEvento();
    renderChips();
    renderEventos();
    marcarPendenteIA(false);
    atualizarNormaIA();
    preview();
    msg("Novo formulário pronto para uma nova versão.", "ok");
  }

  // ---- Preenchimento com IA (LLM) ----------------------------------------
  // Fluxo em duas etapas: a IA gera uma PRÉVIA (nada é gravado) que pode ser
  // editada aqui; "Aplicar ao editor" leva os itens para as tabelas/chips do
  // editor e só "Salvar versão" grava no banco.
  var IA = inicial.llm || {};
  var iaState = {
    modo: "gerar",
    eventos: [],
    feriados: [],
    avisos: [],
    observacoes: [],
    requisitos: null,
    selecionados: {},
    agenda: null,
    estatisticas: null,
    editando: null,
    gerado: false
  };
  var iaTimer = null;

  function normaDaModalidadeIA() {
    var valor = $("fModalidade") ? $("fModalidade").value : "";
    return (IA.normas || {})[valor] || null;
  }

  function rotuloNormaIA() {
    var info = normaDaModalidadeIA();
    if (!info) return "";
    return info.norma + " — " + info.titulo + " (" + info.total_itens + " itens)";
  }

  function atualizarNormaIA() {
    var alvo = $("iaNorma");
    if (alvo) alvo.textContent = rotuloNormaIA() ? "Norma aplicada: " + rotuloNormaIA() : "";
  }

  function modoIA(modo) {
    iaState.modo = modo || "gerar";
    var gerar = iaState.modo === "gerar";
    var titulo = $("iaTitulo");
    if (titulo) titulo.textContent = gerar ? "Preencher eventos com IA" : "Verificar eventos com IA";
    var botao = $("iaGerar");
    if (botao) botao.textContent = gerar ? "Gerar prévia" : "Verificar eventos";
    var ajuda = $("iaAjudaVerificar");
    if (ajuda) ajuda.hidden = gerar;
    var camposGerar = $("iaCamposGerar");
    if (camposGerar) camposGerar.hidden = !gerar;
    var aplicar = $("iaAplicar");
    if (aplicar) aplicar.hidden = !gerar;
    var selecionados = $("iaAplicarSelecionados");
    if (selecionados) selecionados.hidden = gerar;
    var marcarTodos = $("iaMarcarTodos");
    if (marcarTodos) marcarTodos.hidden = gerar;
    var blocoEventos = $("iaBlocoEventos");
    if (blocoEventos) blocoEventos.hidden = !gerar;
    var blocoFeriados = $("iaBlocoFeriados");
    if (blocoFeriados) blocoFeriados.hidden = !gerar;
    atualizarNormaIA();
  }

  function msgIA(texto, tipo) {
    var el = $("iaMsg");
    if (!el) return;
    el.textContent = texto;
    el.className =
      "editor-msg" +
      (tipo === "ok" ? " editor-msg-ok" : tipo === "erro" ? " editor-msg-erro" : "");
  }

  function provedorSelecionadoIA() {
    var sel = $("iaProvedor");
    return sel ? sel.value : "";
  }

  function labelProvedorIA() {
    var valor = provedorSelecionadoIA();
    var achado = (IA.provedores || []).filter(function (p) {
      return p.valor === valor;
    })[0];
    return achado ? achado.label : valor;
  }

  function preencherSelectsIA() {
    var lista = IA.provedores || [];
    var sel = $("iaProvedor");
    if (sel) {
      sel.innerHTML = lista
        .map(function (p) {
          var rotulo =
            p.label + (p.modelo ? " — " + p.modelo : "") + (p.disponivel ? "" : " (sem chave)");
          return (
            '<option value="' +
            esc(p.valor) +
            '"' +
            (p.disponivel ? "" : " disabled") +
            ">" +
            esc(rotulo) +
            "</option>"
          );
        })
        .join("");
      var escolhido =
        lista.filter(function (p) {
          return p.disponivel && p.valor === IA.padrao;
        })[0] ||
        lista.filter(function (p) {
          return p.disponivel;
        })[0];
      if (escolhido) sel.value = escolhido.valor;
    }
    var tipos = $("iaEvTipo");
    if (tipos && !tipos.options.length) {
      tipos.innerHTML += Object.keys(TIPOS_EVENTO)
        .map(function (t) {
          return '<option value="' + esc(t) + '">' + esc(TIPOS_EVENTO[t]) + "</option>";
        })
        .join("");
    }
    var refs = $("iaEvReferencia");
    if (refs && !refs.options.length) {
      refs.innerHTML =
        '<option value="">— não se aplica —</option>' +
        Object.keys(DIAS_SEMANA)
          .map(function (d) {
            return '<option value="' + esc(d) + '">' + esc(DIAS_SEMANA[d]) + "</option>";
          })
          .join("");
    }
  }

  function mostrarPassoIA(passo) {
    var entrada = $("iaStepEntrada");
    var previa = $("iaStepPrevia");
    if (entrada) entrada.hidden = passo !== "entrada";
    if (previa) previa.hidden = passo !== "previa";
  }

  function abrirIA() {
    abrirIAComo("gerar");
  }

  function abrirIAComo(modo) {
    var modal = $("iaModal");
    if (!modal) return;
    if (!IA.habilitado) {
      msg(
        "Nenhum provedor de IA está configurado. Defina a chave de API em uma variável " +
          "de ambiente (DEEPSEEK_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY ou " +
          "ANTHROPIC_API_KEY), reinicie o servidor e recarregue esta página.",
        "erro"
      );
      return;
    }
    preencherSelectsIA();
    modoIA(modo);
    iaState.requisitos = null;
    iaState.observacoes = [];
    iaState.selecionados = {};
    iaState.gerado = false;
    iaState.editando = null;
    if (iaState.modo === "gerar") {
      iaState.eventos = [];
      iaState.feriados = [];
    }
    $("iaCidade").value = $("iaCidade").value || IA.cidade || "";
    $("iaEstado").value = $("iaEstado").value || IA.estado || "";
    $("iaPais").value = $("iaPais").value || IA.pais || "Brasil";
    mostrarPassoIA("entrada");
    msgIA("", "");
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "open");
    $("iaCidade").focus();
  }

  function fecharIA() {
    var modal = $("iaModal");
    if (!modal) return;
    if (typeof modal.close === "function" && modal.open) modal.close();
    else modal.removeAttribute("open");
  }

  function gerarIA() {
    var gerar = iaState.modo === "gerar";
    var cidade = $("iaCidade").value.trim();
    var estado = $("iaEstado").value.trim();
    if (gerar && (!cidade || !estado)) {
      msgIA("Informe a cidade e o estado (UF) onde fica a unidade.", "erro");
      return;
    }
    var p = payload();
    if (!p.data_inicio || !p.data_fim) {
      msgIA(
        "Informe o início e o término do período letivo (bloco 1.2) antes de usar a IA.",
        "erro"
      );
      return;
    }

    var botao = $("iaGerar");
    var rotulo = botao.textContent;
    var iniciadoEm = Date.now();
    botao.disabled = true;
    botao.textContent = "Consultando…";
    msgIA(
      (gerar ? "Gerando eventos em " : "Verificando os eventos com ") +
        labelProvedorIA() +
        "… aguarde (pode levar até " +
        (IA.timeout || 120) +
        "s).",
      ""
    );

    var corpo = {
      cidade: cidade,
      estado: estado,
      pais: $("iaPais").value.trim() || "Brasil",
      provedor: provedorSelecionadoIA(),
      modelo: $("iaModelo").value.trim(),
      instituicao: p.instituicao,
      curso: p.curso,
      modalidade: p.modalidade,
      data_inicio: p.data_inicio,
      data_fim: p.data_fim,
      total_semanas: p.total_semanas,
      semanas_primeira_parte: p.semanas_primeira_parte,
      dias_letivos_previstos: p.dias_letivos_previstos,
      dias_letivos_por_mes: p.dias_letivos_por_mes,
      feriados: p.feriados,
      eventos: p.eventos
    };
    if (gerar) corpo.completar_sabados = $("iaCompletarSabados").checked;

    postJSON(BASE + (gerar ? "api/ia/eventos/" : "api/ia/verificar/"), corpo)
      .then(function (d) {
        botao.disabled = false;
        botao.textContent = rotulo;
        if (!d || !d.ok) {
          msgIA(((d && d.erros) || ["Não foi possível concluir a operação."]).join(" "), "erro");
          return;
        }
        iaState.avisos = d.avisos || [];
        iaState.observacoes = d.observacoes || [];
        iaState.requisitos = d.requisitos || null;
        iaState.editando = null;
        iaState.selecionados = {};
        if (gerar) {
          iaState.eventos = d.eventos || [];
          iaState.feriados = d.feriados || [];
          iaState.estatisticas = d.estatisticas || {};
          iaState.agenda = d.agenda ? recorteAgenda(d.agenda) : null;
        } else {
          iaState.agenda = null;
          iaState.estatisticas = null;
        }
        // Itens faltantes que vieram com sugestão já entram marcados para aplicar.
        ((iaState.requisitos || {}).itens || []).forEach(function (it) {
          if (it.situacao === "faltando" && it.evento_sugerido) {
            iaState.selecionados[it.codigo] = true;
          }
        });
        iaState.gerado = true;
        renderIA();
        mostrarPassoIA("previa");
        if (!gerar) atualizarAgendaEditorIA();
        var segundos = Math.max(1, Math.round((Date.now() - iniciadoEm) / 1000));
        var norma = (iaState.requisitos || {}).norma || "";
        msgIA(
          (gerar ? "Prévia gerada por " : "Verificação concluída por ") +
            (d.provedor_label || d.provedor) +
            (d.modelo ? " (" + d.modelo + ")" : "") +
            " em " +
            segundos +
            "s" +
            (norma ? " — " + norma : "") +
            (gerar
              ? ". Revise, edite e clique em “Aplicar ao editor”."
              : ". Marque os itens faltantes e clique em “Aplicar selecionados ao editor”."),
          "ok"
        );
      })
      .catch(function () {
        botao.disabled = false;
        botao.textContent = rotulo;
        msgIA("Não foi possível falar com o servidor.", "erro");
      });
  }

  function renderResumoIA() {
    var alvo = $("iaResumo");
    if (!alvo) return;
    var ag = iaState.agenda || {};
    var est = iaState.estatisticas || {};
    var req = iaState.requisitos || {};
    var resumoReq = req.resumo || null;
    var previsto =
      (ag.validacao && ag.validacao.previsto) || parseInt($("fPrevistos").value || "0", 10);
    var sabados = typeof ag.sabados_total === "number" ? ag.sabados_total : 0;
    var faltandoSab = (est.faltando || []).reduce(function (a, b) {
      return a + b;
    }, 0);
    var porDiaOk = !ag.validacao || ag.validacao.por_dia_ok !== false;
    var comSugestao = (req.itens || []).filter(function (i) {
      return i.situacao === "faltando" && i.evento_sugerido;
    }).length;

    var html = '<div class="cal-metrics">';
    if (resumoReq) {
      html += metric(
        (req.norma || "Norma") + " — itens conferidos",
        resumoReq.total,
        req.titulo || "",
        "Conferência automática dos requisitos da norma da modalidade."
      );
      html += metric("Itens atendidos", resumoReq.atendidos, "com evidência no calendário");
      html += metric("Itens faltando", resumoReq.faltando, comSugestao + " com sugestão da IA");
      html += metric("Itens a conferir", resumoReq.conferir, "verificação manual");
    }
    if (iaState.modo === "gerar") {
      html += metric(
        "Eventos sugeridos",
        iaState.eventos.length,
        (est.sabados_criados || 0) + " sábado(s) pelo sistema"
      );
      html += metric("Feriados do período", iaState.feriados.length, "federal + estadual + municipal");
    }
    html += metric("Total de dias letivos", ag.total_letivos || 0, "meta: " + (previsto || "—"));
    html += metric(
      "Dias por dia da semana",
      (ag.letivos_por_dia || []).join(" / ") || "0 / 0 / 0 / 0 / 0",
      "mínimo " + (ag.meta_por_dia || 0) + " por dia"
    );
    html += metric("Sábados letivos", sabados, "distribuídos por Referência");
    html += metric(
      "Situação da carga horária",
      porDiaOk && !faltandoSab ? "OK" : "Faltam " + (faltandoSab || "?"),
      porDiaOk ? "todos os dias na meta" : "abaixo da meta em algum dia"
    );
    html += "</div>";
    alvo.innerHTML = html;
  }

  function renderIA() {
    renderResumoIA();
    pintarDiasIA();
    renderEventosIA();
    renderFeriadosIA();
    renderRequisitosIA();
    renderObservacoesIA();
    renderAvisosIA();
  }

  function renderEventosIA() {
    var tbody = $("iaEventosBody");
    if (!tbody) return;
    var ordenados = iaState.eventos.slice().sort(function (a, b) {
      return a.data_inicio < b.data_inicio ? -1 : 1;
    });
    tbody.innerHTML = ordenados
      .map(function (e) {
        var i = iaState.eventos.indexOf(e);
        var ref =
          e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
            ? ""
            : DIAS_SEMANA[e.dia_semana_referencia] || "";
        return (
          "<tr" +
          (i === iaState.editando ? ' class="row-editando"' : "") +
          ">" +
          "<td>" +
          esc(e.data_inicio.split("-").reverse().join("/")) +
          "</td><td>" +
          (e.data_fim ? esc(e.data_fim.split("-").reverse().join("/")) : "—") +
          "</td><td>" +
          esc(e.titulo) +
          "</td><td>" +
          esc(TIPOS_EVENTO[e.tipo] || e.tipo) +
          "</td><td>" +
          esc(ref) +
          "</td>" +
          '<td class="evento-acoes">' +
          '<button type="button" class="btn-editar" data-edit="' +
          i +
          '" title="Editar evento" aria-label="Editar evento">&#9998;</button>' +
          '<button type="button" class="chip-remove" data-idx="' +
          i +
          '" aria-label="Remover">&times;</button>' +
          "</td></tr>"
        );
      })
      .join("");
    Array.prototype.forEach.call(tbody.querySelectorAll(".btn-editar"), function (btn) {
      btn.addEventListener("click", function () {
        editarEventoIA(parseInt(btn.getAttribute("data-edit"), 10));
      });
    });
    Array.prototype.forEach.call(tbody.querySelectorAll(".chip-remove"), function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-idx"), 10);
        iaState.eventos.splice(idx, 1);
        if (iaState.editando === idx) iaState.editando = null;
        else if (iaState.editando !== null && iaState.editando > idx) iaState.editando -= 1;
        atualizarBotaoEventoIA();
        renderIA();
        recalcularIA();
      });
    });
  }

  function limparFormEventoIA() {
    $("iaEvTitulo").value = "";
    $("iaEvInicio").value = "";
    $("iaEvFim").value = "";
    $("iaEvReferencia").value = "";
    $("iaEvDestaque").checked = false;
  }

  function atualizarBotaoEventoIA() {
    var btn = $("iaAddEvento");
    var cancelar = $("iaCancelarEvento");
    var editando = iaState.editando !== null;
    if (btn) btn.textContent = editando ? "Salvar alterações" : "Adicionar evento";
    if (cancelar) cancelar.hidden = !editando;
  }

  function editarEventoIA(idx) {
    var e = iaState.eventos[idx];
    if (!e) return;
    $("iaEvTitulo").value = e.titulo || "";
    $("iaEvTipo").value = e.tipo || "evento";
    $("iaEvInicio").value = e.data_inicio || "";
    $("iaEvFim").value = e.data_fim || "";
    $("iaEvReferencia").value =
      e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
        ? ""
        : String(e.dia_semana_referencia);
    $("iaEvDestaque").checked = !!e.destaque;
    iaState.editando = idx;
    atualizarBotaoEventoIA();
    renderEventosIA();
    $("iaEvTitulo").focus();
  }

  function salvarEventoIA() {
    var titulo = $("iaEvTitulo").value.trim();
    var inicio = $("iaEvInicio").value;
    if (!titulo || !inicio) {
      msgIA("Informe o título e a data inicial do evento.", "erro");
      return;
    }
    var ref = $("iaEvReferencia").value;
    var idx = iaState.editando;
    var anterior = idx !== null ? iaState.eventos[idx] : null;
    var evento = {
      titulo: titulo,
      tipo: $("iaEvTipo").value,
      data_inicio: inicio,
      data_fim: $("iaEvFim").value || "",
      dia_semana_referencia: ref === "" ? null : parseInt(ref, 10),
      descricao: anterior ? anterior.descricao || "" : "",
      destaque: $("iaEvDestaque").checked,
      sugerido_ia: true
    };
    if (idx !== null) {
      iaState.eventos[idx] = evento;
      iaState.editando = null;
      msgIA("Evento da prévia atualizado (ainda não salvo).", "ok");
    } else {
      iaState.eventos.push(evento);
      msgIA("Evento incluído na prévia (ainda não salvo).", "ok");
    }
    limparFormEventoIA();
    atualizarBotaoEventoIA();
    renderIA();
    recalcularIA();
  }

  function cancelarEdicaoEventoIA() {
    iaState.editando = null;
    limparFormEventoIA();
    atualizarBotaoEventoIA();
    renderEventosIA();
  }

  function renderFeriadosIA() {
    var ul = $("iaFeriadosList");
    if (!ul) return;
    var ordenados = iaState.feriados.slice().sort(function (a, b) {
      return a.data < b.data ? -1 : 1;
    });
    ul.innerHTML = ordenados
      .map(function (f, i) {
        var rotulo = f.data.split("-").reverse().join("/");
        var tipo = f.tipo === "ponto_facultativo" ? "Ponto facultativo" : "Feriado";
        var esfera = f.esfera ? " · " + f.esfera : "";
        var confianca = f.confianca === "baixa" ? ' <em class="ia-conf-baixa">confiança baixa</em>' : "";
        return (
          '<li class="chip chip-removable">' +
          '<button type="button" class="chip-remove" data-idx="' +
          i +
          '" aria-label="Remover">&times;</button> ' +
          "<strong>" +
          esc(rotulo) +
          "</strong> " +
          esc(tipo) +
          esc(esfera) +
          " — " +
          esc(f.descricao || "") +
          confianca +
          "</li>"
        );
      })
      .join("");
    Array.prototype.forEach.call(ul.querySelectorAll(".chip-remove"), function (btn) {
      btn.addEventListener("click", function () {
        iaState.feriados.splice(parseInt(btn.getAttribute("data-idx"), 10), 1);
        renderIA();
        recalcularIA();
      });
    });
  }

  function renderAvisosIA() {
    var alvo = $("iaAvisos");
    if (!alvo) return;
    var itens = iaState.avisos || [];
    if (!itens.length) {
      alvo.innerHTML = "";
      return;
    }
    alvo.innerHTML =
      '<div class="cal-alert"><strong>Atenção antes de aplicar:</strong><ul>' +
      itens
        .map(function (a) {
          return "<li>" + esc(a) + "</li>";
        })
        .join("") +
      "</ul></div>";
  }

  function renderRequisitosIA() {
    var alvo = $("iaRequisitos");
    if (!alvo) return;
    var req = iaState.requisitos || {};
    var itens = req.itens || [];
    var titulo = $("iaRequisitosTitulo");
    if (titulo) {
      titulo.textContent = req.norma
        ? "Requisitos " + req.norma + " — " + (req.titulo || "")
        : "Requisitos da norma";
    }
    if (!itens.length) {
      alvo.innerHTML = '<p class="muted">Gere ou verifique para ver o checklist.</p>';
      return;
    }
    var linhas = itens
      .map(function (it) {
        var marca = "";
        if (it.evento_sugerido && it.situacao === "faltando" && iaState.modo === "verificar") {
          marca =
            '<input type="checkbox" class="ia-req-check" data-codigo="' +
            esc(it.codigo) +
            '"' +
            (iaState.selecionados[it.codigo] ? " checked" : "") +
            ">";
        }
        var evidencias = (it.evidencias || [])
          .map(function (e) {
            return "<li>" + esc(e) + "</li>";
          })
          .join("");
        var sugestao = it.evento_sugerido
          ? '<p class="ia-req-sugestao">Sugestão da IA: <strong>' +
            esc(it.evento_sugerido.titulo) +
            "</strong> em " +
            esc((it.evento_sugerido.data_inicio || "").split("-").reverse().join("/")) +
            (it.evento_sugerido.tipo ? " · " + esc(TIPOS_EVENTO[it.evento_sugerido.tipo] || it.evento_sugerido.tipo) : "") +
            (it.evento_sugerido.dia_semana_referencia === null ||
            it.evento_sugerido.dia_semana_referencia === undefined
              ? ""
              : " · referente à " + esc(DIAS_SEMANA[it.evento_sugerido.dia_semana_referencia] || "")) +
            "</p>"
          : "";
        return (
          '<div class="ia-req-item ia-req-' +
          esc(it.situacao) +
          '">' +
          marca +
          '<div class="ia-req-texto">' +
          '<span class="ia-req-badge">' +
          esc(it.codigo) +
          "</span> " +
          esc(it.descricao) +
          ' <em class="ia-req-status">' +
          esc(it.situacao_label || it.situacao) +
          "</em>" +
          (evidencias ? '<ul class="ia-req-ev">' + evidencias + "</ul>" : "") +
          (it.motivo ? '<p class="muted">' + esc(it.motivo) + "</p>" : "") +
          sugestao +
          "</div></div>"
        );
      })
      .join("");
    alvo.innerHTML = linhas;

    Array.prototype.forEach.call(alvo.querySelectorAll(".ia-req-check"), function (chk) {
      chk.addEventListener("change", function () {
        var codigo = chk.getAttribute("data-codigo");
        if (chk.checked) iaState.selecionados[codigo] = true;
        else delete iaState.selecionados[codigo];
      });
    });
  }

  function renderObservacoesIA() {
    var alvo = $("iaObservacoes");
    if (!alvo) return;
    var itens = iaState.observacoes || [];
    if (!itens.length) {
      alvo.innerHTML = "";
      return;
    }
    alvo.innerHTML =
      '<div class="cal-alert"><strong>Observações da IA:</strong><ul>' +
      itens
        .map(function (o) {
          return "<li>" + esc(o) + "</li>";
        })
        .join("") +
      "</ul></div>";
  }

  // Eventos sugeridos pela IA nos itens faltantes da norma (modo verificar).
  function sugeridosIA() {
    var itens = ((iaState.requisitos || {}).itens || []).filter(function (it) {
      return it.situacao === "faltando" && it.evento_sugerido;
    });
    return itens;
  }

  function marcarTodosIA() {
    sugeridosIA().forEach(function (it) {
      iaState.selecionados[it.codigo] = true;
    });
    renderRequisitosIA();
    msgIA("Todos os itens faltantes com sugestão foram marcados.", "ok");
  }

  function aplicarSelecionadosIA() {
    var escolhidos = sugeridosIA().filter(function (it) {
      return iaState.selecionados[it.codigo];
    });
    if (!escolhidos.length) {
      msgIA("Marque pelo menos um item faltante para aplicar no editor.", "erro");
      return;
    }
    var inseridos = 0;
    var chaves = {};
    state.eventos.forEach(function (e) {
      chaves[e.data_inicio + "|" + String(e.titulo || "").toLowerCase()] = true;
    });
    escolhidos.forEach(function (it) {
      var e = it.evento_sugerido;
      var chave = (e.data_inicio || "") + "|" + String(e.titulo || "").toLowerCase();
      if (!e.data_inicio || chaves[chave]) return;
      chaves[chave] = true;
      state.eventos.push({
        titulo: e.titulo,
        tipo: e.tipo || "evento",
        data_inicio: e.data_inicio,
        data_fim: e.data_fim || "",
        dia_semana_referencia:
          e.dia_semana_referencia === undefined ? null : e.dia_semana_referencia,
        descricao: e.descricao || "",
        destaque: !!e.destaque
      });
      inseridos += 1;
    });
    state.eventoEditandoIdx = null;
    fecharIA();
    renderEventos();
    preview();
    var pendente = $("iaPendente");
    if (pendente) pendente.hidden = false;
    msg(
      inseridos +
        " item(ns) da norma aplicado(s) ao editor. NADA foi salvo ainda — confira e " +
        "clique em “Salvar versão”.",
      "ok"
    );
  }

  function payloadIA() {
    var p = payload();
    p.feriados = iaState.feriados.map(function (f) {
      return {
        data: f.data,
        descricao: f.descricao || "",
        origem: f.origem || "manual",
        tipo: f.tipo || "feriado"
      };
    });
    p.eventos = iaState.eventos;
    return p;
  }

  function recorteAgenda(ag) {
    ag = ag || {};
    return {
      dias_por_dia: ag.dias_por_dia,
      meta_por_dia: ag.meta_por_dia,
      letivos_por_dia: ag.letivos_por_dia,
      letivos_seg_sex_por_dia: ag.letivos_seg_sex_por_dia,
      sabados_por_dia: ag.sabados_por_dia,
      sabados_total: ag.sabados_total,
      sabados_sem_referencia: ag.sabados_sem_referencia,
      total_letivos: ag.total_letivos,
      letivos_seg_sex: ag.letivos_seg_sex,
      validacao: ag.validacao
    };
  }

  function pintarDiasIA() {
    var dias = $("iaDiasSemana");
    if (dias) dias.innerHTML = iaState.agenda ? renderResumoDias(iaState.agenda) : "";
  }

  // Recalcula a carga horária no SERVIDOR (mesmo algoritmo do documento) sempre
  // que a prévia é alterada aqui.
  function recalcularIA() {
    if (!iaState.gerado || iaState.modo !== "gerar") return;
    if (iaTimer) clearTimeout(iaTimer);
    iaTimer = setTimeout(function () {
      postJSON(BASE + "api/preview/", payloadIA()).then(function (d) {
        if (!d || !d.agenda) return;
        iaState.agenda = recorteAgenda(d.agenda);
        renderResumoIA();
        pintarDiasIA();
      });
    }, 350);
  }

  // No modo verificar, a carga horária exibida é a do estado atual do editor.
  function atualizarAgendaEditorIA() {
    postJSON(BASE + "api/preview/", payload()).then(function (d) {
      if (!d || !d.agenda) return;
      iaState.agenda = recorteAgenda(d.agenda);
      renderResumoIA();
      pintarDiasIA();
    });
  }

  function aplicarIA() {
    var modo = $("iaModo").value;
    var novosEventos = iaState.eventos.map(function (e) {
      return {
        titulo: e.titulo,
        tipo: e.tipo,
        data_inicio: e.data_inicio,
        data_fim: e.data_fim || "",
        dia_semana_referencia:
          e.dia_semana_referencia === undefined ? null : e.dia_semana_referencia,
        descricao: e.descricao || "",
        destaque: !!e.destaque
      };
    });
    var novosFeriados = iaState.feriados.map(function (f) {
      return {
        data: f.data,
        descricao: f.descricao || "",
        origem: f.origem || "manual",
        tipo: f.tipo === "ponto_facultativo" ? "ponto_facultativo" : "feriado"
      };
    });

    if (modo === "substituir") {
      state.eventos = novosEventos;
      state.feriados = novosFeriados;
    } else {
      var chavesEvento = {};
      state.eventos.forEach(function (e) {
        chavesEvento[e.data_inicio + "|" + String(e.titulo || "").toLowerCase()] = true;
      });
      novosEventos.forEach(function (e) {
        var chave = e.data_inicio + "|" + String(e.titulo || "").toLowerCase();
        if (chavesEvento[chave]) return;
        chavesEvento[chave] = true;
        state.eventos.push(e);
      });
      var datasFeriado = {};
      state.feriados.forEach(function (f) {
        datasFeriado[f.data] = true;
      });
      novosFeriados.forEach(function (f) {
        if (datasFeriado[f.data]) return;
        datasFeriado[f.data] = true;
        state.feriados.push(f);
      });
    }

    state.eventoEditandoIdx = null;
    fecharIA();
    atualizarBotaoEventoIA();
    limparFormEventoIA();
    renderEventos();
    renderChips();
    preview();
    var pendente = $("iaPendente");
    if (pendente) pendente.hidden = false;
    msg(
      "Prévia da IA aplicada ao editor (" +
        novosEventos.length +
        " evento(s) e " +
        novosFeriados.length +
        " feriado(s), modo " +
        modo +
        "). NADA foi salvo ainda — confira e clique em “Salvar versão”.",
      "ok"
    );
  }

  // ---- Exibir/ocultar blocos (preenchimento e prévias) -------------------
  // Facilita a navegação: à medida que o calendário cresce, o usuário pode
  // esconder o preenchimento (para focar nas prévias) ou vice-versa. A escolha
  // é lembrada entre visitas via localStorage.
  var BLOCOS = {
    inputs: { chave: "editor-hide-inputs", rotulo: "preenchimento" },
    previews: { chave: "editor-hide-previews", rotulo: "prévias" }
  };

  function lerOculto(chave) {
    try {
      return localStorage.getItem(chave) === "1";
    } catch (e) {
      return false;
    }
  }

  function gravarOculto(chave, oculto) {
    try {
      localStorage.setItem(chave, oculto ? "1" : "0");
    } catch (e) {
      /* localStorage indisponível — ignora */
    }
  }

  function aplicarBloco(nome, oculto) {
    var cfg = BLOCOS[nome];
    if (!cfg) return;
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-block="' + nome + '"]'),
      function (el) {
        if (oculto) el.setAttribute("hidden", "hidden");
        else el.removeAttribute("hidden");
      }
    );
    var btn = document.querySelector('[data-toggle-block="' + nome + '"]');
    if (btn) {
      btn.setAttribute("aria-pressed", oculto ? "true" : "false");
      btn.textContent = (oculto ? "Mostrar " : "Ocultar ") + cfg.rotulo;
    }
    gravarOculto(cfg.chave, oculto);
  }

  function alternarBloco(nome) {
    var cfg = BLOCOS[nome];
    if (cfg) aplicarBloco(nome, !lerOculto(cfg.chave));
  }

  function mostrarTudo() {
    aplicarBloco("inputs", false);
    aplicarBloco("previews", false);
  }

  Array.prototype.forEach.call(
    document.querySelectorAll("[data-toggle-block]"),
    function (btn) {
      var nome = btn.getAttribute("data-toggle-block");
      btn.addEventListener("click", function () {
        if (nome === "tudo") mostrarTudo();
        else alternarBloco(nome);
      });
    }
  );

  // Restaura a preferência salva (aplicarBloco também sincroniza os botões).
  aplicarBloco("inputs", lerOculto(BLOCOS.inputs.chave));
  aplicarBloco("previews", lerOculto(BLOCOS.previews.chave));

  // ---- Inicialização -----------------------------------------------------
  fill();
  renderChips();
  renderEventos();
  ["fInicio", "fDataFim", "fSemanas", "fSemanas1", "fPrevistos"].forEach(function (id) {
    $(id).addEventListener("change", agendarPreview);
    $(id).addEventListener("input", agendarPreview);
  });
  $("btnAddFeriado").addEventListener("click", function () {
    var valor = $("fFeriado").value;
    if (!valor) return;
    var dia = new Date(valor + "T00:00:00").getDay();
    if (dia === 0 || dia === 6) {
      msg("Selecione um dia útil (segunda a sexta).", "erro");
      return;
    }
    addFeriado(valor, "", "manual", $("fFeriadoTipo").value);
    $("fFeriado").value = "";
    renderChips();
    preview();
  });
  $("btnAddEvento").addEventListener("click", salvarEvento);
  $("btnCancelarEvento").addEventListener("click", cancelarEdicaoEvento);
  $("btnNacionais").addEventListener("click", carregarNacionais);
  $("btnSalvar").addEventListener("click", salvar);
  $("btnNovo").addEventListener("click", novaVersao);

  // ---- Preenchimento/verificação por IA ----------------------------------
  if ($("btnIA")) $("btnIA").addEventListener("click", abrirIA);
  if ($("btnIAVerificar")) {
    $("btnIAVerificar").addEventListener("click", function () {
      abrirIAComo("verificar");
    });
  }
  if ($("fModalidade")) $("fModalidade").addEventListener("change", atualizarNormaIA);
  if ($("iaGerar")) $("iaGerar").addEventListener("click", gerarIA);
  if ($("iaAplicar")) $("iaAplicar").addEventListener("click", aplicarIA);
  if ($("iaAplicarSelecionados")) {
    $("iaAplicarSelecionados").addEventListener("click", aplicarSelecionadosIA);
  }
  if ($("iaMarcarTodos")) $("iaMarcarTodos").addEventListener("click", marcarTodosIA);
  if ($("iaRegerar")) $("iaRegerar").addEventListener("click", gerarIA);
  if ($("iaVoltar")) {
    $("iaVoltar").addEventListener("click", function () {
      mostrarPassoIA("entrada");
    });
  }
  if ($("iaFechar")) $("iaFechar").addEventListener("click", fecharIA);
  if ($("iaCancelar")) $("iaCancelar").addEventListener("click", fecharIA);
  if ($("iaAddEvento")) $("iaAddEvento").addEventListener("click", salvarEventoIA);
  if ($("iaCancelarEvento")) {
    $("iaCancelarEvento").addEventListener("click", cancelarEdicaoEventoIA);
  }

  if ($("fInicio").value) preview();
  else {
    $("calPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver a grade.</p>';
    $("docPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver o documento.</p>';
  }
})();
