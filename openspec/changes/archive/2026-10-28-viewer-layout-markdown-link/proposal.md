# Proposal

## Why

Die Markdown-Darstellung ist heute ein eigener Modus per Schaltfläche und nicht mit dem Original verbunden. Beim Prüfen einer Seite lässt sich nicht sehen, welcher Abschnitt im Markdown zu welchem Layout-Element links gehört, etwa ob eine Abbildung samt Unterschrift und erkannten Textfragmenten richtig zugeordnet ist. Die Markdown-Ansicht soll deshalb als gleichwertige Option neben den Engines im Auswahlmenü der Rekonstruktion erscheinen, Standard sein, und Klicks zwischen Layout und Markdown verknüpfen.

## What Changes

- Die rechte Spalte bietet „Markdown" als Option im bestehenden Auswahlmenü „Rekonstruktion" an (neben `pymupdf`, `layout`, `ocr`, `vl`). Die bisherige Schaltfläche „Markdown anzeigen/ausblenden" entfällt.
- „Markdown" ist die Standardauswahl der rechten Spalte. Die Wahl bleibt wie bisher im Browser erhalten.
- Ein Klick auf ein Layout-Element (Box links) hebt den zugehörigen Abschnitt im Markdown rechts hervor und scrollt ihn in Sicht.
- Optional umschaltbares Overlay: alle verknüpften Layout-Elemente links erhalten je eine eigene Farbe, die zugehörigen Markdown-Abschnitte rechts tragen dieselbe Farbe als Umrandung.
- Zuordnung ist geometrisch (Box-Überlappung), nicht semantisch. Abschnitte ohne Zuordnung bleiben unmarkiert.
- Die Digest-Datei (`document-digest`, Produktions-Output) und die Textquellen-Wahl ändern sich nicht. Die Markdown-Darstellung im Viewer erhält lediglich zusätzliche Anker-Attribute je Abschnitt.

**Nicht-Ziele:**
- Keine Änderung an der Textquellen-Wahl, am Digest oder an der Suche.
- Keine Zuordnung von Text-Layout-Boxen zu einzelnen Absätzen über den Textinhalt hinaus; Textboxen werden nur über Geometrie zugeordnet.
- Keine Bearbeitung der Markdown-Inhalte im Viewer.
- Keine neuen Abhängigkeiten, keine externen Ressourcen (Viewer bleibt offline und ohne Server-Logik).

## Capabilities

### New Capabilities

Keine.

### Modified Capabilities

- `page-inspection`: Die Markdown-Repräsentation wird Option der Rekonstruktions-Auswahl und Standard; neues Requirement für die Verknüpfung zwischen Layout-Elementen und Markdown-Abschnitten.

## Impact

- `src/docparse/digest/page.py`, `src/docparse/digest/markdown.py`: Die Abschnitts-Herkunft (Bounding-Boxen je Abschnitt) wird als Zusatzinformation aus `render_page` bzw. einem Helfer geliefert, ohne den Markdown-Text zu verändern.
- `src/docparse/viewer/data.py`, `src/docparse/viewer/sanitize.py`: Anker-Attribute für Abschnitte durch die Erlaubnisliste lassen; Abschnittsliste mit Boxen in die Seitendaten aufnehmen.
- `src/docparse/viewer/static/page.js`, `style.css`: Auswahlmenü, Standardwert, Overlay und Hervorhebung.
- Tests: `tests/test_viewer_data.py`, `tests/test_digest.py`, ggf. neue Viewer-Tests für die Sanitizer-Erlaubnisliste.
- Keine Änderung an Datenformaten unter `data/results/`.
