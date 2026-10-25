// Sem scripts inline (a política de segurança do servidor não permite).
document.addEventListener("submit", function (e) {
  var msg = e.target && e.target.getAttribute && e.target.getAttribute("data-confirmar");
  if (msg && !window.confirm(msg)) { e.preventDefault(); }
});
document.addEventListener("click", function (e) {
  if (e.target.closest("[data-print]")) { window.print(); }
  if (e.target.closest("[data-print-pdf]")) { imprimirPdf(); }
  if (e.target.closest("[data-fechar]")) { window.close(); }
});
window.addEventListener("load", function () {
  if (document.body.getAttribute("data-auto-print")) {
    setTimeout(function () { window.print(); }, 400);
  }
});

// Escolha do estilo de PDF (tela do mês): guarda a escolha e ajusta o link.
(function () {
  var sel = document.getElementById("pdf-estilo-select");
  var link = document.getElementById("pdf-link");
  if (!sel || !link) { return; }
  var base = link.getAttribute("href").split("?")[0];
  var imp = document.getElementById("imprimir-link");
  var impBase = imp ? imp.getAttribute("href").split("?")[0] : "";
  try {
    var salvo = localStorage.getItem("despesas-pdf-estilo");
    if (salvo) { sel.value = salvo; }
  } catch (e) {}
  function atualizar() {
    link.setAttribute("href", base + "?estilo=" + encodeURIComponent(sel.value));
    if (imp) { imp.setAttribute("href", impBase + "?estilo=" + encodeURIComponent(sel.value)); }
    try { localStorage.setItem("despesas-pdf-estilo", sel.value); } catch (e) {}
  }
  sel.addEventListener("change", atualizar);
  document.addEventListener("DOMContentLoaded", atualizar);
})();

// Imprime o PDF mostrado no quadro da tela "Imprimir".
function imprimirPdf() {
  var f = document.getElementById("pdf-frame");
  if (!f) { return; }
  try { f.contentWindow.focus(); f.contentWindow.print(); } catch (e) { window.print(); }
}
window.addEventListener("load", function () {
  var f = document.getElementById("pdf-frame");
  if (f && document.body.getAttribute("data-auto-print-pdf")) {
    setTimeout(imprimirPdf, 1200);
  }
});

// Tela Relatórios: atalhos de período e seleção de categorias.
(function () {
  var ini = document.getElementById("rel-inicio");
  var fim = document.getElementById("rel-fim");
  if (!ini || !fim) { return; }
  function iso(d) {
    var m = d.getMonth() + 1, dia = d.getDate();
    return d.getFullYear() + "-" + (m < 10 ? "0" : "") + m + "-" + (dia < 10 ? "0" : "") + dia;
  }
  function periodo(nome) {
    var h = new Date(), a = h.getFullYear(), m = h.getMonth();
    switch (nome) {
      case "hoje": return [h, h];
      case "ontem": var o = new Date(a, m, h.getDate() - 1); return [o, o];
      case "semana": var seg = new Date(a, m, h.getDate() - ((h.getDay() + 6) % 7)); return [seg, h];
      case "mes": return [new Date(a, m, 1), new Date(a, m + 1, 0)];
      case "mes-passado": return [new Date(a, m - 1, 1), new Date(a, m, 0)];
      case "3meses": return [new Date(a, m - 2, 1), new Date(a, m + 1, 0)];
      case "6meses": return [new Date(a, m - 5, 1), new Date(a, m + 1, 0)];
      case "ano": return [new Date(a, 0, 1), new Date(a, 11, 31)];
      case "ano-passado": return [new Date(a - 1, 0, 1), new Date(a - 1, 11, 31)];
    }
    return null;
  }
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-preset]");
    if (b) {
      var p = periodo(b.getAttribute("data-preset"));
      if (p) { ini.value = iso(p[0]); fim.value = iso(p[1]); }
    }
    var c = e.target.closest("[data-cats]");
    if (c) {
      var marcar = c.getAttribute("data-cats") === "todas";
      document.querySelectorAll('input[name="cat"]').forEach(function (x) { x.checked = marcar; });
    }
  });
})();
