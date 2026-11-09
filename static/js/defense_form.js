// Defense form: add proponent rows (Django formset).
(function () {
  "use strict";

  var addBtn = document.getElementById("add-proponent");
  var list = document.getElementById("proponent-rows");
  var tpl = document.getElementById("proponent-template");
  var total = document.querySelector('input[name="proponents-TOTAL_FORMS"]');

  function refreshAdd() {
    if (!addBtn || !total) return;
    addBtn.disabled = parseInt(total.value, 10) >= parseInt(addBtn.dataset.max, 10);
  }

  if (addBtn && list && tpl && total) {
    addBtn.addEventListener("click", function () {
      var index = parseInt(total.value, 10);
      if (index >= parseInt(addBtn.dataset.max, 10)) return;
      var html = tpl.innerHTML.replace(/__prefix__/g, String(index));
      var holder = document.createElement("ol");
      holder.innerHTML = html.trim();
      var row = holder.firstElementChild;
      list.appendChild(row);
      total.value = String(index + 1);
      var input = row.querySelector("input[type=text]");
      if (input) input.focus();
      refreshAdd();
    });
    refreshAdd();
  }
})();
