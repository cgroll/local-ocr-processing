# Design

## Context

Siehe `proposal.md` (Why) für die Motivation. Relevanter Stand, den dieses Design voraussetzt:

- Produktions-Suche: `src/docparse/search/{embed,document_embed,fulltext,query,format}.py` -- Seiten-/Block-/Dokument-Embeddings (EmbeddingGemma 2, 768-dim) plus SQLite-FTS5-Volltext über `data/results/enrich/`. Verifiziert: `fulltext.py:enriched_documents` liest ausschließlich aus `data/results/enrich/`, nie aus den Dokument-Summaries -- der Volltextindex ist also für beide Sandbox-Varianten identisch.
- `data/results/digest/<doc>.summary.json` (lokal, `describe`-Modell, 15/73 `status: "degenerate"`) und `<doc>.cloud_summary.json` (Gemini 4 Argon, 73/73 `ok`, aus `cloud-document-summary`) sind die beiden zu vergleichenden Varianten.
- `EmbeddingItem` (`src/docparse/search/format.py`) hat ein `kind`-Feld (`document_summary` bzw. `document_summary_cloud` für die hier relevanten Einträge, `page=0` als Sentinel) -- Filtern nach `kind` ist eine reine Array-Maskierung, kein neuer Indexierungslauf.
- `EmbeddingLoader` (`src/docparse/models/loaders.py`) lädt EmbeddingGemma 2 über `sentence_transformers.SentenceTransformer(model_id, device="cuda", ...)` -- unabhängig vom PaddlePaddle-Stack. Für die Sandbox: derselbe Aufruf mit `device="cpu"`. Modellgewicht liegt bereits lokal im HF-Cache (`~/.cache/huggingface/hub/models--google--embeddinggemma-2/`, 1,4 GB Safetensors), kein Download zur Laufzeit nötig.
- Agent-Laufzeit: `claude_agent_sdk` (Python-Paket, bringt eine 300 MB-Standalone-ELF-Binary mit, kein Node.js nötig) -- verifiziert an einem Schwesterprojekt auf dieser Maschine (`~/research/speech-to-speech/src/speech_to_speech/llm.py`), das bereits `ClaudeAgentOptions(permission_mode=..., cwd=..., mcp_servers=..., disallowed_tools=[...])` + `ClaudeSDKClient` + `await client.query(text)` in genau diesem Headless-Muster verwendet. Dieser Change installiert `claude_agent_sdk` neu (nicht im Projekt-`pyproject.toml`, siehe Decision 1).
- Authentifizierung dieser Maschine läuft über `~/.claude/.credentials.json` (OAuth-Session, `claudeAiOauth`-Schlüssel) -- **kein** `ANTHROPIC_API_KEY` in der Umgebung gesetzt. Für Container-Läufe muss diese eine Datei (nicht das ganze `~/.claude/`-Verzeichnis, das u. a. Projekt-Historie anderer Repos enthält) gezielt read-only gemountet werden.
- Docker + `nvidia-container-toolkit` sind auf der Maschine installiert und funktionieren (verifiziert über `docker run --gpus all ... nvidia-smi`) -- hier nicht gebraucht, da die Sandbox CPU-only läuft (siehe Decision 2).

## Goals / Non-Goals

**Goals:**
- Für jede der 20 Fragen aus `experiments/vlm-qa-test/questions.py` zwei vergleichbare, isolierte Such-Umgebungen bereitstellen (lokal/cloud), in denen ein Claude-Agent frei suchen kann.
- Such-Effizienz (Tool-Aufrufe, besuchte Dokumente, Tokens/Kosten, Dauer) und Korrektheit (per Gemini-Judge) pro Lauf vergleichbar protokollieren.
- Geringes Risiko/geringe Kosten vor dem Vollauf: Pilot zuerst (siehe `tasks.md`).

**Non-Goals:**
- Keine Wiederverwendung oder Erweiterung von `ModelManager`/der Modell-Registry -- die Sandbox braucht kein VRAM-Budget-Konzept, nur ein einzelnes CPU-Modell.
- Keine allgemeine Docker-Infrastruktur für das Projekt -- das Image/Dockerfile ist Spike-spezifisch unter `experiments/agentic-retrieval-eval/`, keine Vorlage für andere Changes.
- Keine Mehrfach-Modell-Unterstützung im Judge (nur Gemini 4 Argon, fest verdrahtet wie in `cloud_summary.py`).

## Decisions

1. **`claude_agent_sdk` als Ephemeral-Abhängigkeit nur im Docker-Image, nicht in `pyproject.toml`.** Begründung: wird ausschließlich innerhalb der Sandbox gebraucht (der Agent, der durchsucht), nicht vom Rest von `docparse`. Analog zum bestehenden Projekt-Muster für Experiment-Skripte (`experiments/vlm-qa-test/run_gemini_vl.py` nutzt `uv run --with google-genai`) -- hier als `pip install claude-agent-sdk` im Dockerfile statt im Projekt-venv.
2. **EmbeddingGemma 2 CPU-only in der Sandbox, kein GPU-Passthrough.** GPU-Passthrough wurde verifiziert (funktioniert auf der Maschine), ist aber unnötiger Aufwand: `EmbeddingLoader` zeigt, dass das Embedding-Modell unabhängig vom GPU-gebundenen PaddlePaddle-Stack ist. Ein eigenes, minimales Lade-Skript in der Sandbox (nicht `docparse.models`/`ModelManager`, die für VRAM-Budgets über mehrere GPU-Modelle gedacht sind) mit `device="cpu"`. Alternative verworfen: die 20 Fragen vorab außerhalb encoden und nur Vektoren mitgeben -- hätte dem Agenten die Fähigkeit genommen, eigene Zwischen-Queries zu stellen, was dem Wunsch nach freier Suchmethode widerspricht.
3. **Echte Docker-Isolation, Agent-Prozess läuft *innerhalb* des Containers, nicht nur mit `cwd` auf den Sandbox-Ordner gesetzt.** Verifiziert: Claude Codes eigenes "Sandbox"-Flag am Bash-Tool schränkt das Dateisystem nicht ein (`cat /etc/hostname`, `ls /home/<user>` funktionierten trotzdem). Die Container-Grenze selbst (kein anderer Mount als Sandbox-Ordner + Credentials-Datei + HF-Cache, kein Internetzugriff) ist die tatsächliche Absicherung, nicht eine SDK-Option. `permission_mode="bypassPermissions"` ist nötig, da niemand interaktiv Tool-Freigaben erteilt.
4. **Credentials: redaktierte Kopie über `CLAUDE_CONFIG_DIR`, kein Mount der echten `~/.claude/.credentials.json`.** Verifiziert (Task 1.1): die echte Datei enthält neben dem Anthropic-Login (`claudeAiOauth`) auch OAuth-Tokens fremder MCP-Server (z. B. Notion, unter `mcpOAuth`) -- die dürfen nicht in den Container. Stattdessen: eine neue, minimale `.credentials.json` nur mit dem `claudeAiOauth`-Objekt in ein eigenes Verzeichnis schreiben und per `CLAUDE_CONFIG_DIR`-Umgebungsvariable (offizieller SDK-Mechanismus, siehe `claude_agent_sdk/_internal/session_resume.py`) read-only in den Container mounten. **Zusätzlich verifiziert:** die CLI verweigert `--dangerously-skip-permissions` (= `permission_mode="bypassPermissions"`) als root -- der Container-Prozess muss als nicht-root-User laufen (`docker run --user <uid>:<gid>`, passend zum Besitzer der Credentials-Datei).
5. **Gefilterte Embedding-Kopie statt zwei komplett unabhängiger Indizes.** `EmbeddingIndex.load()` + eine reine Masken-Operation auf `items`/`vectors` nach `kind != "document_summary_cloud"` (lokal) bzw. `kind != "document_summary"` (cloud), dann `save()` in den jeweiligen Sandbox-Ordner. Kein neuer Lauf von `docparse.search run` nötig, nur Lesen + Filtern + Schreiben des bestehenden Index.
6. **Sandbox-Inhalt ist eine reine Kopie, kein Live-Mount der echten `data/results/`.** Verhindert versehentliches Zurückschreiben aus dem Container und macht die zwei Varianten unabhängig voneinander löschbar/wiederholbar.
7. **Such-Effizienz-Metriken aus dem SDK-Message-Stream ableiten, kein separates Tracing.** `ClaudeSDKClient` liefert laufende Nachrichten (u. a. `ToolUseBlock`) und am Ende eine `ResultMessage` mit Nutzungsdaten. Tool-Aufrufe nach Art zählen wir direkt aus den `ToolUseBlock`-Namen; besuchte Dokumente aus den Pfaden/Argumenten der Bash-/Read-Aufrufe (einfache Heuristik: Dokument-ID aus dem Pfad extrahieren, z. B. `.../digest/ds-lm317.md` -> `ds-lm317`) -- grob, aber für einen Vergleichs-Spike ausreichend.
8. **`allowed_tools` auf die tatsächlich benötigten Dateisystem-Tools beschränken (`Bash`, `Read`, `Glob`, `Grep`), nicht den SDK-Default übernehmen.** Verifiziert (Task 1.1): der Default-Toolset eines frischen Agenten umfasst u. a. `WebSearch`/`WebFetch` -- das würde dem Agenten erlauben, die Frage direkt aus dem Web statt aus dem Sandbox-Corpus zu beantworten und damit genau das zu umgehen, was gemessen werden soll (Such-Effizienz über den lokalen Index). Das ist kein Widerspruch zur Entscheidung "keine Einschränkung der Suchmethode" (`proposal.md`) -- jene bezieht sich auf Methoden, den *Sandbox-Inhalt* zu durchsuchen, nicht auf das Verlassen der Sandbox über Internet-Tools. Nebeneffekt: der Default-Toolset (gut 20 Tools inkl. Cron/Scheduling/Sub-Agenten) erzeugt laut Smoke-Test allein für die Tool-Definitionen ca. 12.300 Cache-Creation-Tokens (~$0,10 für ein triviales "antworte mit OK") -- ein kleinerer, themenbezogener Toolset reduziert auch die Grundkosten jedes Laufs.
9. **Gemini-Judge wiederverwendet das Vertex-AI-Client-Muster aus `cloud_summary.py`** (Projekt/Location-Konstanten, Retry, `usage_metadata`-basierte Kosten), aber als eigenständiges Skript unter `experiments/agentic-retrieval-eval/` mit eigenem Prompt (Frage + Ground Truth + Agenten-Antwort -> Verdikt), nicht als Erweiterung der Produktions-Datei.

## Risks / Trade-offs

- **[Risiko] OAuth-Session-Credentials funktionieren evtl. nicht unverändert innerhalb eines Containers** (z. B. falls an Geräte-/Session-Merkmale gebunden) -> Mitigation: genau das ist ein Pilot-Abnahmekriterium (`tasks.md`, erster Schritt); bei Fehlschlag Rückfalloption wäre ein `ANTHROPIC_API_KEY`-basierter Zugang, aber das ist eine neue Entscheidung, keine stillschweigende Annahme.
- **[Risiko] Dokument-Zählung aus Tool-Aufrufen ist nur eine Heuristik** (Pfad-Parsing, kein echtes Tracing) -> Mitigation: für einen Vergleichs-Spike ausreichend; explizit als grobe Näherung dokumentieren, nicht als exakte Messung ausgeben.
- **[Risiko] Bild-Verifikationspflicht ist nur eine Prompt-Vorgabe, nicht technisch erzwungen** -- der Agent könnte sie ignorieren -> Mitigation: beim Scoring/Review sichtbar (Transkript enthält, ob ein Bild-Read-Tool-Call stattfand), keine Erzwingung nötig für einen Spike.
- **[Trade-off] Zwei vollständige Sandbox-Kopien pro Frage statt eines gemeinsamen Mounts** kostet mehr Festplattenplatz/Build-Zeit, hält die beiden Läufe aber garantiert unabhängig und nebenwirkungsfrei -- bewusst in Kauf genommen.
- **[Risiko] `total_cost_usd`/Token-Felder der SDK-`ResultMessage` sind unter OAuth-Abo-Login evtl. anders befüllt als unter reiner API-Key-Abrechnung** -> Mitigation: im Pilot verifizieren, welche Felder tatsächlich befüllt sind, Metrik-Erfassung entsprechend anpassen (kein Showstopper, nur Detail).

## Open Questions

(keine mehr offen -- die einzige Frage von vorhin, die exakten Feldnamen der `ResultMessage`-Nutzungsdaten, ist durch Task 1.1 beantwortet: `total_cost_usd`, `usage` (inkl. `input_tokens`/`output_tokens`/Cache-Felder), `duration_ms`, `duration_api_ms`, `num_turns`, `result` sind vorhanden und befüllt, auch unter OAuth-Abo-Login, nicht nur unter reiner API-Key-Abrechnung.)

## Verifiziert (Vollauf, 2026-10-26)

- **`max_buffer_size` muss explizit hochgesetzt werden.** Default (1 MB) reicht nicht, sobald der Agent ein großes gescanntes Seitenbild liest -- `gd1-001028` Seite 1 (3,1 MB PNG, ~4,2 MB base64-kodiert) brach mit `CLIJSONDecodeError("JSON message exceeded maximum buffer size of 1048576 bytes...")` ab und beendete den gesamten Lauf (kein Einzelfehler pro Frage, sondern ein Absturz des ganzen Prozesses). Mehrere weitere Scans im Datensatz liegen in ähnlicher Größenordnung (>1 MB PNG). Fix: `ClaudeAgentOptions(max_buffer_size=32_000_000)` in `run_agent.py`.

## Verifiziert (Task 1.1, 2026-10-26)

- Container-Authentifizierung über redaktiertes `CLAUDE_CONFIG_DIR` funktioniert ohne `ANTHROPIC_API_KEY` und ohne Mount des vollen `~/.claude/`-Verzeichnisses.
- Trivialer Einzel-Turn-Call ("antworte mit OK") kostet laut `ResultMessage.total_cost_usd` ca. **$0,10**, überwiegend durch Cache-Creation der Tool-/Skill-Definitionen (~12.300 Tokens) -- wichtig für die Kostenschätzung des Piloten (6-10 Läufe) und sollte durch einen eingeschränkten `allowed_tools`-Satz (Decision 8) reduziert werden.
