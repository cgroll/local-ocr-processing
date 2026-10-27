# Proposal

## Why

Die Markdown-Repräsentation (`viewer-markdown-view`, archiviert) zeigt Tabellen bereits mit ihrem vollen extrahierten Inhalt, aber Figure-/Chart-Blöcke nur als kurze VLM-Beschreibung ohne jedes Bild. Dadurch lässt sich beim Lesen der Markdown-Spalte nicht beurteilen, ob eine Abbildung überhaupt korrekt erkannt wurde (Crop trifft die richtige Stelle, Beschreibung passt zum tatsächlichen Inhalt) -- genau die Art Prüfung, die der Seiten-Inspektor für alle anderen Blockarten schon ermöglicht.

## What Changes

- Die Markdown-Spalte bekommt einen zusätzlichen Galerie-Abschnitt: für jeden Figure-/Chart-Block der Seite (in `position`-Reihenfolge) eine Bildvorschau neben Typ, Label und Beschreibung -- Vorschau als CSS-Ausschnitt des bereits verlinkten vollen Seitenbilds (dieselbe Technik, die die Rekonstruktions-Spalte für Figure-Blöcke schon nutzt), keine neuen Bild-Dateien.
- `page_data()` liefert zusätzlich `enrichment.visual_blocks` (Typ, Label, Bbox, Beschreibung, Status) an den Client.
- Keine Bildvorschau für Tabellen -- die zeigen ihren Inhalt bereits vollständig als Markdown-Tabelle.

## Nicht-Ziele

- Keine pixelgenaue Platzierung der Vorschau an der exakten Stelle im Fließtext -- separater Galerie-Abschnitt, zugeordnet über dieselbe Beschriftung, die im Fließtext bereits als Überschrift erscheint.
- Kein Verlinken oder Kopieren der separat abgelegten Crop-PNG-Dateien unter `data/results/enrich/` -- die Vorschau nutzt denselben CSS-Crop-Trick wie die bestehende Rekonstruktions-Spalte gegen das ohnehin schon verlinkte volle Seitenbild.
- Keine Änderung von `digest/page.py:render_page` oder der Produktions-Digest-Ausgabe -- nur der Viewer bekommt zusätzliche Daten und Darstellung.
- Keine Bildvorschau für Tabellen (siehe oben).
- Keine Änderung an Original-, Rekonstruktions- oder Engine-Vergleichs-Spalte.

## Capabilities

### New Capabilities
(keine)

### Modified Capabilities
- `page-inspection`: Anforderung "Markdown-Repräsentation" erweitert um eine Bildvorschau-Galerie für Figure-/Chart-Blöcke.

## Impact

- `src/docparse/viewer/data.py`: `page_data()` liefert zusätzlich die Visual-Block-Liste aus der Anreicherung.
- `src/docparse/viewer/static/page.js`: `markdownColumn()` rendert zusätzlich eine Galerie aus sicheren DOM-Elementen (kein `innerHTML`), analog zur bestehenden `.fig`-CSS-Crop-Technik aus `blockElement()`.
- `src/docparse/viewer/static/style.css`: Styling für die neue Galerie.
- Keine neuen Abhängigkeiten, keine neuen Dateien unter `data/viewer/`.
