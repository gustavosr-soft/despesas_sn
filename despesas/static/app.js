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
