// Page view: original with engine layers, reconstruction, engine comparison, block inspector.
// All result text goes through textContent; only generator-sanitized table HTML is assigned as markup.
(function () {
  "use strict";

  var ENGINES = ["pymupdf", "layout", "ocr", "vl"];
  var TEXT_TYPES = ["text", "title", "header", "footer", "caption", "list", "line", "cell"];
  var IMAGE_TYPES = ["figure", "image", "drawing", "chart"];
  var STORE_KEY = "docparse-viewer";

  // Original-image overlays are grouped by *granularity*, not by engine: "Einzeltext" (line/word
  // level) vs. "Komponenten" (region level). pymupdf is the only engine that delivers both, so it is
  // split by block type; ocr is all single text (lines); layout and vl are all region-level blocks.
  // Each layer draws a subset of one engine's blocks. (Reconstruction/compare stay engine-based.)
  function isText(b) { return TEXT_TYPES.indexOf(b.type) >= 0; }
  var LAYERS = [
    { key: "text-pymupdf", label: "Text (pymupdf)", engine: "pymupdf", pick: isText },
    { key: "text-ocr", label: "Text (ocr)", engine: "ocr", pick: function () { return true; } },
    { key: "comp-pymupdf", label: "Komponenten (pymupdf)", engine: "pymupdf", pick: function (b) { return !isText(b); } },
    { key: "comp-layout", label: "Komponenten (layout)", engine: "layout", pick: function () { return true; } },
    { key: "comp-vl", label: "Komponenten (vl)", engine: "vl", pick: function () { return true; } },
  ];
  function layerBlocks(layer) { return blocksOf(layer.engine).filter(layer.pick); }
  // Same wording digest/markdown.py's VISUAL_HEADINGS uses, so the gallery heading matches the
  // text heading already visible above it in the Markdown column.
  var VISUAL_HEADINGS = { table: "Tabelle", chart: "Diagramm", figure: "Abbildung" };
  var GALLERY_THUMB_W = 260; // px, independent of the Original column's current zoom
  // Overlay colours: linked layout elements (in the order of data.links) take these in turn, and a
  // Markdown section takes the colour of the first layout element linking to it.
  var LINK_COLORS = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#9a6324"];

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
    var prefs = { mode: state.mode, engineA: state.engineA, engineB: state.engineB, overlay: state.overlay };
    memory = prefs;
    try { localStorage.setItem(STORE_KEY, JSON.stringify(prefs)); } catch (e) { /* no storage: keep in memory */ }
  }

  function engineOk(name) { return data.engines[name] && data.engines[name].state === "ok"; }
  function firstOk(preferred) {
    for (var i = 0; i < preferred.length; i++) if (engineOk(preferred[i])) return preferred[i];
    return preferred[0];
  }

  var prefs = loadPrefs();
  // Right column: "markdown" (default) or an engine. Older saved modes ("markdown") fall back to single.
  var state = {
    mode: prefs.mode === "compare" ? "compare" : "single",
    engineA: prefs.engineA === "markdown" || ENGINES.indexOf(prefs.engineA) >= 0 ? prefs.engineA : "markdown",
    engineB: ENGINES.indexOf(prefs.engineB) >= 0 ? prefs.engineB : firstOk(["ocr", "layout", "pymupdf", "vl"]),
    overlay: prefs.overlay === true,  // Verknüpfungen anzeigen (only with the Markdown column)
    layers: {},   // layer key -> bool
    hidden: {},   // layer key -> {type: true}
    selected: null,
  };
  LAYERS.forEach(function (l) { state.layers[l.key] = false; state.hidden[l.key] = {}; });
  var sectionEls = {};  // Markdown section id -> element, rebuilt with each render

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
      stage.appendChild(reconColumn("engineA", false));
      stage.appendChild(reconColumn("engineB", false));
    } else {
      stage.appendChild(originalColumn());
      stage.appendChild(reconColumn("engineA", true));
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
    toolbar.appendChild(mode);

    if (state.mode === "single") {
      var layers = el("div", "group");
      layers.appendChild(el("span", "", "Ebenen:"));
      LAYERS.forEach(function (l) { layers.appendChild(layerControl(l)); });
      toolbar.appendChild(layers);
    }

    if (markdownShown()) {
      var links = el("div", "group");
      var linkLabel = el("label");
      var linkBox = el("input");
      linkBox.type = "checkbox";
      linkBox.checked = state.overlay;
      linkBox.addEventListener("change", function () { state.overlay = linkBox.checked; savePrefs(); render(); });
      linkLabel.appendChild(linkBox);
      linkLabel.appendChild(document.createTextNode(" Verknüpfungen anzeigen"));
      links.appendChild(linkLabel);
      toolbar.appendChild(links);
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

  function layerControl(layer) {
    var engine = layer.engine;
    var ok = engineOk(engine);
    var blocks = ok ? layerBlocks(layer) : [];
    var wrap = el("span", "layer lay-" + layer.key + " eng-" + engine + (state.layers[layer.key] ? "" : " off"));
    wrap.appendChild(el("span", "sw"));
    var label = el("label");
    var cb = el("input");
    cb.type = "checkbox";
    cb.checked = state.layers[layer.key];
    cb.disabled = !ok || blocks.length === 0;
    cb.addEventListener("change", function () { state.layers[layer.key] = cb.checked; render(); });
    label.appendChild(cb);
    label.appendChild(document.createTextNode(" " + layer.label + (ok ? " (" + blocks.length + ")" : " – " + statusText(engine))));
    wrap.appendChild(label);

    if (ok && blocks.length) {
      var types = [];
      blocks.forEach(function (b) { if (types.indexOf(b.type) < 0) types.push(b.type); });
      types.sort();
      var det = el("details");
      det.appendChild(el("summary", "", "Typen"));
      var box = el("div", "types");
      types.forEach(function (t) {
        var l = el("label");
        var c = el("input");
        c.type = "checkbox";
        c.checked = !state.hidden[layer.key][t];
        c.addEventListener("change", function () {
          if (c.checked) delete state.hidden[layer.key][t]; else state.hidden[layer.key][t] = true;
          var open = det.open;
          render();
          // keep the filter open while toggling
          var again = toolbar.querySelectorAll(".lay-" + layer.key + " details")[0];
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
    LAYERS.forEach(function (layer) {
      if (!state.layers[layer.key] || !engineOk(layer.engine)) return;
      layerBlocks(layer).forEach(function (b) {
        if (state.hidden[layer.key][b.type]) return;
        var r = bboxSize(b);
        var box = el("div", "box eng-" + layer.engine);
        box.dataset.id = b.id;
        box.style.left = px(r.x); box.style.top = px(r.y);
        box.style.width = px(r.w); box.style.height = px(r.h);
        var conf = typeof b.confidence === "number" ? " " + Math.round(b.confidence * 100) + "%" : "";
        box.appendChild(el("span", "", b.type + conf));
        v.page.appendChild(box);
      });
    });
    if (overlayOn()) {
      // Overlay: every layout element that has a linked Markdown section, in its link colour.
      Object.keys(data.links).forEach(function (lid) {
        var b = findBlock(lid);
        if (!b) return;
        var r = bboxSize(b);
        var box = el("div", "lnk-box");
        box.dataset.id = lid;
        box.style.left = px(r.x); box.style.top = px(r.y);
        box.style.width = px(r.w); box.style.height = px(r.h);
        box.style.borderColor = linkColour(lid);
        v.page.appendChild(box);
      });
    }
    col.appendChild(v.wrap);
    return col;
  }

  // Markdown view and its links (single mode only).
  function markdownShown() { return state.mode === "single" && state.engineA === "markdown"; }
  function overlayOn() { return markdownShown() && state.overlay; }
  function linkColour(layoutId) {
    return LINK_COLORS[Object.keys(data.links).indexOf(layoutId) % LINK_COLORS.length];
  }
  // section id -> colour of the first layout element linking to it
  function sectionColours() {
    var out = {};
    Object.keys(data.links).forEach(function (lid) {
      data.links[lid].forEach(function (i) { if (!(i in out)) out[i] = linkColour(lid); });
    });
    return out;
  }
  // Engine behind a right column in compare mode, where a stored "markdown" choice has no meaning.
  function engineChoice(key) {
    if (ENGINES.indexOf(state[key]) >= 0) return state[key];
    return key === "engineA" ? firstOk(["vl", "pymupdf", "ocr", "layout"]) : firstOk(["ocr", "layout", "pymupdf", "vl"]);
  }

  // The right column: a reconstruction of one engine, or the Markdown view. Compare mode has no
  // Markdown option: two flowing texts would not line up box by box.
  function reconColumn(key, withMarkdown) {
    var col = el("div", "col");
    var head = el("div", "col-head");
    head.appendChild(el("span", "", "Rekonstruktion"));
    var choice = withMarkdown ? state[key] : engineChoice(key);
    var sel = el("select");
    (withMarkdown ? ["markdown"].concat(ENGINES) : ENGINES).forEach(function (e) {
      var label = e === "markdown" ? "Markdown" : e + (engineOk(e) ? "" : " (" + (data.engines[e].state === "missing" ? "nicht verarbeitet" : "Fehler") + ")");
      var o = el("option", "", label);
      o.value = e;
      if (e === choice) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener("change", function () { state[key] = sel.value; savePrefs(); render(); });
    head.appendChild(sel);
    col.appendChild(head);

    if (choice === "markdown") {
      col.appendChild(markdownBody());
      return col;
    }
    var engine = choice;
    if (!engineOk(engine)) {
      var n = el("div", "notice" + (data.engines[engine].state === "error" ? " err" : ""), engine + ": " + statusText(engine));
      col.appendChild(n);
      return col;
    }
    var v = makeView();
    v.page.classList.add("eng-" + engine);
    // Skip pymupdf `cell` blocks in the reconstruction: the `table` block already renders the whole
    // table (as HTML), so drawing each cell on top would double the table's text.
    blocksOf(engine).forEach(function (b) {
      if (b.type === "cell") return;
      v.page.appendChild(blockElement(b));
    });
    col.appendChild(v.wrap);
    return col;
  }

  // Markdown body below the column head: the flowing text (sanitized server-side, see
  // viewer/sanitize.py), with each section indexed in sectionEls, then the figure/table gallery.
  function markdownBody() {
    var wrap = el("div", "md");
    var body = el("div", "markdown-body");
    body.innerHTML = data.markdown_html;
    sectionEls = {};
    body.querySelectorAll("[data-section]").forEach(function (n) { sectionEls[n.getAttribute("data-section")] = n; });
    if (overlayOn()) {
      var colours = sectionColours();
      Object.keys(colours).forEach(function (i) {
        if (!sectionEls[i]) return;
        sectionEls[i].style.outline = "2px solid " + colours[i];
        sectionEls[i].style.outlineOffset = "2px";
      });
    }
    wrap.appendChild(body);

    var visuals = (data.visual_blocks || []).filter(function (vb) {
      return vb.status === "ok" && (vb.type === "figure" || vb.type === "chart" || vb.type === "table");
    });
    if (visuals.length) {
      var gallery = el("div", "vb-gallery");
      gallery.appendChild(el("h3", "", "Erkannte Abbildungen/Diagramme/Tabellen"));
      visuals.forEach(function (vb) { gallery.appendChild(visualBlockPreview(vb)); });
      wrap.appendChild(gallery);
    }
    return wrap;
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
    if (vb.description) meta.appendChild(el("p", "vb-desc", vb.description));

    // Tables: show the recognised HTML table below the crop (server-sanitized, so innerHTML is safe
    // here -- same rule as the Markdown body and the reconstruction's table cells).
    if (vb.html) {
      var tableWrap = el("div", "vb-table");
      tableWrap.appendChild(el("div", "vb-sublabel", "Erkannte Tabelle:"));
      var holder = el("div", "vb-table-html");
      holder.innerHTML = vb.html;
      tableWrap.appendChild(holder);
      meta.appendChild(tableWrap);
    }

    // Every component: the raw text fragments whose boxes fall inside it (pymupdf/OCR, geometry
    // only -- same list the digest writes under each figure/table). textContent only, no markup.
    if (vb.fragments && vb.fragments.length) {
      var frag = el("div", "vb-fragments");
      frag.appendChild(el("div", "vb-sublabel", "Gefundene Texte (pymupdf/OCR, unverifiziert):"));
      var ul = el("ul", "vb-frag-list");
      vb.fragments.forEach(function (t) { ul.appendChild(el("li", "", t)); });
      frag.appendChild(ul);
      meta.appendChild(frag);
    }

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
  // A selected layout element highlights its linked Markdown sections; the first one is brought into view.
  function select(id) {
    state.selected = id;
    applySelection();
    var linked = id && data.links[id] ? data.links[id] : [];
    if (linked.length && sectionEls[linked[0]]) sectionEls[linked[0]].scrollIntoView({ block: "center" });
  }

  function applySelection() {
    app.querySelectorAll("[data-selected]").forEach(function (n) { n.removeAttribute("data-selected"); });
    if (state.selected) {
      app.querySelectorAll('[data-id="' + state.selected + '"]').forEach(function (n) { n.setAttribute("data-selected", ""); });
    }
    Object.keys(sectionEls).forEach(function (i) { sectionEls[i].classList.remove("md-hl"); });
    var linked = state.selected && data.links[state.selected] ? data.links[state.selected] : [];
    linked.forEach(function (i) { if (sectionEls[i]) sectionEls[i].classList.add("md-hl"); });
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
