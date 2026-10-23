# engine-adapters Specification

## Purpose

Die Adapter sind der einzige Ort, der die Rohformate der Engines kennt. Jeder Adapter liefert aus demselben Seitenbild Blöcke im gemeinsamen Format, ohne die Stärken oder Schwächen der Engine zu verdecken.

## Requirements

### Requirement: PyMuPDF-Adapter
Der Adapter SHALL aus dem nativen Textlayer Textblöcke mit Text, aus eingebetteten Bildern Blöcke vom Typ `image`, aus Vektorgrafiken zusammengefasste Blöcke vom Typ `drawing` und erkannte einfache Tabellen als Blöcke vom Typ `table` mit HTML liefern, jeweils ohne Konfidenz.

#### Scenario: Native Seite
- **WHEN** eine Seite einen Textlayer hat
- **THEN** enthält das Ergebnis Textblöcke mit Text und Box im Seitenbild

#### Scenario: Gescannte Seite ohne Textlayer
- **WHEN** eine Seite nur ein Rasterbild enthält
- **THEN** ist das Ergebnis `ok` mit einem Block vom Typ `image` und ohne Textblöcke

### Requirement: Layout-Adapter
Der Adapter SHALL die Blöcke von PP-DocLayoutV3 mit Typ, Box, Reihenfolge und Konfidenz liefern; Text wird nicht erzeugt.

#### Scenario: Typzuordnung
- **WHEN** das Layout-Modell einen Block `table` oder `header` erkennt
- **THEN** trägt der Block den entsprechenden Typ und die Originalbezeichnung

### Requirement: OCR-Adapter
Der Adapter SHALL jede von PP-OCRv6 erkannte Textzeile als Block vom Typ `line` mit Text, Box, Polygon und Konfidenz liefern, in Lesereihenfolge der Engine; die Dokumentausrichtung wird nicht verändert, damit Koordinaten zum Seitenbild passen.

#### Scenario: Zeile mit Konfidenz
- **WHEN** eine Textzeile erkannt wurde
- **THEN** enthält der Block Text, Box und die Erkennungskonfidenz der Zeile

#### Scenario: Seite ohne Text
- **WHEN** die OCR keine Zeile findet
- **THEN** ist das Ergebnis `ok` mit leerer Blockliste

### Requirement: VL-Adapter
Der Adapter SHALL die Blöcke von PaddleOCR-VL-1.6 mit Typ, Box, Reihenfolge und Markdown bzw. HTML (bei Tabellen) liefern und Kopf- und Fußzeilen behalten.

#### Scenario: Tabelle
- **WHEN** VL einen Tabellenblock liefert
- **THEN** enthält der Block den HTML-Code der Tabelle und den Typ `table`

#### Scenario: Kopfzeile bleibt erhalten
- **WHEN** die Seite eine Kopfzeile hat
- **THEN** erscheint sie als Block vom Typ `header`

### Requirement: Begrenzte VL-Generierung
Der VL-Lauf SHALL das Token-Limit und das Zeitlimit je Seite aus der Registry verwenden, und eine Seite, die das Zeitlimit überschreitet, SHALL als Fehler mit Hinweis auf das Limit gespeichert werden.

#### Scenario: Zeitüberschreitung
- **WHEN** die Verarbeitung einer Seite das Zeitlimit überschreitet
- **THEN** wird sie abgebrochen, das Ergebnis hat Status `error` mit Hinweis auf das Limit, und die nächste Seite wird verarbeitet
