# Design

## Context

Siehe `proposal.md` -- Why/What Changes für die Motivation. Ausgangslage in Zahlen (Stand der beiden Spikes unter `experiments/`):

- `pymupdf`, `layout`, `ocr`: 405/405 Seiten, 0 Fehler. 341/405 Seiten haben über `pymupdf` einen Textlayer, die restlichen 64 (reine Scans) nicht.
- `vl` (PaddleOCR-VL-1.6): nur 30/405 Seiten erfolgreich (5 Dokumente). Auf zwei weiteren, eigens für den Spike geparsten Dokumenten (Schaltplan+Graph-Seite, dichte Zahlentabelle) lief `vl` auf **allen** Seiten in den 180s-Timeout -- reproduzierbar im echten `docparse.parse`-Pfad, kein Harness-Artefakt.
- `experiments/multimodal-repr-test/`: Qwen2.5-VL-7B-Instruct (4-bit bnb) lieferte für 2 Beispielseiten verlässliche, themenbezogene Beschreibungen von Table-/Chart-/Figure-Crops; EmbeddingGemma 2 richtete Bild, Beschreibung und Volltext im gemeinsamen 768-dim Raum korrekt aus (9/9 Cross-Modal-Treffer).
- `experiments/vlm-qa-test/raw_qwen7b.json`: derselbe Qwen2.5-VL-7B-Lauf maß `vram_peak_nvidia_smi_mib: 7769` -- das Modell allein beansprucht damit mehr als das Registry-Budget von 7680 MB (8192 MB minus 512 MB Reserve). Das ist eine reale Einschränkung für den neuen `describe`-Baustein, nicht nur eine Schätzung.

## Goals / Non-Goals

**Goals:**
- Ein lauffähiger, über alle 405 Seiten reproduzierbarer Such-Index (Volltext + multimodale Embeddings), den `retrieval-eval` als Grundlage nehmen kann.
- Eine Anreicherungsstufe, die unabhängig von `vl`s Verfügbarkeit funktioniert (da `vl` nicht verlässlich für alle Dokumente läuft).
- Eine VRAM-sichere Erweiterung der Modell-Registry um einen sechsten Baustein, ohne die bestehende 8-GB-Garantie zu gefährden.

**Non-Goals:** siehe `proposal.md` -- Nicht-Ziele. Zusätzlich auf Design-Ebene:
- Keine Entscheidung, WIE Volltext- und Vektor-Treffer zu einem einzigen Ranking fusioniert werden (Reciprocal-Rank-Fusion, gewichtete Summe, o. ä.) -- das ist Tuning-Arbeit für `retrieval-eval`, hier werden beide Signale nur nebeneinander mit Herkunft ausgegeben.
- Keine Persistenzschicht, die über flache Dateien hinausgeht (kein FAISS, kein Datenbankserver) -- bei ~500-1000 Vektoren ist Brute-Force-Cosine-Similarity in-process schnell genug.

## Decisions

### Textquelle: `pymupdf` + `ocr`-Fallback, `vl` optional für Tabellen
`pymupdf` deckt 405/405 Seiten ab (0 Fehler) und liefert für 341 Seiten echten Text; die 64 reinen Scans fallen auf `ocr`-Zeilen zurück (ebenfalls 405/405). `vl` wird nur dort zusätzlich für Table-Blöcke genutzt, wo ein erfolgreiches Ergebnis bereits vorliegt -- es wird nicht erneut angefordert oder vorausgesetzt, weil es auf bestimmten Dokumenten reproduzierbar in den Timeout läuft. Alternative (auf vollständige `vl`-Abdeckung warten oder `vl` für alle Seiten erzwingen) wurde verworfen: das würde den Such-Index von einer unzuverlässigen Komponente abhängig machen und den Rollout blockieren.

### Neuer Baustein `describe`: Qwen2.5-VL-3B als Default, nicht 7B
Der Spike nutzte Qwen2.5-VL-7B-Instruct und maß dabei eine VRAM-Spitze von 7769 MB (`experiments/vlm-qa-test/raw_qwen7b.json`) -- mehr als das nutzbare Budget von 7680 MB (8192 MB minus 512 MB Reserve). Selbst bei strikt sequenziellem Betrieb (kein anderes Modell gleichzeitig geladen) bleibt praktisch keine Marge für Schwankungen oder einen fremden Prozess, der schon etwas GPU-Speicher belegt (der VRAM-Wächter aus `model-lifecycle` berücksichtigt das explizit). Qwen2.5-VL-3B-Instruct lief im selben Test-Set mit vergleichbarer QA-Genauigkeit (15/20 vs. 14/20 bei 7B) und deutlich kleinerem Speicherbedarf. Entscheidung: `describe` startet mit der 3B-Variante als Registry-Default; die tatsächliche VRAM-Spitze SHALL vor dem ersten produktiven Lauf mit `python -m docparse.models smoke describe` gemessen und in der Registry als `vram_mb` eingetragen werden (wie bei den bestehenden Bausteinen, siehe Docstring in `registry.py`: "estimate; measured by smoke"). Die themenbezogene Beschreibungsaufgabe ist einfacher als die präzise Werte-QA, bei der 3B getestet wurde -- das Risiko, dass 3B für Beschreibungen qualitativ zu schwach ist, wird als gering eingeschätzt, aber nicht vorab bewiesen (siehe Risiken).

### Dekorations-Filter: geometrische Heuristik, keine ML-Klassifikation
Der Spike zeigte, dass `layout` auch kleine Marketing-Icons als `figure` markiert. Eine Mindestfläche (konfigurierbar, analog zu den überschreibbaren Parametern anderer Registry-Einträge) reicht, um die im Spike beobachteten Fälle zu entfernen, ohne ein eigenes Klassifikationsmodell zu bauen. Alternative (ML-Klassifikator für "dekorativ vs. inhaltlich") wurde als unverhältnismäßiger Aufwand für dieses Problem verworfen.

### Volltextindex: SQLite FTS5
Lokal, dateibasiert, ohne neue Laufzeit-Abhängigkeit (SQLite ist Teil der Python-Standardbibliothek; FTS5 ist in den meisten Standard-Builds aktiviert, wird aber in einer frühen Aufgabe geprüft). Alternative (eine reine Python-BM25-Bibliothek wie `rapidfuzz`/`whoosh`) wurde verworfen, um keine zusätzliche Abhängigkeit für eine bei 405 Seiten triviale Datenmenge einzuführen; falls FTS5 im venv nicht verfügbar ist, ist ein einfacher Substring-Scan über denselben Textkorpus ein akzeptabler Fallback (bei dieser Datenmenge performant genug).

### Vektor-Ablage: flaches Array + Metadaten-JSON
Kein Vektor-DB-Server (z. B. FAISS, Qdrant). Bei ~500-1000 Vektoren (405 Seiten plus einige hundert visuelle Blöcke) ist Brute-Force-Cosine-Similarity über ein In-Memory-Array schnell genug und braucht keine zusätzliche Infrastruktur. Wird die Datenmenge in einem späteren Change deutlich größer, ist das ein eigenständiges, dann zu begründendes Upgrade.

### Dokument-Digest: Zusammensetzen, nicht generieren
Der Digest entsteht rein mechanisch aus bereits vorhandenen Daten (Engine-Ergebnisse + `page-enrichment`), ohne ein Modell neu aufzurufen. Das unterscheidet ihn bewusst vom früheren Summary-Spike (`experiments/vlm-qa-test/run_summary_keywords.py`): dort generierte ein LLM neuen Text aus wenig Input und brach dabei zweimal erkennbar ein (Wiederholungsschleife bei dünnem Input, stille Unvollständigkeit bei fehlenden Seiten). Weil der Digest nichts neu generiert, sondern nur zusammensetzt, entfällt dieses Risiko -- die Qualität des Digests ist exakt die Qualität der schon vorhandenen, bereits geprüften Bausteine (Text, Beschreibungen, Crops).

### HTML→Markdown-Tabellenkonvertierung: einfacher Parser, Pflicht-Hinweis
Das vorhandene Tabellen-HTML stammt ausschließlich aus den eigenen Adaptern (`vl`, `pymupdf`) und ist dadurch strukturell einfach (`table`/`tr`/`td`, optional `rowspan`/`colspan`) -- ein kleiner, selbst geschriebener Parser reicht, keine allgemeine HTML-Bibliothek nötig. `rowspan`/`colspan` haben in Markdown-Tabellen keine Entsprechung; die Entscheidung ist, Zellinhalte bei Spans unverändert in die implizierte Rasterzelle zu kopieren (keine Zusammenführung), und das -- zusammen mit der ohnehin bekannten Zeilenstruktur-Schwäche aus `pymupdf` (Follow-up A) -- in jedem Fall mit dem in der Spec geforderten Hinweistext zu kennzeichnen, statt eine Korrektheit zu suggerieren, die nicht geprüft ist.

### Rohtext-Liste: Bbox-Overlap-Heuristik
Für jeden visuellen Block werden `pymupdf`- und `ocr`-Blöcke derselben Seite aufgenommen, deren Box die Box des visuellen Blocks zu einem relevanten Anteil überlappt (Schnittfläche geteilt durch die Fläche des *kleineren* der beiden Blöcke, Schwellenwert konfigurierbar, siehe "Open Questions") -- nicht nur Blöcke, die vollständig innerhalb liegen, weil Textzeilen oft knapp über den Rand eines Schaltplans hinausragen. Das ist eine reine Geometrie-Heuristik ohne semantische Prüfung, ob ein Fragment inhaltlich wirklich zum Block gehört (z. B. könnte ein eng benachbartes, aber nicht wirklich zugehöriges Label mit auftauchen) -- deshalb die in der Spec geforderte explizite Kennzeichnung als unverifiziert.

### Titel+Summary-Prompt: Anweisung nach dem Inhalt, nicht davor
Ein erster Versuch (`experiments/digest-summary-test/`) stellte die Anweisung ("Write a title and summary...") vor den Dokumentinhalt, wie bei den kürzeren Prompts im Rest des Projekts üblich. Bei den langen Digest-Texten (7.000+ Tokens) führte das reproduzierbar zu Ausgaben, die nur noch Fragmente vom Ende des Dokuments wiederholten, ohne der Anweisung zu folgen -- ein Rezenz-Effekt: Anweisungen, die weit vor dem Generierungspunkt liegen, verlieren bei einem 3B-Modell an Gewicht gegenüber dem unmittelbar vorausgehenden Text. Entscheidung: Anweisung steht im Prompt nach dem Dokumentinhalt, unmittelbar vor der erwarteten Ausgabe. Verifiziert an drei echten Dokumenten (`ds-lm317`, `ds-tps62130`, `ntrs-19760010918`) -- korrekte, inhaltlich treffende Titel/Summary in allen drei Fällen. Das exakte Format (`TITLE:`/`SUMMARY:`-Zeilen) wird vom Modell nicht zuverlässig eingehalten (mal fehlt die Titelzeile, mal ein kaputtes Tag) -- die Ablage SHALL deshalb tolerant parsen (z. B. erste Zeile als Titel-Fallback), nicht auf exaktes Format bestehen.

### Dokument-Fulltext-Embedding: harte Zeichengrenze gegen CUDA-OOM
EmbeddingGemma 2 setzt kein eigenes Token-Limit (`model.max_seq_length` ist praktisch unbegrenzt) und das Shared-Context-Budget aus der Modell-Doku (8192 Token) ist eine Angabe für die Modellarchitektur, keine Garantie für diese 8-GB-Karte. Empirischer Test am größten vorhandenen Digest (`gd1-001147`, 39.398 Zeichen): 19.839 Tokens liefen noch durch, 21.339 Tokens lösten einen CUDA-Out-of-Memory beim Aufbau der Attention-Maske aus (Versuch, 5,78 GiB zu allozieren) -- ein scharfer Cliff, keine graduelle Verschlechterung, durch den quadratischen Speicherbedarf der Attention über die Sequenzlänge. Entscheidung: `document_fulltext` wird vor dem Encode hart auf 20.000 Zeichen gekappt -- deutlich unterhalb der beobachteten Crash-Schwelle (bei den beobachteten Zeichen/Token-Verhältnissen ca. 12.000-16.000 Tokens), mit Sicherheitsabstand für dichtere Inhalte (z. B. tabellenreiche Seiten mit mehr Satzzeichen pro Token). Alternative (Chunking + Mittelung der Teil-Embeddings über das ganze Dokument) wurde als Lösung für eine spätere Iteration zurückgestellt (siehe Nicht-Ziele) -- für ein erstes, funktionierendes Dokument-Embedding reicht die gekappte Variante, ergänzt durch das ungekappte `document_summary`-Embedding, das die inhaltliche Kernaussage ohnehin abdeckt.

### Spaltenbewusste Lesereihenfolge: geometrische Heuristik mit striktem Guard, kein Layout-Abgleich
Beim Nachgehen der 14 degenerierten Titel/Summary-Fälle fiel ein echter, unabhängiger Datenfehler auf: `bs-f-831f-pdp-8-interface-manual-may65` S. 2 hat zweispaltigen Text, aber `ocr` (PP-OCRv6) liefert Zeilen nur nach Y-Position über die ganze Seite sortiert -- das Ergebnis ist Wortsalat aus beiden Spalten im Reißverschlussmuster. Eine systematische Prüfung über alle 405 Seiten (beide Text-Engines) zeigte: naive Spalten-Clusterung allein liefert zu viele Falsch-Positive (257 von 653 geprüften Seiten), weil Datenblätter mit über die Seite verstreuten Schaltplan-Labels (viele unterschiedliche X-Positionen, aber keine echten Spalten) genauso aussehen wie echte Mehrspalten-Prosa. Mit einem strengeren Filter (genau 2-3 X-Cluster, mindestens 4 Blöcke je Cluster, jeder Cluster deckt mindestens 30% der Seitenhöhe ab, Median-Wortzahl je Block mindestens 3) blieben 16 Seiten in 11 Dokumenten übrig -- überwiegend `ocr`-Quellen, `pymupdf` war kaum betroffen (native PDFs bewahren die Spaltenstruktur in der Blockliste meist schon besser).

Entscheidung: die Spalten-Erkennung arbeitet rein geometrisch auf den Boxen der Textquelle selbst (kein Abgleich mit `layout`s eigenen Boxen trotz der ursprünglichen Idee, das Layout-Modell dafür zu nutzen) -- einfacher, in sich geschlossen, und für das beobachtete Problem (OCR-Zeilen sind schon fein genug granular) ausreichend. Der strenge Guard ist bewusst konservativ: im Zweifel wird NICHT umsortiert, weil ein falsch-positiv umsortierter Schaltplan schlimmer wäre als ein unsortiertes, aber immerhin nicht verschlimmertes Mehrspalten-Dokument.

### pymupdf-Encoding-Fix: gezielt, nicht strukturell
Der beobachtete Fehler (µ wird zu "…") betrifft einen spezifischen Glyph/Encoding-Fall bei der Tabellen-/Textextraktion. Die Entscheidung ist, die konkrete Ursache (Font-Encoding-Tabelle oder Decode-Schritt) gezielt zu beheben, nicht die Tabellenextraktion grundsätzlich umzubauen -- die separat bekannte Zeilenstruktur-Schwäche (mehrere Tabellenzeilen in einer `<td>`) bleibt bewusst unangetastet (siehe Nicht-Ziele). Für den Such-Index ist das vertretbar: um eine Seite über Volltext oder Vektor zu *finden*, muss ein Begriff irgendwo im Text der Seite erscheinen -- welche Tabellenzeile exakt gemeint ist, ist eine Frage des nachgelagerten Lese-/Agentenschritts, nicht des Auffindens.

## Risks / Trade-offs

- **[Risiko]** Qwen2.5-VL-3B liefert für Beschreibungen schlechtere Qualität als die im Spike getestete 7B-Variante → **Mitigation**: nach dem ersten Produktionslauf eine Stichprobe der 3B-Beschreibungen gegen die Spike-Qualität (9/9 Cross-Modal-Treffer) prüfen; falls die Qualität merklich abfällt, ist ein Wechsel auf 7B mit entsprechend engerem VRAM-Budget (ggf. reduziertem `max_new_tokens` oder 8-bit statt 4-bit) eine spätere, eigenständige Entscheidung, keine Blockade für diesen Change.
- **[Risiko]** Die Mindestflächen-Heuristik filtert in bisher ungetesteten Dokumenttypen (z. B. alte Scans mit kleinen, aber inhaltlich wichtigen Abbildungen) falsch → **Mitigation**: Schwellenwert bleibt konfigurierbar; nach dem Vollauf eine Stichprobe gefilterter Blöcke sichten. Kein Blocker, da `retrieval-eval` fehlende Treffer ohnehin aufdeckt.
- **[Risiko]** VLM-Beschreibungen sind bei komplexeren oder unüblichen Inhalten ungenau oder halluziniert (im Spike nur 2 Seiten getestet) → **Mitigation**: eine fehlerhafte Beschreibung verschlechtert die Auffindbarkeit nur des betroffenen Blocks, nicht die Korrektheit des übrigen Index; systematische Messung ist explizit Aufgabe von `retrieval-eval`.
- **[Risiko]** SQLite FTS5 ist im venv nicht kompiliert/aktiviert → **Mitigation**: Prüfung als früher Task; Fallback auf Substring-Scan über denselben Korpus, der bei 405 Seiten performant genug ist.
- **[Risiko]** Der µ-Encoding-Fix deckt nicht alle Varianten des Problems ab (die Ursache könnte vielfältiger sein als der im Spike beobachtete Einzelfall) → **Mitigation**: Fix und verbleibende bekannte Fälle dokumentieren statt einen vollständigen Fix zu versprechen; betrifft nur die Textqualität einzelner Zellen, nicht die Auffindbarkeit der Seite.
- **[Trade-off]** Volltext- und Vektortreffer werden unfusioniert nebeneinander ausgegeben -- für `retrieval-eval` bedeutet das etwas mehr Arbeit beim Vergleich, aber verhindert, dass dieser Change eine Rankingformel festlegt, die noch nicht an echten Fragen validiert ist.
- **[Risiko]** Die Bbox-Overlap-Heuristik der Rohtext-Liste kann bei dicht gesetzten Seiten Fragmente einsammeln, die geometrisch nah, aber inhaltlich nicht zum Block gehören (z. B. eine benachbarte Fußnote) → **Mitigation**: Liste ist explizit als unverifiziert gekennzeichnet (Spec-Pflicht), kein Anspruch auf Vollständigkeit oder Zugehörigkeit; Schwellenwert bleibt konfigurierbar.
- **[Risiko]** Ein Digest über viele Seiten (z. B. ein 23-seitiges Bitsavers-Handbuch) kann sehr lang werden → **Mitigation**: explizite Seitenmarkierungen (Spec-Pflicht) erlauben Navigation/Suche innerhalb der Datei; keine Kürzung oder Zusammenfassung, weil das wieder das Generierungs-Risiko aus dem Summary-Spike einführen würde.
- **[Risiko]** Das `document_fulltext`-Embedding ist für Dokumente über der 20.000-Zeichen-Grenze nur eine Teil-Repräsentation (der Anfang, nicht das ganze Dokument) → **Mitigation**: `document_summary` (ungekappt, aus Titel+Summary) bleibt die primäre Dokument-Repräsentation; `document_fulltext` ist ein Zusatzsignal, dessen Teilcharakter in Code-Kommentar und README dokumentiert ist, keine stillschweigende Einschränkung.
- **[Risiko]** Die 20.000-Zeichen-Grenze wurde an einem Dokument (`gd1-001147`) empirisch ermittelt; andere Dokumente mit noch dichterem Markup (mehr Tabellen, mehr Rohtext-Fragmente pro Zeichen) könnten ein ungünstigeres Zeichen/Token-Verhältnis haben → **Mitigation**: großer Sicherheitsabstand zur beobachteten Crash-Schwelle (20.000 Zeichen vs. beobachtete ~19.800-Token-Grenze, die bei typischem Verhältnis erst bei ~27.000+ Zeichen erreicht würde); zusätzlich schlägt ein zu langer Rest nach Kappung nicht mit OOM fehl, sondern bleibt per Definition unter der Grenze.

## Migration Plan

Rein additiv, keine bestehende Engine-Ausgabe wird entfernt. Empfohlene Reihenfolge:

1. `pymupdf`-Encoding-Fix einbauen, betroffene Seiten mit `--force` neu parsen.
2. `describe`-Baustein in Registry/Loader ergänzen, mit `python -m docparse.models smoke describe` die reale VRAM-Spitze messen und eintragen.
3. Anreicherungslauf (`page-enrichment`) über alle 405 Seiten, wiederholbar wie `parse-runner`.
4. Index-Lauf (`search-index`): Embeddings + Volltextindex über alle angereicherten Seiten, inkrementell ergänzbar.
5. Abfrage-Schnittstelle (CLI, analog zu `docparse.parse`/`docparse.viewer`) für manuelle Stichproben vor `retrieval-eval`.
6. Dokument-Digest über alle 73 Dokumente (unabhängig von Schritt 4/5 -- braucht nur `page-enrichment`, kein Embedding-Modell).
7. Titel+Summary-Generierung über alle 73 Digests (`describe`), danach Dokument-Level-Embeddings (`document_summary`, `document_fulltext`) in den bestehenden Index ergänzt.

Rollback ist unkritisch: alle neuen Daten liegen unter `data/results/` (nicht in Git, wie der Rest von `data/`); ein Fehlschlag bedeutet Löschen und erneutes Laufen lassen, ohne bestehende `pymupdf`/`layout`/`ocr`/`vl`-Ergebnisse zu berühren (außer den gezielt neu geparsten Seiten aus Schritt 1).

## Open Questions

- Exakter `vram_mb`-Wert für `describe` -- wird durch den Smoke-Test in Schritt 2 der Migration bestimmt, ändert nichts an Spec oder Taskzuschnitt.
- Exakter Mindestflächen-Schwellenwert für den Dekorations-Filter -- über Registry-ähnliche Konfiguration nachträglich justierbar, ohne den Anforderungstext zu ändern.
- Ob `describe` dauerhaft bei 3B bleibt oder später auf 7B wechselt -- abhängig von der Stichprobenprüfung in Risiko 1, keine Vorentscheidung nötig.
- Exakter Overlap-Schwellenwert für die Rohtext-Liste des Digests -- über eine Konstante nachträglich justierbar, ändert nichts an Spec oder Taskzuschnitt.
- Ob die 20.000-Zeichen-Grenze für `document_fulltext` später durch Chunking+Mittelung ersetzt wird, um auch bei sehr langen Dokumenten eine vollständige Repräsentation zu bekommen -- bewusst zurückgestellt (Nicht-Ziel), keine Vorentscheidung nötig.
- Ob die 13 verbleibenden (von ursprünglich 14) degenerierten Titel/Summary-Fälle, die nicht durch die Spalten-Reihenfolge erklärt sind, später über eine inhaltliche Grounding-Prüfung (z. B. Wortüberlappung zwischen Summary und Dokument) plus Retry mit echtem Sampling angegangen werden -- empirisch geprüft und bewusst zurückgestellt: Retry mit Standardparametern ist deterministisch (liefert denselben kaputten Output erneut), Retry mit `temperature>0` ändert den Output, aber ersetzt offensichtlich kaputten durch möglicherweise unbemerkt falschen (halluzinierten) Text, ohne zusätzliche Grounding-Prüfung also kein Nettogewinn.
