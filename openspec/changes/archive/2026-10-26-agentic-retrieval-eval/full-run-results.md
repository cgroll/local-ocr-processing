# Vollauf-Ergebnisse (20 Fragen x 2 Varianten, 40 Läufe)

Nach dem Pilot (`pilot-notes.md`) auf Nutzer-Wunsch über den gesamten `vlm-qa-test`-Fragensatz
ausgeweitet. Alle 40 Läufe technisch erfolgreich (nach zwei Zwischenfällen, siehe "Stolpersteine"
unten), vom Gemini-Judge bewertet.

## Korrektheit: 19/20 korrekt, identisch in beiden Varianten

| Variante | correct | wrong |
|---|---|---|
| lokal | 19 | 1 |
| cloud | 19 | 1 |

Derselbe einzige Fehlerfall in **beiden** Varianten (Frage 6b, "Ground bus"-Pin): der Agent fand
mehrere Tabellen mit unterschiedlichen Pin-Zuordnungen für "Ground bus" auf verschiedenen Seiten
und wählte nicht die von 6a intendierte F2-Logic-Tabelle (Seite 10, korrekt "pin V"), sondern eine
andere (Seite 15, "Pin 1"). Das ist keine Summary-Qualitätsfrage, sondern eine **Mehrdeutigkeit
der Frage selbst**, sobald sie -- anders als im ursprünglichen `vlm-qa-test`-Aufbau mit fest
vorgegebener Seite -- ohne Kontext zu 6a gestellt wird: "Ground bus" taucht in mehreren
RR-Logic-Tabellen mit je eigenem Pin auf, und 6b nennt (anders als 6a) nicht mehr explizit "F2
Logic table". Ehrlich als Grenze des neuen, realistischeren Aufbaus zu nennen, nicht als Fehler
einer Variante.

**Kein Unterschied zwischen lokal und cloud bei der Korrektheit.**

## Effizienz: keine konsistente Richtung

| Variante | ⌀ Tool-Aufrufe | ⌀ Turns | ⌀ besuchte Dokumente | ⌀ Kosten/Lauf | Gesamtkosten |
|---|---|---|---|---|---|
| lokal | 5.00 | 6.10 | 1.10 | $0.1306 | $2.6128 |
| cloud | 5.40 | 6.60 | 1.15 | $0.1221 | $2.4416 |

Cloud brauchte im Schnitt geringfügig *mehr* Tool-Aufrufe/Turns, aber geringfügig *weniger*
Kosten/Lauf -- beide Unterschiede klein genug, um im Rauschen (Cache-Effekte, siehe
`pilot-notes.md`) unterzugehen, nicht systematisch in eine Richtung. Größte Einzelabweichung:
Frage 5b (lokal 10, cloud 20 Tool-Aufrufe) -- zugunsten lokal, also der Gegenrichtung der
Hypothese. Im Schnitt besuchte der Agent in beiden Varianten nur ~1,1 Dokumente je Frage -- er
fand das richtige Dokument fast immer direkt, ohne breite Exploration über mehrere Kandidaten.
Das erklärt vermutlich mit, warum die Dokument-Summary-Qualität hier kaum durchschlägt: bei
Fakten-Lookup-Fragen wie diesen trägt die Seiten-/Volltextsuche den Großteil der Arbeit, die grobe
Dokument-Summary dient nur der Querschnitts-Orientierung, die bei 1,1 besuchten Dokumenten im
Schnitt kaum gebraucht wird.

## Gesamtkosten

**$5.0767** (Agent $5.0544, Judge $0.0223) für 40 Agent-Läufe + 40 Judge-Bewertungen -- am oberen
Rand der aus dem Pilot hochgerechneten $3-5, wegen der zwei Nachläufe (siehe unten).

## Stolpersteine (während des Vollaufs gefunden und behoben)

1. **`max_buffer_size` zu klein:** Default (1 MB) der Claude Agent SDK reicht nicht für große
   gescannte Seitenbilder (`gd1-001028` S. 1: 3,1 MB PNG, ~4,2 MB base64) -- brach mit
   `CLIJSONDecodeError` den gesamten Lauf ab (kein Einzelfehler, sondern Prozessabsturz). Fix:
   `max_buffer_size=32_000_000` in `run_agent.py` (siehe `design.md`).
2. **Session-Rate-Limit (OAuth-Abo) während des Laufs erreicht**, 6 Läufe (9b, 10a, 10b x 2
   Varianten) schlugen mit "You've hit your session limit" fehl -- nach Reset erfolgreich
   nachgeholt.
3. **OAuth-Token des redaktierten `CLAUDE_CONFIG_DIR`-Snapshots wurde während des mehrstündigen
   Laufs ungültig** ("OAuth token revoked") -- vermutlich weil die echte, parallel laufende
   Host-Session ihr eigenes Token in der Zwischenzeit rotierte und den kopierten Refresh-Token
   invalidierte. Fix: Snapshot kurz vor dem letzten Nachlauf neu aus der aktuell gültigen
   Host-Session gezogen. **Für künftige, noch längere/automatisierte Läufe** wäre eine robustere
   Lösung nötig (z. B. ein dedizierter API-Key statt eines geteilten OAuth-Snapshots) -- für
   diesen einmaligen Vergleichs-Spike war das manuelle Neuziehen ausreichend.

## Fazit

Mit einem Agenten, der frei im Sandbox-Corpus suchen darf und vor der finalen Antwort das
Seitenbild prüfen muss, ist die Dokument-Summary-Qualität (lokal vs. Cloud) für **weder
Korrektheit noch Such-Effizienz** ein messbarer Faktor in diesem 20-Fragen-Satz -- bestätigt die
ursprüngliche Nutzer-Hypothese ("ich traue dem Agenten sowieso zu, dass er ans Ziel kommt").
Das ist ein ehrliches Nullresultat für den Summary-Qualitäts-Vergleich, aber ein positiver Befund
für die Gesamt-Pipeline: Volltext-/Vektorsuche über den angereicherten Seiten-Corpus plus
Pflicht-Bild-Verifikation lösen zuverlässig auch die historisch schwierigsten "Trap"-Fragen
(Schaltplan-Kondensator, Tabellen-MAX-Zeile), an denen reine Pixel-VLMs im ursprünglichen
`vlm-qa-test`-Experiment scheiterten.
