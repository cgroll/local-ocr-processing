# Proposal

## Why

Alle folgenden Changes (Parsing, Viewer, Embedding) brauchen dieselben fünf Bausteine: PyMuPDF, PP-DocLayoutV3, PP-OCRv6, PaddleOCR-VL-1.6 und EmbeddingGemma 2. Auf der 8-GB-Karte dürfen VL-1.6 (~6 GB) und PP-OCRv6 (~1,5 GB) nicht gleichzeitig geladen sein. Ohne eine zentrale Definition entstehen verstreute Modellnamen, Pins und ad-hoc-Ladecode, der den VRAM sprengt.

## What Changes

- Modell-Registry: eine Stelle, die je Baustein Name, Version/Pin, Aufgabe, VRAM-Bedarf und Standardparameter (etwa Token-Limit und Timeout für VL-1.6) beschreibt.
- Lade-Lebenszyklus: Modelle werden einzeln geladen und wieder freigegeben; ein Wächter verhindert das gleichzeitige Laden unverträglicher Modelle.
- Abhängigkeiten: `paddlepaddle-gpu` (CUDA-12.6-Index) und `paddleocr[doc-parser]>=3.7` sowie der Embedding-Stack kommen in `pyproject.toml`, Pins aus dem Referenzprojekt.
- Smoke-Test-Kommando: lädt jedes Modell nacheinander, führt eine Mini-Inferenz auf einer Beispielseite aus und meldet Ladezeit und VRAM-Spitze.

## Nicht-Ziele

- Kein Parsing ganzer Dokumente und kein Zwischenformat (Change `parse-pipeline`).
- Keine Qualitätsbewertung der Modelle und keine Laufzeit-Benchmarks über den Smoke-Test hinaus.
- Keine Embedding-Berechnung für den Datensatz, kein Index (Change `embedding-search`).
- Keine Cloud-Modelle, kein vLLM-Backend, keine Multi-GPU-Unterstützung.
- Keine Routing-Regeln, welche Engine welchen Blocktyp liefert (Change `configurable-routing`).

## Capabilities

### New Capabilities
- `model-registry`: Maschinenlesbare Beschreibung der fünf Bausteine mit Version, Aufgabe, VRAM-Bedarf und Standardparametern.
- `model-lifecycle`: Laden und Freigeben einzelner Modelle unter VRAM-Beschränkung, einschließlich Smoke-Test.

### Modified Capabilities

## Impact

- Neuer Code unter `src/docparse/models/`, neue Tests unter `tests/`.
- `pyproject.toml` und `uv.lock`: Paddle- und Embedding-Abhängigkeiten, zusätzlicher uv-Index `paddle-cu126` (große Downloads, mehrere GB).
- README: Abschnitt zu Modellen und Smoke-Test.
- Modellgewichte werden beim ersten Lauf in die üblichen Caches geladen, nicht ins Git.
