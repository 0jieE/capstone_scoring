// Results page live updates: poll the status endpoint every 5 seconds,
// update the submission chips, and reload when the result completes (or is
// reopened by an unlock).
(function () {
  "use strict";

  var card = document.getElementById("status-card");
  if (!card || !card.dataset.statusUrl) return;

  var url = card.dataset.statusUrl;
  var pageComplete = card.dataset.complete === "1";
  var INTERVAL = 5000;
  var CHIP = { submitted: "chip-ok", draft: "chip-warn", not_started: "chip-muted" };

  function setChip(el, cls, text) {
    if (!el) return;
    el.classList.remove("chip-ok", "chip-warn", "chip-muted");
    el.classList.add(cls);
    el.textContent = text;
  }

  function apply(data) {
    // Reload when the result completes or reopens, or when a panelist
    // changes scores they already submitted.
    if (data.complete !== pageComplete ||
        (data.version !== undefined && data.version !== (card.dataset.version || ""))) {
      window.location.reload();
      return;
    }
    setChip(document.getElementById("submitted-chip"),
            data.complete ? "chip-ok" : (data.submitted ? "chip-warn" : "chip-muted"),
            data.submitted + "/" + data.total + " submitted");
    (data.panelists || []).forEach(function (p) {
      var li = card.querySelector('[data-assignment="' + p.assignment + '"]');
      if (li) setChip(li.querySelector(".status-chip"), CHIP[p.status] || "chip-muted", p.status_label);
    });
    if (String(data.submitted) !== card.dataset.submitted && card.querySelector(".row-tools")) {
      // Manager view: unlock buttons depend on submission state.
      window.location.reload();
    }
  }

  function poll() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", url, true);
    xhr.setRequestHeader("Accept", "application/json");
    xhr.onload = function () {
      if (xhr.status === 200) {
        try { apply(JSON.parse(xhr.responseText)); } catch (e) { /* ignore bad payload */ }
      }
      schedule();
    };
    xhr.onerror = schedule;
    xhr.send();
  }

  function schedule() { window.setTimeout(poll, INTERVAL); }

  schedule();
})();
