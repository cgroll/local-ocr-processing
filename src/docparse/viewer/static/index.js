// Index page: filter the document table by group, tag and free text.
(function () {
  "use strict";
  var group = document.getElementById("f-group");
  var tag = document.getElementById("f-tag");
  var text = document.getElementById("f-text");
  var count = document.getElementById("f-count");
  var rows = Array.prototype.slice.call(document.querySelectorAll("#docs tbody tr"));

  function apply() {
    var g = group.value;
    var t = tag.value ? ";" + tag.value + ";" : "";
    var q = text.value.trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (r) {
      var ok = (!g || r.dataset.group === g) &&
               (!t || r.dataset.tags.indexOf(t) >= 0) &&
               (!q || r.dataset.search.indexOf(q) >= 0);
      r.hidden = !ok;
      if (ok) shown++;
    });
    count.textContent = shown + " / " + rows.length + " Dokumente";
  }

  [group, tag].forEach(function (n) { n.addEventListener("change", apply); });
  text.addEventListener("input", apply);
  apply();
})();
