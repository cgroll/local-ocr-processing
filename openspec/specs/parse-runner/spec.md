# parse-runner Specification

## Purpose

Der Runner verarbeitet die im Manifest beschriebenen Seiten mit den gewählten Engines zuverlässig, wiederholbar und innerhalb der VRAM-Grenzen, und macht den Stand jederzeit prüfbar.

## Requirements

### Requirement: Seitenauswahl aus dem Manifest
Der Runner SHALL die Seiten aus dem Manifest nehmen, je Dokument beschränkt auf `page_range`, und nur Dokumente mit vorhandener, hashgleicher Datei verarbeiten; auf Wunsch SHALL die Auswahl auf einzelne Dokument-IDs oder eine Höchstzahl von Seiten begrenzt werden können.

#### Scenario: Seitenbereich
- **WHEN** ein Dokument `page_range` 2-4 hat
- **THEN** werden nur die Seiten 2, 3 und 4 verarbeitet

#### Scenario: Dokument fehlt
- **WHEN** die Datei eines Manifest-Eintrags nicht vorhanden oder ungültig ist
- **THEN** wird der Eintrag mit einem Hinweis übersprungen und die übrigen Dokumente werden verarbeitet

### Requirement: Engines nacheinander
Der Runner SHALL die gewählten Engines nacheinander ausführen, jeweils mit einem einzigen geladenen Modell über alle ausgewählten Seiten, und das Modell vor der nächsten Engine freigeben.

#### Scenario: Mehrere Engines
- **WHEN** der Lauf mit `layout`, `ocr` und `vl` gestartet wird
- **THEN** ist zu keinem Zeitpunkt mehr als ein GPU-Modell geladen, und jedes Modell wird nur einmal geladen

### Requirement: Wiederholbar und fortsetzbar
Der Runner SHALL vorhandene Seitenergebnisse mit Status `ok` überspringen und nach einem Abbruch ohne Neuberechnung fortsetzen; Seiten mit Status `error` werden bei einem erneuten Lauf wiederholt, und `--force` erzwingt die Neuberechnung.

#### Scenario: Zweiter Lauf
- **WHEN** der Lauf erneut startet und alle Ergebnisse vorhanden und `ok` sind
- **THEN** wird nichts berechnet und der Lauf meldet alle Seiten als übersprungen

#### Scenario: Wiederholung nach Fehler
- **WHEN** eine Seite im ersten Lauf mit Status `error` endete
- **THEN** wird sie im nächsten Lauf erneut versucht

### Requirement: Fehlertoleranz
Ein Fehler oder Timeout bei einer Seite SHALL den Lauf nicht abbrechen; der Lauf SHALL am Ende eine Zusammenfassung aus verarbeiteten, übersprungenen und fehlgeschlagenen Seiten je Engine ausgeben und bei mindestens einem Fehler mit Exit-Code ungleich 0 enden.

#### Scenario: Einzelne Seite scheitert
- **WHEN** eine Engine bei einer Seite eine Ausnahme wirft
- **THEN** wird für die Seite ein Ergebnis mit Status `error` geschrieben und die nächste Seite verarbeitet

### Requirement: Zusammenfassung
Das System SHALL aus den vorhandenen Ergebnissen je Engine die Anzahl Seiten und Fehler, die Laufzeit (Median und Maximum) und die Blockanzahl nach Typ ausgeben.

#### Scenario: Zusammenfassung abrufen
- **WHEN** die Zusammenfassung abgerufen wird
- **THEN** erscheint je Engine eine Zeile mit Seiten, Fehlern, Laufzeiten und Blockzahlen
