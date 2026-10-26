# Spec Delta

## Purpose

Baut aus den geparsten und angereicherten Seiten einen lokal durchsuchbaren Index -- Volltext und multimodale Embeddings im selben Raum -- und stellt eine Abfrage-Schnittstelle bereit, auf der Retrieval-Qualität gemessen und spätere Suche aufgebaut werden kann.

## ADDED Requirements

### Requirement: Multimodale Embeddings je Seite und Block
Das System SHALL mit EmbeddingGemma 2 für jede Seite ein Text-Embedding des narrativen Inhalts und ein Bild-Embedding der ganzen Seite berechnen, und für jeden angereicherten visuellen Block ein Bild-Embedding des Crops sowie ein Text-Embedding seiner Beschreibung; für Table-Blöcke SHALL zusätzlich ein Text-Embedding des vollen Tabelleninhalts berechnet werden.

#### Scenario: Seite mit Tabelle
- **WHEN** eine Seite einen angereicherten Table-Block enthält
- **THEN** liegen für die Seite ein Text- und ein Bild-Embedding vor, und für den Block ein Bild-, ein Beschreibungs- und ein Inhalts-Embedding

#### Scenario: Seite ohne visuelle Blöcke
- **WHEN** eine Seite keine angereicherten visuellen Blöcke hat
- **THEN** liegen nur das Seiten-Text- und das Seiten-Bild-Embedding vor

### Requirement: Volltextindex über denselben Textkorpus
Das System SHALL einen lokalen Volltextindex über narrativen Text, Tabelleninhalt und Beschreibungen führen, sodass eine wörtliche Suchanfrage Seiten findet, in denen der Begriff in einem dieser Texte vorkommt.

#### Scenario: Wörtlicher Treffer in einer Tabelle
- **WHEN** ein Suchbegriff wörtlich im Inhalt eines Table-Blocks vorkommt
- **THEN** liefert die Volltextsuche die zugehörige Seite als Treffer

### Requirement: Reproduzierbare, inkrementelle Ablage
Das System SHALL den Index reproduzierbar unter `data/results/` ablegen (Embeddings als Array mit zugehörigen Metadaten, Volltextindex als eigene Datei), ohne einen Vektor-Datenbank-Server vorauszusetzen, und SHALL bei einem erneuten Lauf nur neue oder geänderte Seiten ergänzen statt den gesamten Index neu zu berechnen.

#### Scenario: Erneuter Lauf ohne Änderungen
- **WHEN** der Indexlauf erneut startet und keine neuen oder geänderten Seiten vorliegen
- **THEN** wird nichts neu berechnet

#### Scenario: Neues Dokument ergänzt
- **WHEN** ein neues Dokument mit angereicherten Seiten hinzukommt und der Indexlauf erneut startet
- **THEN** werden nur dessen Seiten ergänzt, der bestehende Index für andere Dokumente bleibt unverändert

### Requirement: Abfrage-Schnittstelle
Das System SHALL eine Abfrage-Schnittstelle bereitstellen, die zu einer Text-Query sowohl Volltext- als auch Vektor-Treffer liefert und für jeden Treffer erkennbar macht, aus welchem Signal er stammt; eine Query ohne Treffer SHALL eine leere Liste statt eines Fehlers liefern.

#### Scenario: Query mit Fachbegriff
- **WHEN** eine Text-Query gestellt wird, die sowohl wörtlich vorkommt als auch semantisch verwandten Inhalt trifft
- **THEN** liefert die Abfrage Treffer aus Volltext- und Vektorsuche, jeweils mit Angabe des liefernden Signals

#### Scenario: Keine Treffer
- **WHEN** eine Query zu keinem Inhalt im Index passt
- **THEN** liefert die Abfrage eine leere Liste

### Requirement: Dokument-Level-Embeddings
Das System SHALL zusätzlich zu den Seiten-Embeddings zwei dokumentweite Embeddings je Dokument berechnen -- eines aus Titel und Summary (`document-digest`), eines aus dem vollen Markdown-Digest -- und SHALL sie mit einem Sentinel-Wert statt einer echten Seitenzahl kennzeichnen, sodass sie nicht mit Seiten-Embeddings verwechselt werden.

#### Scenario: Dokument-Embeddings vorhanden
- **WHEN** für ein Dokument Titel/Summary und ein Markdown-Digest vorliegen
- **THEN** enthält der Index für dieses Dokument ein `document_summary`- und ein `document_fulltext`-Embedding, beide ohne Seitenbezug

### Requirement: Sichere Längenbegrenzung für lange Texteingaben
Das System SHALL Texteingaben vor dem Embedding auf eine konservative Zeichengrenze kappen, die nachweislich unterhalb der Länge liegt, an der das Modell auf der verwendeten GPU einen Speicherfehler auslöst, statt die volle Länge unbegrenzt zu übergeben.

#### Scenario: Langes Dokument
- **WHEN** der volle Markdown-Digest eines Dokuments die konfigurierte Zeichengrenze überschreitet
- **THEN** wird nur der gekappte Anfang embedded, und das Embedding wird nicht als vollständige Repräsentation des Dokuments ausgegeben

### Requirement: Konsistente Vektordimension
Das System SHALL alle Embeddings mit derselben Dimension und L2-normalisiert ablegen und beim Laden eines Index mit abweichender Dimension einen Fehler melden statt stillschweigend falsche Ähnlichkeiten zu berechnen.

#### Scenario: Index mit falscher Dimension laden
- **WHEN** ein Index geladen wird, dessen gespeicherte Vektordimension von der erwarteten abweicht
- **THEN** meldet das System einen Fehler und lädt den Index nicht
