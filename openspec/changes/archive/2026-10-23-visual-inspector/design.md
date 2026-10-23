# Design

## Context

Vorhanden: `data/results/<engine>/<doc>/<page>.json` für `pymupdf`, `layout`, `ocr` (alle 405 Seiten) und `vl` (bisher 30 Seiten), das Seitenbild `data/pages/<doc>/<page>.png` (150 DPI) und `datasets/manifest.csv`. Alle Boxen sind Pixel im Seitenbild; die Ergebnisse tragen Typ, Originalbezeichnung, Box, Polygon, Text/Markdown/HTML, Konfidenz und Reihenfolge (`docparse.parse.format`). VL-Tabellen sind HTML, VL-Text ist Markdown mit LaTeX-Formeln. Die Texte stammen aus unvertrauenswürdigen Dokumenten (AGENTS.md).

## Goals / Non-Goals

**Goals:**
- Pro Seite schnell erkennen, was welche Engine wo erkannt hat und wo sie sich unterscheiden.
- Funktioniert offline aus dem Dateisystem, ohne Server.

**Non-Goals:**
- Kein Bearbeiten, keine Metriken, kein Zusammenführen der Engines, kein Formel-Rendering, keine externen Bibliotheken (siehe Proposal).

## Decisions

**Statische Seiten, vom Generator erzeugt.** `uv run python -m docparse.viewer build` schreibt `data/viewer/index.html` und `data/viewer/<doc>/<page>.html`. Alternativen: ein lokaler Server mit JSON-API (mehr Teile, nichts gewonnen, weil nur gelesen wird) oder ein einziges Single-Page-App-Bündel (alle Daten in einer Datei, zu groß: 405 Seiten × 4 Engines). Eine Datei pro Seite bleibt klein und hält Ladezeiten kurz.

**Daten eingebettet statt per `fetch`.** Jede Seitendatei trägt ihre Ergebnisse als `<script type="application/json">`-Block (Engine → Ergebnis oder Fehlermarkierung). `fetch` auf `file://` blockieren Browser. Beim Einbetten wird `</` als `<\/` maskiert, damit Dokumenttext den Block nicht beenden kann.

**Bilder per relativem Verweis auf `data/pages/`.** Keine Kopien (132 MB). Der Verweis geht relativ (`../../pages/<doc>/<page>.png`), solange `data/viewer/` neben `data/pages/` liegt; der Ausgabeordner ist deshalb fest unter `data/`. Ausschnitte für Bildblöcke entstehen per CSS (`background-image`, `background-position`) aus demselben PNG, ohne zusätzliche Dateien.

**Vorlage und Skript als feste Dateien.** `src/docparse/viewer/static/{page.js,style.css}` werden einmal nach `data/viewer/assets/` kopiert; die Seiten verweisen darauf. Das JS ist ohne Bibliothek geschrieben (Vanilla). Python erzeugt nur die schmale HTML-Hülle und die JSON-Daten.

**Rekonstruktion im Browser aus dem JSON.** Zeichnen im JS, damit Wechsel der Engine, Ebenen und Vergleich ohne neue Seitenladung gehen. Blockdarstellung nach Typ: Textartige Typen (`text`, `title`, `header`, `footer`, `caption`, `list`, `line`) als absolut positionierter Container mit `white-space: pre-wrap` und einer Schriftgröße aus der Boxhöhe geteilt durch die Zeilenzahl (nach oben und unten begrenzt); `table` aus bereinigtem HTML; `figure`, `image`, `drawing`, `chart` als Ausschnitt des Seitenbilds; `formula` als Quelltext in Festbreitenschrift; Blöcke ohne Inhalt als beschriftete Box. Es wird bewusst nichts „schöner" gemacht, als die Engine geliefert hat.

**Sicherheit: Maskieren im Browser, Tabellen im Generator bereinigen.** Text wird nur über `textContent` gesetzt. Tabellen-HTML läuft im Generator durch einen Sanitizer auf Basis von `html.parser` mit Erlaubnisliste (`table`, `thead`, `tbody`, `tr`, `td`, `th`, `br`; Attribute nur `rowspan` und `colspan` mit Zahlenwerten), alles andere wird verworfen und der Zelltext bleibt. Zusätzlich setzt jede Seite eine Content-Security-Policy per `<meta>` (`default-src 'none'; img-src 'self' data:; style-src 'self'; script-src 'self'`), sodass selbst ein Fehler im Sanitizer keine fremden Ressourcen laden oder Inline-Skripte ausführen könnte. Die eingebetteten JSON-Blöcke sind per `type="application/json"` nicht ausführbar. Der Sanitizer wird bewusst im Generator getestet und nicht dem JS überlassen.

**Gemeinsamer Maßstab, ein Scroll-Container.** Beide Seitenhälften (oder beide Rekonstruktionen im Vergleich) liegen in einem gemeinsamen Container mit zwei Spalten, der vertikal scrollt; die Spalten sind auf Seitenbreite skaliert (CSS-Variable aus Fensterbreite durch Seitenbreite in Pixeln). Dadurch sind Maßstab und Scrollposition automatisch gleich, ohne Synchronisierungs-Code.

**Ebenen und Farben.** Feste Farbe je Engine (`pymupdf` grün, `layout` blau, `ocr` rot, `vl` violett), gleiche Farben auf Indexseite und Legende. Typfilter je Ebene über Checkboxen der in dieser Ebene vorkommenden Typen. Der Zustand (aktive Ebenen, gewählte Engines) wird in `localStorage` gehalten, mit Rückfall ohne Speicher, damit er beim Blättern erhalten bleibt.

**Blockinspektor.** Jeder Block bekommt eine ID `<engine>:<index>`; Klick setzt die Auswahl, markiert `data-selected` in beiden Ansichten und füllt die Seitenleiste mit allen Feldern. Escape oder Klick ins Leere hebt sie auf.

**Index aus Manifest plus Ergebnisbaum.** Der Generator liest das Manifest und zählt je Dokument und Engine die vorhandenen `ok`-, `error`- und fehlenden Ergebnisse gegen die Seiten im `page_range`. Nur Dokumente mit mindestens einem Ergebnis erscheinen. Filter (Gruppe, Tag, Freitext) im JS über `data-`-Attribute der Zeilen.

**Codeort.** `src/docparse/viewer/` mit `build.py` (Orchestrierung), `sanitize.py`, `templates.py` (HTML-Hüllen), `static/`, `__main__.py`. Liest Ergebnisse über `docparse.parse.format`, Manifest über `docparse.dataset.manifest`.

## Risks / Trade-offs

- [Viele kleine Dateien (ca. 405 + Index)] → akzeptabel; Erzeugung in Sekunden, nur lesend.
- [Erzeugte Seiten brauchen `data/pages/` an der erwarteten Stelle] → Ausgabeordner ist fest; Build prüft die Bilder und meldet fehlende.
- [Schriftgröße aus Boxhöhe passt nicht immer (mehrspaltiger Text, Tabellen)] → nur Annäherung, Original bleibt links zum Vergleich; Rekonstruktion ist kein Ersatz für das Bild.
- [VL-Markdown mit HTML-Resten oder LaTeX] → alles als Text; keine Interpretation, damit nichts verfälscht oder ausgeführt wird.
- [Sanitizer-Lücke] → zweite Schicht durch CSP; Tests mit Beispielen aus echten VL-Tabellen und Angriffsmustern.
- [Browser-Verhalten (Layout, Scroll) ist schwer automatisch zu testen] → Generator und Sanitizer per pytest, Darstellung per Sichtprüfung im Browser (Screenshots) in den Tasks.

## Open Questions

- Ob ein kleiner Server (`serve`) später gebraucht wird, etwa für Suche im Folgechange; hier nicht nötig.
