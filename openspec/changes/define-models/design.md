# Design

## Context

Das Projekt enthält bisher nur die Datensatz-Pipeline (`src/docparse/dataset/`); kein Modell ist eingebunden. `pyproject.toml` kündigt die Modell-Abhängigkeiten für diesen Change an. Vorarbeiten liegen im Referenzprojekt `~/docubotics/local-ocr-test` (`paddlepaddle-gpu==3.3.1` aus dem Index `paddle-cu126`, `paddleocr[doc-parser]`, gemessen: PP-OCRv6 ~1,5 GB, VL-1.6 ~6,2 GB VRAM, VL bis 270 s/Seite). Hardware: RTX 3070 Laptop mit 8 GB.

## Goals / Non-Goals

**Goals:**
- Eine Registry, aus der Pipeline, Viewer und Suche Modellwissen beziehen.
- Sicheres sequenzielles Laden mit Wächter, der vor einem OOM schützt.
- Ein Smoke-Test, der zeigt, dass der Stack auf dieser Maschine läuft.

**Non-Goals:**
- Kein Zwischenformat, keine Dokumentverarbeitung, keine Metriken zur Qualität.
- Kein Modell-Server und kein Caching zwischen Prozessen.

## Decisions

**Registry als Python-Dataclasses plus TOML-Override.** `src/docparse/models/registry.py` enthält unveränderliche `ModelSpec`-Objekte (Schlüssel, Aufgabe, Modellname, Gerät, `vram_mb`, `params`). Überschreibungen kommen aus `models.toml` im Repo-Root (nur `params` und Budget). Alternativen: reine YAML/TOML-Registry (verliert Typprüfung, Defaults müssten doppelt gepflegt werden) oder Pydantic (zusätzliche Abhängigkeit ohne Bedarf).

**VRAM-Zahlen als Schätzung, Wächter prüft zusätzlich real.** `vram_mb` stammt aus den Messungen des Referenzprojekts (ocr 1500, layout ca. 500 vorläufig, vl 6200, embedding vorläufig, im Smoke-Test nachzumessen). Der Wächter vergleicht Summe der geladenen Modelle plus Kandidat mit dem Budget und fragt zusätzlich den freien Speicher der GPU ab (`nvidia-smi` über `pynvml`-freien Aufruf per `subprocess`, damit keine weitere Abhängigkeit nötig ist). Fremde Prozesse wie der TTS-Daemon im Referenzprojekt werden so erkannt.

**Loader pro Baustein, gemeinsame Schnittstelle.** `ModelHandle` mit `load()`, `unload()`, `__enter__/__exit__`; je Baustein ein dünner Loader unter `src/docparse/models/loaders/`. Importe von Paddle und Embedding-Bibliothek passieren erst in `load()`, damit Registry und Tests ohne GPU und ohne installierte Gewichte laufen. Freigeben bedeutet Referenz löschen, `gc.collect()` und `paddle.device.cuda.empty_cache()`; bei Torch-Embeddings entsprechend `torch.cuda.empty_cache()`.

**Embedding-Stack: `sentence-transformers`.** EmbeddingGemma wird in der Regel darüber geladen. Die genaue Hugging-Face-ID für „EmbeddingGemma 2“ ist zum Zeitpunkt des Plans nicht verifiziert und steht deshalb in `models.toml` als Parameter; der erste Schritt der Umsetzung prüft die ID und die Token-Anforderung (Gemma-Lizenz kann Login verlangen). Ist sie nicht erreichbar, bleibt der Eintrag registriert und der Smoke-Test meldet ihn als Fehler, die anderen Modelle sind davon unberührt.

**VL-Begrenzung über Token-Limit und Kindprozess.** Das Token-Limit kommt als Generierungsparameter von PaddleOCR-VL. Als harte Sicherung läuft die Smoke-Inferenz von `vl` in einem Kindprozess, der nach dem Zeitlimit beendet wird; so lässt sich ein hängendes Paddle-Backend sicher abbrechen und der VRAM wird mit dem Prozessende frei. Alternative Thread plus Flag kann die native Generierung nicht unterbrechen.

**Smoke-Test-CLI.** `uv run python -m docparse.models {list,check,smoke}`: `list` zeigt die Registry, `check` die Budget-Rechnung, `smoke` die Mini-Inferenz. Beispielseite: erste Seite eines Dokuments aus `data/raw/` (laut Manifest, über PyMuPDF auf ein Bild gerendert), ersatzweise ein mitgeliefertes kleines Testbild.

**Paddle-Pins aus dem Referenzprojekt.** `paddlepaddle-gpu==3.3.1` aus dem expliziten Index `paddle-cu126`, `paddleocr[doc-parser]>=3.7`. Die Abhängigkeiten kommen in eine Gruppe, die auch ohne GPU installierbar bleibt, wo möglich; wenn nicht trennbar, bleiben sie Hauptabhängigkeiten und Tests ohne GPU laufen trotzdem, weil Importe verzögert sind.

## Risks / Trade-offs

- [VRAM-Schätzungen weichen ab] → Wächter prüft den realen freien Speicher zusätzlich; Smoke-Test misst Spitzen, Registry-Werte werden danach angepasst.
- [Paddle gibt GPU-Speicher nicht vollständig frei] → VL läuft im Smoke-Test im Kindprozess; im Einsatz kann derselbe Mechanismus für späteren Change genutzt werden. `empty_cache` reicht für OCR vermutlich aus, wird im Smoke-Test geprüft.
- [Große Downloads (CUDA-Wheels, Gewichte)] → `uv sync` dauert lange und braucht mehrere GB; Hinweis im README, Gewichte nicht im Git.
- [EmbeddingGemma-ID oder Lizenz-Login nicht verfügbar] → Eintrag konfigurierbar, Fehler isoliert (siehe oben).
- [Versionsdrift bei `paddleocr>=3.7`] → `uv.lock` pinnt die tatsächlich benutzte Version.

## Open Questions

- Exakte Hugging-Face-ID und Zugriffsbedingungen von EmbeddingGemma 2 (im ersten Umsetzungsschritt klären).
- Ob PP-DocLayoutV3 allein ladbar ist oder nur über die VL-Pipeline; falls nur dort, wird `layout` als eigener Eintrag mit Hinweis geführt und über die Layout-Komponente der Pipeline geladen.
