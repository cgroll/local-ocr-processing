# Spec Delta

## Purpose

Wandelt die bestehenden Engine-Ergebnisse einer Seite (`pymupdf`, `layout`, `ocr`, optional `vl`) in eine für Suche und Embedding geeignete, angereicherte Form um: eine gewählte Textquelle je Seite, Bild-Crops für Figure-/Chart-/Table-Blöcke und kurze, themenbezogene VLM-Beschreibungen dazu.

## ADDED Requirements

### Requirement: Textquellen-Wahl je Seite
Das System SHALL je Seite `pymupdf` als primäre Textquelle verwenden und auf `ocr`-Zeilen zurückfallen, wenn `pymupdf` keinen Text liefert; liegt zusätzlich ein erfolgreiches `vl`-Ergebnis vor, SHALL dessen HTML für Table-Blöcke verwendet werden statt der primären Quelle, weil es die Zeilenstruktur zuverlässiger erhält.

#### Scenario: Seite mit Textlayer
- **WHEN** eine Seite über `pymupdf` Textblöcke liefert
- **THEN** wird `pymupdf` als Textquelle der Seite verwendet

#### Scenario: Reiner Scan ohne Textlayer
- **WHEN** `pymupdf` für eine Seite keinen Text liefert (reiner Scan)
- **THEN** wird `ocr` als Textquelle für diese Seite verwendet

#### Scenario: VL-Tabelle vorhanden
- **WHEN** für eine Seite ein `vl`-Ergebnis mit Status `ok` und einem Table-Block vorliegt
- **THEN** nutzt der angereicherte Table-Block das HTML aus `vl` statt aus `pymupdf`

### Requirement: Spaltenbewusste Lesereihenfolge
Das System SHALL den narrativen Text einer Seite in spaltenbewusster Lesereihenfolge zusammensetzen (linke Spalte vollständig vor der nächsten Spalte, jeweils von oben nach unten) statt in der von der Textquelle gelieferten Rohreihenfolge, wenn die Seite erkennbar aus mehreren durchlaufenden Textspalten besteht; andernfalls SHALL die Rohreihenfolge der Textquelle unverändert verwendet werden.

#### Scenario: Zweispaltige Seite
- **WHEN** eine Seite aus zwei oder drei durchlaufenden Textspalten besteht und die Textquelle ihre Blöcke zeilenweise über die ganze Seite hinweg liefert (nicht spaltenweise)
- **THEN** wird der narrative Text spaltenweise zusammengesetzt, nicht in der von der Textquelle gelieferten, spaltenübergreifend vermischten Reihenfolge

#### Scenario: Keine echten Spalten
- **WHEN** eine Seite verstreute Blöcke an vielen unterschiedlichen horizontalen Positionen hat, die keine durchlaufenden Spalten bilden (z. B. Bauteillabels in einem Schaltplan)
- **THEN** bleibt die Rohreihenfolge der Textquelle unverändert

### Requirement: Bild-Crop für visuelle Blöcke
Das System SHALL für jeden `layout`-Block vom Typ `figure`, `chart` oder `table` mit einer Fläche über einem konfigurierten Mindestwert einen Bildausschnitt aus dem gerenderten Seitenbild erzeugen und reproduzierbar ablegen; Blöcke unter dem Mindestwert SHALL übersprungen werden.

#### Scenario: Block über Mindestgröße
- **WHEN** ein `figure`-, `chart`- oder `table`-Block die Mindestfläche erreicht
- **THEN** wird ein Bildausschnitt erzeugt und unter einem reproduzierbaren Pfad abgelegt

#### Scenario: Kleine Dekoration
- **WHEN** ein Block vom Typ `figure` unter der Mindestfläche liegt (z. B. ein kleines Logo oder Marketing-Icon)
- **THEN** wird kein Bildausschnitt erzeugt und der Block erscheint nicht in der Anreicherung

### Requirement: Themenbezogene VLM-Beschreibung
Das System SHALL für jeden erzeugten Bildausschnitt mit einem lokalen VLM eine kurze Beschreibung erzeugen, deren Vorgabe sich ausdrücklich auf Art und Thema des Inhalts beschränkt (z. B. Diagrammtyp, abgebildete Größen, grobe Tabellenstruktur) und keine konkreten Werte, Zahlen oder Zellinhalte verlangt.

#### Scenario: Beschreibung für ein Diagramm
- **WHEN** ein `chart`-Block beschrieben wird
- **THEN** nennt die Beschreibung Art des Diagramms und die dargestellten Größen, ohne einzelne Messwerte oder Kurven zu benennen

#### Scenario: Beschreibung für eine Tabelle
- **WHEN** ein `table`-Block beschrieben wird
- **THEN** nennt die Beschreibung das Thema und die grobe Struktur der Tabelle, ohne einzelne Zellen oder Werte wiederzugeben

### Requirement: Wiederholbar und fortsetzbar
Das System SHALL vorhandene Anreicherungen mit Status `ok` überspringen und nach einem Abbruch ohne Neuberechnung fortsetzen; ein Fehler bei einem einzelnen Block (Crop oder Beschreibung) SHALL die übrigen Blöcke und Seiten nicht abbrechen.

#### Scenario: Zweiter Lauf
- **WHEN** der Anreicherungslauf erneut startet und alle Seiten bereits `ok` sind
- **THEN** wird nichts neu berechnet

#### Scenario: Einzelner Block scheitert
- **WHEN** die Beschreibung eines einzelnen Blocks fehlschlägt
- **THEN** wird für diesen Block ein Fehler vermerkt, die übrigen Blöcke der Seite und die folgenden Seiten werden weiter verarbeitet

### Requirement: Ablage der Anreicherung
Das System SHALL je Dokument und Seite eine JSON-Datei unter `data/results/enrich/<doc>/<page>.json` mit der gewählten Textquelle, dem narrativen Text und der Liste angereicherter visueller Blöcke (Typ, Box, Crop-Pfad, Beschreibung, ggf. Tabelleninhalt, Status) schreiben.

#### Scenario: Erfolgreiche Anreicherung
- **WHEN** eine Seite erfolgreich angereichert wurde
- **THEN** enthält die Datei die gewählte Textquelle, den narrativen Text und für jeden visuellen Block Crop-Pfad, Beschreibung und Status `ok`
