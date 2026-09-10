/**
 * Tooltip dos dias do documento publicado (/calendario/ e /versoes/<slug>/).
 *
 * As células das grades (mensal e x1/x2) levam "data-tip" com data, status e
 * eventos; aqui exibimos uma caixa própria no lugar do "title" nativo, que é
 * lento e não aparece no toque. É o mesmo comportamento da prévia do editor
 * (``static/js/editor.js``), mas a página publicada não é clicável — por isso o
 * texto não convida a marcar/desmarcar feriado.
 */
(function () {
  "use strict";

  var tooltipEl = null;

  function tooltip() {
    if (!tooltipEl) {
      tooltipEl = document.createElement("div");
      tooltipEl.className = "doc-tooltip";
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
  // Acessibilidade: as células recebem foco por teclado (aria-label + data-tip).
  document.addEventListener("focusin", function (ev) {
    var alvo = alvoComDica(ev.target);
    if (!alvo) return;
    var box = alvo.getBoundingClientRect();
    mostrarTooltip(alvo, box.left, box.bottom);
  });
  document.addEventListener("focusout", esconderTooltip);
  window.addEventListener("scroll", esconderTooltip, true);
  window.addEventListener("blur", esconderTooltip);
})();
