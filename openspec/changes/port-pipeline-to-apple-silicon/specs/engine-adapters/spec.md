# Spec Delta

## MODIFIED Requirements

### Requirement: VL-Adapter
Der Adapter SHALL die Blöcke von PaddleOCR-VL-1.6 mit Typ, Box, Reihenfolge und Markdown bzw. HTML (bei Tabellen) liefern und Kopf- und Fußzeilen behalten. Das Ergebnis SHALL dasselbe Block-Format haben, unabhängig davon, ob es aus dem seitenweiten Paddle-Pfad (`parsing_res_list`) oder auf Plattformen ohne diesen Pfad aus Layout-Regionen plus element-weiser Recognition zusammengesetzt wird.

#### Scenario: Tabelle
- **WHEN** VL einen Tabellenblock liefert
- **THEN** enthält der Block den HTML-Code der Tabelle und den Typ `table`

#### Scenario: Kopfzeile bleibt erhalten
- **WHEN** die Seite eine Kopfzeile hat
- **THEN** erscheint sie als Block vom Typ `header`

#### Scenario: Zusammensetzung aus Layout und Recognition
- **WHEN** der VL-Lauf auf einer Plattform ohne seitenweiten Paddle-Pfad läuft
- **THEN** werden die Regionen eines Layout-Laufs je einzeln erkannt und als Blöcke mit Typ, Box, Reihenfolge und Markdown/HTML im gemeinsamen Format geliefert, wie es Viewer, `enrich` und `search` erwarten

#### Scenario: Gleiche Block-Struktur über Backends
- **WHEN** dieselbe Seite einmal über den Paddle-Pfad und einmal über den Layout-plus-Recognition-Pfad verarbeitet wird
- **THEN** tragen beide Ergebnisse dieselben Pflichtfelder (Typ, Box, Reihenfolge, Text/Markdown/HTML, Engine `vl`) und sind vom nachgelagerten Format her austauschbar
