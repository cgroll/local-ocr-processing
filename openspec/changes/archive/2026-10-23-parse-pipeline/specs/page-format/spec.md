# Spec Delta

## Purpose

Das Seiten-Zwischenformat ist die einzige Schnittstelle zwischen den Engines und allen Folgeschritten. Es hält fest, was auf einer Seite erkannt wurde, wo, von welcher Engine und wie sicher, und bezieht jede Koordinate auf ein eindeutig definiertes Seitenbild.

## ADDED Requirements

### Requirement: Seitenbild mit fester DPI
Das System SHALL jede Seite eines Dokuments einmal mit einer festen, im Ergebnis gespeicherten DPI (Standard 150) als PNG unter `data/pages/<doc>/<page>.png` rendern, mit 1-basierter Seitennummer, und alle Engines SHALL dasselbe Bild verwenden.

#### Scenario: Seite rendern
- **WHEN** eine Seite zum ersten Mal verarbeitet wird
- **THEN** liegt das Bild unter `data/pages/<doc>/<page>.png` und seine Pixelmaße entsprechen Seitengröße in Punkten mal DPI durch 72

#### Scenario: Seite mit Drehung
- **WHEN** eine PDF-Seite eine eingetragene Drehung oder einen abweichenden Zuschneidebereich hat
- **THEN** zeigt das gerenderte Bild die Seite so, wie sie angezeigt wird, und alle Koordinaten beziehen sich auf dieses Bild

### Requirement: Seitenergebnis als JSON
Das System SHALL pro Engine und Seite genau eine JSON-Datei `data/results/<engine>/<doc>/<page>.json` schreiben, mit Formatversion, Dokument-ID, Seitennummer, DPI, Bildbreite und -höhe in Pixeln, Engine, Engine-Version, Status (`ok` oder `error`), Laufzeit und einer Liste von Blöcken.

#### Scenario: Erfolgreiche Seite
- **WHEN** eine Engine eine Seite erfolgreich verarbeitet hat
- **THEN** enthält die Datei Status `ok`, die Laufzeit in Sekunden und die Blockliste

#### Scenario: Gescheiterte Seite
- **WHEN** die Verarbeitung scheitert
- **THEN** enthält die Datei Status `error`, die Fehlermeldung und eine leere Blockliste, sodass der Fehler später nachvollziehbar ist

### Requirement: Blockfelder
Jeder Block SHALL einen Typ aus einer festen Menge (`text`, `title`, `header`, `footer`, `table`, `figure`, `formula`, `chart`, `list`, `caption`, `line`, `image`, `drawing`, `other`), die Originalbezeichnung der Engine, eine Box `[x0, y0, x1, y1]` in Pixeln des Seitenbilds, die Quell-Engine, eine Lesereihenfolge (oder null) und eine Konfidenz (oder null, wenn die Engine keine liefert) tragen; Text, Markdown und HTML sind optional.

#### Scenario: Block ohne Konfidenz
- **WHEN** eine Engine keine Konfidenz liefert, etwa PyMuPDF
- **THEN** steht die Konfidenz auf null und nicht auf einem erfundenen Wert

#### Scenario: Unbekanntes Engine-Label
- **WHEN** eine Engine ein Label liefert, das keinem Typ zugeordnet ist
- **THEN** erhält der Block den Typ `other` und behält die Originalbezeichnung

### Requirement: Koordinaten in Pixeln des Seitenbilds
Alle Boxen und Polygone SHALL in Pixeln des gerenderten Seitenbilds mit Ursprung links oben liegen; Koordinaten in PDF-Punkten SHALL beim Import mit DPI durch 72 umgerechnet werden.

#### Scenario: PyMuPDF-Koordinaten
- **WHEN** PyMuPDF einen Textblock bei Punktkoordinaten liefert
- **THEN** liegt die gespeicherte Box im Seitenbild an der entsprechenden Stelle, umgerechnet mit der gespeicherten DPI

### Requirement: Validierung
Das System SHALL Seitenergebnisse prüfen können: Pflichtfelder vorhanden, Typ bekannt, Box wohlgeformt (`x0 <= x1`, `y0 <= y1`) und innerhalb der Bildmaße mit kleiner Toleranz.

#### Scenario: Box außerhalb der Seite
- **WHEN** ein Block eine Box außerhalb des Seitenbilds hat
- **THEN** meldet die Validierung Datei, Blocknummer und Abweichung als Fehler

#### Scenario: Gültiges Ergebnis
- **WHEN** alle Seitenergebnisse gültig sind
- **THEN** endet die Validierung mit Exit-Code 0 und der Anzahl geprüfter Dateien
