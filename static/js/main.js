(function () {
  // Tema claro/escuro
  var btn = document.getElementById('themeToggle');
  var saved = null;
  try { saved = localStorage.getItem('site-theme'); } catch (e) {}
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem('site-theme', theme); } catch (e) {}
  }
  if (saved) applyTheme(saved);
  else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) applyTheme('dark');
  if (btn) {
    btn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      applyTheme(cur === 'dark' ? 'light' : 'dark');
    });
  }

  // Seletor de versão (página inicial) — navega para a versão escolhida.
  var versionForm = document.getElementById('homeVersionForm');
  var versionSel = document.getElementById('homeVersion');
  if (versionSel) {
    var goVersion = function () {
      if (versionSel.value) window.location.href = versionSel.value;
    };
    versionSel.addEventListener('change', goVersion);
    if (versionForm) {
      versionForm.addEventListener('submit', function (ev) {
        ev.preventDefault();
        goVersion();
      });
    }
  }

  // Exportar para PDF — usa a impressão do próprio navegador ("Salvar como PDF").
  // Nenhuma biblioteca e nenhuma requisição: por isso funciona no site estático
  // gerado no build (GitHub Pages), inclusive offline.
  var applyGridMode = null; // definido mais abaixo quando a página tem grade
  var currentGridMode = 'superCondensed';
  var printState = null;

  function restorePrintState() {
    if (!printState) return;
    if (printState.mode && applyGridMode) applyGridMode(printState.mode);
    document.title = printState.title;
    printState = null;
  }

  // Carimba a data/hora da geração no cabeçalho impresso (`_print_head.html`).
  function stampPrintDate() {
    var stamp = document.getElementById('printDate');
    if (!stamp) return;
    try { stamp.textContent = 'Gerado em ' + new Date().toLocaleString('pt-BR'); } catch (e) { stamp.textContent = ''; }
  }

  var printButtons = document.querySelectorAll('[data-print-pdf]');
  Array.prototype.forEach.call(printButtons, function (btn) {
    btn.addEventListener('click', function () {
      stampPrintDate();

      // A grade precisa sair completa no PDF: o modo "super condensado" esconde
      // linhas e colunas com display:none inline.
      var mode = btn.getAttribute('data-print-mode');
      printState = {
        mode: (mode && applyGridMode) ? currentGridMode : null,
        title: document.title
      };
      if (mode && applyGridMode) applyGridMode(mode);

      // O título vira o nome sugerido do arquivo ao salvar como PDF.
      var pdfTitle = btn.getAttribute('data-print-title');
      if (pdfTitle) document.title = pdfTitle;

      window.print();
      // Fallback para navegadores que não disparam `afterprint`.
      window.setTimeout(restorePrintState, 1200);
    });
  });
  window.addEventListener('afterprint', function () {
    window.setTimeout(restorePrintState, 0);
  });
  // Impressão pelo atalho do navegador (Ctrl+P) também ganha a data no cabeçalho.
  window.addEventListener('beforeprint', stampPrintDate);

  // Modos de visualização da grade
  var table = document.getElementById('timetable');
  if (!table) return;
  var rows = Array.prototype.slice.call(table.querySelectorAll('tbody .time-row'));
  var first = parseInt(table.dataset.first || '0', 10);
  var last = parseInt(table.dataset.last || (rows.length - 1), 10);
  var activeDays = new Set((table.dataset.activeDays || '').split('|').filter(Boolean));

  function apply(mode) {
    currentGridMode = mode;
    rows.forEach(function (row, i) {
      var hasClass = row.classList.contains('row-active');
      if (mode === 'completed') row.style.display = '';
      else if (mode === 'condensed') row.style.display = (i >= first && i <= last) ? '' : 'none';
      else row.style.display = hasClass ? '' : 'none';
    });
    table.querySelectorAll('.day-head, .day-cell').forEach(function (el) {
      var day = el.getAttribute('data-day');
      el.style.display = (mode === 'superCondensed' && !activeDays.has(day)) ? 'none' : '';
    });
  }
  applyGridMode = apply;

  var toolbar = document.querySelector('.timetable-toolbar') || table.previousElementSibling;
  var modeBtns = (toolbar && toolbar.querySelectorAll) ? toolbar.querySelectorAll('.mode-btn') : [];
  Array.prototype.forEach.call(modeBtns, function (b) {
    b.addEventListener('click', function () {
      Array.prototype.forEach.call(modeBtns, function (x) { x.classList.remove('active'); });
      b.classList.add('active');
      apply(b.getAttribute('data-mode'));
    });
  });

  // Aplica o modo padrão ao abrir a página (botão ativo no HTML, ou superCondensed).
  var current = (toolbar && toolbar.querySelector) ? toolbar.querySelector('.mode-btn.active') : null;
  apply(current ? current.getAttribute('data-mode') : 'superCondensed');
})();
