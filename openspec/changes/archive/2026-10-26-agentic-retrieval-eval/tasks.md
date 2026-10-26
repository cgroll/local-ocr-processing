# Tasks

## 1. Risiko-Check: Claude-Agent-SDK-Zugang im Container

- [x] 1.1 Minimales Docker-Image (nur Python + `pip install claude-agent-sdk`), `~/.claude/.credentials.json` read-only gemountet, kein sonstiger Host-Mount, kein `ANTHROPIC_API_KEY`. Einzeiler-Query ("antworte nur mit OK") darüber laufen lassen. Ergebnis: Antwort kommt zurück -- die OAuth-Session-Authentifizierung funktioniert nachweislich innerhalb eines Containers. Bei Fehlschlag: Rückmeldung an den Nutzer vor Weiterbau (größtes benanntes Risiko aus `design.md`).

## 2. Docker-Image für die Sandbox

- [x] 2.1 Dockerfile: `python:3.12-slim` + `sentence-transformers` (CPU-Torch) + `numpy` + `claude-agent-sdk`, Mount-Punkte für HF-Cache und Sandbox-Ordner vorgesehen. Ergebnis: Image baut; `python -c "from sentence_transformers import SentenceTransformer"` läuft im Container ohne Fehler.
- [x] 2.2 Minimales Such-Skript in der Sandbox (lädt EmbeddingGemma 2 mit `device="cpu"` aus dem gemounteten HF-Cache, Cosine-Similarity gegen eine mitgelieferte `embeddings.npy`, SQLite-FTS5-Abfrage gegen eine mitgelieferte Volltextindex-Datei). Ergebnis: Testaufruf mit einer bekannten Beispiel-Query (z. B. "PSRR") liefert dieselben/plausibel vergleichbare Treffer wie `docparse.search query "PSRR"` in der Produktion.

## 3. Sandbox-Builder

- [x] 3.1 Export-Funktion: lädt den bestehenden `EmbeddingIndex`, maskiert `items`/`vectors` nach `kind`, schreibt eine gefilterte Kopie. Ergebnis: Check, dass die "lokal"-Kopie kein `document_summary_cloud` enthält und die "cloud"-Kopie kein `document_summary`, alle übrigen Kinds (`page_text`, `page_image`, `visual_*`, `document_fulltext`) in beiden Kopien identisch (Zeilenzahl und Werte).
- [x] 3.2 Kopier-Skript für den Rest (`data/results/enrich/`, `data/results/digest/<doc>.md`, die jeweils passende Summary-Datei, `data/pages/`) in zwei Ordner `sandbox_local/` und `sandbox_cloud/`. Ergebnis: Diff der beiden Ordner zeigt nur die erwarteten Unterschiede (Summary-Datei + Embedding-Datei); eine Stichprobe (`find sandbox_* -iname "*question*" -o -iname "*judgment*"`) bestätigt, dass keine Ground-Truth-Datei in irgendeiner Sandbox landet.

## 4. Agent-Harness

- [x] 4.1 Task-Prompt-Vorlage: nur die Frage als Eingabe, keine Dokument-/Seiten-Hinweise, Pflicht-Vorgabe zur Bild-Verifikation vor der finalen Antwort (siehe `proposal.md` Punkt 6). Ergebnis: Prompt-Text dokumentiert, von Hand gegengelesen auf Neutralität (kein versehentlicher Hinweis auf das richtige Dokument).
- [x] 4.2 Runner-Funktion: startet `ClaudeSDKClient` mit `permission_mode="bypassPermissions"`, `cwd` auf den Sandbox-Mountpunkt im Container, sammelt den vollen Message-Stream (Tool-Aufrufe, finale Antwort, `ResultMessage`). Ergebnis: ein Testlauf gegen eine der beiden Sandboxes mit einer einzelnen bekannten Frage liefert eine finale Antwort plus vollständiges Rohtranskript.
- [x] 4.3 Effizienz-Extraktion aus dem Transkript: Tool-Aufrufe nach Art zählen (Suche/Datei lesen/Bild ansehen), besuchte Dokument-IDs aus Pfaden/Argumenten extrahieren, Tokens/Kosten/Dauer aus der `ResultMessage` (exakte Feldnamen hier verifizieren, siehe `design.md` Open Question). Ergebnis: eine kompakte JSON-Zusammenfassung je Lauf (Frage-ID, Variante, Tool-Aufrufe nach Art, Liste besuchter Dokumente, Tokens, Kosten, Dauer, ob eine Bild-Verifikation stattfand, finale Antwort).

## 5. Gemini-Judge

- [x] 5.1 Judge-Skript analog zum Vertex-AI-Client-Muster aus `src/docparse/digest/cloud_summary.py` (Retry, Timeout, Kosten aus `usage_metadata`), eigener Prompt (Frage + Ground Truth + Agenten-Antwort -> Verdikt `correct`/`partial`/`wrong` + kurze Begründung). Ergebnis: Testaufruf mit einer bekannten Frage/Antwort-Kombination aus dem bestehenden `experiments/vlm-qa-test/`-Datensatz liefert ein plausibles, von Hand gegengelesenes Verdikt.

## 6. Pilot

- [x] 6.1 Pilot über 3-5 der 20 Fragen x 2 Varianten (6-10 Läufe gesamt), end-to-end: Sandbox bauen, Agent laufen lassen, Judge bewerten, Effizienz-Metriken sammeln. Ergebnis: eine Zusammenfassungstabelle (Frage, Variante, Judge-Verdikt, Tool-Aufrufe, besuchte Dokumente, Kosten, Dauer, Bild-Verifikation ja/nein) über alle Piloten-Läufe.
- [x] 6.2 Stichprobenkontrolle von Hand: mindestens 3 der Judge-Verdikte gegen das tatsächliche Agenten-Transkript und die Ground Truth gegenlesen. Ergebnis: Notiz, ob der Judge plausibel bewertet oder systematisch daneben liegt (siehe `proposal.md` Nicht-Ziel "kein automatisiertes Scoring ohne jede menschliche Stichprobenkontrolle").
- [x] 6.3 Entscheidungspunkt mit dem Nutzer anhand der Pilot-Ergebnisse: funktioniert die Kette wie gedacht (Docker-Zugang, Sandbox-Trennung, Effizienz-Erfassung, Judge-Plausibilität)? Ergebnis: dokumentierte Entscheidung -- Vollauf wie geplant, Vollauf mit Anpassungen, oder Stopp nach dem Pilot. **Entscheidung:** Nutzer wählte "Vollauf wie geplant" (alle 20x2). Durchgeführt, siehe `full-run-results.md`: 19/20 korrekt in beiden Varianten (identischer einziger Fehlerfall), keine konsistente Effizienz-Differenz. Zwei Zwischenfälle behoben (SDK-`max_buffer_size`, Credential-Rotation), siehe dort "Stolpersteine".

## Workflow follow-up

- Vollauf über alle 20 x 2 Fragen nur nach positiver Entscheidung aus 6.3 -- kein eigener Tracked Task hier, da er von dieser Entscheidung abhängt, nicht vorab feststeht.
- README unter `experiments/agentic-retrieval-eval/` mit Befund, Methodik und bekannten Einschränkungen ergänzen, sobald Pilot (und ggf. Vollauf) abgeschlossen sind.
- Archivieren erst nach Abschluss von Pilot (und ggf. Vollauf); da `skip_specs: true` synct das Archivieren keine Specs, nur Ablage der Artefakte.
