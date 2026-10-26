# Stichprobe: lokale vs. Cloud-Summary (Task 6.3)

5 Dokumente von Hand verglichen (lokale `<doc>.summary.json` vs. `<doc>.cloud_summary.json`),
beide aus demselben Markdown-Digest erzeugt.

## ds-lm317 (Datenblatt)
- Lokal: `status: ok`, inhaltlich korrekt und schon brauchbar konkret (Spannungsbereich, Line-/Load-Regulation-Werte), trailt aber am Ende in eine reine Package-Namen-Aufzählung ab.
- Cloud: zusätzlich Hersteller (Texas Instruments) benannt, konkrete Package-Typen (SOT-223, TO-263, TO-220) im Fließtext statt Aufzählungs-Trailing, erwähnt explizit die Device-Vergleichstabelle.
- **Befund**: kleiner, aber klarer Unterschied -- lokal war hier schon ordentlich, Cloud etwas präziser/strukturierter.

## ds-tps5430 (Datenblatt)
- Lokal: `status: ok`, aber durchgehend vage -- "input voltage ranges, output current capabilities, efficiency" ohne eine einzige Zahl.
- Cloud: 100 mΩ High-Side-MOSFET, 3 A Ausgangsstrom, 500 kHz Schaltfrequenz, 5.5-36 V (TPS5430) bzw. 5.5-23 V (TPS5431), 8-Pin-SOIC-PowerPAD-Gehäuse.
- **Befund**: deutlicher Unterschied -- genau das vorhergesagte Muster (lokal vage bei Zahlen, Cloud konkret).

## ds-tlv9062 (Datenblatt)
- Lokal: `status: ok`, aber verrauschter Titel (führende Doppelpunkte als Parsing-Artefakt) und ohne eine einzige Kennzahl.
- Cloud: 1.8-5.5 V Versorgungsbereich, 10 MHz Bandbreite, <1 µA Shutdown-Strom, zusätzlich konkrete Zielanwendungen (E-Bikes, Rauchmelder, HVAC, Wearables), die lokal gar nicht auftauchen.
- **Befund**: deutlicher Unterschied, sowohl inhaltlich (Zahlen) als auch formal (sauberer Titel).

## gd1-001147 (GovDocs-Report, USGS-Pegelstandsdaten)
- Lokal: `status: degenerate` -- keine Summary vorhanden (bekannter Totalausfall, einer der 15/73).
- Cloud: vollständige, konkrete Summary (genaue Örtlichkeit, Wasserjahr, Vergleichszeiträume 1958-1960 vs. 1961-1999 vor/nach Regulierung).
- **Befund**: größter Unterschied in dieser Stichprobe -- von "nichts" zu einer inhaltlich dichten Summary.

## ntrs-19960015541 (NASA-Report)
- Lokal: `status: ok`, Thema korrekt erfasst, aber ohne bibliografische Details.
- Cloud: zusätzlich exakte Dokumentnummer (NASA TM 110382), Datum (Februar 1996), vollständige Autorenliste und Institutsaffiliationen.
- **Befund**: lokal schon inhaltlich richtig, Cloud liefert zusätzliche, überprüfbare Metadaten.

## Gesamtbild
In dieser Stichprobe war die Cloud-Summary in allen 5 Fällen mindestens gleichwertig, in 3/5
(`ds-tps5430`, `ds-tlv9062`, `gd1-001147`) deutlich besser -- entweder weil die lokale Variante
komplett ausfiel (`gd1-001147`) oder weil sie bei konkreten technischen Werten vage blieb, wo die
Cloud-Variante Zahlen nennt. Kein Fall, in dem die Cloud-Variante schlechter oder falsch wäre.
Das deckt sich mit der Einschätzung aus der ursprünglichen Qualitätsbewertung (20 % lokale
Totalausfälle, systematische Vagheit bei dichten technischen Inhalten) und mit dem
VQA-Experiment-Befund (`experiments/vlm-qa-test/`), dass Gemini 4 Argon gerade bei genau dieser
Art von Inhalt deutlich zuverlässiger ist. Das ist eine kleine, nicht-systematische Stichprobe --
die eigentliche Messung bleibt `retrieval-eval` (Roadmap #7).
