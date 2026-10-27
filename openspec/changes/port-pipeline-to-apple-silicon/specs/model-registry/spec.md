# Spec Delta

## MODIFIED Requirements

### Requirement: Eintrag pro Baustein
Die Registry SHALL für jeden der Bausteine `pymupdf`, `layout` (PP-DocLayoutV3), `ocr` (PP-OCRv6), `vl` (PaddleOCR-VL-1.6) und `embedding` (EmbeddingGemma 2) genau einen Eintrag mit eindeutigem Schlüssel, Aufgabe, Modellname bzw. Version, Ausführungsort und geschätztem Speicherbedarf in MB führen. Der Ausführungsort SHALL neben `cpu` und `gpu` (CUDA) auch plattformspezifische Beschleuniger-Orte (z. B. Apple-Silicon über MLX) ausdrücken können.

#### Scenario: Registry abfragen
- **WHEN** die Registry aufgelistet wird
- **THEN** erscheinen alle fünf Bausteine mit ihren Pflichtfeldern, und PyMuPDF ist mit 0 MB Speicher als CPU-Baustein ausgewiesen

#### Scenario: Unbekannter Schlüssel
- **WHEN** ein nicht registrierter Schlüssel angefordert wird
- **THEN** meldet die Registry einen Fehler, der die gültigen Schlüssel nennt

#### Scenario: Beschleuniger-Ausführungsort
- **WHEN** die Registry auf einer Plattform ohne CUDA läuft und ein Baustein einen plattformspezifischen Beschleuniger-Ausführungsort trägt
- **THEN** ist dieser Ausführungsort im Eintrag abfragbar und wird nicht als Fehler behandelt

### Requirement: Gemeinsames Budget
Die Registry SHALL ein verfügbares Speicher-Budget (Gesamtwert abzüglich einer Reserve) führen und für eine Modellmenge angeben können, ob sie gemeinsam in das Budget passt. Gesamtwert und Reserve SHALL plattformabhängig gesetzt werden können (z. B. dediziertes VRAM gegenüber Unified Memory).

#### Scenario: VL und OCR zusammen
- **WHEN** geprüft wird, ob `vl` und `ocr` gleichzeitig geladen werden können
- **THEN** lautet die Antwort anhand des konfigurierten Budgets ja oder nein, jeweils mit Angabe der Summe und des Budgets

#### Scenario: Plattformabhängiges Budget
- **WHEN** die Konfiguration ein größeres Gesamt-Budget setzt (etwa für Unified Memory)
- **THEN** verwendet die Registry diesen Wert bei der Passt-Prüfung, ohne dass der Code geändert wird

## ADDED Requirements

### Requirement: Backend je Baustein konfigurierbar
Die Registry SHALL für Bausteine mit mehreren möglichen Inferenz-Backends (z. B. CUDA gegenüber MLX) das zu verwendende Backend als Parameter führen und über die Konfigurationsdatei überschreibbar machen, mit einem sinnvollen plattformabhängigen Standard.

#### Scenario: Standard-Backend nach Plattform
- **WHEN** ein Baustein mit mehreren Backends ohne ausdrückliche Konfiguration gelesen wird
- **THEN** trägt er das zur laufenden Plattform passende Standard-Backend (CUDA auf NVIDIA, MLX auf Apple Silicon)

#### Scenario: Backend überschrieben
- **WHEN** die Konfigurationsdatei für einen Baustein ein bestimmtes Backend setzt
- **THEN** liefert die Registry dieses Backend, die übrigen Einträge bleiben unverändert
