# Pilot-Ergebnisse (Task 6.1-6.2)

4 Fragen x 2 Varianten (8 Läufe), ausgewählt für Varianz: native PDFs (`ds-lm317`, `ds-ne555`),
ein bekanntes "Trap"-Schaltplan-Beispiel (`ds-tps62130`, 3a), und das eine Dokument mit
degenerierter lokaler Summary (`gd1-001147`, 8a) -- letzteres der direkteste Test, ob die
Summary-Qualität beim Auffinden überhaupt eine Rolle spielt.

## Korrektheit: 8/8 korrekt in beiden Varianten

| Frage | Dokument | Lokal | Cloud |
|---|---|---|---|
| 1a (PSRR) | ds-lm317 | correct | correct |
| 2a (TRIG-Pin) | ds-ne555 | correct | correct |
| 3a (Ausgangskondensator, Schaltplan-Trap) | ds-tps62130 | correct | correct |
| 8a (MAX-Zeile, Tabellen-Trap, degenerierte lokale Summary) | gd1-001147 | correct | correct |

Beide "Trap"-Fragen, an denen im alten `vlm-qa-test`-Experiment lokale VLMs scheiterten (3a:
Qwen3B hallucinierte 100µF; 8a: alle lokalen Modelle griffen einen falschen Tabellenwert), wurden
hier von **beiden** Sandbox-Varianten richtig gelöst -- der Agent grept den Digest-Text, verwirft
explizit Verwechslungswerte (bei 8a: erkennt und verwirft einen Wert aus einem anderen,
ähnlichen Dokument mit der Begründung "that is the highest monthly mean... not the highest daily
mean"), und bestätigt am Seitenbild. Bestätigt die Nutzer-Hypothese: mit echter Suche + Pflicht-
Bild-Verifikation statt blinder Pixel-Interpretation kommt der Agent zuverlässig ans Ziel,
unabhängig von der Summary-Qualität.

## Effizienz: in dieser kleinen Stichprobe kein klares Bild

| Frage | Variante | Tool-Aufrufe | Turns | Kosten |
|---|---|---|---|---|
| 1a | lokal | 2 | 3 | $0.0851 |
| 1a | cloud | 2 | 3 | $0.0948 |
| 2a | lokal | 2 | 3 | $0.0749 |
| 2a | cloud | 2 | 3 | $0.0112 |
| 3a | lokal | 4 | 5 | $0.0979 |
| 3a | cloud | 4 | 5 | $0.0844 |
| 8a | lokal | 5 | 6 | $0.1263 |
| 8a | cloud | 7 | 8 | **$0.1709** |

Kein konsistenter Vorteil einer Variante. Bei 8a brauchte die Cloud-Variante sogar mehr
Tool-Aufrufe (7 vs. 5, inkl. eines Fehlgriffs in ein unverwandtes Dokument `gd1-001371`) und war
teurer. Bei 2a ist der Kostenunterschied ($0.0749 vs. $0.0112) höchstwahrscheinlich ein
Cache-Artefakt (Anthropics Prompt-Caching über aufeinanderfolgende Läufe, nicht die
Sandbox-Variante) -- `cache_creation_input_tokens: 0` beim Cloud-Lauf vs. `8170` beim lokalen
Lauf bestätigt das. **Ehrlicher Befund:** 4 Fragen reichen nicht, um einen Effizienz-Unterschied
von Cache-Rauschen zu trennen; die Tool-Aufruf-Zahl (robuster gegen Caching als die Dollar-Zahl)
zeigt in dieser Stichprobe ebenfalls keinen klaren Unterschied (gleich bei 1a/2a/3a, 7 vs. 5 bei
8a zugunsten lokal).

## Kosten

Pilot gesamt: **$0.7498** (Agent $0.7455 + Judge $0.0043) für 8 Läufe -- deutlich über der
Proposal-Schätzung (die ging von Größenordnung `cloud-document-summary` aus, ~$0.02-0.03/Aufruf;
tatsächlich liegen Agent-Läufe bei $0.01-0.17/Lauf, meist $0.08-0.13). Grund: der feste
Sitzungs-Overhead (Tool-/Skill-Definitionen, Cache-Erstellung) macht einen Großteil der Kosten
aus, nicht die eigentliche Sucharbeit (siehe `design.md`, Task-1.1-Fund: ~$0.10 allein für einen
trivialen "antworte mit OK"-Call). Hochgerechnet auf 20x2=40 Läufe: grob **$3-5** nur für die
Agent-Läufe (Judge-Kosten vernachlässigbar, ~$0.02 für 40 Verdikte).

## Technische Verifikation

Docker-Zugang (redaktiertes `CLAUDE_CONFIG_DIR`), Sandbox-Trennung (gefilterter Embedding-Index,
getrennte Summary-Dateien, keine Ground-Truth-Leckage), Effizienz-Extraktion und Judge liefen
alle 8/8 Mal ohne Fehler durch. Die Kette funktioniert technisch wie geplant.
