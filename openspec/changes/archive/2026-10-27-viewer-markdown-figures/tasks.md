# Tasks

## 1. Daten

- [x] 1.1 `data.py`: `_visual_blocks_payload(doc_id, page, root)` liest die Anreicherungsdatei (leere Liste, wenn sie fehlt) und gibt `type`/`label`/`bbox`/`description`/`status` je `VisualBlock` zurück; `page_data()` nimmt das Ergebnis als neues Feld `visual_blocks` auf. Ergebnis: Test analog zu `tests/test_viewer_data.py` -- für eine Fixture-Seite mit einem Table- und einem Figure-Block liefert `visual_blocks` beide Einträge mit den erwarteten Feldern; für eine Seite ohne Anreicherung liefert es eine leere Liste.

## 2. Frontend

- [x] 2.1 `static/page.js`: `visualBlockPreview(vb)` baut ein freistehendes Thumbnail (CSS-Crop des Seitenbilds, fester Breiten-Skalierungsfaktor, siehe design.md Decision 1) plus Typ/Label/Beschreibung, über sichere DOM-APIs (kein `innerHTML`). Ergebnis: von Hand gegen eine Beispielseite mit Figure-Block geprüft, Vorschau zeigt den erwarteten Bildausschnitt.
- [x] 2.2 `markdownColumn()`: hängt nach dem Markdown-Text eine Galerie aus allen `visual_blocks`-Einträgen mit `status == "ok"` und `type` in `figure`/`chart` an (Tabellen ausgefiltert), in der gelieferten Reihenfolge. Ergebnis: Test analog zu `tests/test_viewer_templates.py`, der prüft, dass `visual_blocks` im eingebetteten JSON vorkommt und die Seite weiterhin offline/skriptfrei bleibt.
- [x] 2.3 CSS für die Galerie (`style.css`): Thumbnail-Größe, Abstand, Beschriftung -- konsistent mit bestehendem `markdown-body`-Stil.

## 3. Vollauf und Dokumentation

- [x] 3.1 Viewer-Vollauf (`python -m docparse.viewer build`), kein Fehler ggü. dem Stand vor diesem Change.
- [x] 3.2 Stichprobe von 2 Seiten mit Figure/Chart-Blöcken von Hand geprüft (z. B. `ds-tps62130` S. 1 mit Tabelle+Diagramm+Abbildung, eine gescannte Seite mit Figure-Block): Vorschaubilder zeigen den richtigen Seitenausschnitt, Tabellen erscheinen weiterhin ohne zusätzliche Vorschau. Ergebnis: kurze Notiz im README (Abschnitt "Viewer").
- [x] 3.3 README-Abschnitt "Viewer" um die Galerie ergänzen.

## Workflow follow-up

- Archivieren und `page-inspection`-Spec synchronisieren, sobald alle Tasks abgeschlossen sind.
