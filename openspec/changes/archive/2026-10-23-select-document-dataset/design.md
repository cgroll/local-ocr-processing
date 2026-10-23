# Design

## Context

Greenfield: im Projekt gibt es nur Gerüst (`pyproject.toml`, OpenSpec). Motivation und Umfang siehe `proposal.md`. Randbedingungen aus `AGENTS.md`: Rohdaten nicht ins Git, Downloads unvertrauenswürdig, Python 3.12 mit uv. Kein Dokument wird in diesem Change geparst.

## Goals / Non-Goals

**Goals:**
- Ein Manifest, das man von Hand lesen, diffen und mit Pandas laden kann.
- Kuratierung in zwei Schritten: Kandidaten finden, dann bewusst ins Manifest übernehmen.
- Download ist idempotent und prüft jede Datei.

**Non-Goals:**
- Kein Crawler für ganze Quellen, keine Spiegelung der Archive.
- Keine automatische Rechteklärung: der Rechtestatus wird je Quelle vorbelegt und von Hand bestätigt.
- Keine Inhaltsanalyse außer Seitenzahl und Textlayer-Test.

## Decisions

**Manifest als CSV (`datasets/manifest.csv`).** Eine Zeile pro Dokument, Mehrfachwerte (Tags) mit `;` getrennt. Alternativen: JSONL (schlechter von Hand zu lesen), SQLite (nicht diff-bar). Bei 100 Zeilen ist CSV am einfachsten und git-freundlich.

**Nativ vs. gescannt automatisch bestimmen.** Beim ersten Download prüft PyMuPDF pro Seite, ob ein Textlayer mit nennenswertem Text existiert und kein einzelnes Bild den Großteil der Seite bedeckt (sonst gilt sie als Scan, auch mit unsichtbarer OCR-Textschicht, wie sie bei NTRS-Scans üblich ist); Anteil von Seiten mit Text ≥ 0,8 gilt als `native`, ≤ 0,2 als `scanned`, dazwischen `mixed`. Der Wert wird ins Manifest geschrieben und kann von Hand korrigiert werden. Keine Annahme aufgrund der Quelle.

**Kandidaten pro Quelle über eigene Adapter.** NTRS: API-Suche mit Filter auf Elektrik/Elektronik und Rechtefeld. NIST: Publikationsmetadaten. Datenblätter und Bitsavers: kuratierte URL-Listen in einer Seed-Datei (`datasets/seeds/*.txt`), weil dort keine saubere API besteht. GovDocs1/SafeDocs: Stichprobe mit festem Zufalls-Seed aus einer Dateiliste. Der Adapter schreibt Kandidaten in eine Zwischendatei, die Übernahme ins Manifest ist ein separater, bewusster Schritt.

**Download mit `httpx`, sequentiell pro Host.** Streaming mit Größenlimit (Standard 50 MB), PDF-Magic-Check (`%PDF-`) auf den ersten Bytes, Ablage zuerst als `.part`, dann atomar umbenennen. Pro Host eine Pause von mindestens 1 s. Alternative `requests` bietet keinen Vorteil beim Streaming-Limit.

**GovDocs1 als Zip-Pakete.** Digital Corpora liefert GovDocs1 nur als Zips (je 1000 Mischdateien, 290–490 MB), keine Einzel-URLs; SafeDocs wird nicht verwendet, die Ausreißer-Gruppe kommt allein aus GovDocs1. Manifest-URL ist `<zip-url>#<eintrag>`. Die Kandidatensuche lädt ein Zip in `data/cache/`, zieht eine Zufallsstichprobe (fester Seed) der PDF-Einträge, und der Download-Lauf nutzt dasselbe Zip, extrahiert die Einträge und löscht es danach. Einträge werden nur über `zipfile` gelesen (Chunks mit Größenlimit, nie über den Namen auf die Platte geschrieben) gegen Pfadtricks und Zip-Bomben. Alternative Range-Requests auf einzelne Einträge wäre sparsamer, wurde zugunsten des einfacheren Codes abgelehnt.

**Hash-Pinning.** Der SHA256 wird bei der Erstaufnahme ins Manifest geschrieben. Spätere Läufe vergleichen dagegen, so bleibt der Datensatz stabil, auch wenn Hersteller ihre Datenblätter ändern.

**Rechtestatus je Quelle.** NASA/NIST: `public-domain` nach Prüfung des Rechtefelds, sonst `unknown`. Hersteller: `vendor-copyright`. Bitsavers: `unknown`. GovDocs1: `open-license` laut Digital Corpora. `vendor-copyright` und `unknown` bedeuten, dass die Dokumente nur lokal verwendet und nicht veröffentlicht werden.

**Codeort.** `src/docparse/dataset/` mit `manifest.py`, `sources/`, `download.py`, CLI `uv run python -m docparse.dataset {candidates,add,download,summary,validate}`.

## Risks / Trade-offs

- [Links brechen oder Hersteller ändern PDFs] → Hash-Pinning meldet es; Dokument ersetzen oder ersetzen lassen.
- [Hersteller-Server blockieren Bots] → User-Agent mit Kontakt, Pausen, Fallback auf manuellen Download in `data/raw/<id>/`, das Skript verifiziert dann nur.
- [Rechtestatus falsch eingestuft] → Standard `unknown`; nichts aus `data/` wird je veröffentlicht oder committet.
- [Bösartige PDFs] → nur PyMuPDF zum Öffnen, nie ausführen, Größenlimit, Parser-Fehler werden pro Dokument abgefangen.
- [Heuristik nativ/gescannt falsch bei Mischfällen] → Wert ist im Manifest von Hand korrigierbar; `mixed` als eigene Klasse.
- [Ziel von ca. 500 Seiten verleitet zu sehr langen Dokumenten] → Beim Aufnehmen eine Seitenobergrenze je Dokument (Standard 6) in der Spalte `page_range`. Bei 73 Dokumenten ergibt das 405 Seiten; mit 40 wären es über 2000 gewesen. Die Datei bleibt vollständig, nur der Seitenbereich im Manifest gilt als Datensatz.
- [Die ersten Seiten sind oft Vorspann] → In der Stichprobe (4.4) bestand bei 2 von 4 Report-/Scan-Dokumenten der Seitenbereich 1–6 nur aus Deckblatt und Inhaltsverzeichnis. Bei geprüften Dokumenten ist `page_range` von Hand gesetzt, bei den übrigen nicht geprüft. Eine inhaltsbasierte Seitenauswahl bleibt für später offen.
