# Tasks

## 1. Plattform-Abhängigkeiten

- [x] 1.1 In `pyproject.toml` `paddlepaddle-gpu` auf `sys_platform != 'darwin'` markieren und für `sys_platform == 'darwin'` CPU-`paddlepaddle` sowie `mlx`/`mlx-vlm` ergänzen (Pins analog `~/repos/EEP/pyproject.toml`); verifizieren mit `uv lock` ohne Fehler.
- [x] 1.2 `uv sync` auf macOS-arm64 durchlaufen lassen und verifizieren, dass die Installation ohne den bisherigen `paddlepaddle-gpu`-Plattformfehler abschließt.
- [x] 1.3 README/Setup-Abschnitt um den Mac-Pfad ergänzen (MLX-Modellbezug, dass `uv sync` plattformabhängig auflöst); verifizieren, dass die dokumentierten Befehle wörtlich laufen.

## 2. Registry: Gerät und Backend

- [x] 2.1 `ModelSpec.device` um die Werte `mlx` (und `mps`) erweitern und einen `backend`-Parameter (`cuda`|`mlx`) mit plattformabhängigem Default in `default_specs()` einführen; verifizieren über neuen Unit-Test, der auf simuliertem Darwin `mlx` und sonst `cuda` als Default liefert.
- [x] 2.2 `backend` und `device` je Baustein sowie `budget.total_mb`/`reserve_mb` über `models.toml` überschreibbar machen (unbekannte Parameter weiter als Fehler); verifizieren über Test „Backend überschrieben" und „Plattformabhängiges Budget".
- [x] 2.3 `uv run python -m docparse.models list` zeigt den Ausführungsort inkl. `mlx` korrekt an; verifizieren durch Ausführung auf dem Mac.

## 3. Speicher-Wächter für Unified Memory

- [x] 3.1 In `lifecycle.check()` die reale Belegungsmessung nur für `device == "gpu"` (CUDA) versuchen und bei `mlx`/fehlender Messung überspringen; verifizieren über Test „Keine dedizierte GPU-Speichermessung" (Laden zugelassen, wenn Budget passt).
- [x] 3.2 `free_gpu_memory()` so anpassen, dass CUDA-Cache-Leerung nur bei aktivem CUDA erfolgt und MLX-Freigabe über Referenzlösen + `gc` läuft; verifizieren über Test „Freigabe eines MLX-Modells" (keine CUDA-Aufrufe erzwungen).
- [x] 3.3 Budgetbasierte Passt-Prüfung unter erhöhtem Unified-Memory-Budget testen (unverträgliche Kombination meldet weiter Summe+Budget); verifizieren über Test „Unverträgliche Kombination" und „Plattformabhängiges Budget".

## 4. MLX-Loader: embedding

- [x] 4.1 `EmbeddingLoader` um einen MLX-Zweig (analog `eep/embed.py`: Text+Bild, 768d, L2-Normierung, bf16/float32, nie float16) erweitern, der je `backend` verzweigt; CUDA-Zweig unverändert. Rückgabe auf das von `search/embed.py` erwartete Format (float32, L2-normiert) bringen; verifizieren, dass `search`-Aufrufer ohne Änderung arbeiten (bestehende search-Tests).
- [x] 4.2 `uv run python -m docparse.models smoke embedding` auf dem Mac: Modell lädt, Mini-Inferenz liefert 768-dim normierte Vektoren, Freigabe sauber; verifizieren über Smoke-Ausgabe (Exit 0, Dim 768).

## 5. MLX-Loader: describe

- [x] 5.1 MLX-fähiges VLM als `describe`-Backend-Variante wählen (MLX-Qwen2.5-VL-Port o. Ä., Modell-ID in Registry), bitsandbytes-Zweig bleibt CUDA-only; `DescribeHandle.describe`/`generate_text`-Schnittstelle unverändert halten. Verifizieren über Unit-Test, dass die Handle-API gleich bleibt (Signatur/Rückgabetyp).
- [x] 5.2 `uv run python -m docparse.models smoke describe` auf dem Mac: Lädt, erzeugt eine kurze Beschreibung zu einem Beispiel-Crop, gibt frei; verifizieren über Smoke-Ausgabe (Exit 0, nicht-leerer Text).
- [x] 5.3 `enrich`-Durchlauf an einem Beispieldokument prüfen, dass Block-Beschreibungen erzeugt werden; verifizieren über vorhandene `enrich`-Ausgabe (`data/results/enrich/<doc>/<page>.json` mit Beschreibungen).

## 6. MLX-VL: Layout + element-weise Recognition

- [x] 6.1 MLX-VL-Recognition-Baustein nach Vorlage `eep/vlm.py` implementieren (ein `recognise(image, prompt)` pro Region, greedy, max_tokens aus Registry); verifizieren über Unit-Test auf einem einzelnen Region-Crop (nicht-leeres Ergebnis).
- [x] 6.2 Label→Prompt-Mapping (analog `eep/config.py`: table/chart/formula/sonst OCR) einführen und `VlLoader`/`run_vl` so verzweigen, dass auf `backend == "mlx"` Layout-Regionen geholt und je Region erkannt werden, dann in das Roh-Dict (`label`, `bbox`, `content`, `polygon_points`) gegossen werden, das `parse/adapters/vl.py::to_blocks` konsumiert (Adapter unverändert); verifizieren über Test „Zusammensetzung aus Layout und Recognition" und „Gleiche Block-Struktur über Backends".
- [x] 6.3 Sicherstellen, dass `fits`/Wächter die Mac-VL-Kombination (Layout + VL) nicht fälschlich verbietet (über Budget/Backend); verifizieren über Test, dass `run --engines vl` auf dem Mac die Modelle laden darf.
- [x] 6.4 Bestehenden VL-Subprozess-/Timeout-Mechanismus (`executors.py`) mit dem MLX-Pfad verifizieren: eine Seite mit Timeout endet als `error`, nächste Seite läuft weiter; verifizieren über vorhandenen executor-Test bzw. erweiterten Test für den MLX-Pfad.

## 7. End-to-End auf dem Mac

- [x] 7.1 `uv run python -m docparse.models smoke` (alle Bausteine) auf dem Mac: jede Zeile `ok`, Exit 0; verifizieren über Smoke-Ausgabe.
- [x] 7.2 An einem EEP-Beispieldokument (z. B. RüKü-Datenblatt, erste Seiten) den vollen Weg `parse --engines pymupdf,layout,ocr,vl` → `enrich` → `search run` → `viewer build` durchlaufen und die Markdown-Rekonstruktion im Viewer gegen das Original sichten; verifizieren über geöffnete `data/viewer/index.html` (Blöcke, Tabelle als Markdown, Bildvorschau vorhanden).
- [x] 7.3 `uv run pytest` auf dem Mac grün (GPU-/MLX-unabhängige Tests) und — sofern verfügbar — auf Linux/CUDA unverändert grün (Regressionssicherung des CUDA-Pfads); verifizieren über beide Testläufe.
