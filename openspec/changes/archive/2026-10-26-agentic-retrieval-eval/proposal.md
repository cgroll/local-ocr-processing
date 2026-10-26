# Proposal

## Why

`cloud-document-summary` hat gezeigt, dass die Cloud-Summary (Gemini 4 Argon) inhaltlich klar besser ist als die lokale (73/73 vs. 58/73 brauchbar, konkreter bei Zahlen/Fakten). Offen ist, ob das auch zu einer **effizienteren Suche** führt, wenn ein Agent den richtigen Content erst selbst finden muss, statt ihn wie im ursprünglichen `experiments/vlm-qa-test/`-Spike direkt vorgelegt zu bekommen. Das ist die nächste, realistischere Stufe desselben Fragensatzes (gleiche 20 Fragen, gleiche Ground Truth) und ein günstiger, bewusst klein gehaltener Testlauf, bevor eine etwaige systematische Messung (`retrieval-eval`, Roadmap #7) angegangen wird.

## What Changes

- Neues Experiment-Verzeichnis `experiments/agentic-retrieval-eval/` (informeller Spike, analog zu `experiments/vlm-qa-test/`, `experiments/digest-summary-test/`, `experiments/multimodal-repr-test/` -- keiner davon hat eine OpenSpec-Spec, keiner ist Teil der Produktionspipeline).
- Ein Sandbox-Builder, der aus `data/results/{enrich,digest,search}` und `data/pages` zwei Wegwerf-Ordner erzeugt ("lokal" und "cloud"), identisch bis auf die Dokument-Summary-Datei und eine gefilterte Kopie des Embedding-Index (siehe `design.md`).
- Ein schlankes Docker-Image (kein GPU, kein PaddlePaddle) mit `sentence-transformers`(CPU) + `numpy` + `sqlite3`, das EmbeddingGemma 2 aus dem lokalen HF-Cache lädt, für eine minimale Such-CLI innerhalb der Sandbox.
- Ein Agent-Harness, das für jede der 20 Fragen aus `experiments/vlm-qa-test/questions.py` einen Claude-Agent-SDK-Lauf pro Sandbox-Variante startet (nur die Frage als Eingabe, kein Dokument-/Seiten-Hinweis), mit der Vorgabe, die tatsächliche Seiten-PNG vor der finalen Antwort zu verifizieren.
- Protokollierung von Such-Effizienz-Kennzahlen je Lauf (Tool-Aufrufe nach Art, Zahl besuchter Dokumente, Tokens/Kosten der Claude-Session, Wall-Clock-Dauer, ob der richtige Content überhaupt gefunden wurde).
- Ein Scoring-Schritt per LLM-as-Judge (Gemini 4 Argon, nicht Claude) gegen die Ground Truth, Verdikt `correct`/`partial`/`wrong`.
- Gestufter Rollout: zuerst ein Pilot über 3-5 Fragen x 2 Varianten, danach -- nur bei Bedarf -- der Vollauf über alle 20 x 2.

## Nicht-Ziele

- Keine systematische, statistisch robuste Retrieval-Qualitätsmessung -- das bliebe `retrieval-eval` (Roadmap #7), falls separat verfolgt. Dieser Change ist ein begrenzter Vergleich über die bestehenden 20 Fragen, kein Ersatz dafür.
- Keine Produktions-Integration eines agentischen RAG-Layers -- der Agent-Harness lebt ausschließlich unter `experiments/`, nichts davon wird Teil von `src/docparse`.
- Keine Änderung des bestehenden Such-Index oder der `cloud_summary.py`-Produktionslogik -- der Sandbox-Builder liest nur, kopiert in Wegwerf-Ordner, schreibt nie zurück nach `data/results/`.
- Kein GPU im Docker-Image und kein Internetzugriff im Sandbox-Container (EmbeddingGemma 2 läuft CPU-only aus dem lokal gemounteten HF-Cache; dient zugleich der Geheimhaltung der Ground Truth).
- Keine Einschränkung der Suchmethode des Agenten (Grep, Volltext, Vektorsuche, Bildbetrachtung -- alles erlaubt) und keine harte technische Garantie, dass der Agent die Ground Truth unmöglich finden könnte (schwache Geheimhaltung: Ground Truth liegt schlicht nie im Sandbox-Ordner).
- Keine eigene Function-Calling-/Tool-Schema-Entwicklung für den suchenden Agenten -- bewusst ein Out-of-the-Box-Agent (Claude Agent SDK) statt einer selbstgebauten Gemini-Tool-Integration.
- Kein automatisiertes Scoring ohne jede menschliche Stichprobenkontrolle -- die Judge-Verdikte werden zumindest stichprobenhaft von Hand gegengelesen, wie bei den bisherigen Spikes.

## Capabilities

### New Capabilities
(keine -- `skip_specs: true`, siehe `.openspec.yaml`. Dieser Change ändert kein spezifiziertes Verhalten von `src/docparse`; er liest ausschließlich bereits vorhandene `data/results/`-Artefakte, um Wegwerf-Sandboxes für einen externen, informellen Vergleichs-Testlauf zu bauen -- derselbe Status wie die bestehenden Spikes unter `experiments/`, von denen keiner eine OpenSpec-Spec hat.)

### Modified Capabilities
(keine)

## Impact

- Neuer Code ausschließlich unter `experiments/agentic-retrieval-eval/` (Sandbox-Builder, Docker-Image/Dockerfile, Agent-Harness-Skript, Gemini-Judge-Skript) -- nichts unter `src/docparse/`.
- Liest `data/results/{enrich,digest,search}`, `data/pages/`, `experiments/vlm-qa-test/questions.py` (nur die Fragen, nicht `judgments.py`/Ground Truth -- die bleiben außerhalb jeder Sandbox und werden erst beim Scoring außerhalb des Containers herangezogen).
- Nutzt den bereits lokal vorhandenen HF-Cache (`~/.cache/huggingface/hub/models--google--embeddinggemma-2/`) read-only, sowie die bereits in der Umgebung vorhandenen Vertex-AI-Credentials (wie in `cloud_summary.py`) für den Judge-Call.
- Neue Laufzeit-Artefakte (Sandbox-Kopien, Agent-Transkripte, Effizienz-Kennzahlen, Judge-Verdikte) liegen unter `experiments/agentic-retrieval-eval/` bzw. einem Ergebnis-Unterordner davon, nicht unter `data/results/` (kein Produktions-Ergebnis).
- Kosten: Pilot (6-10 Läufe) plus Judge-Calls im Centbereich bis niedrigen einstelligen Dollarbereich (ähnliche Größenordnung wie `cloud-document-summary`); Vollauf (40 Läufe) entsprechend mehr, aber nur nach erfolgreichem Pilot.
