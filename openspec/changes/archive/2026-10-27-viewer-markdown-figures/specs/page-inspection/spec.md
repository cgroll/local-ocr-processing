# Spec Delta

## MODIFIED Requirements

### Requirement: Markdown-Repräsentation
Die Seitenansicht SHALL als dritte Darstellung je Seite den fließenden Markdown-Text zeigen, den `document-digest` für diese Seite erzeugen würde -- mit derselben festen Textquellen-Wahl wie die Produktions-Suche/-Digest (keine Engine-Auswahl für diese Darstellung), wählbar zusätzlich zu Original und Rekonstruktion. Für jeden Figure- oder Chart-Block der Seite SHALL sie zusätzlich eine Bildvorschau zeigen, zugeordnet über Typ und Label, in derselben Reihenfolge wie im Fließtext.

#### Scenario: Seite mit Textquelle
- **WHEN** für eine Seite eine gewählte Textquelle vorliegt (pymupdf oder ocr)
- **THEN** zeigt die Markdown-Darstellung Überschriften, Fließtext, Listen und Tabellen in derselben Formatierung wie der entsprechende Abschnitt der Dokument-Digest-Datei dieser Seite

#### Scenario: Seite ohne jede Textquelle
- **WHEN** für eine Seite keine Textquelle ermittelt werden konnte
- **THEN** zeigt die Markdown-Darstellung einen erkennbaren Leer-Hinweis statt eines Fehlers

#### Scenario: Figure-Block mit Bildvorschau
- **WHEN** eine Seite einen Figure- oder Chart-Block mit Status `ok` hat
- **THEN** zeigt die Markdown-Darstellung dafür eine Bildvorschau des entsprechenden Seitenausschnitts, zusammen mit Typ, Label und Beschreibung

#### Scenario: Tabellen ohne zusätzliche Bildvorschau
- **WHEN** eine Seite einen Table-Block hat
- **THEN** zeigt die Markdown-Darstellung dafür keine zusätzliche Bildvorschau, da der Tabelleninhalt bereits als Markdown-Tabelle erscheint
