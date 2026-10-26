# Spec Delta

## Purpose

Setzt die bereits vorhandenen Engine- und Anreicherungs-Ergebnisse eines Dokuments mechanisch zu einer einzigen, menschen- und LLM-lesbaren Markdown-Datei zusammen -- für alle Seiten eines Dokuments, nicht für eine Suchanfrage.

## ADDED Requirements

### Requirement: Fließtext mit Markdown-Überschriften
Das System SHALL den Fließtext einer Seite anhand der Blocktypen der gewählten Textquelle (`page-enrichment`) formatieren statt als flachen Text auszugeben: `title` als Markdown-Überschrift, `caption` kursiv, `list`-Einträge als Aufzählungspunkte, übrige Typen als Absatz.

#### Scenario: Titel-Block
- **WHEN** eine Seite einen Block vom Typ `title` enthält
- **THEN** erscheint sein Text im Digest als Markdown-Überschrift

#### Scenario: Listen-Block
- **WHEN** eine Seite einen Block vom Typ `list` enthält
- **THEN** erscheint sein Text im Digest als Markdown-Aufzählungspunkt

### Requirement: Tabellen als Markdown mit Unverified-Hinweis
Das System SHALL den Tabelleninhalt jedes Table-Blocks (aus `page-enrichment`, bevorzugt `vl`-HTML) als Markdown-Tabelle darstellen und SHALL jeder konvertierten Tabelle einen Hinweis beifügen, dass ihre Zeilen-/Spaltenzuordnung automatisch erzeugt und nicht verifiziert ist.

#### Scenario: Tabelle mit Hinweis
- **WHEN** ein Table-Block in den Digest aufgenommen wird
- **THEN** erscheint seine Markdown-Tabelle zusammen mit einem Hinweistext zur unverifizierten Struktur

### Requirement: VLM-Beschreibung je visuellem Block
Das System SHALL für jeden Figure-/Chart-/Table-Block die bereits in `page-enrichment` erzeugte Beschreibung in den Digest übernehmen.

#### Scenario: Beschreibung vorhanden
- **WHEN** ein visueller Block eine Beschreibung aus der Anreicherung hat
- **THEN** erscheint sie im Digest neben dem Block

### Requirement: Rohtext-Liste aus überlappenden Engine-Blöcken
Das System SHALL für jeden Figure-/Chart-/Table-Block zusätzlich alle `pymupdf`- und `ocr`-Blöcke der Seite auflisten, deren Box sich mit der Box des visuellen Blocks überlappt, als unstrukturierte, deduplizierte Liste von Textfragmenten, die ausdrücklich als unverifiziert und ohne Struktur gekennzeichnet ist.

#### Scenario: Überlappende Textfragmente
- **WHEN** ein `pymupdf`- oder `ocr`-Block der Seite die Box eines visuellen Blocks überlappt
- **THEN** erscheint sein Text in dessen Rohtext-Liste, erkennbar als unverifiziert

#### Scenario: Keine Überlappung
- **WHEN** kein Block der Seite die Box eines visuellen Blocks überlappt
- **THEN** bleibt dessen Rohtext-Liste leer, statt erfundene Einträge zu zeigen

### Requirement: Eine Datei je Dokument
Das System SHALL alle Seiten eines Dokuments zu genau einer Markdown-Datei unter `data/results/digest/<doc>.md` zusammenfügen, mit einer erkennbaren Markierung jedes Seitenwechsels.

#### Scenario: Mehrseitiges Dokument
- **WHEN** ein Dokument mit mehreren Seiten verarbeitet wird
- **THEN** enthält die erzeugte Datei alle Seiten in Reihenfolge, jede mit erkennbarer Seitenmarkierung

### Requirement: Titel und Summary je Dokument
Das System SHALL aus dem fertigen Markdown-Digest eines Dokuments mit einem lokalen LLM einen kurzen Titel und eine 3-5-Satz-Summary erzeugen und getrennt von der deterministischen `<doc>.md` ablegen; die Anweisung an das Modell SHALL im Prompt nach dem Dokumentinhalt stehen, nicht davor.

#### Scenario: Summary erzeugt
- **WHEN** für ein Dokument ein Markdown-Digest vorliegt
- **THEN** wird eine getrennte Datei mit Titel und Summary erzeugt, und die `<doc>.md` bleibt dabei unverändert

#### Scenario: Anweisung nach dem Inhalt
- **WHEN** der Prompt für die Titel-/Summary-Erzeugung aufgebaut wird
- **THEN** steht der Dokumentinhalt vor der Anweisung, nicht danach

### Requirement: Deterministisch und ohne Modell-Lauf
Das System SHALL den Digest ausschließlich aus bereits vorhandenen Engine- und Anreicherungs-Ergebnissen erzeugen, ohne ein Modell neu aufzurufen, und SHALL bei gleichen Eingaben dieselbe Ausgabe erzeugen.

#### Scenario: Erneuter Lauf ohne Änderungen
- **WHEN** der Digest-Lauf erneut startet, ohne dass sich Engine- oder Anreicherungs-Ergebnisse geändert haben
- **THEN** ist die erzeugte Datei inhaltlich identisch zur vorherigen
