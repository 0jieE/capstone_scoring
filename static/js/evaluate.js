// Live subtotals on the evaluation form.
//
// Mirrors defense/scoring.py score_ratings() exactly, using integer
// arithmetic (no floats): weights are read as thousandths, so r x w is an
// integer number of thousandths. Rounding is ROUND_HALF_UP to 2 decimals.
//   A, B         = sum r*w of the group criteria in that section
//   C(proponent) = sum r*w of the per-proponent criteria for that proponent
//   C            = average C across proponents
//   FINAL        = A + B + C;  FINAL(proponent) = A + B + C(proponent)
// The server recomputes everything on save.
(function () {
  "use strict";

  var form = document.getElementById("eval-form");
  if (!form) return;

  var labels = {};
  try { labels = JSON.parse(document.getElementById("verdict-labels").textContent); } catch (e) { /* ignore */ }

  // "0.150" -> 150 (thousandths); "4.50" -> 4500
  function thousandths(str) {
    var m = /^\s*(\d+)(?:\.(\d*))?\s*$/.exec(String(str));
    if (!m) return 0;
    return parseInt(m[1], 10) * 1000 + parseInt(((m[2] || "") + "000").slice(0, 3), 10);
  }

  // Round num/den thousandths to hundredths, half up (num, den >= 0).
  function roundHundredths(num, den) {
    // value in hundredths = num / (10 * den); half up = floor((2num + 10den) / (20den))
    return Math.floor((2 * num + 10 * den) / (20 * den));
  }

  function fmt(hundredths) {
    var whole = Math.floor(hundredths / 100), frac = hundredths % 100;
    return whole + "." + (frac < 10 ? "0" : "") + frac;
  }

  var cut = (form.dataset.cutoffs || "4.50,3.50,2.50").split(",").map(function (c) {
    return Math.round(thousandths(c) / 10); // hundredths
  });

  function verdictOf(hundredths) {
    if (hundredths >= cut[0]) return "PASSED";
    if (hundredths >= cut[1]) return "MINOR";
    if (hundredths >= cut[2]) return "MAJOR";
    return "FAILED";
  }

  var proponents = (form.dataset.proponents || "").split(",").filter(Boolean);
  var criteria = Array.prototype.map.call(form.querySelectorAll(".criterion"), function (el) {
    return {
      el: el,
      section: el.dataset.section,
      weight: thousandths(el.dataset.weight),
      perProponent: el.dataset.perProponent === "1",
    };
  });

  function checkedValue(name) {
    var input = form.querySelector('input[name="' + name + '"]:checked');
    return input ? parseInt(input.value, 10) : null;
  }

  function setText(id, text) {
    var el = document.getElementById(id);
    if (el) el.textContent = text;
  }

  function recompute() {
    var shared = { A: 0, B: 0, C: 0 };          // thousandths
    var perProp = {};                            // pid -> {A,B,C} thousandths (per-proponent part)
    proponents.forEach(function (pid) { perProp[pid] = { A: 0, B: 0, C: 0 }; });
    var missing = 0;

    criteria.forEach(function (c) {
      var rows = c.el.querySelectorAll(".rating-row");
      Array.prototype.forEach.call(rows, function (row) {
        var r = checkedValue(row.dataset.name);
        var out = row.querySelector(".row-score");
        row.classList.toggle("unrated", r === null);
        if (r === null) {
          missing++;
          if (out) out.textContent = "—";
          return;
        }
        var ws = r * c.weight;
        if (out) out.textContent = "× " + fmt(roundHundredths(c.weight, 1)) + " = " + fmt(roundHundredths(ws, 1));
        if (c.perProponent) {
          var pid = row.dataset.proponent;
          if (perProp[pid]) perProp[pid][c.section] += ws;
        } else {
          shared[c.section] += ws;
        }
      });
    });

    var n = proponents.length;
    var sums = { A: 0, B: 0, C: 0 };             // sum over proponents (thousandths)
    proponents.forEach(function (pid) {
      var p = perProp[pid], finalP = 0;
      ["A", "B", "C"].forEach(function (s) {
        var v = shared[s] + p[s];
        sums[s] += v;
        finalP += v;
      });
      var row = form.querySelector('[data-proponent-row="' + pid + '"]');
      if (row) {
        row.querySelector(".p-c").textContent = fmt(roundHundredths(shared.C + p.C, 1));
        row.querySelector(".p-final").textContent = fmt(roundHundredths(finalP, 1));
      }
    });
    if (n === 0) { n = 1; sums = shared; }

    var finalH = roundHundredths(sums.A + sums.B + sums.C, n);
    setText("sum-A", fmt(roundHundredths(sums.A, n)));
    setText("sum-B", fmt(roundHundredths(sums.B, n)));
    setText("sum-C", fmt(roundHundredths(sums.C, n)));
    setText("sum-final", fmt(finalH));
    setText("bar-final", fmt(finalH));

    var pill = document.getElementById("sum-verdict");
    var text, cls = "";
    if (missing === 0) {
      var v = verdictOf(finalH);
      text = labels[v] || v;
      cls = "v-" + ({ PASSED: "passed", MINOR: "minor", MAJOR: "major", FAILED: "failed" })[v];
    } else {
      text = missing + " rating" + (missing === 1 ? "" : "s") + " left";
    }
    if (pill) { pill.textContent = text; pill.className = "verdict-pill " + cls; }
    setText("bar-verdict", missing === 0 ? text : missing + " left");
    return missing;
  }

  form.addEventListener("change", recompute);
  recompute();

  // On phones the rating guides fill the screen; start them collapsed.
  if (window.matchMedia && window.matchMedia("(max-width: 680px)").matches) {
    Array.prototype.forEach.call(form.querySelectorAll("details.descriptors[open]"), function (d) {
      d.removeAttribute("open");
    });
  }

  var submitBtn = document.getElementById("submit-btn");
  if (submitBtn) {
    submitBtn.addEventListener("click", function (ev) {
      var missing = recompute();
      if (missing > 0) {
        ev.preventDefault();
        var first = form.querySelector(".rating-row.unrated");
        if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
        window.alert("Please rate every item before saving (" + missing + " missing)." +
                     (submitBtn.dataset.resubmit ? "" : " You can use Save draft to keep partial ratings."));
        return;
      }
      var finalText = document.getElementById("sum-final").textContent;
      var verdictText = document.getElementById("sum-verdict").textContent;
      var question = submitBtn.dataset.resubmit
        ? "Save your changes?\n\nFINAL " + finalText + " (" + verdictText + ")\n\nThis replaces the scores you submitted."
        : "Submit your evaluation?\n\nFINAL " + finalText + " (" + verdictText + ")" +
          "\n\nYou can still change it until the Research Coordinator closes scoring.";
      if (!window.confirm(question)) {
        ev.preventDefault();
      }
    });
  }

  // Warn before leaving with unsaved changes.
  var dirty = false;
  form.addEventListener("change", function () { dirty = true; });
  form.addEventListener("input", function () { dirty = true; });
  form.addEventListener("submit", function () { dirty = false; });
  window.addEventListener("beforeunload", function (e) {
    if (dirty && !form.classList.contains("is-locked")) { e.preventDefault(); e.returnValue = ""; }
  });
})();
