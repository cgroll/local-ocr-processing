# Spec Delta

## MODIFIED Requirements

### Requirement: Eintrag pro Baustein
Die Registry SHALL für jeden der Bausteine `pymupdf`, `layout` (PP-DocLayoutV3), `ocr` (PP-OCRv6), `vl` (PaddleOCR-VL-1.6), `embedding` (EmbeddingGemma 2) und `describe` (lokales VLM für kurze Bildbeschreibungen, getrennt von `vl`) genau einen Eintrag mit eindeutigem Schlüssel, Aufgabe, Modellname bzw. Version, Ausführungsort (CPU oder GPU) und geschätztem VRAM-Bedarf in MB führen.

#### Scenario: Registry abfragen
- **WHEN** die Registry aufgelistet wird
- **THEN** erscheinen alle sechs Bausteine mit ihren Pflichtfeldern, und PyMuPDF ist mit 0 MB VRAM als CPU-Baustein ausgewiesen

#### Scenario: Unbekannter Schlüssel
- **WHEN** ein nicht registrierter Schlüssel angefordert wird
- **THEN** meldet die Registry einen Fehler, der die gültigen Schlüssel nennt
