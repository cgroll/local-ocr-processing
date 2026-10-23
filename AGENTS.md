# AGENTS.md

Lokale Dokument-Parsing-Pipeline mit visueller Qualitätskontrolle und semantischer Suche. Überblick und Roadmap: `README.md`.

## Arbeitsweise

- Änderungen laufen über **OpenSpec** (`openspec/`): erst `/opsx:propose`, dann umsetzen, dann archivieren. Kein größeres Feature ohne Change.
- Dokumentation und Specs auf **Deutsch**, Code, Bezeichner und Kommentare auf **Englisch**.
- Python 3.12, Paketverwaltung mit `uv` (`uv sync`, `uv run ...`). Keine globalen Installationen.

## Randbedingungen

- Alles läuft **lokal**; keine Cloud-OCR. Referenzprojekt mit Vorarbeiten: `~/docubotics/local-ocr-test` (Paddle-Setup, Laufzeitmessungen, Stolpersteine in dessen `EVALUATION.md`).
- GPU: RTX 3070 Laptop, **8 GB VRAM**. VL-1.6 (~6 GB) und PP-OCRv6 (~1,5 GB) nicht gleichzeitig laden; EmbeddingGemma separat. Modelle nacheinander laden und freigeben.
- Paddle-Stack: `paddlepaddle-gpu` (CUDA-12.6-Wheels über expliziten Index) plus `paddleocr[doc-parser]>=3.7`. Pins aus dem Referenzprojekt übernehmen.
- VL-1.6: Generierung kann extrem lang laufen (bis 270 s/Seite) und Inhalte weglassen. Immer Token-Limit/Timeout setzen. Kopf-/Fußzeilen mit `markdown_ignore_labels=[]` erhalten.
- Alle Koordinaten im Zwischenformat sind **Pixel im gerenderten Seitenbild** mit festgehaltener DPI/Skalierung; PyMuPDF-Koordinaten (Punkte) beim Import umrechnen.

## Datenregeln

- Heruntergeladene Dokumente sind unvertrauenswürdig: jeweils in eigenes Verzeichnis unter `data/`, nie Skripte dort ausführen, PDFs nur über PyMuPDF/Paddle öffnen.
- Jedes Dokument braucht einen Manifest-Eintrag mit Quelle (URL), Lizenz und Typ-Tag. Nur Dokumente mit Weiterverwendung erlaubender Lizenz committen; Rohdaten gehören nicht ins Git.
- Ergebnisse sind reproduzierbar abgelegt: `data/results/<engine>/<doc>/<page>.json`.

## Konventionen

- Ein gemeinsames Zwischenformat pro Seite (Blöcke mit Typ, Box, Text/Markdown/HTML, Quelle-Engine, Konfidenz), aus dem Viewer, Embedding und Suche gespeist werden. Engines liefern nur Adapter dorthin.
- Visuelle Prüfung (HTML-Viewer) hat Vorrang vor Metriken; Ground-Truth-Metriken sind optional.
- Keine Features über den aktuellen OpenSpec-Change hinaus bauen.
