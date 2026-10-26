# Tasks

## 1. Abhängigkeit und Cloud-Client

- [x] 1.1 `google-genai` als echte Projektabhängigkeit ergänzen (`uv add google-genai`), nicht als Ephemeral-`--with` wie im Spike, da dies Produktionscode wird. Ergebnis: `uv run python -c "import google.genai"` läuft ohne Fehler, `pyproject.toml`/`uv.lock` aktualisiert.
- [x] 1.2 Dünnen Client-Wrapper in neuem Modul `src/docparse/digest/cloud_summary.py` anlegen: Projekt/Location/Modell-ID/Preis-Konstanten (analog `experiments/vlm-qa-test/run_gemini_vl.py`, Modell `gemini-4-argon`), HTTP-Timeout 60s. Ergebnis: Test mit injiziertem Fake-Client prüft, dass `generate_content` mit den erwarteten Parametern (Modell-ID, Timeout-Option) aufgerufen wird, ohne echten Netzwerkzugriff.

## 2. Cloud-Summary-Erzeugung und Parsing

- [x] 2.1 Eigene `CloudDocumentSummary`-Dataclass (`doc_id`, `title`, `summary`, `status`, `model`, `input_tokens`, `output_tokens`, `cost_usd`) plus einfacher, toleranter Titel/Summary-Parser (eigenständig von `summary.py`s Parser, siehe Design-Entscheidung 2). Ergebnis: Tests mit Fake-API-Antworten (vollständiges Format, fehlende Titelzeile, leere Antwort) prüfen korrektes Parsen bzw. `status="error"` bei leerer Antwort.
- [x] 2.2 Retry-Logik: bis zu 3 Versuche bei Netzwerk-/Timeout-Fehlern, danach `status="error"` mit Fehlermeldung statt Abbruch. Ergebnis: Test mit Fake-Client, der zweimal fehlschlägt und beim dritten Versuch erfolgreich ist (Ergebnis `ok`), und Test mit einem Fake-Client, der immer fehlschlägt (Ergebnis `error` nach genau 3 Versuchen).
- [x] 2.3 Kostenberechnung aus `usage_metadata` (prompt/candidates/thoughts Tokens) x Preis-Konstanten. Ergebnis: Test mit bekannten Token-Zahlen prüft exakten berechneten Kostenbetrag.

## 3. Ablageformat

- [x] 3.1 Schreib-/Lesefunktionen für `data/results/digest/<doc>.cloud_summary.json` (Pfad getrennt von `summary.py:summary_path`). Ergebnis: Rundreise-Test Schreiben/Lesen mit allen Feldern aus 2.1.

## 4. Batch-Runner

- [x] 4.1 Runner über die Dokumentliste aus dem Manifest: vorhandene `ok`-Ergebnisse überspringen, `--force` erzwingt Neuberechnung, Fehler bei einem Dokument stoppt den Lauf nicht. Ergebnis: Test mit Fake-Client für (a) einen zweiten Lauf ohne Änderungen (kein neuer Aufruf), (b) `--force` auf einem bereits vorhandenen `ok`-Ergebnis, (c) ein fehlschlagendes Dokument mitten im Lauf, danach laufen die übrigen Dokumente weiter.
- [x] 4.2 Kosten-/Token-Aggregation über alle in einem Lauf tatsächlich ausgeführten Cloud-Aufrufe, am Ende als Zusammenfassung ausgegeben. Ergebnis: Test prüft, dass die aggregierte Summe der Summe der Einzel-Dokument-Kosten/Tokens entspricht, und dass übersprungene (bereits `ok`) Dokumente nicht mitgezählt werden.
- [x] 4.3 CLI-Kommando analog zu `docparse.digest`/`docparse.search` (z. B. `docparse.digest cloud-summary run [--force]`). Ergebnis: Kommando dokumentiert, Beispielaufruf im README (siehe 6.5).

## 5. Dokument-Level Cloud-Embedding

- [x] 5.1 Neue Funktion in `src/docparse/search/document_embed.py` (z. B. `embed_document_cloud_summary`), die aus Titel+Cloud-Summary über den bestehenden `embedding`-Baustein ein Embedding der Art `document_summary_cloud` berechnet; liefert kein Embedding, wenn keine `ok`-Cloud-Summary vorliegt. Ergebnis: Test mit den zwei bereits in `summary.py`-Tests verwendeten Spike-Dokumenten (`ds-lm317`, `ds-tps62130`) prüft Dimension/L2-Normalisierung wie bei `document_summary`, Unterscheidbarkeit der `kind` und leeres Ergebnis bei fehlender/`error`-Cloud-Summary.
- [x] 5.2 Integration in den Such-Runner (z. B. `run_documents_cloud` in `src/docparse/search/runner.py`, analog zu `run_documents`): liest vorhandene `<doc>.cloud_summary.json`, fügt `document_summary_cloud`-Vektoren zum bestehenden Index hinzu, lässt `document_summary`/`document_fulltext`-Einträge unverändert. Ergebnis: Test prüft, dass nach dem Lauf beide Embedding-Arten (`document_summary` und `document_summary_cloud`) für ein Dokument im Index koexistieren, und dass ein erneuter Lauf ohne neue Cloud-Summaries nichts verändert.

## 6. Vollauf, Kostenkontrolle und Stichprobe

- [x] 6.1 Smoke-Lauf über 2-3 Dokumente (`ds-lm317`, `ds-tps62130`, `ntrs-19760010918` -- dieselben wie im ursprünglichen lokalen Summary-Vorabtest) gegen die echte Vertex-AI-API. Ergebnis: tatsächliche Kosten/Tokens liegen in der Größenordnung der Proposal-Schätzung (niedrige einstellige Cent-Beträge je Dokument), Titel/Summary inhaltlich plausibel von Hand geprüft.
- [x] 6.2 Vollauf über alle 73 Dokumente (Cloud-Summary-Generierung + `document_summary_cloud`-Embeddings). Ergebnis: Zusammenfassung mit Anzahl `ok`/`error`, Gesamtkosten und Gesamt-Tokens; Lauf bricht bei Einzelfehlern nicht ab.
- [x] 6.3 Stichprobe von 5 Dokumenten (mindestens die drei Datenblätter aus der vorherigen Qualitätsbewertung, `ds-lm317`, `ds-tps5430`, `ds-tlv9062`, plus zwei weitere) von Hand: Cloud-Summary gegen lokale Summary desselben Dokuments vergleichen, insbesondere ob die Cloud-Variante konkrete Werte/Zahlen nennt, wo die lokale vage blieb. Ergebnis: kurze Notiz je Dokument (im README oder in einem Review-Abschnitt dieses Changes), ehrlich dokumentiert, auch wenn kein Unterschied erkennbar ist.
- [x] 6.4 README um einen Abschnitt zu den neuen Cloud-Artefakten ergänzen: Ablagepfade, CLI-Befehle, tatsächliche Gesamtkosten des Vollaufs, ausdrücklicher Hinweis, dass dies parallele Vergleichsdaten für `retrieval-eval` sind und die Standard-Suche weiterhin die lokalen Embeddings nutzt (keine Verhaltensänderung der bestehenden Suche).

## Workflow follow-up

- Archivieren erst nach `retrieval-eval` (Roadmap #7) in Betracht ziehen, da dieser Change bewusst nur die Datenbasis liefert; bis dahin kann er offen bleiben oder regulär archiviert werden, ohne dass das den späteren Vergleich blockiert.
