# viewer-site Specification

## Purpose

Die Viewer-Seite macht alle vorhandenen Parse-Ergebnisse ohne Server und ohne Netzwerk durchsuchbar und prüfbar. Sie liest nur, was die Pipeline geschrieben hat, und stellt Inhalte aus unvertrauenswürdigen Dokumenten sicher dar.

## Requirements

### Requirement: Statische Erzeugung
Das System SHALL aus Manifest, Seitenbildern und Ergebnisdateien eine statische Seite unter `data/viewer/` erzeugen, die aus dem Dateisystem geöffnet werden kann, und die Quelldaten dabei nicht verändern.

#### Scenario: Erzeugen
- **WHEN** das Build-Kommando läuft
- **THEN** liegt `data/viewer/index.html` samt einer Seite je Dokumentseite vor, und das Kommando nennt den Pfad der Indexseite

#### Scenario: Wiederholter Lauf
- **WHEN** das Kommando erneut läuft
- **THEN** wird der Stand aus den aktuellen Ergebnissen neu erzeugt, ohne Reste gelöschter Dokumente zu behalten

### Requirement: Indexseite
Die Indexseite SHALL alle verarbeiteten Dokumente mit Titel, Gruppe, Typ-Tags, Erzeugungsart, Seitenzahl und je Engine der Anzahl vorhandener, fehlgeschlagener und fehlender Seitenergebnisse listen und nach Gruppe, Tag und Freitext filterbar machen.

#### Scenario: Abdeckung sichtbar
- **WHEN** für ein Dokument nur ein Teil der Seiten VL-Ergebnisse hat
- **THEN** zeigt die Zeile für VL die Anzahl vorhandener Seiten und die Zahl der fehlenden

#### Scenario: Filter
- **WHEN** der Benutzer ein Tag wie `table` wählt
- **THEN** zeigt die Liste nur Dokumente mit diesem Tag

### Requirement: Navigation
Jede Seitenansicht SHALL Verweise auf die vorige und nächste Seite desselben Dokuments, auf das Dokument davor und danach sowie auf den Index tragen, und die Pfeiltasten SHALL zwischen Seiten blättern.

#### Scenario: Blättern
- **WHEN** der Benutzer auf der letzten Seite eines Dokuments „weiter" wählt
- **THEN** wechselt die Ansicht zur ersten Seite des nächsten Dokuments

### Requirement: Fehlende und fehlerhafte Ergebnisse
Das System SHALL für Engines ohne Ergebnis oder mit Status `error` die Seite trotzdem erzeugen und dort ausweisen, dass kein Ergebnis vorliegt bzw. welcher Fehler gemeldet wurde.

#### Scenario: VL fehlt
- **WHEN** zu einer Seite kein VL-Ergebnis existiert
- **THEN** ist die Engine in der Seitenansicht als „nicht verarbeitet" gekennzeichnet und die übrigen Engines funktionieren unverändert

#### Scenario: VL mit Fehler
- **WHEN** das VL-Ergebnis den Status `error` hat
- **THEN** zeigt die Ansicht die Fehlermeldung der Engine statt einer leeren Seite

### Requirement: Sichere Darstellung unvertrauenswürdiger Inhalte
Das System SHALL allen Text aus Ergebnissen maskiert ausgeben und Tabellen-HTML auf eine Erlaubnisliste (Tabellenstruktur mit `rowspan` und `colspan`) beschränken, sodass Inhalte eines Dokuments weder Skripte ausführen noch Ressourcen von außen laden können.

#### Scenario: Skript im Text
- **WHEN** ein Block den Text `<script>alert(1)</script>` enthält
- **THEN** erscheint er als sichtbarer Text und wird nicht ausgeführt

#### Scenario: Fremdes Tabellen-HTML
- **WHEN** ein Tabellen-HTML ein Bild, einen Link oder ein Ereignisattribut enthält
- **THEN** werden diese Teile entfernt und nur die Tabellenstruktur mit Zelltext bleibt

### Requirement: Keine externen Abhängigkeiten
Die erzeugte Seite SHALL ohne Netzwerkzugriff funktionieren und keine Skripte, Stilvorlagen oder Schriften von fremden Hosts laden.

#### Scenario: Offline
- **WHEN** die Seite ohne Internetverbindung geöffnet wird
- **THEN** sind alle Funktionen verfügbar und keine Anfrage geht an einen anderen Host
