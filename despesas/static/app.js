// Sem scripts inline (a política de segurança do servidor não permite).
document.addEventListener("submit", function (e) {
  var msg = e.target && e.target.getAttribute && e.target.getAttribute("data-confirmar");
  if (msg && !window.confirm(msg)) { e.preventDefault(); }
});
document.addEventListener("click", function (e) {
  if (e.target.closest("[data-print]")) { window.print(); }
  if (e.target.closest("[data-fechar]")) { window.close(); }
});
window.addEventListener("load", function () {
  if (document.body.getAttribute("data-auto-print")) {
    setTimeout(function () { window.print(); }, 400);
  }
});
