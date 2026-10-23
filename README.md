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
| 2 | `define-models` | Modell-Registry für PyMuPDF, Layout, PP-OCRv6, VL-1.6, EmbeddingGemma 2: Versionen, VRAM, Laden/Entladen |
| 3 | `parse-pipeline` | Seitenweise Parsing je Engine in ein einheitliches Zwischenformat, Subset-Lauf |
| 4 | `visual-inspector` | HTML-Viewer: Original mit Layern vs. Rekonstruktion, Engine-Vergleich |
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

## Setup

```bash
uv sync
```

Entwicklungsrechner: RTX 3070 Laptop (8 GB VRAM). VL-1.6 braucht ~6 GB, daneben keine weiteren GPU-Prozesse laufen lassen.

## Struktur (geplant)

```
src/docparse/      Bibliothek (Modelle, Pipeline, Viewer, Suche)
data/              Datensatz + Parse-Ergebnisse (nicht im Git)
openspec/          Specs und Changes
```
