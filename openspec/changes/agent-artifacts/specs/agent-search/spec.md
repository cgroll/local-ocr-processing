# Spec Delta

## Purpose

Die Suche macht die exportierten Chunks per Volltext und per Embedding auffindbar und stellt einem Agenten wenige, klare Funktionen bereit, die von der Frage über die Fundstelle bis zum gerenderten Seitenbild führen.

## ADDED Requirements

### Requirement: Lokaler Index
Das System SHALL aus den Artefakten aller exportierten Dokumente einen lokalen Index unter `data/index/` aufbauen, der Chunks mit Volltext und Vektor enthält und ohne Netzwerk benutzbar ist; der Aufbau SHALL wiederholbar sein und nur geänderte Dokumente neu verarbeiten.

#### Scenario: Index aufbauen
- **WHEN** der Index zum ersten Mal gebaut wird
- **THEN** enthält er jeden Chunk aller exportierten Dokumente mit Dokument, Seite, Art und Volltext

#### Scenario: Nur Änderungen
- **WHEN** ein Dokument erneut exportiert wurde und alle anderen unverändert sind
- **THEN** werden nur die Chunks dieses Dokuments neu eingebettet und ersetzt

#### Scenario: Gelöschtes Dokument
- **WHEN** die Artefakte eines Dokuments nicht mehr vorhanden sind
- **THEN** entfernt der nächste Aufbau seine Chunks aus dem Index

### Requirement: Embeddings aus einem gemeinsamen Modell
Das System SHALL Text-Chunks, Tabellen und Figuren mit dem in der Registry geführten Embedding-Modell einbetten: Text als Text, Tabellen als Textserialisierung aus Beschriftung, Kopfzeile und Zeilen, Figuren als Bild des Ausschnitts, sodass Anfrage und alle Chunks im selben Vektorraum liegen.

#### Scenario: Tabelle einbetten
- **WHEN** ein Tabellen-Chunk eingebettet wird
- **THEN** ist der eingebettete Text die Serialisierung aus Beschriftung, Kopfzeile und Zeilen, nicht das rohe HTML

#### Scenario: Figur einbetten
- **WHEN** ein Figuren-Chunk eingebettet wird
- **THEN** wird das Bild des Ausschnitts eingebettet, und eine Textanfrage kann diesen Vektor finden

#### Scenario: Modell nur im Index-Lauf
- **WHEN** der Index gebaut wird
- **THEN** ist das Embedding-Modell der einzige geladene GPU-Baustein und wird danach freigegeben

### Requirement: Suchfunktion
Die Funktion `search` SHALL zu einer Anfrage Treffer mit Chunk-ID, Dokument, Seite, Box, Art, Textauszug, Score und Verweis auf ein zugehöriges Artefakt (Figur oder Tabelle) liefern, wählbar im Modus `text` (Volltext), `semantic` (Vektor) oder `hybrid`, mit Filtern nach Dokument, Tag, Art und einer Höchstzahl.

#### Scenario: Hybride Suche
- **WHEN** eine Anfrage im Modus `hybrid` gestellt wird
- **THEN** erscheinen Treffer aus Volltext und Vektorsuche in einer gemeinsamen, nach Score sortierten Liste ohne doppelte Chunks

#### Scenario: Exakter Begriff
- **WHEN** nach einem seltenen Bezeichner wie `SE555` im Modus `text` gesucht wird
- **THEN** stehen Chunks, die ihn wörtlich enthalten, vor allen anderen

#### Scenario: Filter
- **WHEN** nach Art `figure` und Tag `datasheet` gefiltert wird
- **THEN** enthält das Ergebnis nur Figuren-Chunks von Dokumenten mit diesem Tag

#### Scenario: Keine Treffer
- **WHEN** nichts passt
- **THEN** ist das Ergebnis eine leere Liste mit Exit-Code 0, kein Fehler

### Requirement: Abruf von Seite, Figur und Tabelle
Das System SHALL `get_page` (Markdown einer Seite), `get_figure` und `get_table` (Daten und Datei einer ID) bereitstellen, die Unbekanntes mit einer Fehlermeldung beantworten, die die gültigen Möglichkeiten (etwa Seitenzahl des Dokuments) nennt.

#### Scenario: Seite abrufen
- **WHEN** `get_page` für Dokument und Seite aufgerufen wird
- **THEN** wird das Markdown dieser Seite mit Seitenanker zurückgegeben

#### Scenario: Unbekannte Seite
- **WHEN** die Seitenzahl außerhalb des Dokuments liegt
- **THEN** meldet die Funktion einen Fehler mit der gültigen Spanne

### Requirement: Seitenbild für den Blick des VLM
Die Funktion `render_page` SHALL zu Dokument und Seite den Pfad des Seitenbilds liefern und optional zu einer Box einen Ausschnitt mit Rand erzeugen, in der festgelegten DPI, sodass ein VLM die Fundstelle prüfen kann.

#### Scenario: Ganze Seite
- **WHEN** `render_page` ohne Box aufgerufen wird
- **THEN** wird das Seitenbild der Seite zurückgegeben

#### Scenario: Ausschnitt zu einem Treffer
- **WHEN** `render_page` mit der Box eines Treffers aufgerufen wird
- **THEN** zeigt das Bild genau diese Stelle samt Rand, und der Pfad liegt unter `data/`

### Requirement: Aufruf über die Kommandozeile
Jede Funktion SHALL als Kommando mit maschinenlesbarer Ausgabe (JSON) aufrufbar sein, damit ein Agent sie ohne weiteren Server nutzen kann.

#### Scenario: JSON-Ausgabe
- **WHEN** `search` mit der Option für JSON aufgerufen wird
- **THEN** ist die Ausgabe ein gültiges JSON-Dokument mit den genannten Trefferfeldern

### Requirement: Nachvollziehbare Modellwahl
Der Index SHALL festhalten, mit welchem Modell und welcher Version die Vektoren erzeugt wurden, und eine Suche mit abweichendem Modell SHALL mit einem Hinweis abbrechen, statt unvergleichbare Vektoren zu mischen.

#### Scenario: Modellwechsel
- **WHEN** das Embedding-Modell in der Registry geändert wurde und der Index noch alte Vektoren enthält
- **THEN** meldet die semantische Suche den Widerspruch und verlangt einen Neuaufbau
