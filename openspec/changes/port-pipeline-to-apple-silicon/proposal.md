# Proposal

## Why

Die Pipeline ist fest auf Linux + NVIDIA-GPU (CUDA) verdrahtet: `pyproject.toml` pinnt `paddlepaddle-gpu==3.3.1`, wofür es keine macOS-Wheels gibt, sodass `uv sync` auf Apple Silicon schon beim Auflösen abbricht. Dadurch lässt sich die komplette Pipeline (`parse`, `enrich`, `search`) auf dem vorhandenen Mac (M4, 24 GB Unified Memory) nicht ausführen — obwohl mit `~/repos/EEP` bereits ein lauffähiger Apple-Silicon-Zwilling existiert (CPU-`paddlepaddle` für Layout, `mlx-vlm` für PaddleOCR-VL und EmbeddingGemma 2), dessen Lösungswege sich übernehmen lassen. Konkreter Anlass: der RVA-Dokumentenkorpus (`~/repos/EEP/data/RVA_Sample`, 30 PDFs) soll lokal auf dem Mac geparst und die Markdown-Rekonstruktion im Viewer gegen das Original geprüft werden.

## What Changes

- **Plattformspezifische Abhängigkeiten:** `paddlepaddle-gpu` nur noch unter Linux/Windows, unter macoS-arm64 stattdessen CPU-`paddlepaddle` plus `mlx`/`mlx-vlm`. `uv sync` muss auf beiden Plattformen durchlaufen. Linux/CUDA bleibt voll funktionsfähig.
- **Backend-fähige Modell-Loader:** Die Loader für `vl`, `embedding` und `describe` bekommen je einen MLX-Pfad neben dem bestehenden CUDA-Pfad. Welcher Pfad greift, wird plattform- bzw. konfigurationsabhängig gewählt. `layout` und `ocr` laufen auf dem Mac über CPU-`paddlepaddle` (gleiche Paddle-API, kein neuer Loader nötig).
- **VL über MLX via Layout + element-weise Recognition:** Da der MLX-Pfad (`mlx-vlm`) keine seitenweite `parsing_res_list` wie der Paddle-Pfad liefert, wird das VL-Ergebnis auf dem Mac aus Layout-Boxen (PP-DocLayout) plus je Region einem MLX-Recognition-Call zusammengesetzt und in dasselbe Block-Zwischenformat (Typ, Box, Reihenfolge, Markdown/HTML) überführt. Das von `parse`/`viewer`/`enrich`/`search` konsumierte Format bleibt unverändert.
- **`describe` mit Mac-Ersatz:** Der CUDA-Pfad nutzt Qwen2.5-VL in 4-bit über `bitsandbytes` (CUDA-only). Auf dem Mac tritt ein MLX-fähiges VLM an dessen Stelle; die aufrufende `describe`/`generate_text`-Schnittstelle bleibt gleich.
- **Speicher-Wächter für Unified Memory:** Der an `nvidia-smi`/VRAM gebundene Wächter wird so konfigurierbar/entschärfbar, dass er auf dem Mac (24 GB geteilter Speicher, kein `nvidia-smi`) nicht fälschlich blockiert, ohne die reale Schutzfunktion unter CUDA aufzugeben.
- **Registry/Konfiguration:** Gerät (`gpu`/`cpu`/`mps`/`mlx`) und Backend je Baustein bzw. Budget/Reserve müssen plattformabhängig über `models.toml` bzw. Default-Specs gesetzt werden können.

**Nicht-Ziele:**
- Keine Änderung des Block-Zwischenformats, der Viewer-Ausgabe, der Suchindex-Struktur oder der CLI-Kommandos.
- Keine Qualitäts-/Genauigkeitsgleichheit zwischen CUDA- und MLX-Ergebnissen garantiert; Ziel ist ein lauffähiger, visuell prüfbarer Durchlauf, nicht numerische Parität.
- Kein Aufnehmen der RVA-Dokumente ins Manifest und kein eigentlicher Verarbeitungslauf (separater Folge-Change/Arbeitsschritt).
- Kein Entfernen oder Ablösen des CUDA-Pfads; beide Plattformen bleiben gleichberechtigt.
- Keine neuen Modelle in der Roadmap, keine Routing-/Retrieval-Änderungen.

## Capabilities

### New Capabilities
<!-- keine -->

### Modified Capabilities
- `model-registry`: Geräteangabe je Baustein erweitert um Nicht-CUDA-Ausführungsorte (CPU/MPS/MLX); Budget/Reserve und Gerät plattformabhängig überschreibbar.
- `model-lifecycle`: VRAM-Wächter wird auf Plattformen ohne `nvidia-smi`/dediziertes VRAM (Unified Memory) definiert — konfigurierbares Verhalten statt fälschlicher Blockade, Schutzfunktion unter CUDA bleibt.
- `engine-adapters`: VL-Adapter erhält einen Pfad, der aus Layout-Regionen plus element-weiser Recognition dieselben VL-Blöcke erzeugt wie der seitenweite Paddle-Pfad.

## Impact

- **Abhängigkeiten:** `pyproject.toml` (plattform-markierte Dependencies, `uv.lock`), neu `mlx`, `mlx-vlm` unter macOS.
- **Code:** `src/docparse/models/loaders.py` (vl/embedding/describe backend-fähig), `src/docparse/models/gpu.py` und `.../lifecycle.py` (Wächter), `src/docparse/models/registry.py` + `models.toml` (Gerät/Backend/Budget), `src/docparse/parse/engines.py` + `src/docparse/parse/adapters/vl.py` (Layout+Recognition-Pfad). `enrich`/`search`/`digest` unverändert in der Schnittstelle, nur mittelbar über die Loader betroffen.
- **Plattformen:** macOS-arm64 neu lauffähig; Linux/CUDA unverändert.
- **Vorlagen:** `~/repos/EEP/eep/{vlm,embed,layout}.py` als Referenzimplementierung.
