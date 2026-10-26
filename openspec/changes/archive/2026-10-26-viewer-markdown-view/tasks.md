# Tasks

## 1. Abhängigkeit

- [x] 1.1 `markdown`-Paket als Projektabhängigkeit ergänzen (`uv add markdown`). Ergebnis: `uv run python -c "import markdown; print(markdown.markdown('**x**', extensions=['tables']))"` läuft ohne Fehler, `pyproject.toml`/`uv.lock` aktualisiert.

## 2. Sanitisierung erweitern

- [x] 2.1 `sanitize.py`: neue Funktion (z. B. `sanitize_markdown_html`) mit erweiterter Allow-List (`h1`-`h6`, `p`, `ul`, `ol`, `li`, `strong`, `em`, `code`, `pre`, `blockquote`, zusätzlich zu den bestehenden Tabellen-Tags), auf Basis desselben `HTMLParser`-Mechanismus wie `sanitize_table`; `a`/`img` bleiben ausgeschlossen. Ergebnis: Tests analog zu `tests/test_viewer_sanitize.py` -- erlaubte Tags bleiben erhalten, `<script>`/`<img>`/`<a href="javascript:...">` werden entfernt bzw. deren Inhalt escaped, verschachtelte Listen/Tabellen funktionieren.

## 3. Seiten-Rendering im Build

- [x] 3.1 `build.py`/`data.py`: pro Seite `digest/page.py:render_page(enrichment, source, root)` aufrufen (Textquelle über `enrich/blocks.py:choose_text_source`), Ergebnis über `markdown.markdown(text, extensions=["tables"])` zu HTML wandeln, mit `sanitize_markdown_html` sanitisieren, als neues Feld (z. B. `markdown_html`) in die Seiten-JSON-Daten aufnehmen. Ergebnis: Test analog zu `tests/test_viewer_data.py`, der für eine bekannte Seite (`ds-lm317` p4) prüft, dass `markdown_html` nicht leer ist und eine `<table>` enthält (Device-Comparison-Tabelle).
- [x] 3.2 Seite ohne ermittelbare Textquelle: `markdown_html` enthält einen erkennbaren Leer-Hinweis statt leerem String oder Fehler. Ergebnis: Test mit einer Fixture-Seite ohne Textquelle.

## 4. Frontend: dritter Tab

- [x] 4.1 `static/page.js`: dritten Tab/Toggle "Markdown" neben Original/Rekonstruktion ergänzen; bei Auswahl wird `markdown_html` aus den Seiten-Daten gerendert (bereits sanitisiert serverseitig). Ergebnis: Test analog zu `tests/test_viewer_templates.py`, der prüft, dass die Seite weiterhin offline/skriptfrei bleibt (keine neue Inline-Script-Verletzung) und dass `markdown_html` im eingebetteten JSON vorkommt.
- [x] 4.2 Minimale CSS-Anpassung für die neue Darstellung (Fließtext statt absoluter Positionierung), konsistent mit bestehendem `style.css`. Ergebnis: visuell von Hand gegen eine Beispielseite geprüft (siehe 5.2).

## 5. Vollauf und Dokumentation

- [x] 5.1 Viewer-Vollauf (`python -m docparse.viewer build`) über den gesamten Datensatz, kein Fehler. Ergebnis: Build-Zusammenfassung ohne neue Fehler ggü. dem Stand vor diesem Change.
- [x] 5.2 Stichprobe von 3 Seiten von Hand geprüft (u. a. `ds-lm317` p4 mit Tabelle, eine Scan-Seite mit OCR-Fallback, eine Seite ohne Textquelle): Markdown-Tab zeigt plausiblen, dem jeweiligen `.md`-Digest-Abschnitt entsprechenden Inhalt. Ergebnis: Notiz im README (Abschnitt "Viewer"), welche Seiten geprüft wurden und ob der Inhalt plausibel war.
- [x] 5.3 README-Abschnitt "Viewer" um die dritte Darstellung ergänzen (was sie zeigt, dass sie dieselbe feste Textquellen-Wahl wie die Suche nutzt, keine Engine-Auswahl). Ergebnis: Abschnitt vorhanden.

## Workflow follow-up

- Archivieren und Specs synchronisieren (`page-inspection`, `viewer-site`), sobald alle Tasks abgeschlossen sind.
