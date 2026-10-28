# page-inspection Specification

## Purpose

Die Seitenansicht erlaubt, ein Original und das, was die Engines daraus erkannt haben, direkt nebeneinander zu beurteilen: wo ein Block sitzt, welchen Typ er hat, was er enthält und was eine andere Engine aus derselben Stelle gemacht hat.

## Requirements

### Requirement: Original mit Ebenen
Die linke Seitenhälfte SHALL das Seitenbild zeigen und darüber je Engine eine Ebene mit den Boxen der erkannten Blöcke, farblich nach Engine unterschieden, mit Typ (und Konfidenz, wenn vorhanden) als Beschriftung; jede Ebene SHALL einzeln ein- und ausblendbar sein, und beim Öffnen sind alle Ebenen ausgeschaltet.

#### Scenario: Ebene einschalten
- **WHEN** der Benutzer die Ebene `layout` einschaltet
- **THEN** erscheinen die Layout-Boxen deckungsgleich über dem Seitenbild

#### Scenario: Mehrere Ebenen
- **WHEN** mehrere Ebenen eingeschaltet sind
- **THEN** sind ihre Boxen an der Farbe der Engine unterscheidbar

#### Scenario: Typfilter
- **WHEN** der Benutzer in einer Ebene einzelne Blocktypen abwählt
- **THEN** verschwinden nur Blöcke dieser Typen aus der Ebene

### Requirement: Rekonstruktion der Seite
Die rechte Seitenhälfte SHALL aus den Blöcken einer wählbaren Engine die Seite nachbauen: Text, Überschriften und Zeilen als Text an der Position der Box, Tabellen als Tabelle, Bilder, Grafiken und Diagramme als Ausschnitt des Seitenbilds, Formeln als Quelltext. Blöcke ohne Inhalt (etwa aus der Layout-Engine) SHALL als beschriftete Box nach Typ erscheinen.

#### Scenario: Tabelle aus VL
- **WHEN** die Engine `vl` gewählt ist und die Seite einen Tabellenblock hat
- **THEN** erscheint an dessen Position eine Tabelle mit den erkannten Zellen

#### Scenario: Bildblock
- **WHEN** ein Block vom Typ `figure`, `image` oder `drawing` ist
- **THEN** zeigt die Rekonstruktion an dieser Position den entsprechenden Ausschnitt des Originals

#### Scenario: Layout ohne Text
- **WHEN** die Engine `layout` gewählt ist
- **THEN** erscheinen die Blöcke als beschriftete Boxen nach Typ ohne Text

### Requirement: Maßstabsgleiche Ansichten
Original und Rekonstruktion SHALL denselben Maßstab und dieselbe Scrollposition haben, sodass eine Stelle auf beiden Seiten auf gleicher Höhe liegt, und sich der Seitenbreite des Fensters anpassen.

#### Scenario: Scrollen
- **WHEN** der Benutzer links nach unten scrollt
- **THEN** folgt die rechte Seite, und derselbe Seitenbereich ist auf beiden Seiten sichtbar

### Requirement: Engine-Vergleich
Die Ansicht SHALL zwei Rekonstruktionen verschiedener Engines nebeneinander zeigen können, und der Benutzer SHALL für jede die Engine wählen.

#### Scenario: VL gegen OCR
- **WHEN** der Benutzer links `vl` und rechts `ocr` wählt
- **THEN** sieht er beide Rekonstruktionen derselben Seite im gleichen Maßstab nebeneinander

### Requirement: Blockinspektor
Ein Klick auf einen Block SHALL ihn in Original und Rekonstruktion hervorheben und in einem Bereich alle Felder des Blocks zeigen: Engine, Typ, Originalbezeichnung, Box, Konfidenz, Reihenfolge und Inhalt.

#### Scenario: Block wählen
- **WHEN** der Benutzer in der Rekonstruktion auf einen Block klickt
- **THEN** wird der Block in beiden Ansichten hervorgehoben und seine Felder erscheinen im Inspektor

#### Scenario: Auswahl aufheben
- **WHEN** der Benutzer neben einen Block oder auf Escape klickt
- **THEN** verschwinden Hervorhebung und Inspektor

### Requirement: Markdown-Repräsentation
Die Seitenansicht SHALL den fließenden Markdown-Text zeigen, den `document-digest` für diese Seite erzeugen würde -- mit derselben festen Textquellen-Wahl wie die Produktions-Suche/-Digest (keine Engine-Auswahl für diese Darstellung). Sie SHALL als Option im Auswahlmenü der rechten Spalte „Rekonstruktion" erscheinen, neben den Engines, und SHALL dort die Standardauswahl sein. Für jeden Figure- oder Chart-Block der Seite SHALL sie zusätzlich eine Bildvorschau zeigen, zugeordnet über Typ und Label, in derselben Reihenfolge wie im Fließtext. Der Markdown-Text SHALL in Seitenreihenfolge aufgebaut sein: Abbildungen, Diagramme und Tabellen stehen an der Stelle des Fließtextes, an der sie auf der Seite liegen (nicht gesammelt am Ende), und eine vom Layout erkannte Bildunterschrift (`caption`) steht direkt unter der Beschreibung des Blocks, zu dem sie gehört, statt im Fließtext.

#### Scenario: Abbildung mit Bildunterschrift
- **WHEN** das Layout neben einer Abbildung eine `caption` erkennt und die Textquelle dort Text enthält
- **THEN** steht dieser Text als Bildunterschrift direkt nach der Beschreibung der Abbildung und nicht noch einmal im Fließtext, und der Abbildungsabschnitt steht an seiner Seitenposition zwischen den Textblöcken

#### Scenario: Seite mit Textquelle
- **WHEN** für eine Seite eine gewählte Textquelle vorliegt (pymupdf oder ocr)
- **THEN** zeigt die Markdown-Darstellung Überschriften, Fließtext, Listen und Tabellen in derselben Formatierung wie der entsprechende Abschnitt der Dokument-Digest-Datei dieser Seite

#### Scenario: Seite ohne jede Textquelle
- **WHEN** für eine Seite keine Textquelle ermittelt werden konnte
- **THEN** zeigt die Markdown-Darstellung einen erkennbaren Leer-Hinweis statt eines Fehlers

#### Scenario: Figure-Block mit Bildvorschau
- **WHEN** eine Seite einen Figure- oder Chart-Block mit Status `ok` hat
- **THEN** zeigt die Markdown-Darstellung dafür eine Bildvorschau des entsprechenden Seitenausschnitts, zusammen mit Typ, Label und Beschreibung

#### Scenario: Tabellen ohne zusätzliche Bildvorschau
- **WHEN** eine Seite einen Table-Block hat
- **THEN** zeigt die Markdown-Darstellung dafür keine zusätzliche Bildvorschau, da der Tabelleninhalt bereits als Markdown-Tabelle erscheint

#### Scenario: Standardauswahl
- **WHEN** der Benutzer eine Seite ohne gespeicherte Wahl der rechten Spalte öffnet
- **THEN** zeigt die rechte Spalte die Markdown-Darstellung, und die Schaltfläche „Markdown anzeigen" entfällt

#### Scenario: Wahl als Engine-Option
- **WHEN** der Benutzer im Auswahlmenü „Rekonstruktion" eine Engine wählt
- **THEN** wechselt die rechte Spalte zur Rekonstruktion dieser Engine, und die Wahl bleibt beim Blättern im Browser erhalten

### Requirement: Verknüpfung von Layout-Elementen und Markdown-Abschnitten
Wenn die rechte Spalte die Markdown-Darstellung zeigt, SHALL ein Klick auf ein Layout-Element links den zugehörigen Markdown-Abschnitt rechts hervorheben und in Sicht bringen. Die Zuordnung SHALL aus der geometrischen Überlappung der Boxen folgen und keine Aussage über den semantischen Zusammenhang machen. Ein Overlay SHALL alle verknüpften Layout-Elemente links und die zugehörigen Abschnitte rechts in derselben Farbe umranden.

#### Scenario: Klick auf Abbildung
- **WHEN** der Benutzer bei eingeschalteter Ebene `layout` auf die Box einer Abbildung links klickt
- **THEN** ist der Abbildungsabschnitt im Markdown rechts hervorgehoben und in den sichtbaren Bereich gescrollt

#### Scenario: Klick auf Textbox
- **WHEN** der Benutzer auf eine Layout-Textbox links klickt, die Textblöcke der Textquelle enthält
- **THEN** sind alle Markdown-Abschnitte hervorgehoben, deren Quelle in dieser Box liegt

#### Scenario: Overlay
- **WHEN** der Benutzer das Overlay einschaltet
- **THEN** hat jedes verknüpfte Layout-Element links eine eigene Farbe, und die zugehörigen Markdown-Abschnitte rechts tragen dieselbe Umrandung

#### Scenario: Abschnitt ohne Layout-Bezug
- **WHEN** ein Markdown-Abschnitt mit keiner Layout-Box überlappt
- **THEN** ist er nicht verknüpft und zeigt keine Farbe und keine Hervorhebung

#### Scenario: Auswahl aufheben
- **WHEN** der Benutzer neben ein Element klickt oder Escape drückt
- **THEN** verschwinden Hervorhebung und Overlay-Farben der Verknüpfung
