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
    feriados: (inicial.feriados || []).map(function (d) {
      return { data: d, descricao: "", origem: "manual" };
    })
  };

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

  // ---- Formulário --------------------------------------------------------
  function fill() {
    $("fVersao").value = inicial.versao || "";
    $("fTitulo").value = inicial.titulo || "";
    $("fPeriodo").value = inicial.periodo || "";
    $("fInicio").value = inicial.data_inicio || "";
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
      data_inicio: $("fInicio").value,
      total_semanas: parseInt($("fSemanas").value || "0", 10),
      semanas_primeira_parte: parseInt($("fSemanas1").value || "0", 10),
      etapa: parseInt($("fEtapa").value || "1", 10),
      final: $("fFinal").checked,
      observacoes: $("fObs").value,
      feriados: state.feriados
    };
  }

  // ---- Feriados ----------------------------------------------------------
  function temFeriado(iso) {
    return state.feriados.some(function (f) {
      return f.data === iso;
    });
  }

  function addFeriado(iso, descricao, origem) {
    if (!iso || temFeriado(iso)) return;
    state.feriados.push({
      data: iso,
      descricao: descricao || "",
      origem: origem || "manual"
    });
  }

  function toggleFeriado(iso) {
    if (temFeriado(iso)) {
      state.feriados = state.feriados.filter(function (f) {
        return f.data !== iso;
      });
    } else {
      addFeriado(iso, "", "manual");
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
        return (
          '<li class="chip chip-removable" data-date="' +
          esc(f.data) +
          '">' +
          esc(rotulo) +
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

  // ---- Prévia da grade ---------------------------------------------------
  function metric(rotulo, valor, sub) {
    return (
      '<div class="cal-metric"><span class="cal-metric-label">' +
      esc(rotulo) +
      "</span><strong>" +
      esc(valor) +
      "</strong><small>" +
      esc(sub) +
      "</small></div>"
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
        "quanto menor, melhor"
      ) +
      "</div>";

    if (d.erros && d.erros.length) {
      html +=
        '<div class="cal-alert"><strong>Ajustes necessários:</strong><ul>' +
        d.erros.map(function (e) {
          return "<li>" + esc(e) + "</li>";
        }).join("") +
        "</ul></div>";
    }

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
        var cls =
          "cal-cell" +
          (cell.free ? " cal-free" : "") +
          (cell.part === 1 ? " cal-part1" : "");
        html +=
          '<td class="' +
          cls +
          '" style="background:' +
          esc(cell.color) +
          ';" data-date="' +
          esc(cell.date) +
          '"><span class="cal-date">' +
          (cell.label_html || "") +
          "</span></td>";
      });
      html += "</tr>";
    });
    html += "</tbody></table>";

    var alvo = $("calPreview");
    alvo.innerHTML = html;
    Array.prototype.forEach.call(alvo.querySelectorAll(".cal-cell[data-date]"), function (td) {
      td.addEventListener("click", function () {
        toggleFeriado(td.getAttribute("data-date"));
      });
    });
  }

  var timer = null;
  function agendarPreview() {
    clearTimeout(timer);
    timer = setTimeout(preview, 180);
  }

  function preview() {
    postJSON(BASE + "api/preview/", payload()).then(function (d) {
      if (d && d.linhas) renderPreview(d);
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
    fill();
    renderChips();
    preview();
    msg("Novo formulário pronto para uma nova versão.", "ok");
  }

  // ---- Inicialização -----------------------------------------------------
  fill();
  renderChips();
  ["fInicio", "fSemanas", "fSemanas1"].forEach(function (id) {
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
    addFeriado(valor, "", "manual");
    $("fFeriado").value = "";
    renderChips();
    preview();
  });
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
  }
})();
