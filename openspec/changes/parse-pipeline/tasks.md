# Tasks

## 1. Format und Rendering

- [x] 1.1 `src/docparse/parse/format.py`: `Block`, `PageResult` (Dataclasses), Typmenge, `to_dict`/`from_dict`, Lesen und atomares Schreiben nach `data/results/<engine>/<doc>/<page>.json`. Ergebnis: Rundreise-Test für ein Beispielergebnis.
- [x] 1.2 Validierung (`validate_result`): Pflichtfelder, Typ, Box wohlgeformt und im Bild. Ergebnis: Tests für gültig, Box außerhalb, unbekannter Typ.
- [x] 1.3 `render.py`: Seite mit fester DPI nach `data/pages/<doc>/<page>.png` rendern, Rückgabe als BGR-Array und Metadaten; Drehung und CropBox berücksichtigen. Ergebnis: Test prüft Pixelmaße = Punkte × DPI / 72 und eine gedrehte Test-PDF.

## 2. Adapter

- [x] 2.1 Rohausgaben von OCR, Layout und VL für eine Seite als kleine JSON-Fixtures unter `tests/fixtures/` speichern; Labelmenge von PP-DocLayoutV3 aus dem Modell lesen. Ergebnis: Fixtures vorhanden, Label-Tabelle im Code.
- [x] 2.2 Typ-Zuordnung (`labels.py`) mit `other`-Rückfall. Ergebnis: Test für bekannte und unbekannte Labels.
- [x] 2.3 PyMuPDF-Adapter: Text, Bilder, gruppierte Vektorgrafiken, einfache Tabellen mit Umrechnung Punkte → Pixel. Ergebnis: Tests an einer nativen und einer gescannten Test-PDF.
- [x] 2.4 Layout-Adapter aus Fixture. Ergebnis: Test prüft Typ, Box, Reihenfolge, Konfidenz.
- [x] 2.5 OCR-Adapter aus Fixture (Zeilen mit Polygon und Konfidenz, leere Seite). Ergebnis: Tests.
- [x] 2.6 VL-Adapter aus Fixture (Typen, Markdown, Tabellen-HTML, Kopfzeile bleibt). Ergebnis: Tests; Entscheidung html vs. markdown für Tabellen im Design vermerkt.

## 3. Engines und Runner

- [x] 3.1 `engines.py`: Aufrufe für `pymupdf`, `layout`, `ocr` (ohne Orientierungskorrektur) und `vl` (Token-Limit, `markdown_ignore_labels=[]`), Rückgabe der Rohdaten. Ergebnis: je Engine eine echte Seite verarbeitet, Box-Koordinaten stimmen mit dem Seitenbild überein (Stichprobe per Overlay-PNG im Scratchpad).
- [x] 3.2 Seitenauswahl aus dem Manifest (`page_range`, `--docs`, `--limit`, fehlende Dateien überspringen). Ergebnis: Tests mit Mini-Manifest.
- [x] 3.3 Runner: Engine außen, Seite innen, Modell über `ModelManager`, Fehler pro Seite als `error`-Ergebnis, Überspringen vorhandener `ok`-Ergebnisse, `--force`. Ergebnis: Tests mit Fake-Engine für Fortsetzen, Fehler und Wiederholung.
- [x] 3.4 VL-Worker-Prozess mit Seiten-Timeout, hartem Beenden und Neustart für die restlichen Seiten. Ergebnis: Test mit künstlich kurzem Timeout (Fake-Worker) und manueller Lauf mit echtem VL auf 2 Seiten.
- [x] 3.5 CLI `python -m docparse.parse {run,validate,summary}` mit Exit-Codes. Ergebnis: `validate` und `summary` laufen ohne GPU.

## 4. Subset-Lauf und Doku

- [ ] 4.1 Lauf aller Engines außer VL über den gesamten Datensatz. Ergebnis: Zusammenfassung zeigt 405 Seiten je Engine, Fehler sind begründet; `validate` meldet 0 Fehler.
- [ ] 4.2 VL-Lauf über einen Teil des Datensatzes (mindestens ein Dokument je Gruppe, ca. 20 Seiten). Ergebnis: Zusammenfassung mit Laufzeiten und Timeouts; Beobachtungen zu weggelassenen Inhalten notiert.
- [ ] 4.3 Gesamtlauf von VL über den Rest, falls Zeit erlaubt, sonst fortsetzbar dokumentieren. Ergebnis: Stand der Abdeckung im README.
- [ ] 4.4 README um Abschnitt „Parsing" ergänzen (Format, Befehle, Laufzeiten) und Roadmap-Zeile 3 abhaken. Ergebnis: Abschnitt vorhanden.
