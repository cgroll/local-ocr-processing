# Proposal

## Why

Der Datensatz ist vollständig geparst (`pymupdf`, `layout`, `ocr` für alle 405 Seiten; `vl` nur für 30 Seiten aus 5 Dokumenten, siehe unten), aber es gibt keine Suche über die Ergebnisse. Zwei informelle Spikes (`experiments/vlm-qa-test/`, `experiments/multimodal-repr-test/`) haben vorab geklärt, was überhaupt funktioniert, bevor dafür echter Produktionscode entsteht: lokale VLMs lesen dichte Tabellen/Graphen aus Pixeln unzuverlässig, aber eine reichere Repräsentation (Text, Bild-Crop, kurze themenbezogene VLM-Beschreibung) landet in EmbeddingGemma 2s gemeinsamem Raum nachweislich an der richtigen Stelle (9/9 Treffer in Cross-Modal-Sanity-Checks über zwei Testseiten, siehe `experiments/multimodal-repr-test/README.md`). Jetzt soll daraus ein echter, über den ganzen Datensatz laufender Such-Layer werden, auf dem die Retrieval-Qualität gemessen (`retrieval-eval`, Roadmap #7) und später eine agentische Suche aufgebaut werden kann.

## What Changes

- **Seiten-Anreicherung** (`page-enrichment`): je Seite eine primäre Textquelle wählen (`pymupdf`, bei den 64 reinen Scan-Seiten ohne Textlayer Fallback auf `ocr`-Zeilen; `vl`-Ergebnis übernehmen, wo es vorliegt, aber nie Voraussetzung, da `vl` bei manchen Dokumenten reproduzierbar in den 180s-Timeout läuft). Figure-/Chart-/Table-Regionen aus den `layout`-Boxen als Bildausschnitt croppen, kleine Dekorations-Icons/Logos per einfacher Heuristik aussortieren, pro verbliebenem Crop eine kurze, explizit themenbezogene (nicht wertgenaue) VLM-Beschreibung erzeugen.
- **Such-Index** (`search-index`): für jede Seite und jeden angereicherten Block Text-, Bild- und Beschreibungs-Embeddings mit EmbeddingGemma 2 berechnen (Tabellen zusätzlich mit Embedding ihres vollen Inhalts), reproduzierbar ablegen, dazu eine Volltextsuche über denselben Textkorpus. Eine Abfrage-Schnittstelle liefert zu einer Text-Query Treffer aus beiden Signalen.
- **Neuer Modell-Baustein** `describe` in der Registry (ein lokales VLM für kurze Bildbeschreibungen, z. B. Qwen2.5-VL -- 3B oder 7B je nach VRAM-Messung, siehe `design.md`), getrennt von `vl` (PaddleOCR-VL-1.6, strukturierte Markdown/HTML-Extraktion), weil `vl` genau auf den Seiten unzuverlässig ist, die eine Beschreibung am nötigsten hätten (Schaltpläne, dichte Tabellen).
- Batch-Lauf über alle 405 Seiten/73 Dokumente, wiederholbar/fortsetzbar wie der bestehende `parse-runner` (vorhandene Ergebnisse überspringen, Fehler pro Seite statt Abbruch, Fortschritt zusammenfassbar).
- Der bekannte pymupdf-Encoding-Bug (µ wird zu "…", siehe `experiments/vlm-qa-test/README.md`) wird im `pymupdf`-Adapter behoben, weil er die Textgrundlage der Suche direkt verschlechtert und mit vertretbarem Aufwand behebbar ist.
- **Dokument-Digest** (`document-digest`): zusätzlich zur Seiten-Ebene eine einzelne Markdown-Datei je Dokument (`data/results/digest/<doc>.md`), rein mechanisch aus bereits vorhandenen Daten zusammengesetzt (kein neuer Modell-Lauf). Fließtext mit echten Markdown-Überschriften (Blocktyp → Formatierung, statt dem flachen `narrative_text`-String), Tabellen als Markdown-Tabelle (konvertiert aus dem vorhandenen HTML) mit Pflicht-Hinweis auf unverifizierte Zeilenstruktur, vorhandene VLM-Beschreibungen je Figure/Chart/Table, und zusätzlich je visuellem Block eine Liste der `pymupdf`-/`ocr`-Textfragmente, deren Box sich mit der Blockbox überlappt -- klar als unverifizierte Rohdaten gekennzeichnet (macht z. B. Schaltplan-Bauteillabels wie "VOS", "22 µF" sichtbar, die sonst in keiner Tabelle auftauchen).
- **Titel + Summary je Dokument** (Ergänzung zu `document-digest`): aus dem fertigen Markdown-Digest lässt `describe` (wiederverwendet als reines Textmodell) einen kurzen Titel plus 3-5-Satz-Summary erzeugen, separat abgelegt (`data/results/digest/<doc>.summary.json`), ohne die deterministische `<doc>.md` selbst zu verändern. Empirischer Fund aus einem Vorab-Test (`experiments/digest-summary-test/`): bei langen Dokumenten muss die Anweisung NACH dem Inhalt stehen, sonst verliert das 3B-Modell sie durch einen Rezenz-Effekt.
- **Dokument-Level-Embeddings** (Ergänzung zu `search-index`, das bisher nur Seiten-Embeddings kennt): zwei neue Embedding-Arten im bestehenden Index, mit `page=0` als Sentinel für "nicht seitengebunden" -- `document_summary` (Titel+Summary, das De-facto-Embedding für das ganze Dokument) und `document_fulltext` (der volle Digest-Text, hart auf 20.000 Zeichen gekappt). Die Kappung ist nötig, nicht optional: EmbeddingGemma 2 begrenzt die Eingabelänge nicht selbst und führt bei den längsten Digests (bis zu ~40.000 Zeichen / ~28.000 Tokens) auf der 8-GB-Karte zu einem CUDA-Out-of-Memory -- empirisch eingekreist auf einen scharfen Cliff zwischen ~19.800 und ~21.300 Tokens.

## Nicht-Ziele

- Kein generisches Engine-Routing-Framework (`configurable-routing`, Roadmap #5, eigener Change). Die Textquellen-Wahl hier ist eine enge, fest verdrahtete Regel nur für den Such-Index ("pymupdf, Fallback ocr, vl wenn vorhanden"), keine konfigurierbaren Pro-Blocktyp-Regeln.
- Keine Messung oder Optimierung der Retrieval-Qualität (Trefferquote, Ranking-Tuning) -- das ist `retrieval-eval` (Roadmap #7). Dieser Change liefert die Such-Schnittstelle, nicht den Beweis, dass sie gut genug ist.
- Kein agentischer Such-/RAG-Layer und keine Cloud-Modelle in der Produktionspipeline. Gemini blieb ein Experiment-Werkzeug (`experiments/vlm-qa-test/`) zur Fehleranalyse, nicht Teil dieses Changes -- alles hier läuft lokal.
- Keine echte Vektor-Datenbank; bei 405 Seiten reicht ein flaches Array plus Metadaten-JSON.
- Keine Behebung der pymupdf-Tabellenzeilen-Zusammenquetschung (mehrere Zeilen landen ohne `<tr>`-Trennung in einer `<td>`, siehe `experiments/vlm-qa-test/README.md` Follow-up A). Das ist ein größerer Umbau des `pymupdf`-Tabellen-Adapters und wird nur dokumentiert, nicht hier gefixt.
- Keine ML-gestützte Dekorations-Icon-Erkennung; nur eine einfache geometrische/positionelle Heuristik (siehe `design.md`).
- Keine Zuordnung von OCR-Zeilen zu Layout-Blöcken (unverändert aus `parse-pipeline`).
- Der Dokument-Digest ist kein neues Such-Signal und wird (jedenfalls in diesem Change) nicht embedded oder indiziert -- er ist ein zusätzliches, rein textuelles Lese-Artefakt für Menschen oder einen nachgelagerten Agenten, der ein ganzes Dokument statt einzelner Seiten lesen will. Die Such-Ebene bleibt wie entschieden pro Seite.
- Keine LLM-generierte Zusammenfassung auf Dokumentebene (das war das separate Spike-Experiment `experiments/vlm-qa-test/run_summary_keywords.py` mit eigenen bekannten Risiken -- Wiederholungsschleifen bei wenig Input, stille Unvollständigkeit bei fehlenden Seiten). Der Digest generiert nichts neu, er setzt nur bereits vorhandene Bausteine (Text, Beschreibungen, Crops) mechanisch zusammen.
- Die HTML→Markdown-Tabellenkonvertierung behebt nicht die bekannte Zeilenstruktur-Schwäche von `pymupdf` (s. o.) -- sie stellt dieselbe Struktur nur in anderer Syntax dar, mit explizitem Hinweis auf die Unsicherheit.
- Keine Keyword-Liste neben Titel/Summary -- das war genau der Teil, der im früheren Summary-Keyword-Spike (`experiments/vlm-qa-test/run_summary_keywords.py`) in Wiederholungsschleifen kippte; hier bewusst weggelassen.
- Keine Lösung des grundsätzlichen Longcontext-Speicherproblems (z. B. Chunking mit anschließender Mittelung der Teil-Embeddings) -- nur eine harte, konservative Zeichengrenze mit dokumentierter Einschränkung für die längsten Dokumente.
- Keine Änderung der bestehenden Seiten-Embeddings oder der deterministischen Digest-Erzeugung selbst.

## Capabilities

### New Capabilities
- `page-enrichment`: Textquellen-Wahl je Seite (pymupdf/ocr-Fallback/optional vl), Bild-Crops für Figure/Chart/Table aus den Layout-Boxen, Dekorations-Filter, kurze themenbezogene VLM-Beschreibungen pro Crop.
- `search-index`: Multimodale Embeddings (Text/Bild/Beschreibung/Tabelleninhalt) mit EmbeddingGemma 2, Volltextindex über denselben Textkorpus, reproduzierbare Ablage, Abfrage-Schnittstelle für Text-Queries.
- `document-digest`: Eine Markdown-Datei je Dokument, mechanisch aus den Engine- und Anreicherungs-Ergebnissen zusammengesetzt -- Überschriften aus Blocktypen, Tabellen als Markdown mit Unverified-Hinweis, VLM-Beschreibungen, und Bbox-Overlap-Rohtextlisten für Figure/Chart/Table-Blöcke.

### Modified Capabilities
- `model-registry`: ein sechster Baustein `describe` (lokales VLM für Bildbeschreibungen) kommt zur bisher auf fünf Bausteine festgelegten Liste hinzu.

## Impact

- Neuer Code unter `src/docparse/enrich/` (Crops, Filter, Beschreibungen), `src/docparse/search/` (Embeddings, Volltextindex, Abfrage) und `src/docparse/digest/` (Markdown-Zusammensetzung je Dokument), nutzt `docparse.models` (Registry/ModelManager) und liest `data/results/{pymupdf,layout,ocr,vl,enrich}/...`, ändert diese nicht.
- Erweitert `src/docparse/models/registry.py` und `loaders.py` um den `describe`-Baustein; Smoke-Test deckt ihn automatisch mit ab (generische Anforderung in `model-lifecycle`, keine Änderung dort nötig).
- Fix im `pymupdf`-Adapter (`src/docparse/parse/` o. ä.) für das Unicode-Mangling; bestehende `pymupdf`-Ergebnisse müssen für betroffene Seiten neu berechnet werden (`--force`).
- Neue Verzeichnisse unter `data/results/` (Crops, Beschreibungen, Embeddings, Volltextindex, Dokument-Digests) -- nicht im Git, wie der Rest von `data/`.
- Laufzeit: VLM-Beschreibungen für geschätzt ein paar hundert Figure-/Chart-/Table-Blöcke über alle 405 Seiten (261 Tabellen + 61 Charts + Teilmenge der 346 Figures laut `layout`-Zusammenfassung, abzüglich Dekoration), bei ca. 0,5-2s je Crop im einstelligen Minutenbereich; Embedding-Berechnung ähnlich günstig (EmbeddingGemma 2 ist bereits im Smoke-Test mit ~0,5s/Seite vermessen). Der Dokument-Digest braucht keinen Modell-Lauf (reines Zusammensetzen), Laufzeit über alle 73 Dokumente im Sekundenbereich.
