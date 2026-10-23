# Tasks

## 1. Manifest-Modul

- [x] 1.1 `httpx` zu `pyproject.toml` hinzufügen und `uv sync` ausführen; Prüfung: `uv run python -c "import httpx, pymupdf"` läuft fehlerfrei
- [x] 1.2 `src/docparse/dataset/manifest.py` mit Laden, Speichern und Validierung des CSV-Manifests (Pflichtfelder, eindeutige IDs, erlaubte Rechtestatus-Werte); Prüfung: Unit-Tests für vollständigen Eintrag, fehlendes Feld und doppelte ID mit Zeilen- und Feldangabe in der Fehlermeldung
- [x] 1.3 `summary`-Befehl: Dokumente und Seiten je Gruppe, Anteil nativ/gescannt/gemischt, Tag-Abdeckung mit Lücken-Warnung (Tag unter 5) und Gruppen-Warnung (unter halbem Ziel); Prüfung: Unit-Test mit kleinem Test-Manifest, das beide Warnungen auslöst
- [x] 1.4 `datasets/manifest.csv` mit Kopfzeile anlegen und `data/` in `.gitignore` bestätigen; Prüfung: `uv run python -m docparse.dataset validate` meldet ein leeres, gültiges Manifest

## 2. Download

- [x] 2.1 `download.py` mit Streaming, Größenlimit (Standard 50 MB), PDF-Magic-Check, `.part`-Datei mit atomarem Umbenennen und Ablage in `data/raw/<id>/`; Prüfung: Tests mit lokalem Test-Server für gültiges PDF, HTML-Fehlerseite und übergroße Datei
- [x] 2.2 Pro-Host-Sequenzierung mit Pause (mindestens 1 s) und User-Agent; Prüfung: Test, der bei zwei Einträgen desselben Hosts den Mindestabstand der Anfragen misst
- [x] 2.3 Verifikation und Erstaufnahme: SHA256 und Seitenzahl via PyMuPDF, Abweichung als Fehler, fehlender Hash wird ins Manifest eingetragen; Prüfung: Tests für Hash-Abweichung und Erstaufnahme
- [x] 2.4 Idempotenz und Wiederaufnahme: vorhandene, hashgleiche Dateien überspringen; Prüfung: zweiter Lauf im Test meldet alle Einträge als übersprungen und stellt keine Anfragen
- [x] 2.5 Klassifikation nativ/gescannt/gemischt über Textlayer-Anteil je Seite (Schwellen 0,8 und 0,2) und Seitenobergrenze (Standard 6, Seitenbereich im Manifest); Prüfung: Tests mit einem erzeugten PDF mit Text und einem mit reinem Bildinhalt
- [x] 2.6 Zip-Einträge (`<zip-url>#<eintrag>`): Zip einmal laden (Cache in `data/cache/`), Eintrag mit Größenlimit als `document.pdf` ablegen, Zip nach dem Lauf löschen; Prüfung: Tests mit lokalem Test-Server für zwei Einträge aus einem Zip (ein Zip-Request, Zip danach gelöscht), fehlenden Eintrag und zweiten Lauf ohne neuen Zip-Download

## 3. Kandidatensuche

- [x] 3.1 `candidates`-Befehl mit Adapter für NASA NTRS (Suche, Rechtefeld auswerten) und NIST; Ergebnis in Zwischendatei `data/candidates/<quelle>.csv`; Prüfung: Lauf mit kleinem Limit liefert Kandidaten mit URL und Rechtestatus
- [x] 3.2 Seed-Listen für Hersteller-Datenblätter und Bitsavers (`datasets/seeds/*.txt`) mit URL-Einlesen als Adapter; Prüfung: Befehl liest die Seeds und erzeugt Kandidatenzeilen mit vorbelegtem Rechtestatus
- [x] 3.3 Adapter für GovDocs1 (ohne SafeDocs): Zip laden, PDF-Einträge listen, Zufallsstichprobe mit festem Seed als Kandidaten mit URL `<zip-url>#<eintrag>`; Prüfung: zwei Läufe mit gleichem Seed liefern dieselben Kandidaten
- [x] 3.4 `add`-Befehl übernimmt ausgewählte Kandidaten ins Manifest (Gruppe, Tags, Rechtestatus); Prüfung: Test, dass nur ausdrücklich gewählte IDs übernommen werden

## 4. Datensatz zusammenstellen

- [x] 4.1 Kandidaten sichten und ca. 60–100 Dokumente in den vier Gruppen auswählen (je Tag `table`, `schematic`, `diagram`, `formula`, `plain-text` mindestens fünf); Prüfung: `summary` zeigt keine Gruppen- oder Tag-Warnung
- [x] 4.2 Download des gesamten Datensatzes; Prüfung: Lauf endet ohne Fehler, jedes Manifest-Dokument hat Hash und Seitenzahl, zweiter Lauf überspringt alles
- [x] 4.3 Rechtestatus je Eintrag von Hand gegenprüfen und bestätigen; Prüfung: kein Eintrag mit leerem Rechtestatus, `unknown` bleibt als lokal-nur gekennzeichnet
- [x] 4.4 Stichprobe: von jeder Gruppe zwei Dokumente in einem PDF-Viewer öffnen und Typ-Tags, nativ/gescannt prüfen; Prüfung: Korrekturen sind im Manifest eingetragen
- [x] 4.5 `README.md` um Abschnitt „Datensatz“ ergänzen (Befehle, Gruppen, Rechtehinweis); Prüfung: die dokumentierten Befehle laufen wie beschrieben
- [x] 4.6 Integrationsprüfung: `git status` zeigt nach dem Download keine Dateien unter `data/`; `uv run python -m docparse.dataset validate` und die Tests laufen grün
