# Tasks

## 1. Abschnitte mit Herkunft im Digest

- [x] 1.1 `render_page_sections` in `digest/page.py` einführen, das Liste aus (Markdown-Text, Quell-Boxen) liefert; verify: `uv run pytest tests/test_digest.py` grün, neuer Test vergleicht `render_page` mit der Verkettung der Abschnitte für eine Beispielseite
- [x] 1.2 `assign_fragments` in `digest/markdown.py` zusätzlich die Boxen der Fragmente liefern lassen, Text unverändert; verify: bestehende Tests für `assign_fragments` grün, neuer Test prüft die Box je Fragment
- [x] 1.3 Caption-Box und Fragment-Boxen in die Quell-Boxen des visuellen Abschnitts aufnehmen; verify: Test mit Figure, Caption und Fragment liefert eine Abschnitts-Box, die alle drei umfasst

## 2. Verknüpfung und Seitendaten

- [x] 2.1 Überlappungsregel (≥ 0,5 eigener Fläche) und Verknüpfungsliste `layout:<i>` → Abschnitts-IDs in einer reinen Funktion in `viewer/data.py` umsetzen; verify: Unit-Test mit synthetischen Boxen (voll innen, teilweise, außen, Nachbarbox)
- [x] 2.2 Seitendaten um `markdown_sections` (ID, HTML, Boxen) und `links` erweitern; `markdown_html` durch Abschnitts-Rendering mit `<div data-section>` ersetzen; verify: `uv run python -m docparse.viewer build --docs gd1-001675` erzeugt die Seite ohne Fehler, und `data-section`-Anzahl entspricht der Abschnittszahl (Test)
- [x] 2.3 Sanitizer-Erlaubnisliste um `div` und `data-section` (nur nicht-negative Ganzzahl) erweitern; verify: Tests für fremde Attribute, `<script>` in Abschnitt und `data-section="x"` werden entfernt bzw. abgelehnt

## 3. Viewer-Oberfläche

- [x] 3.1 „Markdown" als erste Option im `<select>` der Rekonstruktion ergänzen, Standard für die rechte Spalte setzen, Schaltfläche „Markdown anzeigen" entfernen; verify: im Browser auf `http://127.0.0.1:8777/viewer/index.html` öffnet eine Seite mit Markdown rechts, und die Auswahl bleibt nach Neuladen erhalten
- [x] 3.2 Klick auf Layout-Box hebt verknüpfte Abschnitte rechts hervor und scrollt sie in Sicht; Escape und Klick ins Leere heben auf; verify: Sichtprüfung auf `gd1-001675` S. 2 (Abbildung „Methodology" mit Fragmenten)
- [x] 3.3 Overlay-Schalter: verknüpfte Layout-Boxen und Abschnitte in gleicher Farbe umranden; verify: Sichtprüfung, dass jede Farbe links und rechts dieselbe Zuordnung zeigt
- [x] 3.4 Schwelle 0,5 an drei Seiten prüfen (`ds-lm317` S. 4, `gd1-001675` S. 2, `bs-pdp-8-memory-schematics-jun70` S. 1) und ggf. anpassen; verify: Ergebnis mit Befund je Seite in der Abschluss-Notiz des Changes

## 4. Integration

- [x] 4.1 Gesamte Testsuite laufen lassen; verify: `uv run pytest` grün
- [x] 4.2 Viewer für alle Dokumente neu erzeugen und Server-Start prüfen; verify: `uv run python -m docparse.viewer build` nennt die Indexseite, Port 8777 liefert HTTP 200

## Workflow follow-up

- Nach Abschluss: `/opsx:archive` ausführen, damit die Änderung in `openspec/specs/page-inspection/spec.md` übernommen wird.
