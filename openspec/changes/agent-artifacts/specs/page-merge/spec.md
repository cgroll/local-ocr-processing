# Spec Delta

## Purpose

Der Merge führt die Ergebnisse mehrerer Engines für eine Seite zu einer einzigen Blockliste zusammen, behält die Herkunft jedes Inhalts und liefert damit die Grundlage für alle Artefakte, die ein Agent liest.

## ADDED Requirements

### Requirement: Zusammengeführtes Seitenergebnis
Das System SHALL aus den vorhandenen Engine-Ergebnissen einer Seite eine zusammengeführte Blockliste im Seiten-Zwischenformat schreiben, unter `data/results/merged/<doc>/<page>.json`, mit denselben Pflichtfeldern wie ein Engine-Ergebnis und `merged` als Engine.

#### Scenario: Seite mit mehreren Engines
- **WHEN** für eine Seite Ergebnisse von `pymupdf`, `layout` und `vl` vorliegen
- **THEN** entsteht genau eine Datei mit Status `ok` und einer Blockliste, deren Koordinaten Pixel im selben Seitenbild sind

#### Scenario: Nur eine Engine vorhanden
- **WHEN** für eine Seite nur das Ergebnis von `ocr` vorliegt
- **THEN** entsteht das zusammengeführte Ergebnis aus dieser Engine allein und der Status bleibt `ok`

#### Scenario: Keine verwertbare Engine
- **WHEN** für eine Seite kein Engine-Ergebnis mit Status `ok` vorliegt
- **THEN** hat das zusammengeführte Ergebnis den Status `error` mit Hinweis auf die fehlenden Eingaben und eine leere Blockliste

### Requirement: Herkunft jedes Blocks
Jeder zusammengeführte Block SHALL festhalten, aus welcher Engine sein Inhalt und aus welcher sein Typ bzw. seine Box stammt, und die Blockfelder des Zwischenformats unverändert tragen.

#### Scenario: Text aus PyMuPDF, Typ aus Layout
- **WHEN** ein Layout-Block `title` einen PyMuPDF-Text enthält
- **THEN** trägt der zusammengeführte Block den Typ `title` und den PyMuPDF-Text, und die Herkunftsangabe nennt `layout` für den Typ und `pymupdf` für den Inhalt

### Requirement: Wahl der Textquelle
Das System SHALL den Text eines Blocks aus dem nativen Textlayer (`pymupdf`) nehmen, wenn die Seite einen hat, und andernfalls aus `vl` bzw. `ocr`; jede Entscheidung SHALL aus einer dokumentierten, festen Regelkette folgen, und die gewählte Quelle SHALL im Block vermerkt sein.

#### Scenario: Nativ erzeugte Seite
- **WHEN** eine Seite einen Textlayer hat
- **THEN** stammt der Text der Textblöcke aus `pymupdf`

#### Scenario: Gescannte Seite
- **WHEN** eine Seite keinen Textlayer hat und ein VL-Ergebnis vorliegt
- **THEN** stammt der Text aus `vl`

#### Scenario: Gescannte Seite ohne VL
- **WHEN** eine Seite keinen Textlayer hat und nur ein OCR-Ergebnis vorliegt
- **THEN** stammt der Text aus `ocr`, in Lesereihenfolge der Engine

### Requirement: Tabellen und Figuren
Das System SHALL für Tabellenblöcke das HTML aus `vl` bevorzugen, wenn vorhanden, sonst das aus `pymupdf`, und für Figuren-, Bild- und Zeichnungsblöcke die Box des Layouts (oder, ohne Layout, der Engine) behalten; Textblöcke, die vollständig in einer Tabellen- oder Figurenbox liegen, SHALL nicht zusätzlich als eigener Text erscheinen.

#### Scenario: Tabelle mit VL und PyMuPDF
- **WHEN** beide Engines an derselben Stelle eine Tabelle liefern
- **THEN** enthält der zusammengeführte Block das VL-HTML, und die PyMuPDF-Tabelle ist nicht doppelt vorhanden

#### Scenario: Text in der Tabelle
- **WHEN** PyMuPDF-Textblöcke innerhalb einer Tabellenbox liegen
- **THEN** erscheinen sie nicht als eigene Textblöcke neben der Tabelle

### Requirement: Lesereihenfolge
Das System SHALL die zusammengeführten Blöcke in eine Lesereihenfolge bringen, die die Reihenfolge des Layouts übernimmt, wenn vorhanden, und sonst von oben nach unten und innerhalb einer Zeile von links nach rechts verläuft.

#### Scenario: Seite mit Layout
- **WHEN** das Layout-Ergebnis eine Lesereihenfolge liefert
- **THEN** folgen die zusammengeführten Blöcke dieser Reihenfolge

#### Scenario: Seite ohne Layout
- **WHEN** kein Layout-Ergebnis vorliegt
- **THEN** sind die Blöcke nach Position von oben nach unten und links nach rechts geordnet

### Requirement: Wiederholbar und fortsetzbar
Der Merge SHALL ohne Modell (nur auf vorhandenen Ergebnissen) laufen, bei unveränderten Eingaben dasselbe Ergebnis liefern und vorhandene Ergebnisse überspringen, sofern keine Eingabe neuer ist oder `--force` gesetzt ist.

#### Scenario: Zweiter Lauf
- **WHEN** der Merge ohne Änderung der Eingaben erneut läuft
- **THEN** wird nichts neu geschrieben und alle Seiten werden als übersprungen gemeldet

#### Scenario: Neue VL-Ergebnisse
- **WHEN** für eine bereits zusammengeführte Seite nachträglich ein VL-Ergebnis erscheint
- **THEN** wird die Seite beim nächsten Lauf neu zusammengeführt
