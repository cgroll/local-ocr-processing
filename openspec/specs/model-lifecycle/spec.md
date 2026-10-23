# model-lifecycle Specification

## Purpose

Der Lebenszyklus sorgt dafür, dass Modelle einzeln und kontrolliert geladen und wieder freigegeben werden, damit die 8-GB-Karte nie überlastet wird und Fehler früh und verständlich auftreten.

## Requirements

### Requirement: Laden und Freigeben einzelner Modelle
Das System SHALL Modelle über die Registry-Schlüssel laden und explizit freigeben können, und Freigeben SHALL den GPU-Speicher des Modells wieder verfügbar machen.

#### Scenario: Laden und Freigeben
- **WHEN** ein GPU-Modell geladen und danach freigegeben wird
- **THEN** liegt der belegte GPU-Speicher nach der Freigabe nahe am Ausgangswert vor dem Laden

#### Scenario: Doppeltes Laden
- **WHEN** ein bereits geladenes Modell erneut angefordert wird
- **THEN** wird die vorhandene Instanz wiederverwendet und nicht ein zweites Mal geladen

### Requirement: VRAM-Wächter
Das System SHALL vor dem Laden eines Modells prüfen, ob es zusammen mit den bereits geladenen Modellen ins Budget passt, und andernfalls das Laden verweigern, ohne bestehende Modelle zu beeinträchtigen.

#### Scenario: Unverträgliche Kombination
- **WHEN** `vl` geladen ist und `ocr` angefordert wird
- **THEN** verweigert das System das Laden mit einer Fehlermeldung, die die geladenen Modelle und den Bedarf nennt

#### Scenario: Reale Belegung berücksichtigt
- **WHEN** ein fremder Prozess so viel GPU-Speicher belegt, dass das Modell nicht passt
- **THEN** meldet das System den freien Speicher laut GPU und verweigert das Laden, statt mit einem Speicherfehler abzustürzen

### Requirement: Sequenzieller Einsatz
Das System SHALL einen Kontext bereitstellen, der ein Modell lädt, für den Block bereitstellt und danach auch im Fehlerfall freigibt.

#### Scenario: Fehler im Block
- **WHEN** innerhalb des Blocks eine Ausnahme auftritt
- **THEN** wird das Modell trotzdem freigegeben und die Ausnahme weitergereicht

### Requirement: Smoke-Test
Das System SHALL ein Kommando bereitstellen, das ausgewählte oder alle Modelle nacheinander lädt, auf einer Beispielseite eine Mini-Inferenz ausführt, wieder freigibt und je Modell Ladezeit, Inferenzzeit, VRAM-Spitze und Erfolg bzw. Fehler ausgibt.

#### Scenario: Alle Modelle gesund
- **WHEN** das Kommando ohne Auswahl läuft
- **THEN** erscheint pro Baustein eine Zeile mit Zeiten und VRAM-Spitze, und der Exit-Code ist 0

#### Scenario: Ein Modell fehlt oder scheitert
- **WHEN** ein Modell nicht geladen werden kann
- **THEN** wird der Fehler für dieses Modell gemeldet, die übrigen Modelle werden weiter geprüft und der Exit-Code ist ungleich 0

#### Scenario: VL-Timeout
- **WHEN** die Inferenz von `vl` das konfigurierte Zeitlimit überschreitet
- **THEN** wird sie abgebrochen und als Fehler mit Hinweis auf das Limit gemeldet
