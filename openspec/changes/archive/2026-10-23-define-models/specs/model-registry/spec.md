# Spec Delta

## Purpose

Die Registry ist die einzige Quelle dafür, welche Modelle die Pipeline kennt, in welcher Version sie laufen und was sie kosten. Alle weiteren Schritte fragen die Registry, statt Modellnamen oder VRAM-Annahmen selbst zu führen.

## ADDED Requirements

### Requirement: Eintrag pro Baustein
Die Registry SHALL für jeden der Bausteine `pymupdf`, `layout` (PP-DocLayoutV3), `ocr` (PP-OCRv6), `vl` (PaddleOCR-VL-1.6) und `embedding` (EmbeddingGemma 2) genau einen Eintrag mit eindeutigem Schlüssel, Aufgabe, Modellname bzw. Version, Ausführungsort (CPU oder GPU) und geschätztem VRAM-Bedarf in MB führen.

#### Scenario: Registry abfragen
- **WHEN** die Registry aufgelistet wird
- **THEN** erscheinen alle fünf Bausteine mit ihren Pflichtfeldern, und PyMuPDF ist mit 0 MB VRAM als CPU-Baustein ausgewiesen

#### Scenario: Unbekannter Schlüssel
- **WHEN** ein nicht registrierter Schlüssel angefordert wird
- **THEN** meldet die Registry einen Fehler, der die gültigen Schlüssel nennt

### Requirement: Standardparameter mit Begrenzung für VL-1.6
Der Registry-Eintrag für `vl` SHALL ein Token-Limit und ein Zeit-Timeout je Seite als Standardparameter tragen und Kopf- und Fußzeilen erhalten (`markdown_ignore_labels` leer).

#### Scenario: Standardwerte des VL-Eintrags
- **WHEN** die Parameter des Eintrags `vl` gelesen werden
- **THEN** sind Token-Limit und Timeout gesetzt und Kopf-/Fußzeilen werden nicht ignoriert

### Requirement: Konfiguration überschreibbar
Die Registry SHALL Standardparameter über eine Konfigurationsdatei im Repository überschreiben lassen, ohne den Code zu ändern, und unbekannte Parameternamen als Fehler melden.

#### Scenario: Timeout überschrieben
- **WHEN** die Konfigurationsdatei einen anderen Timeout für `vl` setzt
- **THEN** liefert die Registry den überschriebenen Wert, alle anderen Einträge bleiben unverändert

#### Scenario: Tippfehler im Parameter
- **WHEN** die Konfiguration einen unbekannten Parameter nennt
- **THEN** schlägt das Laden der Registry mit Datei und Parametername fehl

### Requirement: Gemeinsames Budget
Die Registry SHALL das verfügbare VRAM-Budget (Standard 8192 MB abzüglich einer Reserve) führen und für eine Modellmenge angeben können, ob sie gemeinsam in das Budget passt.

#### Scenario: VL und OCR zusammen
- **WHEN** geprüft wird, ob `vl` und `ocr` gleichzeitig geladen werden können
- **THEN** lautet die Antwort nein, mit Angabe der Summe und des Budgets
