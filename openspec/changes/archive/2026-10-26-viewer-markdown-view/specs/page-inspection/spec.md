# Spec Delta

## ADDED Requirements

### Requirement: Markdown-Repräsentation
Die Seitenansicht SHALL als dritte Darstellung je Seite den fließenden Markdown-Text zeigen, den `document-digest` für diese Seite erzeugen würde -- mit derselben festen Textquellen-Wahl wie die Produktions-Suche/-Digest (keine Engine-Auswahl für diese Darstellung), wählbar zusätzlich zu Original und Rekonstruktion.

#### Scenario: Seite mit Textquelle
- **WHEN** für eine Seite eine gewählte Textquelle vorliegt (pymupdf oder ocr)
- **THEN** zeigt die Markdown-Darstellung Überschriften, Fließtext, Listen und Tabellen in derselben Formatierung wie der entsprechende Abschnitt der Dokument-Digest-Datei dieser Seite

#### Scenario: Seite ohne jede Textquelle
- **WHEN** für eine Seite keine Textquelle ermittelt werden konnte
- **THEN** zeigt die Markdown-Darstellung einen erkennbaren Leer-Hinweis statt eines Fehlers
