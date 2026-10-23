# dataset-manifest Specification

## Purpose

Das Manifest beschreibt den Dokumentensatz maschinenlesbar und versioniert: welche Dokumente dazugehören, woher sie stammen, unter welchen Rechten und mit welchen Eigenschaften. Es ist die einzige Eingabe für alle nachfolgenden Verarbeitungsschritte.

## Requirements

### Requirement: Manifest-Eintrag pro Dokument
Das Manifest SHALL pro Dokument genau einen Eintrag mit stabiler ID, Quell-URL, Gruppe, Lizenz bzw. Rechtestatus, Typ-Tags, Erzeugungsart (nativ oder gescannt), Seitenzahl und SHA256 enthalten.

#### Scenario: Vollständiger Eintrag
- **WHEN** ein Dokument ins Manifest aufgenommen wird
- **THEN** sind alle Pflichtfelder gesetzt und die ID ist im Manifest eindeutig

#### Scenario: Unvollständiger Eintrag
- **WHEN** ein Pflichtfeld fehlt oder die ID doppelt vorkommt
- **THEN** meldet die Manifest-Validierung den Eintrag mit Zeile und Feldnamen als Fehler

### Requirement: Rechtestatus ist dokumentiert
Jeder Eintrag SHALL einen Rechtestatus aus einer festen Menge tragen (z. B. `public-domain`, `open-license`, `vendor-copyright`, `unknown`) und die Quelle dieser Einstufung als Text oder URL.

#### Scenario: Unbekannter Rechtestatus
- **WHEN** der Rechtestatus eines Dokuments nicht geklärt ist
- **THEN** steht er als `unknown` im Manifest und das Dokument gilt als nur lokal nutzbar

### Requirement: Heterogene Zusammensetzung
Das Manifest SHALL Dokumente aus vier Gruppen enthalten: native Hersteller-Datenblätter, NASA-/NIST-Berichte, Bitsavers-Scans mit Schaltplänen und eine Zufallsstichprobe aus GovDocs1/SafeDocs, insgesamt etwa 60 bis 100 Dokumente mit etwa 300 bis 500 Seiten.

#### Scenario: Zusammenfassung
- **WHEN** die Manifest-Zusammenfassung abgerufen wird
- **THEN** zeigt sie je Gruppe Dokument- und Seitenzahl sowie die Anteile nativ und gescannt

#### Scenario: Gruppe zu klein
- **WHEN** eine Gruppe weniger als die Hälfte ihrer Zielanzahl hat
- **THEN** warnt die Zusammenfassung davor

### Requirement: Technische Inhalte abgedeckt
Das Manifest SHALL Typ-Tags für Inhalte führen (mindestens `table`, `schematic`, `diagram`, `formula`, `plain-text`), und jedes dieser Tags SHALL von mindestens fünf Dokumenten getragen werden.

#### Scenario: Tag-Abdeckung
- **WHEN** die Zusammenfassung erzeugt wird
- **THEN** listet sie je Tag die Anzahl der Dokumente und kennzeichnet Tags unter fünf als Lücke

### Requirement: Nur das Manifest wird versioniert
Das Manifest SHALL in Git liegen, die heruntergeladenen Dokumente nicht.

#### Scenario: Git-Status nach Download
- **WHEN** alle Dokumente heruntergeladen wurden
- **THEN** zeigt `git status` keine Dateien unter `data/` an
