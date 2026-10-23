# Spec Delta

## Purpose

Der Export legt pro Dokument lesbare, greifbare Artefakte ab, die ein Agent mit Dateizugriff durchsuchen kann, und verknüpft jede Fundstelle über stabile IDs mit Dokument, Seite und Box, damit der letzte Blick immer auf die gerenderte Seite fällt.

## ADDED Requirements

### Requirement: Artefaktverzeichnis je Dokument
Das System SHALL für jedes Dokument mit zusammengeführten Seitenergebnissen ein Verzeichnis `data/artifacts/<doc>/` mit `meta.json`, `doc.md`, `pages/<page>.md`, `chunks.jsonl`, `figures/` und `tables/` schreiben, mit vierstelliger, 1-basierter Seitennummer wie im Zwischenformat.

#### Scenario: Dokument exportieren
- **WHEN** der Export für ein Dokument mit zusammengeführten Seiten läuft
- **THEN** existieren alle genannten Dateien und Verzeichnisse, und `pages/` enthält genau eine Markdown-Datei je zusammengeführter Seite

#### Scenario: Seite ohne Ergebnis
- **WHEN** für eine Seite im Seitenbereich kein zusammengeführtes Ergebnis mit Status `ok` vorliegt
- **THEN** fehlt ihre Seitendatei, `meta.json` führt die Seite als fehlend, und der Export der übrigen Seiten läuft weiter

### Requirement: Markdown mit Seitenankern
`doc.md` SHALL die Seiten in Reihenfolge enthalten, jede eingeleitet von einem Seitenanker mit Dokument-ID und Seitennummer; der Inhalt einer Seite SHALL in `doc.md` und in `pages/<page>.md` identisch sein, in Lesereihenfolge, mit Überschriften als Markdown-Überschriften.

#### Scenario: Seite im Dokument finden
- **WHEN** ein Text in `doc.md` gefunden wird
- **THEN** lässt sich die Seite aus dem nächstvorangehenden Seitenanker ablesen, ohne weitere Dateien zu öffnen

#### Scenario: Inhalt gleich
- **WHEN** `pages/0003.md` und der Abschnitt von Seite 3 in `doc.md` verglichen werden
- **THEN** stimmt der Inhalt abgesehen vom Anker überein

### Requirement: Stabile IDs für Figuren und Tabellen
Jede Figur und jede Tabelle SHALL eine ID der Form `<doc>-p<seite>-f<n>` bzw. `<doc>-p<seite>-t<n>` tragen, mit n in Lesereihenfolge je Seite; bei unveränderten Eingaben SHALL der Export dieselben IDs vergeben.

#### Scenario: Wiederholter Export
- **WHEN** der Export bei unveränderten Eingaben erneut läuft
- **THEN** erhalten alle Figuren und Tabellen dieselben IDs wie zuvor

#### Scenario: ID im Markdown
- **WHEN** eine Seite eine Figur und eine Tabelle enthält
- **THEN** erscheinen beide im Seiten-Markdown mit ihrer ID

### Requirement: Figuren als Ausschnitt mit Beschreibung
Für jede Figur (Block vom Typ `figure`, `chart`, `image` oder `drawing` ab einer Mindestgröße) SHALL der Export den Ausschnitt des Seitenbilds als PNG unter `figures/<id>.png` ablegen und in `figures/figures.json` ID, Seite, Box, Beschriftung (falls vorhanden) und, falls erzeugt, die Beschreibung und die Quelle der Beschreibung festhalten.

#### Scenario: Figur mit Beschriftung
- **WHEN** eine Figur eine benachbarte Beschriftung (`caption`) hat
- **THEN** steht die Beschriftung in den Figurendaten und im Markdown neben der ID

#### Scenario: Beschreibung nicht erzeugt
- **WHEN** keine Beschreibung erzeugt wurde
- **THEN** ist das Feld leer, der Export gelingt trotzdem, und das Markdown nennt ID und Beschriftung ohne erfundenen Text

### Requirement: Tabellen als Daten und als Text
Für jede Tabelle SHALL der Export den bereinigten HTML-Code unter `tables/<id>.html` und, soweit rechteckig auflösbar, eine CSV unter `tables/<id>.csv` ablegen; im Seiten-Markdown SHALL eine kleine Tabelle inline als Markdown-Tabelle stehen und eine große nur ID, Beschriftung, Dimension und Kopfzeile.

#### Scenario: Kleine Tabelle
- **WHEN** eine Tabelle höchstens die konfigurierte Zellenzahl hat
- **THEN** steht sie vollständig als Markdown-Tabelle im Seiten-Markdown und zusätzlich als Datei

#### Scenario: Große Tabelle
- **WHEN** eine Tabelle die Grenze überschreitet
- **THEN** zeigt das Seiten-Markdown ID, Beschriftung, Zeilen- und Spaltenzahl und die Kopfzeile, und verweist auf die Datei

#### Scenario: Verbundene Zellen
- **WHEN** eine Tabelle `rowspan` oder `colspan` enthält und sich nicht rechteckig auflösen lässt
- **THEN** fehlt die CSV, das HTML bleibt erhalten, und der Verzicht ist in den Tabellendaten vermerkt

### Requirement: Chunks mit Rückverweis
`chunks.jsonl` SHALL eine durchsuchbare Einheit je Zeile enthalten, mit eindeutiger Chunk-ID, Dokument-ID, Seitennummer, Box im Seitenbild, Art (`text`, `table` oder `figure`), Text, Quell-Engine und – bei Tabellen und Figuren – der ID des zugehörigen Artefakts.

#### Scenario: Text-Chunk
- **WHEN** ein Textabschnitt exportiert wird
- **THEN** trägt sein Chunk Dokument, Seite, Box der zusammengefassten Blöcke, Art `text` und den Text

#### Scenario: Figuren-Chunk
- **WHEN** eine Figur exportiert wird
- **THEN** trägt ihr Chunk Art `figure`, die Figuren-ID, Box und als Text Beschriftung, Beschreibung (falls vorhanden) und den Text innerhalb der Box

#### Scenario: Jeder Chunk ist auflösbar
- **WHEN** ein beliebiger Chunk gelesen wird
- **THEN** lässt sich aus Dokument und Seite das Seitenbild und aus der Box die Stelle darauf bestimmen

### Requirement: Dokument-Metadaten
`meta.json` SHALL Dokument-ID, Titel, Typ-Tag, Tags, Quelle (URL), Rechtestatus, Seitenzahl, exportierte Seiten, Fehlendes und, falls erzeugt, eine Zusammenfassung enthalten; Titel, Quelle, Rechtestatus und Tags SHALL aus dem Manifest übernommen werden.

#### Scenario: Aus dem Manifest
- **WHEN** das Manifest zu einem Dokument Titel, Quelle und Rechtestatus enthält
- **THEN** stehen genau diese Werte in `meta.json`

#### Scenario: Zusammenfassung fehlt
- **WHEN** keine Zusammenfassung erzeugt wurde
- **THEN** ist das Feld leer und `meta.json` bleibt gültig

### Requirement: Lokal, nicht im Git
Der Export SHALL ausschließlich unter `data/` schreiben, Inhalte der Quelldokumente nur lokal ablegen und nie Skripte oder Inhalte der Dokumente ausführen.

#### Scenario: Ausgabeort
- **WHEN** der Export läuft
- **THEN** liegen alle erzeugten Dateien unter `data/artifacts/`
