# Design

## Context

- Viewer-Datenfluss ist komplett clientseitig: `build.py` ruft `data.py:page_data()` auf, das ein JSON-Objekt pro Seite zusammenstellt; `templates.py:page_html()` bettet es als `<script type="application/json" id="page-data">` ein. Die gesamte Darstellung (Overlays, Rekonstruktions-Spalten, Engines-Vergleichen, Block-Inspektor) wird von `static/page.js` aus diesem JSON gerendert. Kein serverseitiges HTML-Rendering von Blockinhalten heute, außer der Tabellen-Sanitisierung (`sanitize.py:sanitize_table`). CSP verbietet Inline-Skripte (`script-src 'self'`).
- `digest/page.py:render_page(enrichment, source, root) -> str` rendert bereits eine einzelne Seite zu Markdown, ohne Dokument-weite Schleife. Inputs: `PageEnrichment` (`enrich/format.py:read_enrichment`) und die gewählte Textquelle (`enrich/blocks.py:choose_text_source(doc_id, page, root)`).
- `choose_text_source` liefert immer genau eine Quelle (pymupdf primär, ocr-Fallback, vl für Tabellen) -- nicht nutzerwählbar, anders als die bestehende Rekonstruktions-Spalte.
- `digest/markdown.py:html_table_to_markdown` erzeugt echte Pipe-Table-Markdown-Syntax (`| a | b |`), kein HTML.
- Keine Markdown→HTML-Bibliothek (Python oder JS) ist aktuell im Projekt vorhanden (`pyproject.toml` leer in dieser Hinsicht, `static/` hat nur `index.js`/`page.js`/`style.css`).

## Goals / Non-Goals

**Goals:**
- Markdown-Ansicht fügt sich in den bestehenden JSON-Blob → `page.js`-rendert-Datenfluss ein, statt einen zweiten Rendering-Mechanismus einzuführen.
- Sicherheit bleibt auf dem Niveau der bestehenden Tabellen-Sanitisierung -- kein neuer Angriffsvektor durch VLM-generierten Text, der jetzt durch einen Markdown-Renderer läuft.
- Build bleibt offline/deterministisch: kein Netzwerk, keine Modell-Aufrufe.

**Non-Goals:**
- Keine Wiederverwendung der Rekonstruktions-Spalten-Infrastruktur (Engine-Dropdown, Box-Positionierung) -- die Markdown-Ansicht ist ein eigener, einfacherer Tab ohne Positionierung.
- Keine Streaming- oder inkrementelle Aktualisierung der Markdown-Ansicht -- einmal beim Build gerendert, wie alles andere im Viewer.

## Decisions

1. **Markdown→HTML serverseitig beim Build, nicht clientseitig.** Begründung: passt zum bestehenden Prinzip "keine externen Abhängigkeiten, CSP ohne Inline-Skripte" (`viewer-site`, Requirement "Keine externen Abhängigkeiten") -- ein JS-Markdown-Parser müsste vendort werden (neue Asset-Datei, neue Wartungslast), während eine reine Python-Bibliothek nur die Build-Zeit-Abhängigkeiten erweitert, nicht die ausgelieferte Seite. Alternative verworfen: eigener Mini-Markdown-Parser analog zu `sanitize.py`s HTML-Allow-List -- Markdown-Syntax (verschachtelte Listen, Tabellen, Emphasis) ist komplexer als die Tabellen-HTML-Teilmenge, die `sanitize.py` abdeckt; das Rad hier neu zu erfinden lohnt sich nicht, wenn das Ergebnis ohnehin sanitisiert wird.
2. **Python-Markdown (`markdown`-Paket) als neue Abhängigkeit**, mit der `tables`-Extension aktiviert (`markdown.markdown(text, extensions=["tables"])`), weil `html_table_to_markdown` Pipe-Table-Syntax erzeugt, die ohne diese Extension nicht als `<table>` gerendert würde. Reine Python-Bibliothek, keine C-Erweiterung, passt zum übrigen reinen-Python-Charakter von `src/docparse/viewer/`.
3. **Sanitisierung: bestehende Allow-List in `sanitize.py` erweitern, nicht durch eine Drittanbieter-HTML-Sanitizer-Bibliothek ersetzen.** Neue Funktion (z. B. `sanitize_markdown_html`) mit erweiterter `ALLOWED_TAGS`-Menge (zusätzlich zu den bestehenden Tabellen-Tags: `h1`-`h6`, `p`, `ul`, `ol`, `li`, `strong`, `em`, `code`, `pre`, `blockquote`), auf Basis desselben `HTMLParser`-Mechanismus. **`a`/`img`-Tags bleiben bewusst ausgeschlossen** (kein Use-Case für Links/Bilder in Markdown-Fließtext aus VLM-Beschreibungen, vermeidet `href`/`src`-Validierungsaufwand).
4. **Rendering-Ergebnis als neues JSON-Feld, nicht als separate statische HTML-Datei.** `data.py:page_data()` bekommt ein zusätzliches Feld (z. B. `markdown_html: str`, bereits sanitisiert) neben den bestehenden Engine-Blöcken. `page.js` fügt einen dritten Tab hinzu, der bei Auswahl `container.innerHTML = data.markdown_html` setzt (bereits serverseitig sanitisiert, damit konsistent mit dem bestehenden Umgang mit Tabellen-HTML in `page.js`).
5. **`render_page()` direkt pro Seite aufgerufen, nicht über `write_digest`/`render_document`.** Vermeidet unnötiges erneutes Rendern aller Seiten eines Dokuments beim Bauen einer einzelnen Seite; `render_page` ist bereits auf genau diesen Anwendungsfall zugeschnitten (siehe Kontext).
6. **Leere Textquelle -> erkennbarer Leer-Hinweis, kein Fehler.** Konsistent mit dem bestehenden Umgang mit fehlenden Engine-Ergebnissen im Viewer (`viewer-site`, Requirement "Fehlende und fehlerhafte Ergebnisse").

## Risks / Trade-offs

- **[Risiko] Zusätzliche Abhängigkeit (`markdown`-Paket) nur für den Viewer** -> Mitigation: reine Python-Bibliothek, kein zur Laufzeit ausgeliefertes JS, kein Netzwerkzugriff; Build-Zeit-Kosten, keine Auswirkung auf die ausgelieferte statische Seite.
- **[Risiko] Erweiterte Sanitisierungs-Allow-List könnte eine Lücke übersehen** (z. B. ein Markdown-Konstrukt, das zu einem nicht bedachten HTML-Tag führt) -> Mitigation: Allow-List-Prinzip (nur explizit erlaubte Tags durchlassen, alles andere verwerfen) ist strukturell sicher gegen unbekannte Tags, nicht nur gegen bekannte schädliche; dasselbe Muster wie die bereits produktiv genutzte Tabellen-Sanitisierung.
- **[Trade-off] Markdown-Ansicht dupliziert zur Build-Zeit Arbeit, die `document-digest` beim eigentlichen Digest-Lauf schon einmal gemacht hat** (kein gemeinsamer Cache) -> bewusst in Kauf genommen: `render_page` ist günstig (kein Modell-Aufruf, nur Textverarbeitung), und eine geteilte Zwischenablage wäre zusätzliche Komplexität für wenig Laufzeitgewinn bei der aktuellen Datensatzgröße (405 Seiten).
