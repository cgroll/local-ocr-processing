# Tasks

## 1. Abhängigkeiten und Klärung

- [ ] 1.1 Hugging-Face-ID und Zugriffsbedingungen von EmbeddingGemma 2 prüfen und in `models.toml` festhalten. Ergebnis: ID und Login-Bedarf sind dokumentiert.
- [ ] 1.2 Prüfen, ob PP-DocLayoutV3 einzeln ladbar ist (Paddle-API). Ergebnis: Ladeweg für `layout` ist festgelegt und im Design vermerkt.
- [ ] 1.3 `paddlepaddle-gpu==3.3.1` (Index `paddle-cu126`), `paddleocr[doc-parser]>=3.7` und `sentence-transformers` in `pyproject.toml` eintragen, `uv sync` ausführen. Ergebnis: `uv run python -c "import paddle; print(paddle.device.is_compiled_with_cuda())"` meldet `True`.

## 2. Registry

- [ ] 2.1 `src/docparse/models/registry.py` mit `ModelSpec` und den fünf Einträgen anlegen. Ergebnis: Test prüft Pflichtfelder und 0 MB für PyMuPDF.
- [ ] 2.2 Standardparameter für `vl` (Token-Limit, Timeout, `markdown_ignore_labels=[]`) ergänzen. Ergebnis: Test liest die Werte.
- [ ] 2.3 `models.toml`-Override mit Validierung unbekannter Parameter implementieren. Ergebnis: Tests für Überschreibung und Tippfehler.
- [ ] 2.4 Budget-Rechnung (`fits(keys)`) mit Summe und Reserve. Ergebnis: Test `vl`+`ocr` passt nicht, `ocr`+`layout` passt.

## 3. Lebenszyklus

- [ ] 3.1 `ModelHandle`-Schnittstelle mit `load`, `unload`, Kontextmanager und Wiederverwendung. Ergebnis: Test mit Fake-Loader, inkl. Freigabe bei Ausnahme.
- [ ] 3.2 VRAM-Wächter mit Registry-Summe und Abfrage des freien GPU-Speichers. Ergebnis: Tests mit gemockter GPU-Abfrage für beide Szenarien.
- [ ] 3.3 Loader für `pymupdf` und `ocr` (PP-OCRv6, `lang="de"`). Ergebnis: Mini-Inferenz auf einer Beispielseite liefert Text.
- [ ] 3.4 Loader für `layout` und `vl` (mit Token-Limit, Kindprozess und Timeout). Ergebnis: Mini-Inferenz liefert Blöcke bzw. Markdown, Timeout-Test bricht ab.
- [ ] 3.5 Loader für `embedding`. Ergebnis: Mini-Inferenz liefert einen 768-dim Vektor.

## 4. Smoke-Test und Doku

- [ ] 4.1 CLI `python -m docparse.models {list,check,smoke}` mit Zeile pro Modell und Exit-Code. Ergebnis: `list` und `check` laufen ohne GPU.
- [ ] 4.2 `smoke` auf der Maschine ausführen, gemessene VRAM-Spitzen in die Registry übernehmen. Ergebnis: alle Bausteine grün oder Fehler begründet; Werte in `registry.py` angepasst.
- [ ] 4.3 Prüfen, dass nach Freigabe der VRAM wieder nahe am Ausgangswert liegt. Ergebnis: Messwert im Smoke-Ausgabeprotokoll.
- [ ] 4.4 README um Abschnitt „Modelle“ mit Befehlen, Download-Hinweis und Messwerten ergänzen. Ergebnis: Abschnitt vorhanden, Roadmap-Zeile 2 abgehakt.
