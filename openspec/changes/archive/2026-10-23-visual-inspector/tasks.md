# Tasks

## 1. Generator und Sicherheit

- [x] 1.1 `src/docparse/viewer/sanitize.py`: Erlaubnisliste für Tabellen-HTML (`table`, `thead`, `tbody`, `tr`, `td`, `th`, `br`, Attribute `rowspan`/`colspan` nur numerisch), Zelltext maskiert. Ergebnis: Tests mit einer echten VL-Tabelle (`tests/fixtures/vl_table_raw.json`) und Angriffsmustern (Skript, Bild, Link, `onclick`, `javascript:`).
- [x] 1.2 Datenaufbereitung: Ergebnisse einer Seite aller Engines laden, Fehler und fehlende Ergebnisse markieren, Tabellen bereinigen, JSON sicher einbetten (`</` maskieren). Ergebnis: Tests für fehlende Engine, `error`-Ergebnis und `</script>` im Text.
- [x] 1.3 Index-Daten aus Manifest und Ergebnisbaum: Abdeckung je Dokument und Engine (ok, error, fehlend gegen `page_range`). Ergebnis: Test mit Mini-Manifest und halb gefüllten Ergebnissen.
- [x] 1.4 HTML-Hüllen (`templates.py`) für Index und Seite mit CSP-Meta, Navigation (Seite, Dokument, Index) und Verweisen auf `assets/`. Ergebnis: Test prüft, dass keine fremden Hosts und keine Inline-Skripte vorkommen.
- [x] 1.5 `build.py` und CLI `python -m docparse.viewer build [--docs ...]`: Ausgabe nach `data/viewer/`, Assets kopieren, alte Ausgabe ersetzen, fehlende Seitenbilder melden. Ergebnis: Lauf über den Datensatz erzeugt Index und alle Seiten, `git status` zeigt nichts unter `data/`.

## 2. Seitenansicht (Browser)

- [x] 2.1 `static/style.css` und Grundgerüst `page.js`: Daten lesen, gemeinsamer Container mit Maßstab aus Fensterbreite, linke Spalte mit Seitenbild. Ergebnis: Seite zeigt das Original in passender Größe; Sichtprüfung per Screenshot.
- [x] 2.2 Ebenen: eine Overlay-Ebene je Engine mit Farbe, Beschriftung (Typ, Konfidenz), Ein-/Ausschalter, Typfilter. Ergebnis: Sichtprüfung auf einer Seite aller vier Engines (Boxen deckungsgleich mit dem Original).
- [x] 2.3 Rekonstruktion: Darstellung nach Blocktyp (Text, Tabelle, Bildausschnitt, Formel, leere Box), Engine wählbar. Ergebnis: Sichtprüfung für `pymupdf`, `ocr`, `layout` und `vl` auf einer Tabellenseite.
- [x] 2.4 Engine-Vergleich: zweite Rekonstruktion, Engine pro Seite wählbar, Zustand in `localStorage` (mit Rückfall). Ergebnis: `vl` gegen `ocr` im gleichen Maßstab nebeneinander.
- [x] 2.5 Blockinspektor: Klick wählt, hebt in beiden Ansichten hervor, zeigt alle Felder; Escape und Klick ins Leere heben auf. Ergebnis: Sichtprüfung.
- [x] 2.6 Navigation und Fehlerfälle: Pfeiltasten, Seitensprung, Anzeige „nicht verarbeitet" und Fehlermeldung der Engine. Ergebnis: Sichtprüfung an einer Seite ohne VL-Ergebnis und an einem Fehlerergebnis.
- [x] 2.7 Indexseite: Tabelle mit Abdeckung je Engine, Filter nach Gruppe, Tag und Freitext. Ergebnis: Sichtprüfung; Filter `table` zeigt nur passende Dokumente.

## 3. Abschluss

- [x] 3.1 Offline- und Sicherheitsprüfung im Browser: keine Anfragen an andere Hosts, Skript im Text bleibt Text. Ergebnis: Netzwerkprotokoll der Seite zeigt nur lokale Dateien; Testseite mit präpariertem Text.
- [x] 3.2 Durchsicht von je einer Seite pro Dokumentgruppe (Datenblatt, Bericht, Scan, GovDocs) und Notizen zu Auffälligkeiten (Unterschiede der Engines, Fehlerbilder) im README oder einer Notizdatei. Ergebnis: Notizen liegen vor.
- [x] 3.3 README um Abschnitt „Viewer" ergänzen (Befehl, Bedienung, Ebenenfarben) und Roadmap-Zeile 4 abhaken. Ergebnis: Abschnitt vorhanden.
