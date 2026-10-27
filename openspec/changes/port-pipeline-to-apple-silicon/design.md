# Design

## Context

Siehe `proposal.md – Why`. Aktueller Zustand: Die Loader (`src/docparse/models/loaders.py`) sind fest auf CUDA-Backends geschrieben (`PaddleOCRVL` über Paddle/CUDA, `SentenceTransformer(device="cuda")`, Qwen2.5-VL in 4-bit über `bitsandbytes`). Der Speicher-Wächter (`gpu.py`, `lifecycle.py`) liest `nvidia-smi`. `pyproject.toml` pinnt `paddlepaddle-gpu==3.3.1` ohne Plattform-Marker. Das Block-Zwischenformat, der Runner (`parse/runner.py`, `executors.py`, inkl. VL-Subprozess mit Timeout), Viewer, `enrich` und `search` sind framework-neutral und bleiben unangetastet.

Referenzimplementierung liegt vor: `~/repos/EEP` löst dieselben drei Modelle auf Apple Silicon — `eep/vlm.py` (PaddleOCR-VL via `mlx-vlm`, element-weise `recognise(image, prompt)`), `eep/embed.py` (EmbeddingGemma 2 via MLX, Text+Bild, 768d, L2-normiert), `eep/layout.py` (PP-DocLayout über CPU-`paddlepaddle`), `eep/config.py` (PP-DocLayout-Label → VL-Task-Prompt-Mapping). Modelle werden dort als MLX-Ports geladen (`mlx-community/PaddleOCR-VL-bfloat16`, `mlx-community/embeddinggemma-2-bf16`).

## Goals / Non-Goals

**Goals:**
- `uv sync` und der volle Pipeline-Durchlauf (`parse`, `enrich`, `search`, `viewer`) laufen auf macOS-arm64 (M4, 24 GB).
- Backend-Auswahl hinter der bestehenden Loader-/Registry-Schnittstelle gekapselt; `RUNNERS`, Adapter-Aufrufer und CLIs rufen unverändert.
- CUDA-Pfad bleibt bit-identisch zum Ist-Zustand lauffähig.

**Non-Goals (design-level):**
- Keine Abstraktionsschicht, die jedes denkbare Backend generisch bedient — nur die zwei konkret gebrauchten (CUDA, MLX) plus CPU-Paddle für `layout`/`ocr`.
- Keine gemeinsame Gewichts-Quelle: CUDA lädt wie bisher (Paddle/HF), MLX lädt MLX-Ports. Kein Konvertierungs-Shim.
- Kein neuer Download-Mechanismus im Kern; der genaue Modellbezug (HF vs. ModelScope, Proxy) ist Umsetzungsdetail des Mac-Loaders.

## Decisions

### D1 — Plattform-Marker in `pyproject.toml` statt extras
`paddlepaddle-gpu` bekommt `sys_platform != 'darwin'`, `paddlepaddle` (CPU) und `mlx`/`mlx-vlm` bekommen `sys_platform == 'darwin'`. Begründung: `uv sync` soll auf jeder Plattform ohne zusätzliches Flag das Richtige auflösen; ein `--extra mac` (wie es EEP teils nutzt) wäre eine manuelle Fehlerquelle. Alternative (ein gemeinsames `paddlepaddle` CPU überall) verworfen: würde den gemessenen CUDA-Durchsatz auf dem Linux-Rechner zunichtemachen.

### D2 — Backend-Wahl in der Registry, Ausführung im Loader
Die Registry führt je Baustein einen `backend`-Parameter (`cuda` | `mlx`) mit plattformabhängigem Default (ermittelt einmalig, z. B. `sys.platform == "darwin"` → `mlx`), überschreibbar in `models.toml`. Der jeweilige Loader verzweigt anhand `spec.params["backend"]`. Begründung: Die Registry ist laut bestehender Spec ohnehin die einzige Quelle für „welches Modell, welche Version, welcher Ort"; Backend gehört dorthin. Die schweren Importe bleiben wie bisher in `load()` lokal, damit die Registry ohne GPU/MLX nutzbar bleibt. Alternative (Backend per Umgebungsvariable) verworfen: nicht versioniert, nicht pro Baustein steuerbar.

### D3 — `device`-Feld erweitern statt umdeuten
`ModelSpec.device` nimmt zusätzlich `mlx` (und bei Bedarf `mps`) an. Der Wächter behandelt `gpu` (CUDA) wie bisher; für `mlx` greift die budgetbasierte Prüfung, aber nicht die `nvidia-smi`-Messung. Begründung: minimaler Eingriff, `device` ist bereits das Feld, an dem der Wächter entscheidet.

### D4 — Wächter: reale Messung nur wo messbar
`gpu_free_mb()` gibt auf Nicht-CUDA ohnehin `None` zurück, und `lifecycle.check()` überspringt die Realmessung bei `None` bereits. Der Eingriff ist daher klein: (a) die Realmessung nur noch für `device == "gpu"` versuchen, (b) `free_gpu_memory()` räumt `paddle`/`torch`-CUDA-Caches nur, wenn CUDA tatsächlich aktiv ist (MLX-Freigabe = Referenzen lösen + `gc`). Das Budget für Unified Memory wird in `models.toml` gesetzt (z. B. `total_mb` deutlich höher, da 24 GB geteilt). Begründung: Die bestehende Schutzlogik unter CUDA bleibt unberührt; auf dem Mac verhindert nur noch das Budget Überladung, was bei 24 GB geteiltem Speicher und sequenziellem Laden ausreicht.

### D5 — VL auf MLX: Layout-Regionen + element-weise Recognition
Der Mac-`vl`-Pfad lädt PP-DocLayout (CPU-Paddle, bereits als `layout` vorhanden) für die Regionen und ruft je Region `mlx-vlm` mit einem task-spezifischen Prompt auf (Label→Prompt-Mapping wie in `eep/config.py`: `table`→"Table Recognition:", `chart`→"Chart Recognition:", `formula`→"Formula Recognition:", sonst "OCR:"). Die Ergebnisse werden in dasselbe Roh-Dict (`label`, `bbox`, `content`, `polygon_points`) gegossen, das `parse/adapters/vl.py::to_blocks` bereits konsumiert — der Adapter selbst bleibt unverändert. Begründung: Der MLX-Pfad liefert keine seitenweite `parsing_res_list`; diese Zusammensetzung ist der in EEP erprobte Weg und hält das Downstream-Format stabil. Alternative (ganze Seite → ein Markdown-Block) wurde vom Nutzer zugunsten echter per-Region-Boxen verworfen.

**Konsequenz Runner:** Der Mac-`vl`-Lauf braucht zur Inferenzzeit zwei Modelle (Layout + VL). Layout ist klein (~CPU) und VL ist das große MLX-Modell; bei 24 GB ist das unkritisch, aber der Wächter/`fits` darf diese Kombination auf dem Mac nicht verbieten (über Budget/`backend` lösbar). Der bestehende VL-Subprozess-/Timeout-Mechanismus (`executors.py`) bleibt und umschließt den zusammengesetzten Lauf.

### D6 — `describe` auf MLX statt bitsandbytes
`bitsandbytes` ist CUDA-only. Auf dem Mac tritt ein MLX-fähiges VLM an die Stelle von Qwen2.5-VL-4bit, hinter der unveränderten `DescribeHandle`-Schnittstelle (`describe(image, prompt)`, `generate_text(prompt)`). Die konkrete Modellwahl (z. B. ein MLX-Qwen2.5-VL-Port) wird in der Umsetzung festgelegt und in der Registry als Backend-Variante geführt. Begründung: `enrich` und die Summary-Erzeugung hängen nur an dieser Schnittstelle, nicht am Modell.

### D7 — EmbeddingGemma 2 über MLX
Der Mac-`embedding`-Loader nutzt `mlx-vlm` wie `eep/embed.py` (Text- und Bild-Encode, 768d, L2-Normierung, Matryoshka-Trunkierung). Rückgabe wird auf dasselbe Array-Format gebracht, das `search/embed.py` erwartet (NumPy-float32, L2-normiert). Begründung: torch-MPS wäre die Alternative, aber MLX ist in EEP bereits erprobt und schneller; die Modellkarte warnt vor float16 — bf16/float32 wird eingehalten.

## Risks / Trade-offs

- **MLX-VL-Qualität weicht vom CUDA-Paddle-Pfad ab** (anderes Zusammensetzen, element-weise statt seitenweit) → Mitigation: Ziel ist visuelle Prüfbarkeit im Viewer, nicht Parität (Non-Goal im Proposal); Stichprobe gegen EEPs bekannte Ergebnisse (RüKü-Datenblatt, Token-Recall 0,80–0,99).
- **Zwei Modelle gleichzeitig beim Mac-VL (Layout+VL)** → Mitigation: 24 GB Unified Memory, sequenzielle Regionen-Calls, Budget in `models.toml` passend gesetzt; Wächter nur budgetbasiert.
- **`uv.lock` divergiert zwischen Plattformen / CI** → Mitigation: Plattform-Marker so wählen, dass ein einziger Lock beide Plattformen auflöst; `uv sync` auf beiden Plattformen als Task verifizieren.
- **Modell-Download hinter Firmen-Proxy** (EEP braucht ModelScope + truststore) → Mitigation: Download ist Umsetzungsdetail des Mac-Loaders; Doku-Task, kein Kern-API-Eingriff.
- **Regressionsgefahr für den CUDA-Pfad** durch Loader-Verzweigung → Mitigation: CUDA-Zweig bleibt wörtlich der bisherige Code; Default-Backend plattformabhängig, bestehende Tests auf Linux unverändert grün.

## Migration Plan

1. Plattform-Marker in `pyproject.toml`, Lock neu auflösen, `uv sync` auf Mac prüfen.
2. Registry/`device`/`backend` + `models.toml`-Defaults, dann Wächter (klein) — beides ohne Modell-Laden testbar.
3. Loader-Zweige (embedding → describe → vl) einzeln über `models smoke` auf dem Mac verifizieren.
4. `parse --engines pymupdf,layout,ocr`, dann `vl`, dann `enrich`/`search` an einem EEP-Beispieldokument gegenprüfen.

Rollback: Backend-Default wieder auf `cuda` zwingen bzw. Plattform-Marker zurücknehmen; der CUDA-Pfad ist nie entfernt.

## Open Questions

- Konkrete MLX-Modell-IDs für `describe` (MLX-Qwen-Variante) — in Schritt 3 festzulegen, ändert weder Spec noch Task-Zuschnitt.
