// Page view: original with engine layers, reconstruction, engine comparison, block inspector.
// All result text goes through textContent; only generator-sanitized table HTML is assigned as markup.
(function () {
  "use strict";

  var ENGINES = ["pymupdf", "layout", "ocr", "vl"];
  var TEXT_TYPES = ["text", "title", "header", "footer", "caption", "list", "line"];
  var IMAGE_TYPES = ["figure", "image", "drawing", "chart"];
  var STORE_KEY = "docparse-viewer";
  // Same wording digest/markdown.py's VISUAL_HEADINGS uses, so the gallery heading matches the
  // text heading already visible above it in the Markdown column.
  var VISUAL_HEADINGS = { table: "Tabelle", chart: "Diagramm", figure: "Abbildung" };
  var GALLERY_THUMB_W = 260; // px, independent of the Original column's current zoom

  var app = document.getElementById("app");
  var data = JSON.parse(document.getElementById("page-data").textContent);
  var imageHref = app.dataset.image;
  var pages = app.dataset.pages ? app.dataset.pages.split(",").map(Number) : [];

  // ---- persistent per-viewer state (engine choices, mode); layers always start off ----
  var memory = {};
  function loadPrefs() {
    try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {}; } catch (e) { return memory; }
  }
  function savePrefs() {
    var prefs = { mode: state.mode, engineA: state.engineA, engineB: state.engineB };
    memory = prefs;
    try { localStorage.setItem(STORE_KEY, JSON.stringify(prefs)); } catch (e) { /* no storage: keep in memory */ }
  }

  function engineOk(name) { return data.engines[name] && data.engines[name].state === "ok"; }
  function firstOk(preferred) {
    for (var i = 0; i < preferred.length; i++) if (engineOk(preferred[i])) return preferred[i];
    return preferred[0];
  }

  var prefs = loadPrefs();
  var state = {
    mode: prefs.mode === "compare" ? "compare" : "single",
    engineA: ENGINES.indexOf(prefs.engineA) >= 0 ? prefs.engineA : firstOk(["vl", "pymupdf", "ocr", "layout"]),
    engineB: ENGINES.indexOf(prefs.engineB) >= 0 ? prefs.engineB : firstOk(["ocr", "layout", "pymupdf", "vl"]),
    layers: {},   // engine -> bool
    hidden: {},   // engine -> {type: true}
    selected: null,
  };
  ENGINES.forEach(function (e) { state.layers[e] = false; state.hidden[e] = {}; });

  // ---- helpers ----
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  function px(n) { return n + "px"; }
  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function blocksOf(engine) { return engineOk(engine) ? data.engines[engine].blocks : []; }
  function findBlock(id) {
    var engine = id.split(":")[0];
    return blocksOf(engine).filter(function (b) { return b.id === id; })[0] || null;
  }
  function statusText(engine) {
    var r = data.engines[engine];
    if (r.state === "missing") return "nicht verarbeitet";
    if (r.state === "error") return "Fehler: " + r.error;
    return "";
  }
  function bboxSize(b) { return { x: b.bbox[0], y: b.bbox[1], w: b.bbox[2] - b.bbox[0], h: b.bbox[3] - b.bbox[1] }; }

  // ---- layout ----
  var pageSize = data.size;
  var toolbar, stageScroll, stage, inspector;
  var views = []; // {wrap, page} for scaling

  function build() {
    app.textContent = "";
    toolbar = el("div", "toolbar");
    stageScroll = el("div", "stage-scroll");
    stage = el("div", "stage");
    stageScroll.appendChild(stage);
    inspector = el("aside", "inspector");
    app.appendChild(toolbar);
    app.appendChild(stageScroll);
    app.appendChild(inspector);
    render();
    window.addEventListener("resize", applyScale);
  }

  function render() {
    views = [];
    renderToolbar();
    stage.textContent = "";
    if (state.mode === "compare") {
      stage.appendChild(reconColumn("engineA"));
      stage.appendChild(reconColumn("engineB"));
    } else if (state.mode === "markdown") {
      stage.appendChild(originalColumn());
      stage.appendChild(markdownColumn());
    } else {
      stage.appendChild(originalColumn());
      stage.appendChild(reconColumn("engineA"));
    }
    applyScale();
    applySelection();
  }

  function applyScale() {
    var cols = stage.children.length || 1;
    var gap = 16;
    var avail = stageScroll.clientWidth - 32 - gap * (cols - 1);
    var scale = Math.max(0.1, avail / cols / pageSize[0]);
    stage.style.setProperty("--scale", String(scale));
    stage.style.setProperty("--inv", String(1 / scale));
    views.forEach(function (v) {
      v.wrap.style.width = px(pageSize[0] * scale);
      v.wrap.style.height = px(pageSize[1] * scale);
    });
  }

  // ---- toolbar ----
  function renderToolbar() {
    toolbar.textContent = "";

    var mode = el("div", "group");
    var btn = el("button", "", state.mode === "compare" ? "Vergleich beenden" : "Engines vergleichen");
    btn.type = "button";
    btn.addEventListener("click", function () {
      state.mode = state.mode === "compare" ? "single" : "compare";
      savePrefs();
      render();
    });
    mode.appendChild(btn);

    var mdBtn = el("button", "", state.mode === "markdown" ? "Markdown ausblenden" : "Markdown anzeigen");
    mdBtn.type = "button";
    mdBtn.addEventListener("click", function () {
      state.mode = state.mode === "markdown" ? "single" : "markdown";
      savePrefs();
      render();
    });
    mode.appendChild(mdBtn);
    toolbar.appendChild(mode);

    if (state.mode === "single" || state.mode === "markdown") {
      var layers = el("div", "group");
      layers.appendChild(el("span", "", "Ebenen:"));
      ENGINES.forEach(function (e) { layers.appendChild(layerControl(e)); });
      toolbar.appendChild(layers);
    }

    if (pages.length > 1) {
      var jump = el("div", "group");
      jump.appendChild(el("span", "", "Seite:"));
      var sel = el("select");
      pages.forEach(function (p) {
        var o = el("option", "", String(p));
        o.value = String(p);
        if (p === data.page) o.selected = true;
        sel.appendChild(o);
      });
      sel.addEventListener("change", function () {
        location.href = String(sel.value).padStart(4, "0") + ".html";
      });
      jump.appendChild(sel);
      toolbar.appendChild(jump);
    }
  }

  function layerControl(engine) {
    var ok = engineOk(engine);
    var wrap = el("span", "layer eng-" + engine + (state.layers[engine] ? "" : " off"));
    wrap.appendChild(el("span", "sw"));
    var label = el("label");
    var cb = el("input");
    cb.type = "checkbox";
    cb.checked = state.layers[engine];
    cb.disabled = !ok;
    cb.addEventListener("change", function () { state.layers[engine] = cb.checked; render(); });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + engine + (ok ? " (" + blocksOf(engine).length + ")" : " – " + statusText(engine))));
    wrap.appendChild(label);

    if (ok) {
      var types = [];
      blocksOf(engine).forEach(function (b) { if (types.indexOf(b.type) < 0) types.push(b.type); });
      types.sort();
      var det = el("details");
      det.appendChild(el("summary", "", "Typen"));
      var box = el("div", "types");
      types.forEach(function (t) {
        var l = el("label");
        var c = el("input");
        c.type = "checkbox";
        c.checked = !state.hidden[engine][t];
        c.addEventListener("change", function () {
          if (c.checked) delete state.hidden[engine][t]; else state.hidden[engine][t] = true;
          var open = det.open;
          render();
          // keep the filter open while toggling
          var again = toolbar.querySelectorAll(".eng-" + engine + " details")[0];
          if (again && open) again.open = true;
        });
        l.appendChild(c);
        l.appendChild(document.createTextNode(" " + t));
        box.appendChild(l);
      });
      det.appendChild(box);
      wrap.appendChild(det);
    }
    return wrap;
  }

  // ---- columns ----
  function makeView() {
    var wrap = el("div", "pagewrap");
    var page = el("div", "page");
    page.style.width = px(pageSize[0]);
    page.style.height = px(pageSize[1]);
    wrap.appendChild(page);
    views.push({ wrap: wrap, page: page });
    return { wrap: wrap, page: page };
  }

  function originalColumn() {
    var col = el("div", "col");
    var head = el("div", "col-head");
    head.appendChild(el("span", "", "Original"));
    col.appendChild(head);
    var v = makeView();
    var img = el("img");
    img.src = imageHref;
    img.alt = "page image";
    img.width = pageSize[0];
    img.height = pageSize[1];
    v.page.appendChild(img);
    ENGINES.forEach(function (e) {
      if (!state.layers[e] || !engineOk(e)) return;
      blocksOf(e).forEach(function (b) {
        if (state.hidden[e][b.type]) return;
        var r = bboxSize(b);
        var box = el("div", "box eng-" + e);
        box.dataset.id = b.id;
        box.style.left = px(r.x); box.style.top = px(r.y);
        box.style.width = px(r.w); box.style.height = px(r.h);
        var conf = typeof b.confidence === "number" ? " " + Math.round(b.confidence * 100) + "%" : "";
        box.appendChild(el("span", "", b.type + conf));
        v.page.appendChild(box);
      });
    });
    col.appendChild(v.wrap);
    return col;
  }

  function reconColumn(key) {
    var col = el("div", "col");
    var head = el("div", "col-head");
    head.appendChild(el("span", "", "Rekonstruktion"));
    var sel = el("select");
    ENGINES.forEach(function (e) {
      var o = el("option", "", e + (engineOk(e) ? "" : " (" + (data.engines[e].state === "missing" ? "nicht verarbeitet" : "Fehler") + ")"));
      o.value = e;
      if (e === state[key]) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { state[key] = sel.value; savePrefs(); render(); });
    head.appendChild(sel);
    col.appendChild(head);

    var engine = state[key];
    if (!engineOk(engine)) {
      var n = el("div", "notice" + (data.engines[engine].state === "error" ? " err" : ""), engine + ": " + statusText(engine));
      col.appendChild(n);
      return col;
    }
    var v = makeView();
    v.page.classList.add("eng-" + engine);
    blocksOf(engine).forEach(function (b) { v.page.appendChild(blockElement(b)); });
    col.appendChild(v.wrap);
    return col;
  }

  function markdownColumn() {
    var col = el("div", "col");
    var head = el("div", "col-head");
    head.appendChild(el("span", "", "Markdown"));
    col.appendChild(head);
    var body = el("div", "markdown-body");
    body.innerHTML = data.markdown_html; // sanitized server-side, see viewer/sanitize.py
    col.appendChild(body);

    var visuals = (data.visual_blocks || []).filter(function (vb) {
      return vb.status === "ok" && (vb.type === "figure" || vb.type === "chart");
    });
    if (visuals.length) {
      var gallery = el("div", "vb-gallery");
      gallery.appendChild(el("h3", "", "Erkannte Abbildungen/Diagramme"));
      visuals.forEach(function (vb) { gallery.appendChild(visualBlockPreview(vb)); });
      col.appendChild(gallery);
    }
    return col;
  }

  // Freestanding thumbnail (own scale factor, not tied to the Original/Rekonstruktion columns'
  // --scale) -- same CSS-crop-of-the-full-page-image technique as blockElement()'s ".fig" case,
  // built with safe DOM APIs only (no innerHTML -- data.markdown_html is the only sanitized-HTML
  // insertion point in this view, see viewer/sanitize.py).
  function visualBlockPreview(vb) {
    var r = bboxSize(vb);
    var k = r.w > 0 ? GALLERY_THUMB_W / r.w : 1;
    var item = el("div", "vb-item");
    var thumb = el("div", "vb-thumb");
    thumb.style.width = px(GALLERY_THUMB_W);
    thumb.style.height = px(r.h * k);
    thumb.style.backgroundImage = 'url("' + imageHref + '")';
    thumb.style.backgroundPosition = px(-r.x * k) + " " + px(-r.y * k);
    thumb.style.backgroundSize = px(pageSize[0] * k) + " " + px(pageSize[1] * k);
    item.appendChild(thumb);
    var meta = el("div", "vb-meta");
    meta.appendChild(el("div", "vb-heading", (VISUAL_HEADINGS[vb.type] || vb.type) + ": " + vb.label));
    if (vb.description) meta.appendChild(el("p", "", vb.description));
    item.appendChild(meta);
    return item;
  }

  // ---- reconstruction of one block ----
  function content(b) { return b.text || b.markdown || ""; }

  function fitFont(text, w, h) {
    var lines = text.split("\n");
    var fs = clamp(h / (lines.length * 1.2), 6, 48);
    for (var i = 0; i < 20; i++) {
      var perLine = Math.max(1, Math.floor(w / (0.5 * fs)));
      var total = 0;
      lines.forEach(function (l) { total += Math.max(1, Math.ceil(l.length / perLine)); });
      if (total * fs * 1.2 <= h || fs <= 6) break;
      fs = Math.max(6, fs * 0.92);
    }
    return fs;
  }

  function blockElement(b) {
    var r = bboxSize(b);
    var n = el("div", "blk");
    n.dataset.id = b.id;
    n.style.left = px(r.x); n.style.top = px(r.y);
    n.style.width = px(r.w); n.style.height = px(r.h);

    if (b.type === "table" && b.html) {
      n.classList.add("tbl");
      n.innerHTML = b.html; // sanitized by the generator, see viewer/sanitize.py
      var rows = Math.max(1, n.querySelectorAll("tr").length);
      n.style.fontSize = px(clamp(r.h / rows / 1.9, 6, 24));
    } else if (IMAGE_TYPES.indexOf(b.type) >= 0) {
      n.classList.add("fig");
      n.style.backgroundImage = 'url("' + imageHref + '")';
      n.style.backgroundPosition = px(-r.x) + " " + px(-r.y);
      n.style.backgroundSize = px(pageSize[0]) + " " + px(pageSize[1]);
    } else if (b.type === "formula" && content(b)) {
      n.classList.add("formula");
      n.textContent = content(b);
      n.style.fontSize = px(fitFont(content(b), r.w, r.h));
    } else if (content(b)) {
      n.classList.add("txt");
      n.textContent = content(b);
      n.style.fontSize = px(fitFont(content(b), r.w, r.h));
    } else {
      n.classList.add("empty", "eng-" + b.engine);
      n.appendChild(el("span", "", b.type));
    }
    return n;
  }

  // ---- selection and inspector ----
  function select(id) {
    state.selected = id;
    applySelection();
  }

  function applySelection() {
    app.querySelectorAll("[data-selected]").forEach(function (n) { n.removeAttribute("data-selected"); });
    if (state.selected) {
      app.querySelectorAll('[data-id="' + state.selected + '"]').forEach(function (n) { n.setAttribute("data-selected", ""); });
    }
    renderInspector();
  }

  function row(dl, k, v) {
    dl.appendChild(el("dt", "", k));
    dl.appendChild(el("dd", "", v));
  }

  function renderInspector() {
    inspector.textContent = "";
    inspector.appendChild(el("h2", "", "Block"));
    var b = state.selected ? findBlock(state.selected) : null;
    if (!b) {
      inspector.appendChild(el("p", "hint", "Block anklicken, um alle Felder zu sehen. Escape oder Klick ins Leere hebt die Auswahl auf."));
      return;
    }
    var dl = el("dl");
    row(dl, "Engine", b.engine);
    row(dl, "Typ", b.type);
    row(dl, "Bezeichnung", b.label);
    row(dl, "Box", b.bbox.map(function (v) { return Math.round(v * 10) / 10; }).join(", "));
    row(dl, "Konfidenz", typeof b.confidence === "number" ? b.confidence.toFixed(4) : "–");
    row(dl, "Reihenfolge", b.order === undefined ? "–" : String(b.order));
    inspector.appendChild(dl);
    [["text", "Text"], ["markdown", "Markdown"], ["html", "HTML (bereinigt)"]].forEach(function (f) {
      if (b[f[0]]) {
        inspector.appendChild(el("div", "", f[1]));
        inspector.appendChild(el("pre", "", b[f[0]]));
      }
    });
    if (!b.text && !b.markdown && !b.html) inspector.appendChild(el("p", "hint", "Kein Inhalt (Engine liefert nur die Box)."));
  }

  // ---- events ----
  app.addEventListener("click", function (ev) {
    var t = ev.target.closest ? ev.target.closest("[data-id]") : null;
    if (t && app.contains(t)) select(t.dataset.id);
    else if (ev.target.closest && ev.target.closest(".toolbar, .inspector, .col-head")) return;
    else select(null);
  });

  document.addEventListener("keydown", function (ev) {
    var tag = (ev.target.tagName || "").toLowerCase();
    if (tag === "input" || tag === "select" || tag === "textarea") return;
    if (ev.key === "Escape") { select(null); return; }
    var rel = ev.key === "ArrowRight" ? ["next", "next-doc"] : ev.key === "ArrowLeft" ? ["prev", "prev-doc"] : null;
    if (!rel || ev.altKey || ev.ctrlKey || ev.metaKey) return;
    var link = document.querySelector('a[rel="' + rel[0] + '"]') || document.querySelector('a[rel="' + rel[1] + '"]');
    if (link) location.href = link.getAttribute("href");
  });

  // ---- start (page size comes from a result, or from the image when none is readable) ----
  if (pageSize) {
    build();
  } else {
    var probe = new Image();
    probe.onload = function () { pageSize = [probe.naturalWidth, probe.naturalHeight]; build(); };
    probe.onerror = function () { app.textContent = "Seitenbild nicht gefunden: " + imageHref; };
    probe.src = imageHref;
  }
})();
