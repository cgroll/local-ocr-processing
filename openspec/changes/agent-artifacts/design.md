# Design

## Context

Stand (siehe README): `pymupdf`, `layout` und `ocr` liegen für alle 405 Seiten vor, `vl` nur für 30. Das Zwischenformat (`page-format`) ist stabil, der Viewer liest die Engines aus einer festen Liste (`ENGINES` in `viewer/data.py`). EmbeddingGemma 2 steht in der Registry (~0,9 GB, ohne Audio-Encoder, Text und Bild im selben 768-dim Raum). Die Sichtprüfung zeigt, dass keine Engine allein reicht: PyMuPDF liefert exakten Text, aber zerrissene Tabellenköpfe und ohne Leerzeichen zusammengesetzte Zellen; VL liefert gute Tabellen, aber lückenhaft und langsam; Figuren (Pin-Diagramme) sind Vektorpfade plus Beschriftungen, die kein Engine semantisch zusammenfasst. Der Agent soll Fundstellen finden und am Ende per VLM die Seite ansehen (Motivation: siehe proposal.md).

## Goals / Non-Goals

**Goals:**
- Jede Fundstelle führt über (Dokument, Seite, Box) zum Seitenbild.
- Artefakte sind für Agenten mit Dateizugriff lesbar und per `grep` brauchbar, auch ohne Index.
- Alle Schritte sind wiederholbar, fortsetzbar und laufen mit einem Modell zur Zeit.

**Non-Goals:**
- Kein Optimieren der Merge-Regeln über Sichtprüfung hinaus; keine Metriken.
- Kein Server, keine MCP-Anbindung.
- Kein Umbau des Zwischenformats.

## Decisions

**1. Die Seite ist die Einheit.** Alle Artefakte tragen Dokument und Seite; die Box ist die feinere Auflösung. Begründung: Der Agent prüft am Ende die Seite per VLM, und Engines scheitern seitenweise. Alternative: Dokumentweise Chunks ohne Seitenbezug – verworfen, weil der Rückweg zum Bild fehlt.

**2. Merge als feste Regelkette, nicht als Konfiguration.** Reihenfolge: (a) Typ und Box aus Layout, sonst aus der Engine mit Inhalt; (b) Text aus PyMuPDF bei vorhandenem Textlayer, sonst VL, sonst OCR; (c) Tabellen-HTML aus VL vor PyMuPDF; (d) Textblöcke in Tabellen-/Figurenboxen unterdrücken; (e) Lesereihenfolge aus Layout, sonst geometrisch. Jeder Block vermerkt die Herkunft von Typ, Box und Inhalt. Das ist bewusst einfach; `configurable-routing` macht es später konfigurierbar. Alternative: Ensemble/Abstimmung zwischen Engines – verworfen, zu aufwendig für den ersten Schritt.

**3. Zuordnung Text ↔ Layout-Block über Überdeckung.** Ein PyMuPDF-/OCR-Block gehört zu dem Layout-Block, der ihn am stärksten überdeckt (Anteil der Fläche des Textblocks, Schwelle im Code, später prüfen). Text ohne Layout-Block bleibt ein eigener Block. Alternative: Text neu aus Wörtern in der Layout-Box zusammensetzen – verworfen für jetzt (genauer, aber der Adapter liefert Blöcke, keine Wörter).

**4. Markdown plus `chunks.jsonl` plus Dateien statt einer Datenbank als Wahrheit.** Der Agent kann Dateien lesen und `grep`en; der Index ist abgeleitet und kann neu gebaut werden. Alternative: nur Datenbank – verworfen, weil schwerer zu prüfen und zu diffen.

**5. Stabile IDs aus Dokument, Seite und Lesereihenfolge** (`<doc>-p<seite>-f<n>`, `-t<n>`). Sie ändern sich nur, wenn sich die Blockliste der Seite ändert. Alternative: Hash des Inhalts – verworfen, weil sie bei jeder Textkorrektur wechselt und für Menschen unlesbar ist.

**6. Tabellen: Daten als Datei, Text im Markdown nach Größe.** Kleine Tabellen inline, große nur als Stub mit Kopfzeile, sonst blähen sie Seiten-Markdown und Treffer auf. Für das Embedding wird eine Textserialisierung (Beschriftung, Kopfzeile, Zeile als „Spalte: Wert“) verwendet, nicht das HTML.

**7. Figuren: Ausschnitt als Datei, Embedding aus dem Bild, Beschreibung als zusätzlicher Text.** Der Figuren-Chunk trägt Beschriftung, Beschreibung (falls vorhanden) und Text innerhalb der Box. Ob zusätzlich zum Bild-Vektor auch ein Text-Vektor der Beschreibung gespeichert wird, ist offen (siehe unten).

**8. Index: SQLite mit FTS5 für Volltext, Vektoren daneben.** Eine Datei, lokal, keine Dienste. Die Vektorsuche läuft bei der erwarteten Größe (einige Tausend Chunks) auch als exakte Brute-Force-Suche mit NumPy; `sqlite-vec` ist eine Option, kein Muss. Hybride Suche per Rangfusion (Reciprocal Rank Fusion) statt Gewichtung, weil Scores von FTS5 und Kosinus nicht vergleichbar sind.

**9. Modelle nacheinander.** Ablauf je Stufe: Merge (CPU) → Beschreibungen (VLM, falls gewählt) → Embeddings (EmbeddingGemma) → Index (CPU). Jede Stufe lädt ihr Modell über den `ModelManager` und gibt es frei; keine zwei GPU-Modelle gleichzeitig.

**10. Schnittstelle als CLI mit JSON.** `docparse.search search|get-page|get-figure|get-table|render-page`. Ein Agent mit Shell-Zugriff braucht nichts weiter; ein MCP-Server kann diese Funktionen später dünn umhüllen.

## Risks / Trade-offs

- [Merge verschlechtert Seiten, die ein Engine allein besser hätte] → Herkunft je Block im Ergebnis, Merge als eigene Ebene im Viewer prüfbar; Nicht-Ziel ist ein Optimum.
- [VL liegt nur für 30 von 405 Seiten vor] → Der Merge muss mit fehlendem VL laufen und bei späterem VL neu zusammenführen (steht in der Spec); die Qualität der Tabellen ist bis dahin schwächer.
- [Schlechte PyMuPDF-Tabellen landen in Markdown und Suche] → Tabellen als Daten ablegen und mit VL-Ergebnis bevorzugen; schlechte Kopfzeilen mindern die Auffindbarkeit, bleiben aber über den Seitenblick prüfbar.
- [Beschreibungen halluzinieren] → Herkunft im Figurendatensatz festhalten, Beschreibung nie als Text des Dokuments ausgeben, Seitenblick bleibt der letzte Schritt.
- [Bild-Embeddings von Schaltplänen sind wenig aussagekräftig] → Figuren-Chunks tragen zusätzlich Beschriftung und Text in der Box; ob das reicht, zeigt ein kleines Frage-Set.
- [Rechte] → Artefakte enthalten Inhalte der Quelldokumente und bleiben unter `data/`, nicht im Git.

## Migration Plan

Rein additiv: neue Verzeichnisse `data/results/merged/`, `data/artifacts/`, `data/index/`; bestehende Ergebnisse, Format und Specs bleiben unverändert. Zurückrollen heißt, diese Verzeichnisse zu löschen. Der Viewer bekommt `merged` als zusätzliche Engine (Anpassung der festen Liste; siehe Tasks).

## Open Questions

Diese Fragen sind bewusst noch nicht entschieden; die Specs sind so formuliert, dass sie keine davon vorwegnehmen.

1. **Modell für Beschreibungen, Tags und Zusammenfassung.** Kandidaten: VL-1.6 (bereits vorhanden, ~5 GB, langsam), ein kleineres lokales VLM, oder ein Text-LLM auf Beschriftung und Text in der Figurenbox (Figuren) bzw. auf `doc.md` (Tags, Zusammenfassung). Zu klären: Qualität auf Schaltplänen, Laufzeit pro Figur, VRAM, ob ein neuer Registry-Eintrag nötig ist (dann Delta auf `model-registry`).
2. **Seitenzusammenfassungen** ja oder nein; Annahme bis dahin: nein, nur Dokument-Zusammenfassung.
3. **Chunk-Größen und -Grenzen** (Absatz, Abschnitt unter Überschrift, feste Länge mit Überlappung); Annahme: Abschnitt unter einer Überschrift, geteilt bei zu langer Länge, nie über Seitengrenzen.
4. **Mindestgröße für Figuren** und Schwellen für „große Tabelle“ im Markdown.
5. **Figuren: nur Bild-Vektor oder zusätzlich Text-Vektor der Beschreibung?** Ein Test an einigen Pin-Diagrammen sollte es zeigen.
6. **Kleines Frage-Set (Hit@k)** zur Plausibilisierung der Suche in diesem Change oder erst in `retrieval-eval`?
7. **Aufteilung:** Zwei Changes (`agent-artifacts`: Merge + Export; `agent-search`: Beschreibungen, Embeddings, Index, Schnittstelle) oder ein gemeinsamer? Der Zuschnitt überlappt mit den Roadmap-Einträgen `configurable-routing` und `embedding-search`. Die Tasks sind in zwei Abschnitte geteilt, sodass die Trennung später ohne Umbau möglich ist.
8. **Vektorlösung:** `sqlite-vec` oder NumPy-Brute-Force.
