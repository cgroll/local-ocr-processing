# Design

## Context

- `blockElement()` (`static/page.js`) rendert Figure-Blöcke der Rekonstruktions-Spalte bereits als CSS-Crop des vollen Seitenbilds: `backgroundImage` = volles Seitenbild, `backgroundSize` = volle Seitenpixelmaße, `backgroundPosition` = `-x,-y` der Box -- funktioniert, weil das umgebende `.page`-Element in echten Seitenpixelmaßen aufgebaut und erst per CSS `transform: scale(var(--scale))` auf Bildschirmgröße gebracht wird.
- Für die neue Galerie brauche ich dieselbe Grundtechnik, aber **ohne** die `.page`/`--scale`-Maschinerie -- die Galerie-Einträge sind freistehende, fest kleine Vorschaubilder, kein Teil der maßstabsgleichen Original/Rekonstruktions-Ansicht.
- `markdown_html` wird weiterhin unverändert über `innerHTML` gesetzt (bereits sanitisiert); die neue Galerie kommt als separates, über sichere DOM-APIs gebautes Element danach -- kein Vermischen der beiden Rendering-Pfade.
- `page_data()` liest für `markdown_html` bereits einmal die Anreicherungsdatei (`_page_markdown`). Für die Galerie wird sie ein zweites Mal gelesen (eigene kleine Funktion) statt die bestehende, bereits getestete `markdown_html`-Funktion umzubauen -- siehe Decision 3.

## Goals / Non-Goals

**Goals:**
- Jede Figure/Chart-Vorschau beweist für sich, dass Crop-Koordinaten und Beschreibung zur richtigen Seitenstelle gehören, ohne dass das volle Seitenbild separat geöffnet werden muss.
- Keine neuen Dateien, kein neuer Build-Schritt, der Bilder kopiert.

**Non-Goals:**
- Keine eigene Zoom-/Scroll-Synchronisation der Galerie mit Original/Rekonstruktion.
- Keine Wiederverwendung der `.page`/`--scale`-Infrastruktur für die Galerie-Thumbnails.

## Decisions

1. **Freistehende Thumbnails mit eigenem Skalierungsfaktor**, nicht Wiederverwendung von `blockElement()`s `.fig`-Pfad direkt. Eigene kleine Funktion (z. B. `visualBlockPreview(vb)`): feste Thumbnail-Breite (z. B. 260px), Skalierungsfaktor `k = THUMB_W / bboxWidth`, `backgroundPosition`/`backgroundSize` damit berechnet -- unabhängig vom aktuellen Zoom der Original-Spalte. Begründung: `blockElement()` ist an die absolute Positionierung innerhalb eines maßstabsgleichen `.page`-Containers gekoppelt; die Galerie braucht das nicht und eine Kopplung würde unnötige Abhängigkeiten zwischen unabhängigen Darstellungen schaffen.
2. **Nur `figure`/`chart`, Status `ok`**, gefiltert aus `data.visual_blocks` -- `table`-Einträge werden ignoriert (ihr Inhalt steht schon als Markdown-Tabelle da), `status != "ok"` ebenso (konsistent mit `render_page`, das fehlgeschlagene visuelle Blöcke auch überspringt).
3. **Eigene, kleine `_visual_blocks_payload()`-Funktion in `data.py`**, die die Anreicherungsdatei separat liest, statt `_page_markdown`/`markdown_html` umzubauen, um die Rohdaten mit herauszureichen. Kostet einen zweiten Datei-Read pro Seite beim Build (vernachlässigbar bei 405 Seiten, siehe bereits akzeptierte Build-Zeit-Kosten in `viewer-markdown-view`), hält dafür die bereits getestete `markdown_html`-Funktion unangetastet und ihre Signatur/ihr Rückgabewert unverändert.
4. **Übertragene Felder minimal:** `type`, `label`, `bbox`, `description`, `status` -- nicht `crop_path` (Datei wird nicht referenziert, siehe Nicht-Ziele), nicht `content_text`/`content_source` (nur für Tabellen relevant, hier ausgefiltert).

## Risks / Trade-offs

- **[Trade-off] Galerie steht nicht an der exakten Stelle im Fließtext**, sondern gesammelt danach -- akzeptiert (siehe proposal.md, Nicht-Ziele); Zuordnung über identische Typ/Label-Beschriftung wie im Fließtext.
- **[Risiko] Sehr breite oder sehr schmale Bounding-Boxen** (z. B. eine fast seitenbreite, aber niedrige Grafik) ergeben bei fester Thumbnail-Breite ein sehr flaches oder sehr hohes Vorschaubild -> Mitigation: Höhe ergibt sich proportional aus der Box, kein Zuschneiden/Verzerren; im schlimmsten Fall ein unbequem langes Thumbnail, kein falscher Bildausschnitt.
