# Proposal

## Why

Die Parse-Ergebnisse (405 Seiten × 3 Engines, VL für einen Teil) liegen als JSON vor, aber ob sie stimmen, lässt sich nur am Bild beurteilen. AGENTS.md gibt der visuellen Prüfung Vorrang vor Metriken. Ohne Viewer bleibt unklar, welche Engine bei welchem Seitentyp gut ist (Tabellen, Schaltpläne, Scans), und damit auch, wie das Routing später aussehen soll.

## What Changes

- Statischer HTML-Viewer, erzeugt aus den Ergebnissen: eine Indexseite über alle Dokumente und eine Seite je Dokumentseite.
- Linke Seitenhälfte: das Original mit ein- und ausblendbaren Ebenen je Engine (Layout-Boxen, OCR-Zeilen, PyMuPDF-Blöcke, VL-Blöcke), farbig nach Engine, mit Typ und Konfidenz.
- Rechte Seitenhälfte: Rekonstruktion der Seite aus den Ergebnissen einer wählbaren Engine (Text und Tabellen an der erkannten Position, Bilder und Grafiken als Ausschnitte des Seitenbilds).
- Engine-Vergleich: zwei Rekonstruktionen nebeneinander und ein Blockinspektor mit allen Feldern des gewählten Blocks.
- Fehlende oder fehlgeschlagene Ergebnisse (etwa VL für noch nicht verarbeitete Seiten) werden als solche angezeigt.
- Kommando `uv run python -m docparse.viewer build`; Ausgabe unter `data/viewer/`.

## Nicht-Ziele

- Kein Server, keine Bearbeitung der Ergebnisse, kein Korrigieren oder Annotieren von Blöcken.
- Keine Metriken, keine Ground-Truth-Vergleiche und keine automatische Bewertung der Engines.
- Keine Zusammenführung der Engines zu einer Seite und keine Routing-Regeln (Change `configurable-routing`).
- Kein Rendern von Formeln (LaTeX bleibt als Quelltext sichtbar) und kein vollständiges Markdown-Rendering.
- Keine Parsing-Läufe aus dem Viewer heraus; er liest nur vorhandene Ergebnisse.
- Keine externen Skripte, Schriften oder Bibliotheken: alles läuft offline aus lokalen Dateien.

## Capabilities

### New Capabilities
- `viewer-site`: Erzeugung der statischen Seite aus Manifest und Ergebnissen: Index, Seitendateien, Navigation, Umgang mit fehlenden Daten, sichere Ausgabe.
- `page-inspection`: Darstellung einer Seite: Original mit Ebenen, Rekonstruktion, Engine-Vergleich und Blockinspektor.

### Modified Capabilities

## Impact

- Neuer Code unter `src/docparse/viewer/` (Generator, Sanitizer, Vorlagen, CLI) und Tests unter `tests/`.
- Liest `datasets/manifest.csv`, `data/pages/` und `data/results/`; ändert sie nicht.
- Neues Verzeichnis `data/viewer/` (nicht im Git).
- Keine neuen Abhängigkeiten.
