# Tasks

Teil A (Gruppen 1–3) braucht kein Modell und hängt von keiner offenen Frage ab. Teil B (Gruppen 4–6) setzt die Entscheidungen aus design.md „Open Questions“ voraus; Gruppe 4 klärt sie zuerst.

## 1. Merge

- [ ] 1.1 Paket `docparse.merge` anlegen, Eingaben aus `data/results/<engine>/<doc>/<page>.json` lesen und Ergebnis nach `data/results/merged/<doc>/<page>.json` schreiben; Ergebnis: leere Seite wird mit Status `ok` bzw. `error` laut Spec geschrieben (Unit-Test mit Fixture-Ergebnissen)
- [ ] 1.2 Zuordnung Text ↔ Layout-Block über Flächenüberdeckung und Herkunftsfelder je Block; Ergebnis: Test mit NE555-S.-3-ähnlicher Fixture (Layout-`title` + PyMuPDF-Text → Typ `title`, Text aus `pymupdf`, Herkunft beider vermerkt)
- [ ] 1.3 Regelkette für Textquelle (PyMuPDF bei Textlayer, sonst VL, sonst OCR); Ergebnis: Tests für nativ, gescannt mit VL, gescannt nur mit OCR
- [ ] 1.4 Tabellen- und Figurenregeln: VL-HTML vor PyMuPDF, Textblöcke in Tabellen-/Figurenboxen unterdrücken; Ergebnis: Tests „Tabelle mit VL und PyMuPDF“ und „Text in der Tabelle“
- [ ] 1.5 Lesereihenfolge aus Layout, sonst geometrisch; Ergebnis: Tests mit und ohne Layout
- [ ] 1.6 CLI `python -m docparse.merge run [--docs] [--limit] [--force]` und `validate` (nutzt Format-Validierung): überspringt unveränderte Seiten, mergt neu bei neueren Eingaben; Ergebnis: zweiter Lauf meldet alle Seiten als übersprungen, `validate` endet mit Exit-Code 0
- [ ] 1.7 Viewer: `merged` als zusätzliche Engine in der festen Engine-Liste (Ebene, Rekonstruktion, Herkunft im Blockinspektor); Ergebnis: Viewer-Build zeigt `merged` auf der NE555-Seite 3, Sichtprüfung gegen die Eingaben, Test der Viewer-Daten
- [ ] 1.8 README-Abschnitt „Merge“ mit Regelkette und Befehlen ergänzen; Ergebnis: die dokumentierten Befehle laufen wie beschrieben auf `ds-ne555`

## 2. Export

- [ ] 2.1 Paket `docparse.export`: Verzeichnisstruktur, `meta.json` aus Manifest, fehlende Seiten vermerken; Ergebnis: Test mit Manifest-Fixture, Seite ohne Ergebnis fehlt in `pages/`, Rest läuft durch
- [ ] 2.2 Markdown-Erzeugung (`pages/<page>.md`, `doc.md` mit Seitenankern, Überschriften, Lesereihenfolge); Ergebnis: Test, dass Seitenabschnitt in `doc.md` und Seitendatei identisch ist
- [ ] 2.3 Stabile IDs für Figuren und Tabellen in Lesereihenfolge; Ergebnis: Test, dass ein zweiter Export dieselben IDs erzeugt
- [ ] 2.4 Figuren-Ausschnitte (PNG aus dem Seitenbild, Mindestgröße), `figures/figures.json` mit Beschriftung und leerem Beschreibungsfeld; Ergebnis: Ausschnitt der Pin-Diagramme in `ds-ne555` S. 3 liegt vor, Beschriftung wird einer benachbarten `caption` zugeordnet
- [ ] 2.5 Tabellen: bereinigtes HTML, CSV bei rechteckiger Auflösung, Inline-Markdown für kleine und Stub für große Tabellen; Ergebnis: Tests für kleine, große und verbundene Zellen (ohne CSV, mit Vermerk)
- [ ] 2.6 `chunks.jsonl` mit Chunk-ID, Seite, Box, Art, Quelle, Artefakt-ID (vorläufige Chunk-Regel aus Design, Annahme 3); Ergebnis: Test, dass jeder Chunk Dokument, Seite und Box trägt und zum Seitenbild auflösbar ist
- [ ] 2.7 CLI `python -m docparse.export run [--docs] [--force]` (nur unter `data/artifacts/` schreibend); Ergebnis: Lauf über das gesamte Subset ohne Fehler, Zusammenfassung mit Zahl der Seiten, Figuren, Tabellen, Chunks
- [ ] 2.8 Sichtprüfung der Artefakte (je eine Seite pro Gruppe) und README-Abschnitt „Export“; Ergebnis: kurze Beobachtungstabelle im README, die dokumentierten Befehle laufen wie beschrieben

## 3. Ausschnitte lesen (ohne Modell)

- [ ] 3.1 `get_page`, `get_figure`, `get_table` und `render_page` als Kommandos mit JSON-Ausgabe, mit Fehlermeldung samt gültiger Spanne bei unbekannten Eingaben; Ergebnis: Tests gegen die Artefakte der Fixture
- [ ] 3.2 `render_page` mit Box (Ausschnitt mit Rand, Pfad unter `data/`); Ergebnis: Ausschnitt zu einer Chunk-Box zeigt dieselbe Stelle wie das Seitenbild (Sichtprüfung plus Maßtest)

## 4. Entscheidungen (vor Teil B)

- [ ] 4.1 Modell für Beschreibungen, Tags und Zusammenfassung wählen: je Kandidat zehn Pin-Diagramm- und Schaltplan-Figuren beschreiben lassen, Laufzeit und VRAM messen, Ergebnis in design.md festhalten (Entscheidung ersetzt Frage 1; bei neuem Modell Registry-Delta ergänzen)
- [ ] 4.2 Offene Fragen 2–6 und 8 in design.md entscheiden (Seitenzusammenfassungen, Chunk-Größen, Schwellen, Figuren-Vektoren, Frage-Set, Vektorlösung); Ergebnis: jede Frage in design.md als entschieden mit Begründung oder bewusst vertagt
- [ ] 4.3 Entscheidung zur Aufteilung (ein Change oder zwei) und zum Verhältnis zu `configurable-routing`/`embedding-search` treffen; Ergebnis: README-Roadmap und tasks.md entsprechend angepasst

## 5. Beschreibungen, Tags, Zusammenfassung

- [ ] 5.1 Stufe „describe“: gewähltes Modell über `ModelManager` laden, Figurenbeschreibungen erzeugen und mit Quelle in `figures.json` eintragen; Ergebnis: Lauf auf `ds-ne555` füllt Beschreibungen, nach dem Lauf ist das Modell freigegeben (VRAM-Test), Zeitlimit je Figur gesetzt
- [ ] 5.2 Tags und Zusammenfassung je Dokument in `meta.json`, getrennt von den Manifest-Tags; Ergebnis: Test, dass Manifest-Felder unverändert bleiben und das Feld fehlt, wenn die Stufe nicht lief
- [ ] 5.3 Wiederholbar und fortsetzbar (vorhandene Beschreibungen überspringen, `--force`); Ergebnis: zweiter Lauf meldet alles als übersprungen

## 6. Index und Suche

- [ ] 6.1 Paket `docparse.search`: Index-Schema (Chunks, FTS5, Vektoren, Modellvermerk) und inkrementeller Aufbau; Ergebnis: Tests für Neuaufbau, geändertes Dokument, gelöschtes Dokument
- [ ] 6.2 Embeddings über `ModelManager` (Text, Tabellen-Serialisierung, Figuren als Bild); Ergebnis: Test der Serialisierung, VRAM nach dem Lauf wieder frei, EmbeddingGemma ist das einzige geladene GPU-Modell
- [ ] 6.3 `search` im Modus `text`, `semantic`, `hybrid` (Rangfusion) mit Filtern und JSON-Ausgabe; Ergebnis: Tests „exakter Begriff `SE555` zuerst“, „Filter Art + Tag“, „keine Treffer = leere Liste, Exit-Code 0“
- [ ] 6.4 Modellvermerk im Index und Abbruch bei Widerspruch; Ergebnis: Test mit künstlich verändertem Modellnamen
- [ ] 6.5 Plausibilisierung mit einigen Fragen auf dem Subset (je Frage erwartete Seite, Hit@k nur als Zahl berichtet, falls Frage 6 so entschieden); Ergebnis: Tabelle im README mit Treffer und Beobachtungen
- [ ] 6.6 README-Abschnitt „Suche“ mit Befehlen und Agenten-Ablauf (search → get_page → render_page → VLM); Ergebnis: die dokumentierten Befehle laufen wie beschrieben

## 7. Abschluss

- [ ] 7.1 Gesamtlauf Merge → Export → (Beschreibung) → Index → Suche über das Subset; Ergebnis: ohne Fehler, `parse validate` und `merge validate` mit Exit-Code 0, `uv run pytest` grün
- [ ] 7.2 Roadmap in README (Status der Changes) aktualisieren; Ergebnis: Tabelle spiegelt die Entscheidung aus 4.3

## Workflow follow-up

- Nach Review den Change mit `/opsx:archive` archivieren und die Specs `page-merge`, `agent-export`, `agent-search` in `openspec/specs/` prüfen.
