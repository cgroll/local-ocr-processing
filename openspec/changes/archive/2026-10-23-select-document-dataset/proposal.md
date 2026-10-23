# Proposal

## Why

Das Projekt soll Parsing und semantische Suche auf allgemeinen Dokumenten aus dem Internet erproben, nicht auf eigenen Daten. Dafür fehlt ein kleiner, heterogener, öffentlicher Dokumentensatz, der auch technische Unterlagen mit Schaltplänen, Tabellen und Scans enthält. Ohne ihn lassen sich weder die Pipeline noch der Viewer sinnvoll prüfen.

## What Changes

- Ein **Manifest** (eine Zeile pro Dokument) beschreibt den Datensatz: Quelle (URL), Lizenz bzw. Rechtestatus, Gruppe, Typ-Tags, nativ vs. gescannt, Seitenzahl, SHA256.
- Ein **Download-Skript** arbeitet das Manifest ab, lädt jedes PDF in ein eigenes Verzeichnis unter `data/`, prüft Hash und Seitenzahl und ist wiederholbar.
- Ein **Kuratierungs-Skript** hilft, Kandidaten aus den Quellen zu ziehen und ins Manifest zu übernehmen.
- Der Datensatz umfasst ca. 60–100 PDFs (ca. 300–500 Seiten) in vier Gruppen:
  - ca. 20 native Hersteller-Datenblätter (TI, Analog Devices, STMicro, Infineon)
  - ca. 20 NASA-NTRS- und NIST-Berichte, teils gescannt
  - ca. 10 Bitsavers-Scans mit Schaltplänen (alte Handbücher)
  - ca. 20 Zufallsstichprobe aus GovDocs1/SafeDocs als Ausreißer
- Rohdaten bleiben außerhalb von Git; nur das Manifest wird versioniert.

**Nicht-Ziele:** Parsing, Modelle, Ground Truth/Labels, Viewer, Embeddings. Keine Weitergabe oder Veröffentlichung der heruntergeladenen Dokumente.

## Capabilities

### New Capabilities
- `dataset-manifest`: Struktur, Pflichtfelder und Zusammensetzung des versionierten Dokumentenmanifests.
- `dataset-acquisition`: Reproduzierbares, sicheres Herunterladen und Verifizieren der Dokumente laut Manifest.

### Modified Capabilities

## Impact

- Neu: `data/` (ignoriert), `datasets/manifest.csv` bzw. Ähnliches, Skripte unter `src/docparse/dataset/`.
- Abhängigkeiten: `pymupdf` (schon vorhanden), `httpx` oder `requests` für Downloads.
- Netzwerkzugriff auf NASA NTRS, NIST, Hersteller-Server, Bitsavers, Digital Corpora.
- Alle späteren Changes (`parse-pipeline`, `visual-inspector`, ...) nutzen dieses Manifest als Eingabe.
