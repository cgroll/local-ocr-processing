# Spec Delta

## MODIFIED Requirements

### Requirement: VRAM-Wächter
Das System SHALL vor dem Laden eines Modells prüfen, ob es zusammen mit den bereits geladenen Modellen ins Speicher-Budget passt, und andernfalls das Laden verweigern, ohne bestehende Modelle zu beeinträchtigen. Auf Plattformen ohne auslesbaren dedizierten GPU-Speicher (kein `nvidia-smi`, geteiltes Unified Memory) SHALL die reale Belegungsprüfung übersprungen werden, statt das Laden fälschlich zu blockieren; die budgetbasierte Passt-Prüfung bleibt wirksam.

#### Scenario: Unverträgliche Kombination
- **WHEN** `vl` geladen ist und `ocr` angefordert wird und beide zusammen das Budget übersteigen
- **THEN** verweigert das System das Laden mit einer Fehlermeldung, die die geladenen Modelle und den Bedarf nennt

#### Scenario: Reale Belegung berücksichtigt
- **WHEN** auf einer CUDA-Plattform ein fremder Prozess so viel GPU-Speicher belegt, dass das Modell nicht passt
- **THEN** meldet das System den freien Speicher laut GPU und verweigert das Laden, statt mit einem Speicherfehler abzustürzen

#### Scenario: Keine dedizierte GPU-Speichermessung
- **WHEN** die Plattform keinen dedizierten GPU-Speicher ausliest (z. B. Apple Silicon mit Unified Memory)
- **THEN** überspringt das System die reale Belegungsprüfung und lässt das Laden zu, sofern die budgetbasierte Passt-Prüfung erfüllt ist

### Requirement: Laden und Freigeben einzelner Modelle
Das System SHALL Modelle über die Registry-Schlüssel laden und explizit freigeben können, und Freigeben SHALL den vom Modell belegten Beschleuniger-Speicher wieder verfügbar machen, unabhängig vom verwendeten Backend (CUDA oder MLX).

#### Scenario: Laden und Freigeben
- **WHEN** ein Beschleuniger-Modell geladen und danach freigegeben wird
- **THEN** liegt der belegte Speicher nach der Freigabe nahe am Ausgangswert vor dem Laden

#### Scenario: Doppeltes Laden
- **WHEN** ein bereits geladenes Modell erneut angefordert wird
- **THEN** wird die vorhandene Instanz wiederverwendet und nicht ein zweites Mal geladen

#### Scenario: Freigabe eines MLX-Modells
- **WHEN** ein über MLX geladenes Modell freigegeben wird
- **THEN** werden dessen Referenzen und zwischengespeicherte Speicherblöcke gelöst, ohne dass CUDA-spezifische Aufräumschritte verlangt werden
