# Local Document Parsing & Semantic Search

Framework, um beliebige Dokumente (PDFs, Scans, technische Unterlagen mit Tabellen und Schaltplänen) **lokal** zu parsen, das Ergebnis **visuell zu prüfen** und anschließend **semantisch durchsuchbar** zu machen. Aufbauend auf `docubotics/local-ocr-test`, aber mit öffentlichen Dokumenten statt eigener Daten.

## Ziel

1. Einen kleinen, heterogenen, öffentlichen Dokumentendatensatz zusammenstellen (auch Datenblätter, Normen, Handbücher mit Schaltplänen und Tabellen).
2. Pro Seite vier Extraktionswege vergleichen:
   | Baustein | Rolle | Wann stark |
   |---|---|---|
   | **PyMuPDF** | nativer Textlayer, Bilder, Vektorgrafiken, einfache Tabellen | digital erzeugte PDFs |
   | **PP-DocLayoutV3** | Layout: Blöcke mit Typ, Box, Lesereihenfolge | immer als Strukturgeber |
   | **PP-OCRv6** | reine Zeilen-OCR (Text + Box, ohne Strukturverständnis) | Scans, schnell, wenig VRAM |
   | **PaddleOCR-VL-1.6** | VLM: Tabellen, Formeln, Diagramme als Markdown/HTML | komplexe Tabellen, Handschrift; langsam |
3. Jede Seite als **HTML nachbauen**: links das Original mit ein-/ausblendbaren Layern (Layout-Boxen, OCR-Zeilen, Tabellen, Bilder), rechts die rekonstruierte Seite (erkannte Inhalte an erkannter Position, Bilder als Ausschnitte eingebunden).
4. Das Parse-Ergebnis **embedden** (Text-Markdown und Seiten-/Bildausschnitte mit EmbeddingGemma 2, ein gemeinsamer 768-dim Raum) und **volltext-/vektorsuchbar** machen.
5. Retrieval prüfen, später RAG mit Fragen-Antwort-Test obendrauf.

Das Ganze soll als konfigurierbare Pipeline in anderen Projekten wiederverwendbar sein.

## Roadmap (OpenSpec-Changes)

| # | Change | Inhalt |
|---|---|---|
| 1 | `select-document-dataset` | Datensatz recherchieren, Subset herunterladen, Manifest mit Quelle/Lizenz/Typ |
| 2 ✓ | `define-models` | Modell-Registry für PyMuPDF, Layout, PP-OCRv6, VL-1.6, EmbeddingGemma 2: Versionen, VRAM, Laden/Entladen |
| 3 ✓ | `parse-pipeline` | Seitenweise Parsing je Engine in ein einheitliches Zwischenformat, Subset-Lauf |
| 4 ✓ | `visual-inspector` | HTML-Viewer: Original mit Layern vs. Rekonstruktion, Engine-Vergleich |
| 5 | `configurable-routing` | Konfigurierbare Regeln, welche Engine welchen Blocktyp liefert (z. B. Tabellen: PyMuPDF vs. VL) |
| 6 ✓ | `embedding-search` | Embeddings, Index, Volltext- und Vektorsuche |
| 7 | `retrieval-eval` | Testfragen, Retrieval-Metriken, optional RAG |

Specs und Changes liegen in `openspec/`. Neue Änderungen mit `/opsx:propose "idee"` anlegen.

## Datensatz

73 öffentliche PDFs, 405 Seiten im Datensatz (je Dokument höchstens `page_range`, Standard 6 Seiten), versioniert als `datasets/manifest.csv`. Die PDFs selbst liegen unter `data/raw/<id>/document.pdf` und sind nicht im Git.

| Gruppe | Dokumente | Quelle | Rechtestatus |
|---|---|---|---|
| `datasheet` | 22 | Datenblätter von TI, Infineon, Microchip, Vishay, Diodes (native PDFs) | `vendor-copyright` |
| `report` | 20 | NASA NTRS (14, meist gescannte Berichte), NIST (6) | `public-domain`, 3× `unknown` |
| `scan` | 11 | Bitsavers: Schaltpläne und Handbücher alter DEC-Rechner (Scans) | `unknown` |
| `corpus-sample` | 20 | Zufallsstichprobe aus GovDocs1 (Zip 001, Seed 1) | `open-license` |

**Rechte:** Der Rechtestatus ist aus den Angaben der Quellen abgeleitet, nicht juristisch geprüft. Dokumente mit `vendor-copyright` oder `unknown` nur lokal verwenden, nicht weitergeben oder veröffentlichen.

```bash
uv run python -m docparse.dataset validate --verified   # Manifest prüfen (inkl. Hash, Seitenzahl, Art)
uv run python -m docparse.dataset summary               # Zahlen je Gruppe, nativ/gescannt, Tag-Abdeckung
uv run python -m docparse.dataset download              # fehlende PDFs laden und prüfen (wiederholbar)
```

Neue Dokumente aufnehmen: erst Kandidaten suchen, dann gezielt übernehmen.

```bash
uv run python -m docparse.dataset candidates ntrs --query "circuit schematic" --tags "schematic;diagram" --limit 10
uv run python -m docparse.dataset candidates nist --query "thermocouple tables" --tags table
uv run python -m docparse.dataset candidates seeds --seed-file datasets/seeds/datasheets.txt
uv run python -m docparse.dataset candidates govdocs --zip 001 --limit 20 --seed 1 --tags plain-text   # lädt ein ~300 MB Zip
uv run python -m docparse.dataset add data/candidates/ntrs.csv ntrs-19760010918 ...                    # nur die genannten IDs
uv run python -m docparse.dataset download
```

Hinweise: Die Tags sind nur für 8 Dokumente von Hand geprüft. `page_range` umfasst bei den meisten Dokumenten die ersten 6 Seiten; bei Berichten und Scans ist das oft nur Vorspann. Bei geprüften Dokumenten ist er von Hand gesetzt (Spalte `notes`). Manche Hersteller (Analog Devices, ST, onsemi) blockieren automatische Downloads, dort PDF von Hand nach `data/raw/<id>/document.pdf` legen, `download` trägt dann Hash und Seitenzahl ein. Tests: `uv run pytest`.

## Modelle

Die Registry (`src/docparse/models/registry.py`, Überschreibungen in `models.toml`) führt die fünf Bausteine mit Version, Gerät und VRAM-Bedarf. Modelle werden einzeln über den `ModelManager` geladen und wieder freigegeben; ein Wächter verweigert Kombinationen, die nicht ins Budget (8192 MB abzüglich 512 MB Reserve) oder in den real freien GPU-Speicher passen.

| Schlüssel | Modell | VRAM-Spitze (gemessen) | Laden / Inferenz |
|---|---|---|---|
| `pymupdf` | PyMuPDF | 0 MB (CPU) | – |
| `layout` | PP-DocLayoutV3 | ~770 MB | 1–9 s / 0,8 s |
| `ocr` | PP-OCRv6 (de) | ~1,4 GB | 2 s / 1,1 s |
| `vl` | PaddleOCR-VL-1.6 (Vision-Encoder in bf16) | ~4,9 GB | 8–17 s / 4–40 s |
| `embedding` | `google/embeddinggemma-2` (ohne Audio-Encoder, bf16) | ~0,9 GB | 6,5 s / 0,5 s |

Messung mit einer Mini-Inferenz auf einer Seite; bei VL-1.6 wächst der Bedarf mit der Länge der Generierung. Mit fp32-Vision-Encoder (Paddle-Standard) lag die Spitze bei ~7,3 GB, und lange Generierungen liefen auf dichten Tabellenseiten in Speicherdruck (Minuten pro Seite oder Speicherfehler); `vision_bf16` behebt das (dichte Tabellenseite: 38 s statt über 10 min). Deshalb sind `max_new_tokens` (2048) und `timeout_s` (180) in der Registry gesetzt. VL-1.6 läuft im Smoke-Test in einem Kindprozess, damit ein hängender Lauf hart beendet werden kann. Nach der Freigabe bleiben höchstens ~200 MB (CUDA-Kontext) belegt.

```bash
uv run python -m docparse.models list              # Registry anzeigen
uv run python -m docparse.models check vl ocr      # passt die Kombination ins Budget? (Exit 1 = nein)
uv run python -m docparse.models smoke             # alle Modelle nacheinander laden, Mini-Inferenz, Zeiten und VRAM
uv run python -m docparse.models smoke ocr layout  # nur ausgewählte
```

Beim ersten Lauf werden Gewichte geladen (Paddle nach `~/.paddlex`, EmbeddingGemma nach `~/.cache/huggingface`); `uv sync` lädt zudem mehrere GB CUDA-Wheels. Beides liegt nicht im Git.

## Parsing

`docparse.parse` schreibt pro Engine und Seite ein JSON in das gemeinsame Zwischenformat: `data/results/<engine>/<doc>/<page>.json` (Seitenzahl vierstellig, 1-basiert). Das Seitenbild liegt einmal mit 150 DPI unter `data/pages/<doc>/<page>.png`; **alle Koordinaten sind Pixel in diesem Bild** (Ursprung links oben). Ein Block hat `type` (`text`, `title`, `header`, `footer`, `table`, `figure`, `formula`, `chart`, `list`, `caption`, `line`, `image`, `drawing`, `other`), `label` (Original der Engine), `bbox`, `polygon`, `text`/`markdown`/`html`, `engine`, `confidence` (null, wenn die Engine keine liefert) und `order`.

| Engine | liefert | Median pro Seite (405 Seiten) |
|---|---|---|
| `pymupdf` | Textblöcke, Bilder, gruppierte Vektorgrafiken, einfache Tabellen (HTML), keine Konfidenz | 0,3 s |
| `layout` | typisierte Blöcke (PP-DocLayoutV3) mit Konfidenz, ohne Text | 0,1 s |
| `ocr` | Textzeilen mit Polygon und Konfidenz (PP-OCRv6) | 0,9 s |
| `vl` | typisierte Blöcke mit Markdown, Tabellen als HTML (PaddleOCR-VL-1.6) | 9,5 s (30 Seiten) |

```bash
uv run python -m docparse.parse run --engines pymupdf,layout,ocr   # alle Seiten laut Manifest, fortsetzbar
uv run python -m docparse.parse run --engines vl --docs ds-lm317   # nur ein Dokument
uv run python -m docparse.parse run --engines vl --limit 20        # höchstens 20 Seiten
uv run python -m docparse.parse validate                           # Format und Boxen prüfen
uv run python -m docparse.parse summary                            # Seiten, Fehler, Laufzeiten, Blockzahlen je Engine
```

Engines laufen nacheinander, jeweils mit einem geladenen Modell. Vorhandene `ok`-Ergebnisse werden übersprungen, Seiten mit Status `error` beim nächsten Lauf erneut versucht (`--force` rechnet alles neu). VL läuft in einem eigenen Prozess: überschreitet eine Seite `timeout_s` (180 s), wird der Prozess beendet, die Seite als Fehler gespeichert und mit einem frischen Prozess weitergemacht. Das passiert selten und ist meist nicht reproduzierbar (zwei Seiten im Teillauf liefen beim zweiten Versuch in 9 s und 17 s durch).

**Stand:** `pymupdf`, `layout` und `ocr` liegen für alle 405 Seiten vor (0 Fehler, `validate` ohne Beanstandung). `vl` liegt für 30 Seiten aus 5 Dokumenten vor (LM317, NE555, ein Bitsavers-Scan, ein NASA-Bericht, eine GovDocs-Datei). Der Rest läuft mit `uv run python -m docparse.parse run --engines vl` und dauert grob 1,5 bis 3 Stunden (375 Seiten, Median ~10 s plus gelegentliche Timeouts).

**Bewusste Entscheidungen:** Orientierungskorrektur und Entzerrung sind für OCR und VL aus, damit die Boxen zum Seitenbild passen; gedrehte Scans bleiben gedreht. pymupdf-Boxen werden auf die Seite beschnitten, Blöcke ganz außerhalb entfallen. Die Engines werden nicht zusammengeführt (Change `configurable-routing`), und OCR-Zeilen sind nicht den Layout-Blöcken zugeordnet.

## Viewer

`docparse.viewer` erzeugt aus Manifest, Seitenbildern und Ergebnissen eine statische Seite unter `data/viewer/` (nicht im Git, kein Server nötig, keine externen Ressourcen). Die Seitenbilder werden aus `data/pages/` verlinkt, der Ordner muss also neben `data/viewer/` liegen.

```bash
uv run python -m docparse.viewer build                     # alle Dokumente mit mindestens einem Ergebnis
uv run python -m docparse.viewer build --docs ds-lm317     # nur ausgewählte Dokumente
```

Das Kommando nennt den Pfad der `index.html`. Direkt aus dem Dateisystem öffnen oder lokal ausliefern (`python -m http.server` im Ordner `data/`).

**Bedienung:**
- *Index:* Abdeckung je Engine (ok / Fehler / fehlend), Filter nach Gruppe, Tag und Freitext.
- *Seite, links:* Original mit Ebenen je Engine (beim Öffnen alle aus), je Ebene ein Typfilter. Beschriftung der Boxen: Typ und Konfidenz.
- *Seite, rechts:* Rekonstruktion aus einer wählbaren Engine (Text an der Boxposition, Tabellen als Tabelle, Bilder als Ausschnitt, Formeln als Quelltext, leere Blöcke als beschriftete Box). „Engines vergleichen" zeigt stattdessen zwei Rekonstruktionen im gleichen Maßstab.
- *Block anklicken:* hebt ihn in beiden Ansichten hervor, rechts erscheinen alle Felder. Escape oder Klick ins Leere hebt die Auswahl auf.
- *Navigation:* Pfeiltasten blättern (am Dokumentende ins nächste Dokument), Seitenwahl in der Leiste. Die Wahl von Engine und Vergleichsmodus bleibt im Browser (`localStorage`) erhalten.

**Ebenenfarben:** `pymupdf` grün, `layout` blau, `ocr` rot, `vl` violett.

**Sicherheit:** Text wird nur als Text eingesetzt, Tabellen-HTML läuft im Generator durch eine Erlaubnisliste (`table`, `tr`, `td`, ... mit numerischem `rowspan`/`colspan`), und jede Seite trägt eine Content-Security-Policy ohne fremde Hosts und ohne Inline-Skripte.

**Beobachtungen aus der Sichtprüfung** (je eine Seite pro Gruppe, nur wo VL vorliegt):

| Gruppe | Seite | Beobachtung |
|---|---|---|
| Datenblatt | `ds-lm317` S. 4 (Vergleichstabelle) | VL und OCR treffen die Struktur. VL liefert die Tabelle zusammenhängend mit `rowspan`, aber mit wörtlichen `\n` in Zellen (`LM317\n(Legacy Chip)`) und LaTeX-Resten (`$ T_{JA} $`). OCR liefert nur Zeilen, einzelne Zellen sind verstümmelt (etwa `nput vnge`). |
| Datenblatt | `ds-lm317` S. 2 | Alle vier Engines decken sich in Text und Position. Layout trennt Logo und Kopfzeile sauber. |
| Bericht (Scan) | `ntrs-19760010918` S. 10 | VL rekonstruiert die Tabelle sauber. PyMuPDF liefert hier nur Text, die Zeilenstruktur der Tabelle fehlt, und Scanrauschen bleibt sichtbar. |
| Scan (Bitsavers) | `bs-dec-08-…` S. 4 | VL erkennt beide Spalten als Tabellen (28 und 22 Zeilen). PyMuPDF liefert nur einen Bildblock (die ganze Seite). Die Seite ist 2600 px breit, der Viewer skaliert sie. |
| GovDocs | `gd1-001028` S. 1 | Titelseite mit Foto: VL und PyMuPDF zeigen Foto als Ausschnitt, Text an passender Stelle. |

Die Zahl der Beobachtungen ist klein (vier Seiten, VL liegt nur für 30 Seiten vor). Aussagen über die Güte der Engines oder Routing-Regeln folgen aus dem Change `configurable-routing`, nicht aus diesen Notizen.

## Suche

Zwei Stufen, beide über das bestehende Zwischenformat (`data/results/{pymupdf,layout,ocr,vl}/`), ohne eine der vier Engines zu ändern:

1. **`docparse.enrich`** wählt je Seite eine Textquelle (`pymupdf`, bei reinen Scans ohne Textlayer Fallback auf `ocr`; `vl`s HTML für Table-Blöcke, wo es vorliegt, weil es die Zeilenstruktur zuverlässiger erhält als `pymupdf`), setzt den Fließtext in **spaltenbewusster Lesereihenfolge** zusammen (linke Spalte komplett vor der nächsten, statt der von `ocr`/`pymupdf` gelieferten reinen Y-Position-Reihenfolge, die bei mehrspaltigen Seiten Wortsalat erzeugt -- betraf 16 Seiten in 11 Dokumenten, überwiegend gescannte, zweispaltige Handbücher/Paper; ein strenger Filter verhindert Fehlalarme bei Schaltplänen mit verstreuten Bauteillabels), croppt Figure-/Chart-/Table-Regionen aus den `layout`-Boxen als Bildausschnitt (Dekorations-Icons unter 10.000 px² werden herausgefiltert) und lässt ein lokales VLM (`describe`, Qwen2.5-VL-3B-Instruct) pro Crop eine kurze, bewusst themenbezogene Beschreibung schreiben -- nie konkrete Werte, siehe `experiments/multimodal-repr-test/`. Ablage unter `data/results/enrich/<doc>/<page>.json` plus die Crop-PNGs daneben.
2. **`docparse.search`** embeddet Seiten-Text, Seiten-Bild und je angereichertem Block Bild/Beschreibung/Inhalt mit `embedding` (EmbeddingGemma 2, gemeinsamer 768-dim Raum für Text und Bild) und baut einen SQLite-FTS5-Volltextindex über denselben Textkorpus. `query` liefert zu einer Text-Query Volltext- und Vektor-Treffer nebeneinander, je mit Herkunft markiert -- keine Fusion zu einem Ranking, das ist Aufgabe von `retrieval-eval`.
3. **`docparse.digest`** setzt zusätzlich eine Markdown-Datei je **Dokument** zusammen (`data/results/digest/<doc>.md`, alle Seiten in einer Datei, Seitenwechsel als `## Seite N`) -- rein mechanisch aus den Ergebnissen von oben, ohne neuen Modell-Lauf. Fließtext bekommt echte Überschriften (Blocktyp → Markdown-Formatierung statt flachem Text), Tabellen werden aus dem HTML in Markdown-Tabellen umgewandelt (mit Pflicht-Hinweis, dass die Zeilenzuordnung unverifiziert ist), und zu jedem Figure-/Chart-/Table-Block kommt zusätzlich eine Liste aller `pymupdf`-/`ocr`-Textfragmente, deren Box sich mit dem Block überlappt -- macht z. B. bei Schaltplänen Bauteillabels wie "VOS" oder "22 µF" sichtbar, die sonst in keiner Tabelle stehen.
4. **Dokument-Ebene für die Suche:** aus dem fertigen Digest lässt `describe` (wiederverwendet als reines Textmodell) einen kurzen Titel + 3-5-Satz-Summary erzeugen (`data/results/digest/<doc>.summary.json`, getrennt von der deterministischen `.md`), und daraus zwei zusätzliche Embeddings je Dokument (`document_summary`, `document_fulltext`, Sentinel `page=0` statt echter Seitenzahl) im selben Index. `document_fulltext` wird vor dem Embedden hart auf 20.000 Zeichen gekappt -- EmbeddingGemma 2 begrenzt die Eingabelänge nicht selbst und crasht bei den längsten Digests (~40.000 Zeichen) sonst mit einem CUDA-Out-of-Memory auf der 8-GB-Karte (empirisch eingekreist: ~19.800 Tokens laufen noch, ~21.300 Tokens crashen).
5. **Cloud-Summary (Vergleichsdaten, additiv):** aus demselben Digest-Text erzeugt zusätzlich ein Cloud-Flaggschiffmodell (Gemini 4 Argon, über Vertex AI) eine zweite Titel+Summary (`data/results/digest/<doc>.cloud_summary.json`, `src/docparse/digest/cloud_summary.py`), daraus ein drittes Dokument-Embedding (`document_summary_cloud`, ebenfalls `page=0`-Sentinel). Das ist **reine Vergleichsdatenbasis für `retrieval-eval`** (Roadmap #7, noch nicht umgesetzt) -- die Standard-Suche (`docparse.search query`) nutzt weiterhin ausschließlich die lokalen Embeddings, keine Verhaltensänderung. Siehe `openspec/changes/cloud-document-summary/`.

```bash
uv run python -m docparse.enrich run                              # alle Seiten laut Manifest, fortsetzbar
uv run python -m docparse.enrich run --docs ds-lm317 --force       # ein Dokument neu anreichern
uv run python -m docparse.digest run                                # ein Markdown-Digest je Dokument, kein GPU nötig
uv run python -m docparse.digest cloud-summary                      # Cloud-Vergleichs-Summary je Dokument (kostenpflichtig, siehe unten)
uv run python -m docparse.search run                               # Seiten- + Dokument-Embeddings (lokal + Cloud), inkrementell
uv run python -m docparse.search query "PSRR" --top-k 5             # Volltext- und Vektor-Treffer
uv run python -m docparse.search query "..." --fulltext-only        # ohne GPU/Embedding-Modell
```

**Digest-Stand:** 73/73 Dokumente, 0 Fehler. Stichprobe von Hand gesichtet (`ds-lm317`, `ds-tps62130`, `bs-dec-08-hrka-d-rk8-schem-dec70`): Überschriften, Tabellen und Beschreibungen passend; bei `ds-tps62130`s Schaltplan-Abbildung tauchen in der Rohtext-Liste u. a. "VOS", "100 kΩ", "22 µF" auf -- Werte, die sonst in keinem Block strukturiert vorliegen.

**Titel/Summary-Stand, ehrlich:** 73/73 Dokumente verarbeitet, **15 von 73 (~21%) liefern degenerierten Output** (leere Antwort, eine Wortwiederholungsschleife wie "Title Title Title..." x180, zeichenweise Wiederholung wie bei einer LaTeX-Tabellen-Halluzination, das Modell echot das Prompt-Trennzeichen zurück, oder -- subtiler -- es schreibt nur den unausgefüllten Platzhalter seines eigenen Formats zurück, z. B. `<paragraph>` statt echtem Text) -- erkannt und als `status: "degenerate"` markiert statt stillschweigend als Text embedded (siehe `src/docparse/digest/summary.py:is_degenerate`). Die Platzhalter-Variante wurde erst in einer zweiten Prüfungsrunde gefunden: zwei Fälle, die zunächst als "ok" durchgingen, bestanden nur aus dem Wort `<paragraph>`; bei drei weiteren Fällen war das Problem rein kosmetisch (echter, brauchbarer Text, nur mit Platzhalter-Tags wie `<abstract>` oder `<ref lang="en">` verunreinigt) -- der Parser bereinigt solche Tags jetzt generell, statt nur `<title>`/`<summary>` zu kennen. Betroffene Dokumente bekommen **kein** `document_summary`-Embedding (58 statt 73), aber weiterhin ein `document_fulltext`-Embedding (unbeeinflusst, da rein mechanisch aus dem Digest gekappt, keine Modell-Generierung). Ein Versuch mit stärkerer `repetition_penalty` behob einen beobachteten Fall, verschlechterte einen anderen aber zu kohärent wirkendem, aber unsinnigem mehrsprachigem Text -- keine saubere Parameter-Lösung gefunden, deshalb Erkennung statt Vermeidung. Der Ursache systematisch nachgegangen: nur 1 der ursprünglich 14 als "kaputt" erkannten Fälle (`bs-f-831f-pdp-8-interface-manual-may65`) hatte eine klar identifizierbare Ursache in der Eingabequalität (die Spalten-Vertauschung, inzwischen behoben) -- stellte sich bei genauerem Hinsehen aber als weiterhin degeneriert heraus (`<paragraph>`-Platzhalter), nur aus einem anderen Grund. Die übrigen Fälle betreffen überwiegend Dokumente mit sauberem, kohärentem Text ohne erkennbares Muster (weder Länge noch Tabellendichte korrelieren zuverlässig) -- das sieht nach einer inhärenten Unzuverlässigkeit des 3B-Modells bei Long-Context-Generierung aus, nicht nach durchgängig schlechtem Input.

Aktueller Gesamt-Index: 2385 Vektoren (405 Seiten-Bild, 399 Seiten-Text, 619 Block-Bild, 618 Block-Beschreibung, 212 Tabellen-Inhalt, 73 Dokument-Volltext, 59 Dokument-Summary).

**Cloud-Summary-Stand, ehrlich:** 73/73 Dokumente verarbeitet, **73/73 `ok`** -- im Gegensatz zu den 15/73 lokalen Totalausfällen (zwei Dokumente brauchten einen zweiten Versuch wegen echter 504-Timeouts der Vertex-API, beide liefen beim erneuten Aufruf durch die bestehende Retry-/Resume-Logik durch). Tatsächliche Gesamtkosten für alle 73 Dokumente: **$1.1969** (Preis Stand 2026-10-25, $2.00/Mtok in, $10.00/Mtok out). Stichprobe von 5 Dokumenten gegen die lokale Variante verglichen (`openspec/changes/cloud-document-summary/review-notes.md`): in allen 5 Fällen mindestens gleichwertig, in 3/5 deutlich besser -- entweder weil die lokale Variante komplett ausfiel (`gd1-001147`, einer der 15 Degenerate-Fälle) oder weil sie bei konkreten technischen Werten vage blieb (`ds-tps5430`: lokal keine einzige Zahl, Cloud nennt 100 mΩ MOSFET, 3 A, 500 kHz, 5.5-36 V; `ds-tlv9062` ähnlich). Kein Fall, in dem die Cloud-Variante schlechter war. Index enthält jetzt zusätzlich 73 `document_summary_cloud`-Vektoren (2457 Vektoren gesamt) -- additiv, die lokalen `document_summary`/`document_fulltext`-Einträge sind unverändert. Die eigentliche Frage, ob das auch zu besserer *Suche* führt, bleibt offen für `retrieval-eval`.

**Stand:** Beide Läufe sind über den gesamten Datensatz durch. Anreicherung: 405/405 Seiten, 0 Seiten-Fehler, 0 Block-Fehler, 619 Crops nach Dekorations-Filter. Index: 2253 Embeddings (405 Seiten-Bild, 399 Seiten-Text -- 6 Seiten ohne jeden extrahierbaren Text --, 619 Block-Bild, 618 Block-Beschreibung, 212 Tabellen-Inhalt).

**Modelle:**

| Schlüssel | Modell | VRAM (gemessen) | Rolle |
|---|---|---|---|
| `describe` | Qwen2.5-VL-3B-Instruct (4-bit bnb) | 3500 MB | Kurzbeschreibungen für Figure/Chart/Table-Crops |
| `embedding` | EmbeddingGemma 2 | ~1100 MB | Text- und Bild-Embeddings im gemeinsamen Raum |

`describe` ist bewusst von `vl` (PaddleOCR-VL) getrennt: `vl` läuft bei manchen Dokumenten (dichte Schaltpläne/Graphen, dichte Zahlentabellen) auf allen Seiten in den 180s-Timeout -- reproduzierbar, nicht nur im informellen Test (`experiments/vlm-qa-test/`). `describe` nutzt die 3B- statt der 7B-Variante: 7B maß in einem Vorab-Experiment ~7,8 GB VRAM, fast das gesamte 8-GB-Budget ohne Marge; 3B maß im eigenen Smoke-Test 3,5 GB bei vergleichbarer QA-Genauigkeit im Vorab-Test.

**Bekannte Einschränkungen:**
- Der Dekorations-Filter (10.000 px² Mindestfläche) ist an einem einzigen beobachteten Fall (vier TI-Marketing-Icons) kalibriert, nicht an einer systematischen Stichprobe über den ganzen Datensatz.
- `pymupdf`s Tabellen-Zeilenstruktur bleibt stellenweise schwach (mehrere Zeilen landen ohne `<tr>`-Trennung in einer Zelle, siehe `experiments/vlm-qa-test/README.md`, Follow-up A) -- für die Volltextsuche unkritisch (ein Begriff muss nur irgendwo auf der Seite stehen), für ein exaktes Auslesen einer bestimmten Zeile aber weiterhin ein offenes Problem.
- Die Volltextsuche verlangt alle Query-Wörter (FTS5 `AND`-Verknüpfung) -- keine Phrasen- oder OR-Suche.
- Vektorsuche liefert immer die nächstgelegenen Treffer, auch zu einer bedeutungslosen Query -- es gibt keine Ähnlichkeits-Schwelle, ab der "kein Treffer" zurückkommt.

**Stichprobe (6 Queries von Hand gegen den Vollindex, Plausibilitäts-Check, keine systematische Messung):**

| Query | Beobachtung |
|---|---|
| `PSRR` | Volltext trifft `ds-lm317` S. 4 (die Tabelle mit dem PSRR-Wert) sofort richtig. Vektor-Treffer sind dagegen schwächer/breiter gestreut (0.73-0.78, NASA-Berichte) -- eine kurze Abkürzung allein ist für die Embedding-Query semantisch arm. |
| `efficiency versus output current` | Trifft sowohl per Volltext als auch per Vektor (0.865) exakt die zwei Effizienz-Graphen (`ds-tps5430`, `ds-tps62130`) -- der Idealfall, den der Multimodal-Spike versprach. |
| `schematic circuit diagram` | Breite, aber plausible Trefferstreuung über mehrere Schaltplan-Figuren verschiedener Dokumente (DEC-Technical-Manual, TPS62130, DRV8825), alle mit konsistent hoher Ähnlichkeit (~0.85). |
| `NE555 timer pin configuration` | Vektor-Treffer sind ausschließlich und korrekt `ds-ne555`-Seiten; keine Volltext-Treffer, weil nicht alle Begriffe wörtlich auf einer Seite stehen (FTS5-`AND`). |
| `drainage area gaging station` | **Echter Lückenfall:** Die Phrase steht wörtlich im narrativen Text von `gd1-001147` S. 1, aber dessen Seiten-Text-Embedding liegt in den Top-5 der Vektorsuche nicht vorne (Rang hinter mehreren unrelated Datenblatt-Tabellen). Genau die Art Fehltreffer, die `retrieval-eval` systematisch messen soll. |
| `zzyxqwerty blorple nonsense term` | Keine Volltext-Treffer (korrekt), aber Vektorsuche liefert trotzdem "nächste" Treffer mit moderater Ähnlichkeit (~0.70) -- erwartetes Verhalten einer reinen Nearest-Neighbor-Suche ohne Schwellenwert, kein Bug. |

## Setup

```bash
uv sync
```

Entwicklungsrechner: RTX 3070 Laptop (8 GB VRAM). VL-1.6 braucht ~5 GB, daneben keine weiteren GPU-Prozesse laufen lassen.

## Struktur (geplant)

```
src/docparse/      Bibliothek (Modelle, Pipeline, Viewer, Suche)
data/              Datensatz + Parse-Ergebnisse (nicht im Git)
openspec/          Specs und Changes
```
