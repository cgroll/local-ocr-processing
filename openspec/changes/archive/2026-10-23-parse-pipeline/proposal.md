# Proposal

## Why

Der Datensatz (73 Dokumente, 405 Seiten) und die Modelle (Registry, Lade-Wächter) liegen vor, aber noch nichts parst eine Seite in ein Format, das Viewer, Embedding und Suche gemeinsam nutzen können. Jede Engine liefert ihre eigene Struktur (PyMuPDF-Dicts, Paddle-OCR-Zeilen mit Polygonen, Layout-Boxen, VL-Blöcke mit Markdown). Ohne ein gemeinsames Zwischenformat müsste jeder Folgeschritt vier Formate kennen.

## What Changes

- Zwischenformat pro Seite: ein JSON mit Seitenmaße, DPI und einer Liste von Blöcken (Typ, Box in Pixeln des gerenderten Seitenbilds, Text/Markdown/HTML, Quell-Engine, Konfidenz, Reihenfolge).
- Seiten-Rendering: jede Seite wird einmal mit fester DPI als Bild gerendert und abgelegt; alle Engines und alle Koordinaten beziehen sich auf dieses Bild.
- Vier Adapter, die Rohergebnisse in das Format überführen: PyMuPDF (Textblöcke, Bilder, Vektorgrafiken, einfache Tabellen), PP-DocLayoutV3 (typisierte Blöcke), PP-OCRv6 (Zeilen), PaddleOCR-VL-1.6 (Blöcke mit Markdown/HTML).
- Batch-Lauf über das Manifest: Engines nacheinander (jeweils ein Modell geladen), Seiten gemäß `page_range`, wiederholbar und fortsetzbar, Fehler und Timeouts pro Seite statt Abbruch.
- Ablage der Ergebnisse unter `data/results/<engine>/<doc>/<page>.json`, dazu Validierungs- und Zusammenfassungs-Kommando.

## Nicht-Ziele

- Kein HTML-Viewer und keine Rekonstruktion der Seite (Change `visual-inspector`).
- Keine Zusammenführung mehrerer Engines zu einer Seite und keine Routing-Regeln (Change `configurable-routing`); jede Engine schreibt ihr eigenes Ergebnis.
- Keine Zuordnung von OCR-Zeilen zu Layout-Blöcken, keine Wortboxen.
- Keine Embeddings, kein Index (Change `embedding-search`).
- Keine Qualitätsmetriken gegen Ground Truth und keine Tabellenstruktur-Normalisierung über den HTML-String hinaus.
- Kein vLLM-Backend, keine Parallelisierung über mehrere Prozesse.

## Capabilities

### New Capabilities
- `page-format`: Das gemeinsame Seiten-Zwischenformat, das Seiten-Rendering mit fester DPI und die Koordinatenkonvention.
- `engine-adapters`: Überführung der Rohergebnisse von PyMuPDF, Layout, OCR und VL in das Zwischenformat.
- `parse-runner`: Wiederholbarer, fehlertoleranter Batch-Lauf über den Datensatz mit Ablage, Validierung und Zusammenfassung.

### Modified Capabilities

## Impact

- Neuer Code unter `src/docparse/parse/` (Format, Rendering, Adapter, Runner, CLI) und Tests unter `tests/`.
- Nutzt `docparse.models` (ModelManager, Registry) und `docparse.dataset.manifest`; ändert beides nicht.
- Neue Verzeichnisse `data/pages/` (gerenderte Bilder) und `data/results/` (nicht im Git).
- Laufzeit eines Vollaufs: VL-1.6 dominiert (bis 270 s pro Seite im Worst Case, Median ca. 30 s), etwa 400 Seiten.
