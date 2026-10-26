# Proposal

## Why

Der Viewer zeigt bisher nur das Original (mit Engine-Overlays) und eine räumlich positionierte Rekonstruktion je Engine. Was fehlt, ist die Ansicht, die am Ende tatsächlich in die Suche und an nachgelagerte Agenten geht: der fließende Markdown-Text aus `document-digest`. Ohne ihn im Viewer muss man zur Prüfung zwischen Viewer und den rohen `.md`-Dateien hin- und herspringen; mit ihm lässt sich direkt neben Original und Rekonstruktion beurteilen, ob der Digest-Text für eine Seite plausibel ist.

## What Changes

- Dritte Darstellung je Seite im bestehenden Seiten-Inspektor: **Markdown**, als zusätzlicher Tab/Toggle neben Original und Rekonstruktion -- zeigt den fließenden Markdown-Text, den `document-digest` für diese Seite erzeugen würde (identisch zur Produktions-Textquellen-Wahl: `pymupdf` primär, `ocr`-Fallback bei Scans, `vl`-HTML für Tabellen, keine eigene Engine-Auswahl für diese Ansicht).
- Build-seitig ruft `docparse.viewer` pro Seite `digest/page.py:render_page()` direkt auf (nicht den Dokument-weiten `write_digest`/`render_document`-Pfad) und rendert das Ergebnis zu HTML, serverseitig vor dem Einbetten in die Seiten-JSON-Daten sanitisiert (Allow-List-Erweiterung von `sanitize.py`, nicht roh per `innerHTML`).
- Neue, pure Python-Abhängigkeit für Markdown→HTML-Konvertierung (siehe `design.md` für die Wahl).

## Nicht-Ziele

- Keine Änderung der bestehenden Original-/Rekonstruktions-Spalten oder des "Engines vergleichen"-Modus -- die Markdown-Ansicht ist rein additiv, ein dritter Tab, kein Ersatz.
- Keine neue, separate Pro-Seiten-Markdown-Datei unter `data/results/digest/` -- der Viewer ruft `render_page()` zur Build-Zeit direkt auf und schreibt nichts Neues weg; bleibt "kein Modell-Aufruf, rein mechanisch" wie der bestehende Digest.
- Keine Engine-Auswahl für die Markdown-Ansicht -- sie spiegelt immer dieselbe feste Quellenwahl (`choose_text_source`) wie die Produktions-Suche/-Digest, kein Dropdown wie bei der Rekonstruktions-Spalte.
- Keine allgemeine Markdown-Rendering-Bibliothek für das ganze Projekt -- die neue Abhängigkeit wird ausschließlich vom Viewer-Build-Schritt genutzt.
- Keine Änderung von `digest/markdown.py`/`digest/page.py` selbst -- der Viewer ruft die bestehenden, unveränderten Rendering-Funktionen auf.
- Keine Live-Konvertierung im Browser (kein JS-Markdown-Parser, kein CDN) -- passt zum bestehenden Prinzip "keine externen Abhängigkeiten, offline nutzbar" (`viewer-site`).

## Capabilities

### New Capabilities
(keine)

### Modified Capabilities
- `page-inspection`: neue Anforderung "Markdown-Repräsentation" -- dritte Darstellung je Seite neben Original und Rekonstruktion.
- `viewer-site`: Anforderung "Sichere Darstellung unvertrauenswürdiger Inhalte" erweitert -- die Allow-List-Sanitisierung gilt jetzt auch für das aus Markdown gerenderte HTML, nicht nur für Tabellen-HTML.

## Impact

- Neuer/geänderter Code in `src/docparse/viewer/` (`build.py` ruft pro Seite `digest/page.py:render_page()` auf, `data.py` bekommt ein neues Feld für das sanitisierte Markdown-HTML, `sanitize.py` um eine erweiterte Allow-List ergänzt, `static/page.js` um einen dritten Tab, `templates.py`/CSS bei Bedarf).
- Neue Abhängigkeit in `pyproject.toml` (reine Python-Bibliothek für Markdown→HTML, siehe `design.md`).
- Liest `data/results/enrich/<doc>/<page>.json` und die zugrunde liegenden Engine-Ergebnisse zusätzlich beim Viewer-Build (bereits vorhandene Daten, kein neuer Pipeline-Schritt) -- etwas höhere Build-Zeit pro Seite (I/O für Rohtext-Fragmente, wie bereits im bestehenden `document-digest`-Build).
- Betrifft nur den Viewer; `src/docparse/digest/` und `src/docparse/search/` bleiben unverändert.
