# Proposal

## Why

Die 73 bestehenden Dokument-Summaries (`document-digest`, erzeugt vom lokalen `describe`-Modell) sind zu 15/73 (≈20%) komplett degenerate (leer/Wiederholungsschleife/Prompt-Echo), und die übrigen 58 bleiben bei präzisen Fakten aus dichten technischen Inhalten (Datenblätter, Schaltpläne) durchgehend vage statt konkrete Werte zu nennen. Das deckt sich mit dem informellen VQA-Befund aus `experiments/vlm-qa-test/`: Gemini 4 Argon (Cloud-Flaggschiff über Vertex AI) hat dort 20/20 Fragen korrekt beantwortet, genau auf den dichte-Tabellen-/Schaltplan-Fragen, an denen die lokalen Modelle scheiterten. Bevor `retrieval-eval` (Roadmap #7) misst, ob schlechtere Summaries tatsächlich zu schlechterer Suche führen, braucht es dafür eine zweite, mit einem starken Modell erzeugte Datenbasis (Summaries + deren Embeddings) neben der bestehenden lokalen.

## What Changes

- Neuer Baustein, der aus demselben Markdown-Digest (`document-digest`) wie die lokale Summary eine zweite, vom Cloud-Flaggschiffmodell **Gemini 4 Argon** (über Vertex AI, wie bereits in `experiments/vlm-qa-test/run_gemini_vl.py` genutzt) erzeugte Titel+Summary berechnet -- gleicher Input, damit beide Varianten vergleichbar sind.
- Separate Ablage getrennt von der lokalen Summary-Datei (z. B. `data/results/digest/<doc>.cloud_summary.json`), inkl. Status (`ok`/Fehler), verwendetem Modell und Token-/Kosten-Angabe je Dokument.
- Batch-Runner über alle 73 Dokumente, wiederholbar/fortsetzbar wie die bestehenden Digest-/Such-Runner (vorhandene `ok`-Ergebnisse überspringen, `--force`, Fehler pro Dokument statt Abbruch -- Netzwerk-/Rate-Limit-Fehler sind bei Cloud-Calls häufiger als bei lokalen Modellen), mit Retry- und Timeout-Handling analog zum bestehenden Spike-Skript.
- Eine neue Dokument-Level-Embedding-Art im bestehenden Such-Index (`search-index`): `document_summary_cloud`, berechnet mit dem bereits vorhandenen `embedding`-Baustein (EmbeddingGemma 2) aus Titel+Cloud-Summary, mit `page=0`-Sentinel wie die bestehenden Dokument-Embeddings, aber als eigene, von `document_summary` unterscheidbare Art -- die lokale Variante bleibt unverändert im Index.
- CLI-Integration analog zu den bestehenden `docparse.digest`/`docparse.search`-Kommandos, inkl. einer Gesamtkosten-/Token-Zusammenfassung nach einem Vollauf.
- Laufende Gesamtkosten-Ausgabe, damit vor einem Vollauf über alle 73 Dokumente abschätzbar ist, was er kostet (Vorbild: Spike maß $0.029 für zwei Bild-Extraktionen).

## Nicht-Ziele

- Kein Ersatz der lokalen Summary oder der lokalen `document_summary`-Embeddings -- beide Varianten bleiben parallel im Index, keine Löschung, kein Umschalten, keine Auswahl welche Variante die Suche tatsächlich nutzt.
- Keine Messung oder kein Vergleich der Retrieval-Qualität zwischen beiden Varianten -- das ist `retrieval-eval` (Roadmap #7). Dieser Change liefert nur die zweite Datenbasis, nicht den Beweis, dass sie besser sucht.
- Kein generisches Cloud-Modell-Routing-Framework (`configurable-routing`, Roadmap #5) -- fest verdrahtet auf genau ein Cloud-Modell (Gemini 4 Argon über Vertex AI), keine Modellauswahl, kein Fallback zwischen mehreren Cloud-Modellen.
- Keine Cloud-Variante für Bild-Beschreibungen (`page-enrichment` bleibt vollständig lokal) und keine Cloud-Variante für `document_fulltext` -- nur die kurze Titel+Summary wird zusätzlich per Cloud-Modell erzeugt. Ein Cloud-`document_fulltext` würde bei den längsten Digests (bis ~40.000 Zeichen) die Kosten deutlich erhöhen, ohne für den geplanten späteren Vergleich einen erkennbaren Zusatznutzen zu bringen.
- Keine Änderung an `model-registry`/`model-lifecycle` -- der Cloud-Aufruf läuft nicht über `ModelManager`/VRAM-Budget, da kein lokales, GPU-VRAM-belegendes Modell beteiligt ist.
- Keine dauerhafte Cloud-Pipeline-Integration oder Automatisierung (kein Cron, kein automatischer Fallback bei lokalem Fehlschlag auf die Cloud-Variante) -- ein einmaliger, manuell angestoßener Batch-Lauf über den vorhandenen Datensatz.
- Keine Änderung an der bestehenden lokalen Summary-Generierung (`document-digest`) selbst -- derselbe Markdown-Digest wird nur zusätzlich an das Cloud-Modell geschickt.

## Capabilities

### New Capabilities
- `cloud-document-summary`: Titel+Summary je Dokument, erzeugt von einem Cloud-Flaggschiffmodell (Gemini 4 Argon über Vertex AI) aus dem bestehenden Markdown-Digest, getrennt von der lokalen Summary abgelegt, mit Token-/Kosten-Tracking, wiederholbarem/fortsetzbarem Batch-Lauf und Fehlerbehandlung pro Dokument -- inklusive der daraus abgeleiteten `document_summary_cloud`-Embedding-Art im bestehenden Such-Index (`page=0`-Sentinel, unterscheidbar von `document_summary`).

### Modified Capabilities
(keine -- `search-index`, dessen bestehende Dokument-Level-Embeddings hier um eine weitere Art ergänzt werden, ist Teil des noch nicht archivierten `embedding-search`-Changes und existiert deshalb noch nicht als eigene Capability unter `openspec/specs/`; die Erweiterung wird daher oben als Teil von `cloud-document-summary` geführt, nicht als Delta auf einen noch nicht existierenden Pfad.)

## Impact

- Neuer Code voraussichtlich unter `src/docparse/digest/` (Cloud-Summary-Generator, analog zu `summary.py`, aber mit Cloud-API-Aufruf statt `ModelManager`) und einer Erweiterung von `src/docparse/search/document_embed.py`/`runner.py` um die neue Embedding-Art.
- Nutzt die bereits in der Umgebung vorhandenen Vertex-AI-Credentials (`GEMINI_API_KEY`/ADC, GCP-Projekt wie in `experiments/vlm-qa-test/run_gemini_vl.py`) -- kein neuer Secrets-Mechanismus.
- Neue Dateien unter `data/results/digest/*.cloud_summary.json`, nicht im Git (wie der Rest von `data/results/`).
- Erweitert den bestehenden Such-Index (`data/results/search/`) um zusätzliche Vektoren; bestehende Einträge bleiben unverändert.
- Laufende Kosten: Spike-Pricing ($2.00/Mtok in, $10.00/Mtok out für Gemini 4 Argon) auf kurze Text-Prompts (Markdown-Digest als Input, 220 Token Output) angewendet ergibt geschätzt niedrige einstellige Cent-Beträge je Dokument, insgesamt im niedrigen einstelligen Dollar-Bereich für alle 73 Dokumente -- wird im Runner als Summe ausgegeben statt nur geschätzt.
