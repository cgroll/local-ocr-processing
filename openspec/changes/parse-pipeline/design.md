# Design

## Context

Vorhanden sind das Manifest (`docparse.dataset.manifest`, 73 Dokumente, `page_range` je Dokument) und die Modelle (`docparse.models`: Registry, `ModelManager`, Smoke-Test). Bei der Vorab-Untersuchung der Rohausgaben (Mini-Probe auf einer Seite, 150 DPI, 1275×1650 px) zeigte sich:

- **OCR** (`PaddleOCR.predict`): `rec_texts`, `rec_scores`, `rec_polys` (4 Punkte), `rec_boxes` (`[x0,y0,x1,y1]`). Mit aktivierter Dokument-Orientierung läuft intern ein Vorverarbeitungsschritt, der das Bild drehen kann; dann stimmen Koordinaten nicht mehr mit dem Seitenbild überein.
- **Layout** (`LayoutDetection.predict`): `boxes` mit `label`, `score`, `coordinate`, `polygon_points`, `order` (hier `None`).
- **VL** (`PaddleOCRVL.predict`): `parsing_res_list` mit Label, `bbox` und Inhalt je Block, zusätzlich `layout_det_res` mit denselben Boxen und `width`/`height` des Eingabebilds. Die Koordinaten liegen im Eingabebild.
- Alle drei akzeptieren ein BGR-Array, wie es `docparse.models.smoke.make_sample` erzeugt.

## Goals / Non-Goals

**Goals:**
- Ein Format, das für jede Engine denselben Koordinatenraum und dieselben Felder nutzt.
- Ein Lauf, der Stunden dauern darf, aber nie halb verloren geht.

**Non-Goals:**
- Kein Viewer, kein Merge der Engines, keine Zeilen-zu-Block-Zuordnung, keine Metriken (siehe Proposal).

## Decisions

**Format als JSON-Datei pro Engine und Seite.** `data/results/<engine>/<doc>/<page>.json` mit vierstelliger Seitennummer (`0001.json`). Felder: `version`, `doc_id`, `page`, `dpi`, `width`, `height`, `engine`, `engine_version`, `status`, `error`, `seconds`, `blocks`. Block: `type`, `label`, `bbox`, `polygon` (optional), `text`, `markdown`, `html`, `engine`, `confidence`, `order`. Alternativen: JSONL pro Dokument (schlechter für Wiederaufnahme pro Seite) oder Parquet (nicht von Hand lesbar). Implementierung als `dataclasses` mit `to_dict`/`from_dict`, kein Pydantic.

**Ein Seitenbild für alle.** `render.py` rendert mit PyMuPDF `get_pixmap(matrix=Matrix(dpi/72, dpi/72))` auf Basis der angezeigten Seite (berücksichtigt Drehung und CropBox) nach `data/pages/<doc>/<page>.png`. Dieses PNG wird von allen Engines gelesen (als Array) und später vom Viewer angezeigt. PyMuPDF-Koordinaten (Punkte, unrotierter Raum) gehen durch `page.transformation_matrix * Matrix(dpi/72)`, damit rotierte Seiten stimmen.

**Orientierungskorrektur und Entzerrung aus.** Für OCR und VL `use_doc_orientation_classify=False` und `use_doc_unwarping=False`, damit das Eingabebild nicht verändert wird und Boxen zum Seitenbild passen. Das Referenzprojekt nutzte die Orientierung bei Fotos; für PDF-Renderings ist sie unnötig. Gedrehte Scans bleiben gedreht und werden als Befund sichtbar.

**Typ-Zuordnung über Tabelle.** Eine Tabelle ordnet die Labels von PP-DocLayoutV3 den festen Blocktypen zu (z. B. `doc_title`/`paragraph_title` → `title`, `table` → `table`, `image` → `figure`, `formula` → `formula`, `header`/`footer` → gleichnamig). Unbekannte Labels werden `other`, das Original bleibt in `label`. Die genaue Labelmenge wird im ersten Umsetzungsschritt aus dem Modell gelesen.

**Adapter als reine Funktionen.** Jeder Adapter hat die Form `to_blocks(raw, page_ctx) -> list[Block]` und kennt kein Dateisystem; `page_ctx` trägt DPI und Bildmaße. Dadurch sind Adapter mit gespeicherten Rohausgaben ohne GPU testbar (kleine Fixtures aus der Probe). Die Engine-Aufrufe liegen getrennt in `engines.py` (Aufruf und Rückgabe der Rohdaten).

**PyMuPDF-Blöcke.** `get_text("dict")` für Textblöcke (Zeilen zusammengefügt), `get_image_info()` für Bilder, `get_drawings()` zu Blöcken gruppiert (Rechtecke mit Abstand unter einem Schwellwert zusammengefasst, mit Mindestgröße, damit Linien und Rahmen nicht tausende Blöcke ergeben), `find_tables()` für einfache Tabellen mit HTML. Kein Konfidenzwert.

**Runner: Engine außen, Seite innen.** `for engine in engines: with manager.use(engine): for page in pages`. So wird jedes Modell einmal geladen. Fortsetzen über die Existenz einer `ok`-Datei; geschrieben wird atomar (`.tmp` und Umbenennen). Pro Seite werden Ausnahmen gefangen und als `error`-Ergebnis gespeichert.

**VL im Worker-Prozess mit Seiten-Timeout.** Das native Paddle-Generieren lässt sich in-process nicht unterbrechen. Für `vl` startet der Runner einen Kindprozess (`spawn`), der das Modell lädt und Seiten aus einer Queue verarbeitet; der Elternprozess wartet pro Seite höchstens `timeout_s` (aus der Registry), beendet den Worker bei Überschreitung hart (VRAM wird mit Prozessende frei), schreibt ein `error`-Ergebnis und startet für die restlichen Seiten einen neuen Worker. Der Mechanismus aus `docparse.models.smoke` (Pipe, Kill) dient als Vorbild; die gemeinsame Hilfsfunktion wird bei Bedarf in `docparse.models` gehoben, statt Code zu duplizieren.

**CLI.** `uv run python -m docparse.parse {run,validate,summary}`. `run --engines pymupdf,layout,ocr,vl --docs ID... --limit N --force`. `summary` liest nur vorhandene Ergebnisse (ohne GPU). Standard-Engines: alle vier.

**Codeort.** `src/docparse/parse/` mit `format.py`, `render.py`, `adapters/{pymupdf,layout,ocr,vl}.py`, `engines.py`, `runner.py`, `summary.py`, `__main__.py`.

## Risks / Trade-offs

- [VL ist langsam, ca. 400 Seiten bei Median 30 s und gelegentlich Timeouts] → Fortsetzbarkeit, Seiten-Timeout, Teil-Läufe über `--docs`/`--limit`; ein Vollauf kann über Nacht laufen.
- [VL lässt Inhalte weg] → wird nicht korrigiert; das Format hält nur fest, was geliefert wurde. Der Viewer soll es sichtbar machen.
- [Gruppierung der Vektorgrafiken liefert zu viele oder zu wenige Blöcke] → Schwellwerte als Parameter, Sicht in der Zusammenfassung (Blockanzahl nach Typ); Feinabstimmung gehört zur visuellen Prüfung.
- [Labelmenge von PP-DocLayoutV3 unvollständig abgebildet] → Rückfall `other` mit Originallabel; die Tabelle wird im ersten Task aus dem Modell erzeugt.
- [Gedrehte Scans liefern schlechte OCR, da keine Orientierungskorrektur] → bewusst; als Beobachtung dokumentieren statt Koordinaten zu verfälschen.
- [Rohausgaben der Pipelines ändern sich mit Paddle-Updates] → Adapter-Tests mit gespeicherten Rohdaten; `uv.lock` pinnt Versionen.

## Open Questions

- Geklärt (Umsetzung 2.6): VL liefert Tabellen als HTML (`<table>…`); der Adapter legt sie in `html`, alles andere in `markdown` und `text`.
- Beobachtung (Umsetzung 2.1): Auf dichten Tabellenseiten (z. B. `ds-lm317` Seite 4 und 6) erzeugt VL-1.6 sehr langsam Token für Token (CPU-gebunden, GPU-Auslastung nahe 0 %) und läuft bei 2048 neuen Token in einen GPU-Speicherfehler. Das ist die in der Registry vorgesehene Situation; Seiten-Timeout und Worker-Neustart (Task 3.4) fangen sie ab, solche Seiten werden `error`-Ergebnisse.
