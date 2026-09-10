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
    })
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
    $("fModalidade").value = inicial.modalidade || "integrado_proeja";
    $("fSemestre").value = inicial.semestre || "";
    $("fInicio").value = inicial.data_inicio || "";
    $("fDataFim").value = inicial.data_fim || "";
    $("fPrevistos").value = inicial.dias_letivos_previstos || 0;
    $("fSemanas").value = inicial.total_semanas || 18;
    $("fSemanas1").value = inicial.semanas_primeira_parte || 9;
    $("fEtapa").value = inicial.etapa || 1;
    $("fFinal").checked = !!inicial.final;
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
      final: $("fFinal").checked,
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
    var ordenados = state.eventos.slice().sort(function (a, b) {
      return a.data_inicio < b.data_inicio ? -1 : 1;
    });
    tbody.innerHTML = ordenados
      .map(function (e) {
        var i = state.eventos.indexOf(e);
        var ref =
          e.dia_semana_referencia === null || e.dia_semana_referencia === undefined
            ? ""
            : DIAS_SEMANA[e.dia_semana_referencia] || "";
        return (
          "<tr>" +
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
          '<td><button type="button" class="chip-remove" data-idx="' +
          i +
          '" aria-label="Remover">&times;</button></td>' +
          "</tr>"
        );
      })
      .join("");
    Array.prototype.forEach.call(tbody.querySelectorAll(".chip-remove"), function (btn) {
      btn.addEventListener("click", function () {
        state.eventos.splice(parseInt(btn.getAttribute("data-idx"), 10), 1);
        renderEventos();
        agendarPreview();
      });
    });
  }

  function addEvento() {
    var titulo = $("evTitulo").value.trim();
    var inicio = $("evInicio").value;
    if (!titulo || !inicio) {
      msg("Informe o título e a data inicial do evento.", "erro");
      return;
    }
    var ref = $("evReferencia").value;
    state.eventos.push({
      titulo: titulo,
      tipo: $("evTipo").value,
      data_inicio: inicio,
      data_fim: $("evFim").value || "",
      dia_semana_referencia: ref === "" ? null : parseInt(ref, 10),
      descricao: "",
      destaque: $("evDestaque").checked
    });
    $("evTitulo").value = "";
    $("evInicio").value = "";
    $("evFim").value = "";
    $("evReferencia").value = "";
    $("evDestaque").checked = false;
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
      '<span class="cal-legend-item"><span class="cal-swatch swatch-part1">01</span> 1ª parte (data em negrito)</span>' +
      '<span class="cal-legend-item"><span class="cal-swatch swatch-evento"></span> Dia com evento</span>' +
      '<span class="cal-legend-item"><span class="moved-day">(dia)</span> Aula remanejada</span>' +
      "</div>"
    );
  }

  function renderPreview(d) {
    var html = "";
    html +=
      '<div class="cal-metrics">' +
      metric("Semanas", d.w, (d.parametros ? d.parametros.total_semanas : "") + " + " + d.semanas_extras + " reposição") +
      metric("Feriados na faixa", d.f, "dias úteis") +
      metric("Dias letivos", d.dias_letivos, "de " + d.dias_totais + " dias") +
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
    html += '<table class="cal-table"><thead><tr><th class="cal-corner">Semana</th>';
    (d.weekdays || []).forEach(function (dia) {
      html += '<th class="cal-day">' + esc(dia) + "</th>";
    });
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
  function salvar(marcarFinal) {
    if (marcarFinal) $("fFinal").checked = true;
    postJSON(BASE + "api/salvar/", payload())
      .then(function (res) {
        if (res && res.ok) {
          msg(
            "Versão " + res.versao + " salva" + (res.final ? " como final/publicável" : "") + ".",
            "ok"
          );
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
    fill();
    renderChips();
    renderEventos();
    preview();
    msg("Novo formulário pronto para uma nova versão.", "ok");
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
  $("btnAddEvento").addEventListener("click", addEvento);
  $("btnNacionais").addEventListener("click", carregarNacionais);
  $("btnSalvar").addEventListener("click", function () {
    salvar(false);
  });
  $("btnFinal").addEventListener("click", function () {
    salvar(true);
  });
  $("btnNovo").addEventListener("click", novaVersao);

  if ($("fInicio").value) preview();
  else {
    $("calPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver a grade.</p>';
    $("docPreview").innerHTML =
      '<p class="muted">Informe a data de início para ver o documento.</p>';
  }
})();
