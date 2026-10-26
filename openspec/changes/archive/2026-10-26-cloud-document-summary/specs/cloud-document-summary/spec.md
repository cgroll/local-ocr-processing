# Spec Delta

## Purpose

Erzeugt für jedes Dokument zusätzlich zur lokalen Titel+Summary eine zweite, von einem Cloud-Flaggschiffmodell erzeugte Variante aus demselben Digest-Text, damit später (in `retrieval-eval`) verglichen werden kann, ob eine stärkere Summary auch zu besserer Suche führt.

## ADDED Requirements

### Requirement: Cloud-Summary aus demselben Digest-Input
Das System SHALL aus dem bereits vorhandenen Markdown-Digest eines Dokuments (`document-digest`) -- demselben Text, der auch der lokalen Summary zugrunde liegt -- über Gemini 4 Argon (Vertex AI) einen Titel und eine 3-5-Satz-Summary erzeugen.

#### Scenario: Digest vorhanden
- **WHEN** für ein Dokument ein Markdown-Digest vorliegt
- **THEN** wird aus genau diesem Digest-Text ein Cloud-Titel und eine Cloud-Summary erzeugt

### Requirement: Getrennte Ablage von der lokalen Summary
Das System SHALL die Cloud-Summary in einer eigenen Datei getrennt von der lokalen Summary-Datei und der deterministischen `<doc>.md` ablegen, inklusive Status, verwendetem Modellnamen sowie Eingabe-/Ausgabe-Tokenzahl und berechnetem Kostenbetrag für diesen Aufruf.

#### Scenario: Erfolgreicher Cloud-Aufruf
- **WHEN** ein Cloud-Summary-Aufruf für ein Dokument erfolgreich zurückkommt
- **THEN** wird eine vom lokalen Summary-Ergebnis getrennte Datei geschrieben, die Titel, Summary, Status `ok`, Modellname, Token-Zahlen und Kosten enthält, und die lokale Summary-Datei sowie `<doc>.md` bleiben unverändert

### Requirement: Fehler pro Dokument statt Abbruch
Das System SHALL einen fehlgeschlagenen Cloud-Aufruf für ein Dokument (Netzwerkfehler, Rate-Limit, Timeout) nach einer begrenzten Zahl von Wiederholungsversuchen als Fehler für dieses Dokument vermerken, ohne den Lauf über die restlichen Dokumente abzubrechen.

#### Scenario: Einzelner Dokumentaufruf schlägt dauerhaft fehl
- **WHEN** der Cloud-Aufruf für ein Dokument nach allen Wiederholungsversuchen weiterhin fehlschlägt
- **THEN** wird für dieses Dokument ein Fehlerstatus vermerkt, und die übrigen Dokumente werden weiter verarbeitet

### Requirement: Wiederholbar und fortsetzbar
Das System SHALL vorhandene Cloud-Summary-Ergebnisse mit Status `ok` bei einem erneuten Lauf überspringen und nur fehlende oder per Option erzwungene Dokumente neu berechnen.

#### Scenario: Zweiter Lauf ohne Änderungen
- **WHEN** der Cloud-Summary-Lauf erneut startet und alle Dokumente bereits ein `ok`-Ergebnis haben
- **THEN** wird kein weiterer Cloud-Aufruf ausgeführt

#### Scenario: Erzwungene Neuberechnung
- **WHEN** der Lauf mit einer expliziten Erzwingungs-Option für ein bereits vorhandenes `ok`-Ergebnis gestartet wird
- **THEN** wird für dieses Dokument ein neuer Cloud-Aufruf ausgeführt und das vorhandene Ergebnis ersetzt

### Requirement: Kostenzusammenfassung je Lauf
Das System SHALL nach einem Batch-Lauf über mehrere Dokumente die Summe der tatsächlich angefallenen Kosten und Token-Zahlen über alle in diesem Lauf verarbeiteten Dokumente ausgeben.

#### Scenario: Vollauf über mehrere Dokumente
- **WHEN** ein Batch-Lauf über mehrere Dokumente abgeschlossen ist
- **THEN** zeigt die Zusammenfassung die Gesamtkosten und Gesamt-Tokenzahlen aller in diesem Lauf tatsächlich ausgeführten Cloud-Aufrufe

### Requirement: Dokument-Level-Embedding der Cloud-Summary
Das System SHALL aus Titel und Cloud-Summary eines Dokuments mit dem bestehenden `embedding`-Baustein (EmbeddingGemma 2) ein Embedding der Art `document_summary_cloud` berechnen und im bestehenden Such-Index ablegen, mit demselben Seiten-Sentinel wie die übrigen Dokument-Level-Embeddings, aber als von `document_summary` unterscheidbare Art.

#### Scenario: Cloud-Summary vorhanden
- **WHEN** für ein Dokument eine Cloud-Summary mit Status `ok` vorliegt
- **THEN** enthält der Such-Index für dieses Dokument zusätzlich ein `document_summary_cloud`-Embedding, ohne das vorhandene `document_summary`-Embedding zu verändern

#### Scenario: Keine Cloud-Summary vorhanden
- **WHEN** für ein Dokument keine erfolgreiche Cloud-Summary vorliegt
- **THEN** wird für dieses Dokument kein `document_summary_cloud`-Embedding erzeugt, und der restliche Index bleibt unverändert
