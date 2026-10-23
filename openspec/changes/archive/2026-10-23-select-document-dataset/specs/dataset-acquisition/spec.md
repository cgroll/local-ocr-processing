# Spec Delta

## Purpose

Das Herunterladen der Dokumente laut Manifest ist reproduzierbar, wiederholbar und sicher im Umgang mit unvertrauenswürdigen Dateien aus dem Internet.

## ADDED Requirements

### Requirement: Download laut Manifest
Das System SHALL jedes Manifest-Dokument in ein eigenes Verzeichnis `data/raw/<id>/` laden.

#### Scenario: Erster Lauf
- **WHEN** das Download-Kommando auf ein Manifest ohne lokale Daten angewendet wird
- **THEN** liegt für jede ID ein Verzeichnis mit der PDF-Datei vor und der Lauf endet mit einer Zusammenfassung aus Erfolgen und Fehlern

### Requirement: Wiederholbarer Lauf
Das Download-Kommando SHALL bereits vorhandene, hashgleiche Dokumente überspringen und nach einem Abbruch ohne Neuladen des Vorhandenen fortsetzen.

#### Scenario: Zweiter Lauf
- **WHEN** das Kommando erneut läuft und alle Dokumente vorhanden und gültig sind
- **THEN** wird nichts heruntergeladen und der Lauf meldet alle Einträge als übersprungen

### Requirement: Verifikation nach dem Laden
Das System SHALL nach jedem Download SHA256 und Seitenzahl mit dem Manifest vergleichen und bei Abweichung die Datei nicht als gültig behandeln.

#### Scenario: Hash weicht ab
- **WHEN** der SHA256 einer geladenen Datei vom Manifest abweicht
- **THEN** wird der Eintrag als Fehler gemeldet und die Datei nicht für nachfolgende Schritte freigegeben

#### Scenario: Erstaufnahme
- **WHEN** ein Eintrag noch keinen Hash hat
- **THEN** berechnet das System Hash und Seitenzahl und trägt sie ins Manifest ein

### Requirement: Sicherer Umgang mit unvertrauenswürdigen Dateien
Das System SHALL heruntergeladene Dateien ausschließlich über PyMuPDF öffnen, nie ausführen, und Dateityp (PDF-Magic) und Größenlimit prüfen, bevor eine Datei als Dokument gilt.

#### Scenario: Kein PDF
- **WHEN** die geladene Datei kein PDF ist, etwa eine HTML-Fehlerseite
- **THEN** wird sie verworfen und der Eintrag als Fehler gemeldet

#### Scenario: Übergroße Datei
- **WHEN** die Datei das konfigurierte Größenlimit überschreitet
- **THEN** bricht der Download ab und meldet den Eintrag als Fehler

### Requirement: Rücksichtsvolle Downloads
Das System SHALL pro Host höchstens eine Anfrage gleichzeitig stellen, Wartezeiten zwischen Anfragen einhalten und einen eindeutigen User-Agent senden.

#### Scenario: Mehrere Dokumente vom selben Host
- **WHEN** mehrere Einträge denselben Host haben
- **THEN** werden sie nacheinander mit Pause geladen

### Requirement: Einträge aus Zip-Paketen
Das System SHALL Manifest-URLs der Form `<zip-url>#<eintrag>` unterstützen: das Zip einmal laden, den Eintrag als `data/raw/<id>/document.pdf` ablegen wie einen direkten Download und das Zip nach dem Lauf löschen.

#### Scenario: Mehrere Einträge aus demselben Zip
- **WHEN** mehrere Manifest-Einträge auf dasselbe Zip verweisen
- **THEN** wird das Zip nur einmal geladen und danach gelöscht

#### Scenario: Eintrag fehlt im Zip
- **WHEN** der benannte Eintrag nicht im Zip enthalten oder zu groß ist
- **THEN** wird der Manifest-Eintrag als Fehler gemeldet und die übrigen Einträge werden weiter verarbeitet

#### Scenario: Zweiter Lauf
- **WHEN** alle Einträge aus dem Zip bereits vorliegen und gültig sind
- **THEN** wird das Zip nicht erneut geladen
