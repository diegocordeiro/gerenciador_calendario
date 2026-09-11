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
    atualizarMensagens();
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
    atualizarCabecalho();
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

  // Explicação da métrica "Aulas remanejadas fora do padrão" com a leitura dos
  // valores atuais do calendário.
  function renderAjudaMetricas(d) {
    var m = (d && d.metricas) || { parity: 0, weekday: 0, part: 0 };
    return (
      '<div class="cal-help">' +
      '<strong>Como ler “Aulas remanejadas fora do padrão”</strong>' +
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
            ["fora", "nao_letivo", "letivo_sabado", "reposicao"].indexOf(c.status) === -1;
          var titulo = rotulo + " — " + (c.status_label || "");
          if (c.eventos && c.eventos.length) titulo += " — " + c.eventos.join("; ");
          if (clicavel) titulo += " · Clique para marcar/desmarcar feriado";
          html +=
            '<td class="doc-dia doc-dia-' +
            esc(c.status) +
            (c.letivo ? " doc-dia-conta" : "") +
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
        (mes.reposicoes ? " • Sábados de reposição: " + esc(mes.reposicoes) : "") +
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
    // Rodapé = soma das colunas (quando o servidor manda `totais_tabela`), para a
    // conta sempre fechar com as linhas. O "Mínimo" é por dia na linha e o mínimo
    // do semestre (mínimo × 5) no rodapé.
    var tot = agenda.totais_tabela || {};
    var segSexTotal = tot.seg_sex !== undefined ? tot.seg_sex : agenda.letivos_seg_sex;
    var sabadosTotal =
      tot.sabados !== undefined
        ? tot.sabados
        : agenda.sabados_contabilizados !== undefined
        ? agenda.sabados_contabilizados
        : agenda.sabados_total;
    var letivosTotal = tot.total !== undefined ? tot.total : agenda.total_letivos;
    var minimoSemestre =
      tot.minimo_semestre !== undefined
        ? tot.minimo_semestre
        : agenda.meta_por_dia
        ? agenda.meta_por_dia * 5
        : previsto;
    return (
      "<h3>Dias letivos por dia da semana</h3>" +
      '<p class="muted">Contagem de <strong>segunda a sexta, em separado</strong>. Os ' +
      "<strong>sábados letivos</strong> entram somados ao " +
      "<strong>dia da semana do campo “Referência”</strong> do evento. A meta é " +
      "distribuída pelos 5 dias úteis (ex.: 100/5 = 20 por dia). O tipo " +
      "<strong>“Sábado de reposição” não entra na carga horária</strong>.</p>" +
      '<table class="doc-table doc-table-dias"><thead><tr>' +
      "<th>Dia da semana</th><th>Seg–sex</th><th>Sábados</th><th>Total</th><th>Mínimo" +
      (previsto ? " (" + esc(previsto) + "/5)" : "") +
      "</th><th>Situação</th></tr></thead><tbody>" +
      linhas +
      '</tbody><tfoot><tr><th>Total</th><td>' +
      esc(segSexTotal) +
      "</td><td>" +
      esc(sabadosTotal) +
      "</td><td>" +
      esc(letivosTotal) +
      "</td><td>" +
      (minimoSemestre ? esc(minimoSemestre) : "—") +
      "</td><td>" +
      (porDiaOk ? "OK" : "Abaixo da meta") +
      "</td></tr></tfoot></table>" +
      (agenda.sabados_sem_referencia
        ? '<p class="muted"><strong>' +
          esc(agenda.sabados_sem_referencia) +
          " sábado(s) letivo(s) sem Referência — não contabilizados por dia. O total " +
          "do documento (" +
          esc(agenda.total_letivos) +
          " dias) inclui esse(s) dia(s).</strong></p>"
        : "") +
      '<p class="muted">Total do documento: <strong>' +
      esc(agenda.total_letivos) +
      "</strong> dias letivos (" +
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
            (l.conta ? " — <em>conta na carga horária</em>" : " — não conta") +
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
    // Os avisos da carga horária saem daqui: ficam agrupados na área de
    // mensagens do editor, com atalho de volta para esta prévia.
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

  // Última agenda calculada pelo servidor (usada para corrigir Referências e mostrar
  // os avisos da carga horária).
  var ultimaAgenda = null;

  function renderPreview(d) {
    var html = "";
    var ag = d.agenda || {};
    ultimaAgenda = d.agenda || null;
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
        "Aulas remanejadas fora do padrão",
        d.metricas.parity + " / " + d.metricas.weekday + " / " + d.metricas.part,
        "ideal: 0 / 0 / 0 — quanto menor, melhor",
        "Cada número conta aulas remanejadas que perderam a paridade (x1/x2), o dia da semana ou a parte do semestre. Menor é melhor — este indicador é só diagnóstico e não altera a carga horária."
      ) +
      "</div>";

    html += renderAjudaMetricas(d);

    // Os ajustes necessários saem da prévia: ficam agrupados na área de
    // mensagens do editor, com atalho de volta para esta prévia.
    var evPorData = eventosPorData(d.agenda);
    // Sábado de cada semana (sábado letivo x sábado de reposição), casado por data.
    var sabPorData = {};
    ((d.agenda && d.agenda.sabados_letivos) || []).forEach(function (s) {
      sabPorData[s.date] = s;
    });
    var repPorData = {};
    ((d.agenda && d.agenda.dias_reposicao) || []).forEach(function (s) {
      repPorData[s.date] = s;
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
      var rep = repPorData[linha.sabado];
      var sabDica = sab
        ? sab.titulo + (sab.referencia ? " — " + sab.referencia : "")
        : rep
        ? rep.titulo + " — não entra na carga horária"
        : "Sábado sem aula";
      html +=
        '<td class="cal-cell cal-sabado' +
        (sab ? " cal-sabado-letivo" : rep ? " cal-sabado-reposicao" : "") +
        '" data-tip="' +
        esc(sabDica) +
        '" aria-label="' +
        esc(sabDica) +
        '"><span class="cal-date">' +
        (sab || rep
          ? esc((sab || rep).label)
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
    atualizarStatus(d);
    atualizarAlertas(d);
  }

  var timer = null;
  function agendarPreview() {
    atualizarContadores();
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
    marcarEstadoSalvo(pendente ? "pendente" : "salvo");
    atualizarMensagens();
  }

  function salvar() {
    postJSON(BASE + "api/salvar/", payload())
      .then(function (res) {
        if (res && res.ok) {
          msg("Versão " + res.versao + " salva.", "ok");
          marcarPendenteIA(false);
          sincronizarVersaoSalva(res.versao);
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
    if (!confirmarDescarte("Há alterações não salvas. Começar uma nova versão e descartá-las?")) {
      return;
    }
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

  // ---- Sábados sem Referência --------------------------------------------
  // A Referência de um "sábado letivo" é o dia da semana que ele repõe: o dia com
  // maior déficit em relação à meta (previsto/5). Sábado de REPOSIÇÃO não entra na
  // carga horária, então não precisa de Referência.
  function corrigirReferenciasSabados() {
    var sabados = state.eventos.filter(function (e) {
      return (
        e.tipo === "sabado_letivo" &&
        (e.dia_semana_referencia === null || e.dia_semana_referencia === undefined)
      );
    });
    if (!sabados.length) {
      msg("Nenhum sábado letivo sem Referência.", "erro");
      return;
    }
    var ag = ultimaAgenda || {};
    var meta =
      (ag.totais_tabela && ag.totais_tabela.minimo_por_dia) || ag.meta_por_dia || 0;
    if (!meta) {
      msg(
        "Informe os “Dias letivos previstos” (bloco 1.2) para calcular o déficit de cada dia.",
        "erro"
      );
      return;
    }
    var contagem = (ag.letivos_por_dia || [0, 0, 0, 0, 0]).slice();
    var ordem = [];
    var preenchidos = 0;
    sabados.forEach(function (e) {
      var elegiveis = [];
      for (var k = 0; k < 5; k += 1) {
        if (meta - contagem[k] > 0) elegiveis.push(k);
      }
      if (!elegiveis.length) return;
      elegiveis.sort(function (a, b) {
        var da = meta - contagem[a];
        var db = meta - contagem[b];
        if (db !== da) return db - da;
        var oa = ordem.filter(function (x) {
          return x === a;
        }).length;
        var ob = ordem.filter(function (x) {
          return x === b;
        }).length;
        if (oa !== ob) return oa - ob;
        return a - b;
      });
      var escolhido = elegiveis[0];
      e.dia_semana_referencia = escolhido;
      contagem[escolhido] += 1;
      ordem.push(escolhido);
      preenchidos += 1;
    });
    if (!preenchidos) {
      msg(
        "A meta de cada dia da semana já está atingida — nenhuma Referência foi alterada.",
        "erro"
      );
      return;
    }
    renderEventos();
    preview();
    marcarPendenteIA(true);
    msg(
      preenchidos +
        " sábado(s) letivo(s) receberam o dia com maior déficit em “Referência”. " +
        "NADA foi salvo ainda — clique em “Salvar versão”.",
      "ok"
    );
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
    if (!alvo) return;
    var info = normaDaModalidadeIA();
    if (!info) {
      alvo.textContent = "";
      alvo.removeAttribute("title");
      return;
    }
    alvo.textContent = "Norma aplicada: " + rotuloNormaIA();
    // A referência completa (resoluções, LDB e a atualização das normas) vai no tooltip.
    if (info.referencia) alvo.title = info.referencia;
    else alvo.removeAttribute("title");
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

  function opcoesProvedoresIA() {
    return (IA.provedores || [])
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
  }

  function provedorPadraoIA() {
    var lista = IA.provedores || [];
    var escolhido =
      lista.filter(function (p) {
        return p.disponivel && p.valor === IA.padrao;
      })[0] ||
      lista.filter(function (p) {
        return p.disponivel;
      })[0];
    return escolhido ? escolhido.valor : "";
  }

  function preencherSelectProvedorIA(sel) {
    if (!sel) return;
    sel.innerHTML = opcoesProvedoresIA();
    var padrao = provedorPadraoIA();
    if (padrao) sel.value = padrao;
  }

  function preencherSelectsIA() {
    preencherSelectProvedorIA($("iaProvedor"));
    preencherSelectProvedorIA($("iaFerProvedor"));
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
      sabados_contabilizados: ag.sabados_contabilizados,
      sabados_sem_referencia: ag.sabados_sem_referencia,
      dias_reposicao: ag.dias_reposicao,
      reposicoes_total: ag.reposicoes_total,
      totais_tabela: ag.totais_tabela,
      notas: ag.notas,
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

  // ---- Verificação de feriados por IA ------------------------------------
  // A lista colada fica apenas na memória da página (não é persistida). A IA só
  // converte as linhas em data/nome/tipo; o veredito vem do servidor.
  var iaFerState = {
    itens: [],
    resumo: null,
    extras: [],
    avisos: [],
    selecionados: {},
    gerado: false
  };
  var iaFerTexto = "";

  function msgFer(texto, tipo) {
    var el = $("iaFerMsg");
    if (!el) return;
    el.textContent = texto;
    el.className =
      "editor-msg" +
      (tipo === "ok" ? " editor-msg-ok" : tipo === "erro" ? " editor-msg-erro" : "");
  }

  function mostrarPassoFer(passo) {
    if ($("iaFerEntrada")) $("iaFerEntrada").hidden = passo !== "entrada";
    if ($("iaFerPrevia")) $("iaFerPrevia").hidden = passo !== "previa";
  }

  function anoBaseFer() {
    var inicio = $("fInicio") ? $("fInicio").value : "";
    var fim = $("fDataFim") ? $("fDataFim").value : "";
    if (!inicio) return "";
    var a = inicio.split("-")[0];
    var b = fim ? fim.split("-")[0] : a;
    return a === b ? a : a + "–" + b;
  }

  function labelProvedorFer() {
    var sel = $("iaFerProvedor");
    var valor = sel ? sel.value : "";
    var achado = (IA.provedores || []).filter(function (p) {
      return p.valor === valor;
    })[0];
    return achado ? achado.label : valor;
  }

  function abrirIAFeriados() {
    var modal = $("iaFeriados");
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
    if ($("iaFerLista") && iaFerTexto) $("iaFerLista").value = iaFerTexto;
    if ($("iaFerAno")) $("iaFerAno").textContent = anoBaseFer() || "—";
    mostrarPassoFer("entrada");
    msgFer("", "");
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "open");
    if ($("iaFerLista")) $("iaFerLista").focus();
  }

  function fecharIAFeriados() {
    var modal = $("iaFeriados");
    if (!modal) return;
    if (typeof modal.close === "function" && modal.open) modal.close();
    else modal.removeAttribute("open");
  }

  function verificarFeriadosIA() {
    var lista = ($("iaFerLista") ? $("iaFerLista").value : "").trim();
    if (!lista) {
      msgFer("Cole a lista de feriados para conferir.", "erro");
      return;
    }
    var p = payload();
    if (!p.data_inicio || !p.data_fim) {
      msgFer("Informe o início e o término do período (bloco 1.2) antes de conferir.", "erro");
      return;
    }
    iaFerTexto = lista;

    var botao = $("iaFerGerar");
    var rotulo = botao.textContent;
    var iniciadoEm = Date.now();
    botao.disabled = true;
    botao.textContent = "Conferindo…";
    msgFer(
      "Conferindo a lista com " +
        labelProvedorFer() +
        "… aguarde (pode levar até " +
        (IA.timeout || 120) +
        "s).",
      ""
    );

    postJSON(BASE + "api/ia/feriados/", {
      lista: lista,
      provedor: $("iaFerProvedor") ? $("iaFerProvedor").value : "",
      modelo: $("iaFerModelo") ? $("iaFerModelo").value.trim() : "",
      modalidade: p.modalidade,
      instituicao: p.instituicao,
      curso: p.curso,
      data_inicio: p.data_inicio,
      data_fim: p.data_fim,
      feriados: p.feriados
    })
      .then(function (d) {
        botao.disabled = false;
        botao.textContent = rotulo;
        if (!d || !d.ok) {
          msgFer(((d && d.erros) || ["Não foi possível conferir a lista."]).join(" "), "erro");
          return;
        }
        iaFerState.itens = d.itens || [];
        iaFerState.resumo = d.resumo || null;
        iaFerState.extras = d.extras_no_calendario || [];
        iaFerState.avisos = d.avisos || [];
        iaFerState.selecionados = {};
        iaFerState.itens.forEach(function (it) {
          if (it.sugestao) iaFerState.selecionados[it.data] = true;
        });
        iaFerState.gerado = true;
        renderFeriadosIA();
        mostrarPassoFer("previa");
        var segundos = Math.max(1, Math.round((Date.now() - iniciadoEm) / 1000));
        var r = iaFerState.resumo || {};
        msgFer(
          "Conferência concluída por " +
            (d.provedor_label || d.provedor) +
            (d.modelo ? " (" + d.modelo + ")" : "") +
            " em " +
            segundos +
            "s — " +
            (r.mapeados || 0) +
            " mapeado(s), " +
            (r.faltando || 0) +
            " faltando, " +
            (r.divergentes || 0) +
            " divergente(s).",
          r.ok ? "ok" : ""
        );
      })
      .catch(function () {
        botao.disabled = false;
        botao.textContent = rotulo;
        msgFer("Não foi possível falar com o servidor.", "erro");
      });
  }

  function renderFeriadosIA() {
    var resumo = $("iaFerResumo");
    if (resumo) {
      var r = iaFerState.resumo || {};
      resumo.innerHTML =
        '<div class="cal-metrics">' +
        metric("Itens na lista", r.total || 0, (r.fora_do_periodo || 0) + " fora do período") +
        metric("✅ Mapeados", r.mapeados || 0, "já cadastrados") +
        metric("➡️ Faltando", r.faltando || 0, "para adicionar") +
        metric("⚠ Divergentes", r.divergentes || 0, "data ou tipo diferente") +
        metric("Fora da sua lista", r.extras_no_calendario || 0, "cadastrados no calendário") +
        "</div>";
    }

    var tbody = $("iaFerBody");
    if (tbody) {
      tbody.innerHTML = iaFerState.itens
        .map(function (it) {
          var marca = it.sugestao
            ? '<input type="checkbox" class="ia-fer-check" data-data="' +
              esc(it.data) +
              '"' +
              (iaFerState.selecionados[it.data] ? " checked" : "") +
              ">"
            : "";
          var sugestao = "—";
          if (it.sugestao) {
            sugestao =
              it.sugestao.acao === "ajustar_tipo"
                ? "Ajustar para " + esc(it.tipo_label)
                : "Adicionar " +
                  esc(it.tipo_label) +
                  " em " +
                  esc(it.sugestao.data.split("-").reverse().join("/"));
          }
          return (
            '<tr class="ia-fer-' +
            esc(it.situacao) +
            '"><td>' +
            marca +
            " " +
            esc(it.situacao_icone || "") +
            " " +
            esc(it.situacao_label) +
            '</td><td class="ia-fer-original">' +
            esc(it.original || "") +
            "</td><td>" +
            esc(it.data.split("-").reverse().join("/")) +
            "</td><td>" +
            esc(it.descricao) +
            "</td><td>" +
            esc(it.tipo_label) +
            (it.fora_do_periodo ? ' <em class="muted">(fora do período)</em>' : "") +
            "</td><td>" +
            (it.registro ? esc(it.registro) : "—") +
            "</td><td>" +
            sugestao +
            "</td></tr>" +
            (it.motivo
              ? '<tr class="ia-fer-motivo"><td colspan="7" class="muted">' +
                esc(it.motivo) +
                "</td></tr>"
              : "")
          );
        })
        .join("");

      Array.prototype.forEach.call(tbody.querySelectorAll(".ia-fer-check"), function (chk) {
        chk.addEventListener("change", function () {
          var data = chk.getAttribute("data-data");
          if (chk.checked) iaFerState.selecionados[data] = true;
          else delete iaFerState.selecionados[data];
        });
      });
    }

    var extras = $("iaFerExtras");
    if (extras) {
      extras.innerHTML = (iaFerState.extras || []).length
        ? '<div class="cal-alert"><strong>Cadastrados no calendário e fora da sua lista:</strong><ul>' +
          iaFerState.extras
            .map(function (e) {
              return (
                "<li>" +
                esc(e.data_label) +
                " — " +
                esc(e.descricao || "(sem descrição)") +
                " (" +
                esc(e.tipo_label) +
                ")</li>"
              );
            })
            .join("") +
          "</ul></div>"
        : "";
    }

    var avisos = $("iaFerAvisos");
    if (avisos) {
      avisos.innerHTML = (iaFerState.avisos || []).length
        ? '<div class="cal-alert"><strong>Atenção:</strong><ul>' +
          iaFerState.avisos
            .map(function (a) {
              return "<li>" + esc(a) + "</li>";
            })
            .join("") +
          "</ul></div>"
        : "";
    }
  }

  function marcarTodosFer() {
    iaFerState.itens.forEach(function (it) {
      if (it.sugestao) iaFerState.selecionados[it.data] = true;
    });
    renderFeriadosIA();
    msgFer("Todos os itens com sugestão foram marcados.", "ok");
  }

  function aplicarFeriadosIA() {
    var aplicados = 0;
    iaFerState.itens.forEach(function (it) {
      if (!it.sugestao || !iaFerState.selecionados[it.data]) return;
      var existente = state.feriados.filter(function (f) {
        return f.data === it.data;
      })[0];
      if (it.sugestao.acao === "ajustar_tipo" && existente) {
        existente.tipo = it.tipo;
        if (!existente.descricao) existente.descricao = it.descricao;
        aplicados += 1;
      } else if (!existente) {
        state.feriados.push({
          data: it.data,
          descricao: it.descricao,
          origem: it.origem || "manual",
          tipo: it.tipo
        });
        aplicados += 1;
      }
    });
    if (!aplicados) {
      msgFer("Marque ao menos um item com sugestão para aplicar.", "erro");
      return;
    }
    fecharIAFeriados();
    renderChips();
    preview();
    marcarPendenteIA(true);
    msg(
      aplicados +
        " feriado(s) da conferência aplicado(s) ao editor (NADA foi salvo ainda — " +
        "clique em “Salvar versão”).",
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
    // As prévias são abas: ao reexibir o bloco, só a aba ativa fica visível.
    if (nome === "previews") aplicarAba();
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
  if ($("btnRefSabados")) {
    $("btnRefSabados").addEventListener("click", corrigirReferenciasSabados);
  }
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

  // ---- Verificação de feriados por IA (modal) -----------------------------
  if ($("btnIAFeriados")) $("btnIAFeriados").addEventListener("click", abrirIAFeriados);
  if ($("iaFerGerar")) $("iaFerGerar").addEventListener("click", verificarFeriadosIA);
  if ($("iaFerAplicar")) $("iaFerAplicar").addEventListener("click", aplicarFeriadosIA);
  if ($("iaFerMarcarTodos")) $("iaFerMarcarTodos").addEventListener("click", marcarTodosFer);
  if ($("iaFerRegerar")) $("iaFerRegerar").addEventListener("click", verificarFeriadosIA);
  if ($("iaFerVoltar")) {
    $("iaFerVoltar").addEventListener("click", function () {
      mostrarPassoFer("entrada");
    });
  }
  if ($("iaFerFechar")) $("iaFerFechar").addEventListener("click", fecharIAFeriados);
  if ($("iaFerCancelar")) $("iaFerCancelar").addEventListener("click", fecharIAFeriados);

  // ---- Ferramenta: barra fixa, índice, abas e status ----------------------
  // O editor se comporta como uma ferramenta: ações sempre visíveis (barra
  // fixa), índice lateral com scroll-spy, blocos recolhíveis, prévias em abas,
  // busca de bloco/campo (Ctrl+K) e barra de status com os números do cálculo.
  var headerEl = document.querySelector(".site-header");
  var topbarEl = $("editorTopbar");

  // Atalhos acompanham o sistema: no macOS o modificador é ⌘ (Command) e o
  // Option é ⌥ — os rótulos na tela mudam junto. O iPadOS se apresenta como
  // "MacIntel", então o teste por plataforma/UA já o cobre (⌘ vale lá também).
  var navInfo = typeof navigator !== "undefined" && navigator ? navigator : {};
  var plataformaNav = String(
    (navInfo.userAgentData && navInfo.userAgentData.platform) || navInfo.platform || ""
  );
  var ehMac = /Mac|iPhone|iPad|iPod/i.test(plataformaNav + " " + String(navInfo.userAgent || ""));
  var TECLA_CTRL = ehMac ? "⌘" : "Ctrl";
  var TECLA_ALT = ehMac ? "⌥" : "Alt";

  // O texto pode vir de um modelo com "{mod}" (ex.: "{mod} K" → "⌘ K" no macOS e
  // "Ctrl K" nos demais), preservando o resto do rótulo.
  Array.prototype.forEach.call(document.querySelectorAll("[data-mod]"), function (el) {
    var tecla = el.getAttribute("data-mod") === "alt" ? TECLA_ALT : TECLA_CTRL;
    var modelo = el.getAttribute("data-mod-texto") || "{mod}";
    el.textContent = modelo.replace("{mod}", tecla);
  });
  if ($("editorStatusKeys")) {
    $("editorStatusKeys").textContent =
      TECLA_CTRL + "+S salvar · " + TECLA_CTRL + "+K buscar · " + TECLA_ALT + "+1…6 blocos";
  }

  function medirOffsets() {
    var raiz = document.documentElement;
    if (headerEl) raiz.style.setProperty("--editor-offset", headerEl.offsetHeight + "px");
    if (topbarEl) raiz.style.setProperty("--editor-topbar-h", topbarEl.offsetHeight + "px");
  }

  // Recolher/expandir cada bloco (a escolha é lembrada entre visitas).
  function aplicarRecolhido(bloco, recolhido) {
    bloco.classList.toggle("is-collapsed", recolhido);
    var btn = bloco.querySelector("[data-collapse]");
    if (!btn) return null;
    btn.setAttribute("aria-expanded", recolhido ? "false" : "true");
    var txt = btn.querySelector(".editor-block-toggle-txt");
    if (txt) txt.textContent = recolhido ? "Expandir" : "Recolher";
    return btn;
  }

  function guardarRecolhido(chave, recolhido) {
    try {
      localStorage.setItem("editor-collapse-" + chave, recolhido ? "1" : "0");
    } catch (e) {
      /* localStorage indisponível — ignora */
    }
  }

  Array.prototype.forEach.call(document.querySelectorAll(".editor-block"), function (bloco) {
    var btn = bloco.querySelector("[data-collapse]");
    if (!btn) return;
    var chave = btn.getAttribute("data-collapse");
    var salvo = null;
    try {
      salvo = localStorage.getItem("editor-collapse-" + chave);
    } catch (e) {
      salvo = null;
    }
    aplicarRecolhido(bloco, salvo === "1");
    btn.addEventListener("click", function () {
      var recolhido = !bloco.classList.contains("is-collapsed");
      aplicarRecolhido(bloco, recolhido);
      guardarRecolhido(chave, recolhido);
      medirOffsets();
    });
  });

  // Prévias em abas (o conjunto inteiro continua sendo o bloco "previews").
  var abas = Array.prototype.slice.call(document.querySelectorAll("[data-preview-tab]"));
  var paineis = Array.prototype.slice.call(document.querySelectorAll("[data-preview-panel]"));

  function aplicarAba(nome) {
    if (!abas || !abas.length) return;
    var alvo = nome;
    if (!alvo) {
      try {
        alvo = localStorage.getItem("editor-preview-tab");
      } catch (e) {
        alvo = null;
      }
    }
    var existe = abas.some(function (a) {
      return a.getAttribute("data-preview-tab") === alvo;
    });
    if (!existe) alvo = abas[0].getAttribute("data-preview-tab");
    abas.forEach(function (a) {
      var ativa = a.getAttribute("data-preview-tab") === alvo;
      a.classList.toggle("is-active", ativa);
      a.setAttribute("aria-selected", ativa ? "true" : "false");
    });
    paineis.forEach(function (p) {
      if (p.getAttribute("data-preview-panel") === alvo) p.removeAttribute("hidden");
      else p.setAttribute("hidden", "hidden");
    });
    try {
      localStorage.setItem("editor-preview-tab", alvo);
    } catch (e) {
      /* ignora */
    }
  }

  abas.forEach(function (a) {
    a.addEventListener("click", function () {
      aplicarAba(a.getAttribute("data-preview-tab"));
    });
  });

  // Navegação do índice + destaque do bloco visível (scroll-spy).
  var navLinks = Array.prototype.slice.call(document.querySelectorAll("[data-nav-block]"));

  function irPara(id, focoId) {
    var el = document.getElementById(id);
    if (!el) return;
    var grupo = el.closest ? el.closest("[data-block]") : null;
    if (grupo && grupo.hasAttribute("hidden")) {
      aplicarBloco(grupo.getAttribute("data-block"), false);
    }
    if (el.classList.contains("is-collapsed")) {
      var btn = aplicarRecolhido(el, false);
      if (btn) guardarRecolhido(btn.getAttribute("data-collapse"), false);
    }
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    if (focoId) {
      window.setTimeout(function () {
        var campo = $(focoId);
        if (!campo) return;
        try {
          campo.focus({ preventScroll: true });
        } catch (e) {
          campo.focus();
        }
      }, 320);
    }
  }

  navLinks.forEach(function (a) {
    a.addEventListener("click", function (ev) {
      ev.preventDefault();
      irPara(a.getAttribute("href").replace("#", ""));
    });
  });

  var alvosNav = Array.prototype.slice.call(document.querySelectorAll("[data-nav-target]"));
  var visiveisNav = {};

  function destacarNoIndice(nome) {
    navLinks.forEach(function (a) {
      a.classList.toggle("is-active", a.getAttribute("data-nav-block") === nome);
    });
  }

  if (window.IntersectionObserver && alvosNav.length) {
    var observador = new window.IntersectionObserver(
      function (entradas) {
        entradas.forEach(function (e) {
          visiveisNav[e.target.id] = e.isIntersecting;
        });
        for (var i = 0; i < alvosNav.length; i++) {
          if (visiveisNav[alvosNav[i].id]) {
            destacarNoIndice(alvosNav[i].getAttribute("data-nav-target"));
            return;
          }
        }
      },
      { rootMargin: "-25% 0px -60% 0px" }
    );
    alvosNav.forEach(function (el) {
      observador.observe(el);
    });
  }

  // Busca rápida: blocos + campos do formulário (Ctrl+K).
  var buscaInput = $("editorBusca");
  var buscaLista = $("editorBuscaResultados");
  var destinos = [];

  function semAcento(texto) {
    var t = String(texto || "").toLowerCase().trim();
    if (typeof t.normalize === "function") {
      t = t.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    }
    return t;
  }

  function montarDestinos() {
    destinos = [];
    navLinks.forEach(function (a) {
      destinos.push({
        rotulo: a.textContent.replace(/\s+/g, " ").trim(),
        bloco: a.getAttribute("href").replace("#", ""),
        campo: ""
      });
    });
    Array.prototype.forEach.call(
      document.querySelectorAll("#editorSteps label.field"),
      function (label) {
        var copia = label.cloneNode(true);
        Array.prototype.forEach.call(copia.querySelectorAll("small, .field-hint"), function (s) {
          if (s.parentNode) s.parentNode.removeChild(s);
        });
        var texto = copia.textContent.replace(/\s+/g, " ").trim();
        var controle = label.querySelector("input[id], select[id], textarea[id]");
        if (!texto || !controle) return;
        var dono = controle.closest ? controle.closest("[data-nav-target]") : null;
        destinos.push({
          rotulo: texto,
          bloco: dono ? dono.id : "",
          campo: controle.id
        });
      }
    );
  }

  function desenharBusca(termo) {
    if (!buscaLista) return;
    var t = semAcento(termo);
    if (!t) {
      buscaLista.hidden = true;
      buscaLista.innerHTML = "";
      return;
    }
    var achados = destinos
      .filter(function (d) {
        return semAcento(d.rotulo).indexOf(t) !== -1;
      })
      .slice(0, 12);
    if (!achados.length) {
      buscaLista.innerHTML = '<li><button type="button" disabled>Nada encontrado</button></li>';
      buscaLista.hidden = false;
      return;
    }
    buscaLista.innerHTML = achados
      .map(function (d) {
        return (
          '<li><button type="button" data-destino="' +
          esc(d.bloco) +
          '" data-campo="' +
          esc(d.campo) +
          '">' +
          esc(d.rotulo) +
          "<small>" +
          (d.campo ? "ir para o campo" : "ir para o bloco") +
          "</small></button></li>"
        );
      })
      .join("");
    buscaLista.hidden = false;
  }

  function abrirDestino(bloco, campo) {
    if (buscaInput) {
      buscaInput.value = "";
      desenharBusca("");
    }
    if (campo) {
      var alvo = document.getElementById(campo);
      var dono = alvo && alvo.closest ? alvo.closest("[data-nav-target]") : null;
      irPara(dono ? dono.id : bloco, campo);
      return;
    }
    if (bloco) irPara(bloco);
  }

  if (buscaInput) {
    buscaInput.addEventListener("input", function () {
      desenharBusca(buscaInput.value);
    });
    buscaInput.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" && buscaLista) {
        var primeiro = buscaLista.querySelector("button[data-destino], button[data-campo]");
        if (primeiro && !primeiro.disabled) {
          ev.preventDefault();
          abrirDestino(primeiro.getAttribute("data-destino"), primeiro.getAttribute("data-campo"));
        }
      } else if (ev.key === "Escape") {
        buscaInput.value = "";
        desenharBusca("");
      }
    });
  }

  if (buscaLista) {
    buscaLista.addEventListener("click", function (ev) {
      var btn =
        ev.target && ev.target.closest
          ? ev.target.closest("button[data-destino], button[data-campo]")
          : null;
      if (!btn || btn.disabled) return;
      abrirDestino(btn.getAttribute("data-destino"), btn.getAttribute("data-campo"));
    });
  }

  // Botões espalhados pela página que acionam a ação correspondente da barra
  // fixa (sem duplicar id): hoje só o "Salvar versão" do bloco 1.2.
  Array.prototype.forEach.call(document.querySelectorAll("[data-quick]"), function (btn) {
    btn.addEventListener("click", function () {
      if (btn.getAttribute("data-quick") === "salvar" && $("btnSalvar")) {
        $("btnSalvar").click();
      }
    });
  });

  // ---- Bloco 1.1: filtro da lista e proteção do trabalho -------------------
  var etapasBusca = $("etapasBusca");
  var etapasLista = $("etapasLista");
  var etapasCartoes = etapasLista
    ? Array.prototype.slice.call(etapasLista.querySelectorAll(".editor-etapa"))
    : [];

  // A versão aberta no formulário — o JS mantém este destaque, inclusive depois
  // de salvar uma versão nova.
  function cartaoAtual() {
    return document.querySelector(".editor-etapa.is-atual");
  }

  // Estado "busca-primeiro": sem busca aparece só a versão aberta; sem versão
  // aberta a área fica vazia e as versões salvas são encontradas pela busca.
  function filtrarEtapas() {
    if (!etapasBusca || !etapasLista) return;
    var termo = semAcento(etapasBusca.value);
    var atual = cartaoAtual();
    var focado = !termo && !!atual;
    var visiveis = 0;

    Array.prototype.forEach.call(etapasCartoes, function (cartao) {
      // Sem termo não há "encontrados": quem decide é o modo focado.
      var achou =
        !!termo &&
        semAcento(cartao.getAttribute("data-search") || "").indexOf(termo) !== -1;
      var mostrar = focado ? cartao === atual : achou;
      cartao.hidden = !mostrar;
      if (mostrar) visiveis += 1;
    });

    var total = etapasCartoes.length;
    var contagem = $("etapasContagem");
    if (contagem) {
      if (termo) {
        contagem.textContent =
          visiveis + " de " + total + " " + (total === 1 ? "versão" : "versões");
        contagem.removeAttribute("title");
      } else if (atual) {
        contagem.textContent =
          "versão aberta · " + total + " " + (total === 1 ? "salva" : "salvas");
        contagem.title = "Busque por outra versão para trocar";
      } else {
        contagem.textContent =
          total + " " + (total === 1 ? "versão salva" : "versões salvas");
        contagem.removeAttribute("title");
      }
    }

    var vazio = $("etapasVazio");
    if (vazio) {
      if (!total) {
        vazio.textContent =
          "Nenhuma versão salva ainda — preencha os parâmetros e salve a primeira.";
        vazio.hidden = false;
      } else if (!termo && !atual) {
        vazio.textContent =
          "Nenhuma versão aberta — use a busca acima para encontrar e abrir uma versão salva.";
        vazio.hidden = false;
      } else if (termo && !visiveis) {
        vazio.textContent = "Nenhuma versão encontrada para a busca.";
        vazio.hidden = false;
      } else {
        vazio.hidden = true;
      }
    }
  }

  if (etapasBusca) {
    etapasBusca.addEventListener("input", filtrarEtapas);
    etapasBusca.addEventListener("search", filtrarEtapas);
  }

  // Trocar de versão (ou começar uma nova) com alterações não salvas precisa de
  // confirmação — antes o trabalho era descartado em silêncio.
  function confirmarDescarte(mensagem) {
    if (estadoSalvo !== "pendente") return true;
    return window.confirm(mensagem);
  }

  if (etapasLista) {
    etapasLista.addEventListener("click", function (ev) {
      var link =
        ev.target && ev.target.closest ? ev.target.closest("[data-abrir-etapa]") : null;
      if (!link) return;
      if (
        !confirmarDescarte("Há alterações não salvas nesta versão. Abrir outra e descartá-las?")
      ) {
        ev.preventDefault();
      }
    });
  }

  // Fechar/recarregar a página com alterações pendentes também avisa.
  window.addEventListener("beforeunload", function (ev) {
    if (estadoSalvo !== "pendente") return undefined;
    ev.preventDefault();
    ev.returnValue = "";
    return "";
  });

  if ($("btnAtualizarLista")) {
    $("btnAtualizarLista").addEventListener("click", function () {
      window.location.reload();
    });
  }

  // Depois de salvar: a URL passa a apontar para a versão aberta e o cartão do
  // bloco 1.1 é remarcado sem recarregar a página.
  function sincronizarVersaoSalva(versao) {
    var cartao = null;
    Array.prototype.forEach.call(document.querySelectorAll(".editor-etapa"), function (c) {
      if (!cartao && c.getAttribute("data-versao") === versao) cartao = c;
    });
    var aviso = $("etapasDesatualizada");
    if (!cartao) {
      if (aviso) aviso.hidden = false;
      return;
    }
    if (aviso) aviso.hidden = true;

    Array.prototype.forEach.call(document.querySelectorAll(".editor-etapa"), function (c) {
      var atual = c === cartao;
      c.classList.toggle("is-atual", atual);
      var chip = c.querySelector("[data-estado-etapa]");
      if (atual && !chip) {
        chip = document.createElement("span");
        chip.className = "editor-etapa-chip is-atual";
        chip.setAttribute("data-estado-etapa", "em edição");
        chip.textContent = "em edição";
        var head = c.querySelector(".editor-etapa-head");
        var nome = c.querySelector(".editor-etapa-versao");
        if (head && nome) head.insertBefore(chip, nome.nextSibling);
        else if (head) head.appendChild(chip);
      } else if (!atual && chip && chip.parentNode) {
        chip.parentNode.removeChild(chip);
      }
      var avisoCartao = c.querySelector("[data-aviso-etapa]");
      if (atual && !avisoCartao) {
        avisoCartao = document.createElement("p");
        avisoCartao.className = "editor-etapa-aviso";
        avisoCartao.setAttribute("data-aviso-etapa", "1");
        avisoCartao.hidden = true;
        avisoCartao.innerHTML =
          "Alterações não salvas nesta versão — clique em <em>Salvar versão</em> para gravá-las.";
        var acoes = c.querySelector(".editor-etapa-acoes");
        if (acoes) c.insertBefore(avisoCartao, acoes);
        else c.appendChild(avisoCartao);
      } else if (!atual && avisoCartao && avisoCartao.parentNode) {
        avisoCartao.parentNode.removeChild(avisoCartao);
      }
    });

    if ($("etapasAberta")) {
      $("etapasAberta").innerHTML = "em edição: <strong>" + esc(versao) + "</strong>";
    }
    var slug = cartao.getAttribute("data-slug");
    if (slug && window.history && window.history.replaceState) {
      window.history.replaceState(null, "", "?versao=" + encodeURIComponent(slug));
    }
    atualizarCartaoEmEdicao();
    filtrarEtapas();
  }

  // ---- Área única de mensagens (abaixo do quadro azul) --------------------
  // A caixa só aparece quando há conteúdo: mensagem da interface, alerta de IA
  // pendente ou algum dos grupos de alerta do cálculo.
  function atualizarMensagens() {
    var caixa = $("editorMensagens");
    if (!caixa) return;
    var msgEl = $("editorMsg");
    var pendenteEl = $("iaPendente");
    var alertasEl = $("editorAlertas");
    var temMensagem = !!(msgEl && String(msgEl.textContent || "").trim());
    var temPendente = !!(pendenteEl && !pendenteEl.hidden);
    var temAlertas = !!(alertasEl && String(alertasEl.innerHTML || "").trim());
    caixa.hidden = !(temMensagem || temPendente || temAlertas);
  }

  function grupoAlerta(titulo, itens, tipo, destino, rotuloDestino) {
    if (!itens || !itens.length) return "";
    return (
      '<div class="editor-alerta-grupo ' +
      tipo +
      '"><div class="editor-alerta-head"><strong>' +
      esc(titulo) +
      " (" +
      itens.length +
      ")</strong>" +
      (destino
        ? '<button type="button" class="editor-alerta-link" data-ir-preview="' +
          destino +
          '">' +
          esc(rotuloDestino) +
          "</button>"
        : "") +
      "</div><ul>" +
      itens
        .map(function (item) {
          return "<li>" + esc(item) + "</li>";
        })
        .join("") +
      "</ul></div>"
    );
  }

  // Alertas do cálculo (antes espalhados pelas prévias): agrupados aqui, cada um
  // com um atalho que pula para a prévia onde o ponto aparece.
  function atualizarAlertas(d) {
    var caixa = $("editorAlertas");
    if (!caixa) return;
    var ag = (d && d.agenda) || {};
    var erros = (d && d.erros) || [];
    var avisos = (ag.validacao && ag.validacao.avisos) || [];
    var notas = ag.notas || [];
    caixa.innerHTML =
      grupoAlerta("Ajustes necessários", erros, "is-erro", "grade", "Ver na prévia da grade") +
      grupoAlerta(
        "Atenção na carga horária",
        avisos,
        "is-alerta",
        "doc",
        "Ver na prévia do documento"
      ) +
      grupoAlerta(
        "Observações do cálculo",
        notas,
        "is-info",
        "doc",
        "Ver na prévia do documento"
      );
    atualizarMensagens();
  }

  if ($("editorAlertas")) {
    $("editorAlertas").addEventListener("click", function (ev) {
      var btn =
        ev.target && ev.target.closest ? ev.target.closest("[data-ir-preview]") : null;
      if (!btn) return;
      var destino = btn.getAttribute("data-ir-preview");
      aplicarAba(destino);
      irPara(destino === "grade" ? "bloco-2-2" : "bloco-2-1");
    });
  }

  // Cabeçalho da barra fixa e estado de salvamento.
  function atualizarCabecalho() {
    var versao = ($("fVersao") && $("fVersao").value.trim()) || "nova versão";
    var etapa = ($("fEtapa") && $("fEtapa").value.trim()) || "1";
    var periodo = ($("fPeriodo") && $("fPeriodo").value.trim()) || "";
    if ($("toolVersao")) $("toolVersao").textContent = versao;
    if ($("toolEtapa")) $("toolEtapa").textContent = "etapa " + etapa;
    if ($("toolPeriodo")) {
      $("toolPeriodo").textContent = periodo || "—";
      $("toolPeriodo").hidden = !periodo;
    }
    if ($("stVersao")) $("stVersao").textContent = versao + (periodo ? " · " + periodo : "");
  }

  var estadoSalvo = "salvo";

  function marcarEstadoSalvo(estado) {
    estadoSalvo = estado === "pendente" ? "pendente" : "salvo";
    var el = $("stSalvo");
    if (el) {
      el.textContent = estadoSalvo === "pendente" ? "não salvo" : "salvo";
      el.className = estadoSalvo === "pendente" ? "is-warn" : "is-ok";
    }
    atualizarCartaoEmEdicao();
  }

  // Reflete o estado no cartão da versão aberta (bloco 1.1): chip e aviso, para
  // não confundir "estou editando" com "já está gravado".
  function atualizarCartaoEmEdicao() {
    var pendente = estadoSalvo === "pendente";
    Array.prototype.forEach.call(
      document.querySelectorAll(".editor-etapa.is-atual"),
      function (cartao) {
        cartao.classList.toggle("is-pendente", pendente);
        var chip = cartao.querySelector("[data-estado-etapa]");
        if (chip) chip.textContent = pendente ? "alterações não salvas" : "em edição";
        var aviso = cartao.querySelector("[data-aviso-etapa]");
        if (aviso) aviso.hidden = !pendente;
      }
    );
  }

  function setTexto(id, texto, classe) {
    var el = $(id);
    if (!el) return;
    el.textContent = texto;
    if (classe !== undefined && classe !== null) el.className = classe;
  }

  function atualizarContadores() {
    setTexto("stFeriados", String(state.feriados.length), "");
    setTexto("stEventos", String(state.eventos.length), "");
    setTexto("navFeriados", String(state.feriados.length), "");
    setTexto("navEventos", String(state.eventos.length), "");
  }

  // Quantitativos do rodapé e do Resumo do índice. Tudo vem do mesmo payload da
  // prévia (nada é recalculado aqui) e segue a precedência usada na tabela do
  // documento ("Dias letivos por dia da semana").
  var DIAS_CURTOS = ["Seg", "Ter", "Qua", "Qui", "Sex"];

  function atualizarStatus(d) {
    var ag = (d && d.agenda) || {};
    var tot = ag.totais_tabela || {};
    var dias = ag.dias_por_dia || [];
    var previstos = parseInt(($("fPrevistos") && $("fPrevistos").value) || "0", 10) || 0;
    var total = typeof ag.total_letivos === "number" ? ag.total_letivos : null;
    var metaDia = tot.minimo_por_dia !== undefined ? tot.minimo_por_dia : ag.meta_por_dia;
    var sabados =
      tot.sabados !== undefined
        ? tot.sabados
        : ag.sabados_contabilizados !== undefined
        ? ag.sabados_contabilizados
        : ag.sabados_total;
    var semRef =
      tot.sabados_sem_referencia !== undefined
        ? tot.sabados_sem_referencia
        : ag.sabados_sem_referencia;
    var textoLetivos = total === null ? "—" : total + (previstos ? " / " + previstos : "");

    atualizarContadores();
    setTexto(
      "stLetivos",
      textoLetivos,
      total === null ? "" : previstos && total < previstos ? "is-warn" : "is-ok"
    );
    setTexto("navLetivos", textoLetivos, "");

    // Sábados letivos contabilizados (os de reposição não entram na carga horária).
    var avisoSemRef = typeof semRef === "number" && semRef > 0;
    var textoSabados = typeof sabados === "number" ? String(sabados) : "—";
    setTexto("stSabados", textoSabados, total === null ? "" : avisoSemRef ? "is-warn" : "is-ok");
    setTexto(
      "navSabados",
      avisoSemRef ? textoSabados + " (" + semRef + " sem Ref.)" : textoSabados,
      ""
    );

    // Dias letivos por dia da semana (seg–sex + os sábados pela Referência).
    // O `textContent` é escrito direto para não perder a classe do rótulo.
    if ($("navPorDiaMeta")) {
      $("navPorDiaMeta").textContent = metaDia ? metaDia + "/dia" : "";
    }
    if ($("navPorDia")) {
      $("navPorDia").innerHTML = dias
        .map(function (dia, i) {
          var nome = DIAS_CURTOS[dia.weekday !== undefined ? dia.weekday : i] || dia.label || "";
          var alvo = dia.meta || metaDia || 0;
          var detalhe =
            nome +
            ": " +
            dia.letivos +
            (alvo ? "/" + alvo : "") +
            " (seg–sex " +
            dia.seg_sex +
            " + sábados " +
            dia.sabados +
            ")";
          return (
            '<li class="editor-nav-dia ' +
            (dia.ok ? "is-ok" : "is-warn") +
            '" title="' +
            esc(detalhe) +
            '">' +
            '<span class="editor-nav-dia-nome">' +
            esc(nome) +
            "</span>" +
            '<span class="editor-nav-dia-val">' +
            esc(dia.letivos) +
            (alvo ? "/" + esc(alvo) : "") +
            "</span></li>"
          );
        })
        .join("");
    }
    var valores = dias.map(function (dia) {
      return dia.letivos;
    });
    var algumAbaixo = dias.some(function (dia) {
      return !dia.ok;
    });
    setTexto(
      "stPorDia",
      valores.length ? valores.join("/") : "—",
      valores.length ? (algumAbaixo ? "is-warn" : "is-ok") : ""
    );
    if ($("stPorDia")) {
      $("stPorDia").title = dias.length
        ? dias
            .map(function (dia, i) {
              return (
                (DIAS_CURTOS[dia.weekday !== undefined ? dia.weekday : i] || "") +
                " " +
                dia.letivos +
                (dia.meta ? "/" + dia.meta : "")
              );
            })
            .join(" · ")
        : "";
    }
  }


  ["fVersao", "fEtapa", "fPeriodo"].forEach(function (id) {
    if (!$(id)) return;
    $(id).addEventListener("input", atualizarCabecalho);
    $(id).addEventListener("change", atualizarCabecalho);
  });

  // Qualquer edição no preenchimento marca a versão como "não salvo" (a busca do
  // bloco 1.1 leva data-sem-sujeira para não contar como edição).
  if ($("editorSteps")) {
    ["input", "change"].forEach(function (evt) {
      $("editorSteps").addEventListener(evt, function (ev) {
        var alvo = ev.target;
        if (!alvo || !/^(INPUT|SELECT|TEXTAREA)$/.test(alvo.tagName || "")) return;
        if (alvo.hasAttribute("data-sem-sujeira")) return;
        marcarEstadoSalvo("pendente");
      });
    });
  }

  // No macOS o Option (⌥) troca o caractere (⌥3 vira £), então o número do bloco
  // vem do `ev.code` (Digit1…Digit6 / Numpad1…Numpad6), que não muda com os
  // modificadores e continua funcionando com teclado ABNT/estrangeiro.
  function numeroDoBloco(ev) {
    var peloCodigo = /^(?:Digit|Numpad)([1-6])$/.exec(ev.code || "");
    if (peloCodigo) return parseInt(peloCodigo[1], 10);
    return /^[1-6]$/.test(ev.key || "") ? parseInt(ev.key, 10) : null;
  }

  // Atalhos de teclado: salvar, buscar e pular entre os blocos.
  document.addEventListener("keydown", function (ev) {
    var meta = ev.ctrlKey || ev.metaKey;
    if (meta && !ev.altKey && (ev.key === "s" || ev.key === "S")) {
      ev.preventDefault();
      if ($("btnSalvar")) $("btnSalvar").click();
      return;
    }
    if (meta && !ev.altKey && (ev.key === "k" || ev.key === "K")) {
      ev.preventDefault();
      if (buscaInput) {
        buscaInput.focus();
        buscaInput.select();
      }
      return;
    }
    if (ev.altKey && !meta) {
      var numero = numeroDoBloco(ev);
      var link = numero === null ? null : navLinks[numero - 1];
      if (link) {
        ev.preventDefault();
        irPara(link.getAttribute("href").replace("#", ""));
      }
    }
  });

  medirOffsets();
  montarDestinos();
  filtrarEtapas();
  atualizarCabecalho();
  atualizarContadores();
  aplicarAba();
  window.addEventListener("load", medirOffsets);

  if ($("fInicio").value) preview();
  else {
    $("calPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver a grade.</p>';
    $("docPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver o documento.</p>';
  }
})();
