# Proposal

## Why

Die Pipeline liefert pro Seite die Ergebnisse von vier Engines, die sich ergänzen und widersprechen (PyMuPDF: exakter Text, aber zerrissene Tabellen und keine Figuren-Semantik; VL: gute Tabellen, aber langsam und lückenhaft). Ein Agent, der Fragen an die Dokumentensammlung beantworten soll, kann damit nichts anfangen: Er braucht pro Dokument eine **eindeutige, lesbare und durchsuchbare Darstellung**, in der jede Fundstelle auf (Dokument, Seite, Box) zurückführt. Der letzte Schritt des Agenten ist immer der Blick eines VLM auf die gerenderte Seite; die Artefakte müssen ihn dorthin führen, nicht die Antwort ersetzen.

## What Changes

- **Merge pro Seite:** Aus den vorhandenen Engine-Ergebnissen entsteht je Seite eine zusammengeführte Blockliste im bestehenden Zwischenformat (feste Regelkette, siehe design.md): Text aus PyMuPDF bei vorhandener Textebene, sonst OCR bzw. VL; Typen und Regionen aus dem Layout; Tabellen und Figuren mit VL-Nachbearbeitung, soweit vorhanden.
- **Export pro Dokument** unter `data/artifacts/<doc>/`: `doc.md` (mit Seitenankern), `pages/NNNN.md`, Figuren-Ausschnitte mit stabilen IDs und Beschreibung, Tabellen als HTML/CSV mit stabilen IDs, `chunks.jsonl` (eine durchsuchbare Einheit je Zeile, mit Dokument, Seite, Box, Art) und `meta.json` (Titel, Typ-Tag, Tags, Zusammenfassung, Quelle, Lizenz).
- **Index und Suche:** Embeddings mit EmbeddingGemma 2 (Text, Tabellen als Textserialisierung, Figuren als Bild) und ein lokaler SQLite-Index mit Volltext (FTS5) und Vektoren; hybride Suche.
- **Agenten-Schnittstelle:** dünne Funktionen `search`, `get_page`, `get_figure`/`get_table`, `render_page`, jeweils als CLI-Kommando (MCP-Anbindung ist nachgelagert).
- **Beschreibungen, Tags, Zusammenfassung** werden von einem VLM bzw. LLM erzeugt. Welches Modell, ist **offen** und wird in diesem Change nur als Austauschpunkt vorbereitet (siehe design.md).

## Capabilities

### New Capabilities
- `page-merge`: Zusammenführen der Engine-Ergebnisse einer Seite zu einer Blockliste mit Herkunft je Block.
- `agent-export`: Artefakte je Dokument (Markdown, Figuren, Tabellen, Chunks, Metadaten) mit stabilen IDs und Rückverweis auf Seite und Box.
- `agent-search`: Embeddings, Index, hybride Suche und die Agenten-Schnittstelle bis zur gerenderten Seite.

### Modified Capabilities
<!-- keine: das Zwischenformat (page-format) bleibt unverändert; die Registry-Erweiterung um ein Beschreibungsmodell hängt an einer offenen Entscheidung und kommt erst mit ihr -->

## Nicht-Ziele

- Keine konfigurierbaren Routing-Regeln (Roadmap `configurable-routing`); der Merge ist eine fest verdrahtete, dokumentierte Regelkette.
- Keine Qualitätsmetriken oder Frage-Antwort-Evaluierung (Roadmap `retrieval-eval`); höchstens ein kleines Frage-Set zur Plausibilisierung, falls entschieden.
- Kein RAG, kein Agent, keine MCP-Server-Implementierung: nur die Artefakte und die Funktionen, die ein Agent aufrufen kann.
- Keine Verbesserung der Engine-Adapter (etwa der PyMuPDF-Tabellenerkennung); Schwächen werden im Merge umgangen oder dokumentiert.
- Keine Cloud-Dienste; alle Modelle laufen lokal und nacheinander.
- Keine seitenweisen Zusammenfassungen und keine Bild-Embeddings anderer Modelle (offene Frage bzw. später).

## Impact

- **Code:** neue Pakete `docparse.merge`, `docparse.export`, `docparse.search` unter `src/docparse/`; Aufruf über `uv run python -m docparse.<paket> ...`.
- **Daten:** neues Verzeichnis `data/artifacts/<doc>/` und ein Index unter `data/index/` (beide nicht im Git); Eingaben unverändert aus `data/results/` und `data/pages/`.
- **Abhängigkeiten:** SQLite (FTS5 in der Standardbibliothek), eine Vektorlösung (offen: `sqlite-vec` oder NumPy-Brute-Force bei kleinem Korpus); EmbeddingGemma 2 ist in der Registry bereits vorhanden.
- **Roadmap:** überlappt mit `configurable-routing` (Merge) und `embedding-search` (Index); der Zuschnitt, ob dieser Change geteilt oder jene ersetzt werden, ist in design.md als offene Frage geführt.
- **Daten- und Rechtehinweis:** Artefakte enthalten Inhalte der Quelldokumente (auch `vendor-copyright`/`unknown`) und bleiben lokal, nicht im Git.
