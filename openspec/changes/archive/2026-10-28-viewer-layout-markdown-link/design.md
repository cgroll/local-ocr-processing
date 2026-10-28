# Design

## Context

Der Viewer rendert die Markdown-Darstellung serverseitig: `viewer/data.py:_page_markdown` ruft `digest/page.py:render_page` auf, das den Seitentext als einen flachen String aus Abschnitten zusammensetzt (`parts`, verbunden mit Leerzeilen). Danach läuft `markdown.markdown` über den gesamten Text und `sanitize_markdown_html` auf die Erlaubnisliste. Im Ergebnis gibt es keine Information mehr, welcher Abschnitt aus welchem Block stammt. Die Layout-Blöcke (`layout:<i>`) und die Blöcke der Textquellen haben jedoch Boxen in Seitenpixeln, und `_visual_blocks_payload` liefert die Boxen der Enrichment-Visuals bereits in die Seitendaten. Die Rekonstruktion-Auswahl in `static/page.js` (`reconColumn`) ist ein `<select>` über `ENGINES`; die Markdown-Darstellung hängt dagegen an einer eigenen Schaltfläche (`state.mode === "markdown"`). Siehe proposal.md für die Motivation.

## Goals / Non-Goals

**Goals:**
- Die Markdown-Darstellung bleibt textlich identisch zum Digest (bis auf Anker), damit die Stichprobe aus der README weiter gilt.
- Die Verknüpfung entsteht einmal serverseitig und ist im Browser nur noch Anzeige.
- Der Viewer bleibt offline und ohne Server-Logik.

**Non-Goals:**
- Keine Änderung an Textquellen-Wahl, Digest-Datei, Suche oder Routing (`configurable-routing`).
- Keine semantische Zuordnung; Verknüpfung ist rein geometrisch.

## Decisions

**1. Abschnitte mit Herkunft liefert `digest/page.py` über einen gemeinsamen Pfad.**
Eine neue Funktion (z. B. `render_page_sections`) gibt eine Liste `(markdown_text, source_bboxes)` zurück. `render_page` wird als Verkettung dieser Liste reimplementiert, damit der Digest byte-identisch bleibt (Test in `tests/test_digest.py`). Alternative: Anker per Regex im fertigen String suchen. Verworfen, weil Überschriften, Tabellen und Caption-Konsum bereits in `render_page` entschieden werden und ein Regex sie nicht sauber trennt.

**2. Visuelle Abschnitte bilden ihren Block einschließlich Caption und Textfragmente ab.**
Der Abschnitt eines Figure/Chart/Table-Blocks hat als Quell-Boxen seine eigene Box, die Box der zugeordneten Caption und die Boxen der zugeordneten Fragmente. Damit deckt ein Klick auf die Layout-Box der Abbildung den ganzen Abschnitt ab. Die Fragmente werden dafür intern mit Boxen statt nur mit Text geführt (`assign_fragments` liefert heute nur Strings; das wird um die Box erweitert, Text bleibt gleich).

**3. Verknüpfungsregel: Layout-Box ↔ Abschnitt über Überlappung der Quell-Boxen.**
Ein Abschnitt ist mit einer Layout-Box verknüpft, wenn mindestens eine seiner Quell-Boxen zu ≥ 0,5 ihrer eigenen Fläche in der Layout-Box liegt (gleiche Logik wie `_own_overlap_ratio` mit Schwelle 0,5, nicht 0,3, damit Nachbarboxen nicht mitgezogen werden). Die Verknüpfungsliste (`layout:<i>` → Abschnitts-IDs) wird serverseitig in `data.py` berechnet und in die Seitendaten geschrieben. Begründung: Der Browser braucht keine Geometrie-Logik, und Test und Anzeige nutzen dieselbe Regel.

**4. Anker im HTML über eine Erlaubnisliste-Erweiterung.**
Jeder Abschnitt wird einzeln durch `markdown.markdown` gerendert und in `<div data-section="<id>">` gehüllt. `sanitize_markdown_html` erhält `div` als erlaubtes Tag und `data-section` als einzig erlaubtes Attribut, dessen Wert eine nicht-negative Ganzzahl sein muss. Alternative: Abschnitts-Liste außerhalb des HTML ausliefern und per Textposition zuordnen. Verworfen, weil fragil bei Tabellen.

**5. Auswahlmenü und Default.**
`reconColumn` bekommt im `<select>` einen zusätzlichen Eintrag `markdown` als erste Option; `state` für die rechte Spalte startet mit `markdown`. Die Schaltfläche „Markdown anzeigen" und `state.mode === "markdown"` entfallen. Der Vergleichsmodus (`compare`) bleibt unverändert und bietet `markdown` nicht an, weil zwei Textspalten keinen Vergleich auf Boxebene erlauben.

**6. Overlay und Hervorhebung rein clientseitig.**
Farben kommen aus einer festen Palette in `page.js` (zyklisch über die verknüpften Layout-Boxen). Das Overlay schaltet nur Klassen und `outline`-Farben um; Klick auf Layout-Box setzt die Auswahl wie der bestehende Blockinspektor (`select(id)`), erweitert um die verknüpften Abschnitte.

## Risks / Trade-offs

- **[Text-Layout-Boxen passen selten 1:1 zu Absätzen]** → Mehrere Absätze hängen an einer Box, oder ein Absatz überlappt zwei Boxen. Mitigation: Die Regel in Entscheidung 3 erlaubt Mehrfachzuordnung; die Hervorhebung zeigt alle, das ist gewollt. Die Sichtprüfung auf den Seiten `ds-lm317` S. 4, `gd1-001675` S. 2 und `bs-pdp-8-memory-schematics-jun70` S. 1 entscheidet über die Schwelle 0,5.
- **[Bildvorschau-Thumbnails verschieben sich]** → Die Galerie wird nicht umgebaut; nur Abschnitts-Anker kommen dazu. Mitigation: Tests auf Galerie-Reihenfolge laut bestehendem Spec.
- **[Digest-Drift]** → Wenn `render_page` und die Abschnittsfunktion auseinanderlaufen, weicht die Anzeige vom Digest ab. Mitigation: `render_page` ist die Verkettung der Abschnittsfunktion, und ein Test vergleicht den Digest mit der Verkettung.
- **[Sanitizer-Oberfläche wächst]** → `div` und `data-section` kommen in die Erlaubnisliste. Mitigation: Nur numerischer Attributwert, keine anderen Attribute; Tests für fremde Attribute bleiben grün.

## Migration Plan

Keine Datenmigration: Ergebnisse unter `data/results/` bleiben unverändert. Der Viewer wird mit `docparse.viewer build` neu erzeugt. Rückbau durch Revert des Commits; gespeicherte `localStorage`-Wahl der Rechten Spalte mit altem Wert `single`/`markdown` wird beim Laden auf den Default `markdown` zurückgesetzt, falls der Wert nicht zu einer gültigen Option passt.

## Open Questions

Keine. Die Schwelle 0,5 wird bei der Sichtprüfung festgelegt (Tasks), ist aber kein offener Designpunkt.
