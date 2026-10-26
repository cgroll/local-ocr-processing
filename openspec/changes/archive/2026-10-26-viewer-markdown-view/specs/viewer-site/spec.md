# Spec Delta

## MODIFIED Requirements

### Requirement: Sichere Darstellung unvertrauenswürdiger Inhalte
Das System SHALL allen Text aus Ergebnissen maskiert ausgeben und sowohl Tabellen-HTML als auch aus Markdown gerendertes HTML (Überschriften, Absätze, Listen, Tabellen) auf eine Erlaubnisliste bekannter Tags beschränken (Tabellenstruktur mit `rowspan` und `colspan` eingeschlossen), sodass Inhalte eines Dokuments weder Skripte ausführen noch Ressourcen von außen laden können.

#### Scenario: Skript im Text
- **WHEN** ein Block den Text `<script>alert(1)</script>` enthält
- **THEN** erscheint er als sichtbarer Text und wird nicht ausgeführt

#### Scenario: Fremdes Tabellen-HTML
- **WHEN** ein Tabellen-HTML ein Bild, einen Link oder ein Ereignisattribut enthält
- **THEN** werden diese Teile entfernt und nur die Tabellenstruktur mit Zelltext bleibt

#### Scenario: Aus Markdown gerendertes HTML
- **WHEN** die Markdown-Repräsentation einer Seite zu HTML gerendert wird
- **THEN** wird das Ergebnis auf dieselbe Art der Erlaubnisliste unterzogen wie Tabellen-HTML, sodass darin enthaltener Text aus Engine-Ergebnissen (z. B. VLM-Beschreibungen) weder Skripte ausführen noch Ressourcen von außen laden kann
