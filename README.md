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
| 6 | `embedding-search` | Embeddings, Index, Volltext- und Vektorsuche |
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
