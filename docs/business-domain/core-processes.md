# Kernprozesse des Prüfungsausschusses

Diese Prozesslandkarte beschreibt die fachlichen Kernprozesse eines
Prüfungsausschusses auf oberster Ebene. Sie legt noch keine technische
Umsetzung fest. Detaillierte Prozessbeschreibungen ergänzen künftig pro
Kernprozess Rollen, Verantwortlichkeiten, Fachregeln, Varianten und
Nachweise.

```mermaid
flowchart LR
  A["Prüfungshalbjahr planen"] --> B["Zulassung und Anträge bewerten"]
  B --> C["Schriftliche Prüfungen organisieren"]
  C --> D["Mündliche Prüfung planen und durchführen"]
  D --> E["Prüfungsleistungen bewerten"]
  E --> F["Ergebnis feststellen, dokumentieren und bekanntgeben"]
```

Die Darstellung zeigt die grundlegende fachliche Abfolge. Vorbereitung und
Organisation können sich überlappen; die Bewertungsprozesse haben außerdem
eigene, zeitlich getrennte Schritte.

## Kernprozesse

| Kernprozess | Fachliches Ergebnis |
| --- | --- |
| [Prüfungshalbjahr planen](processes/plan-exam-half-year.md) | Termine, Kapazitäten, Zuständigkeiten und der organisatorische Rahmen des Halbjahrs sind festgelegt. |
| [Zulassung und Anträge bewerten](processes/assess-admission-and-applications.md) | Zu jedem Antrag liegt eine nachvollziehbare Entscheidung mit Auflagen oder Konsequenzen vor. |
| [Schriftliche Prüfungen organisieren](processes/organise-written-examinations.md) | Korrekturaufträge sind verteilt, fristgerecht bearbeitet und die Ergebnisse konsolidiert. |
| [Mündliche Prüfung planen und durchführen](processes/plan-and-conduct-oral-examinations.md) | Prüfungstage, Prüfungsorte, Prüflinge und regelkonforme Besetzungen stehen fest; die Prüfungen werden ordnungsgemäß durchgeführt. |
| [Prüfungsleistungen bewerten](processes/assess-examination-performances.md) | Für Dokumentation, Präsentation und Fachgespräch liegen verbindliche, im Ausschuss festgestellte Bewertungen vor. |
| [Ergebnis feststellen, dokumentieren und bekanntgeben](processes/determine-document-and-communicate-results.md) | Ergebnis, Ausschussbeschluss und Nachweise sind vollständig dokumentiert und den vorgesehenen Empfängerinnen und Empfängern bekanntgegeben. |

## User Journeys für den Frontend-Abgleich

Die User Journeys ergänzen die Prozesssteckbriefe um die Perspektive einer
handelnden Rolle. Sie sind ein Prüfmaßstab für das Frontend, keine zweite
Prozessbeschreibung.

| Journey | Rolle | Zugeordneter Kernprozess |
| --- | --- | --- |
| [Prüfungshalbjahr planen](user-journeys/plan-exam-half-year.md) | Vorsitz und Stellvertretung | Prüfungshalbjahr planen |
| [Verfügbarkeit melden](user-journeys/report-availability.md) | Ausschussmitglied / Prüfer:in | Prüfungshalbjahr planen |
| [Mündlichen Prüfungstag vorbereiten und durchführen](user-journeys/prepare-and-conduct-oral-examination-day.md) | Prüfer:in | Mündliche Prüfung planen und durchführen |
| [Dokumentation individuell bewerten](user-journeys/assess-documentation.md) | Prüfer:in | Prüfungsleistungen bewerten |
| [Präsentation und Fachgespräch bewerten](user-journeys/assess-presentation-and-expert-interview.md) | Prüfer:in | Prüfungsleistungen bewerten |
| [Ergebnis gemeinsam feststellen](user-journeys/determine-results.md) | Ausschussmitglied | Ergebnis feststellen, dokumentieren und bekanntgeben |

## Entscheidungsmatrizen

| Matrix | Zugeordneter Kernprozess |
| --- | --- |
| [Besetzung und Planbarkeit eines Prüfungstags](decision-matrices/exam-day-staffing-and-feasibility.md) | Prüfungshalbjahr planen |
| [Ausfall und Ersatzbesetzung](decision-matrices/examiner-absence-and-replacement.md) | Mündliche Prüfung planen und durchführen |

## Bewertungsprozess für Prüfungsleistungen

Bewertungen folgen stets zwei getrennten fachlichen Vorgängen:

1. Jede Prüferin und jeder Prüfer bewertet die jeweilige Prüfungsleistung
   zunächst individuell.
2. Der Ausschuss berät anschließend und stellt eine gemeinschaftliche
   Gesamtbewertung fest.

Die Einzelbewertung und die gemeinschaftliche Gesamtbewertung dürfen zeitlich
getrennt stattfinden. Erst die gemeinschaftlich festgestellte Bewertung ist
das verbindliche Ergebnis des Ausschusses.

### Dokumentation

Die Dokumentation wird vor dem Prüfungstag abgegeben und liegt dem Ausschuss
rechtzeitig vor. Die Prüferinnen und Prüfer nehmen ihre Einzelbewertungen daher
vor dem Prüfungstag vor. Am Prüfungstag berät der Ausschuss darüber und stellt
die gemeinschaftliche Gesamtbewertung der Dokumentation fest.

### Präsentation und Fachgespräch

Präsentation und Fachgespräch finden am Prüfungstag statt. Die Prüferinnen und
Prüfer bewerten beide Leistungen dort jeweils zunächst individuell. Noch am
Prüfungstag berät der Ausschuss die Einzelbewertungen und stellt die
gemeinschaftliche Gesamtbewertung fest.

```mermaid
flowchart LR
  D["Dokumentation abgegeben"] --> DE["Individuell bewerten\nvor dem Prüfungstag"]
  DE --> DG["Gemeinschaftlich bewerten\nam Prüfungstag"]

  P["Präsentation durchführen"] --> PE["Individuell bewerten\nam Prüfungstag"]
  PE --> PG["Gemeinschaftlich bewerten\nam Prüfungstag"]

  F["Fachgespräch durchführen"] --> FE["Individuell bewerten\nam Prüfungstag"]
  FE --> FG["Gemeinschaftlich bewerten\nam Prüfungstag"]

  DG --> G["Verbindliche Bewertungen\naller Leistungsbestandteile"]
  PG --> G
  FG --> G
```

Eine Gesamtbewertung der Prüfungsleistung kann erst festgestellt werden, wenn
die gemeinschaftlichen Bewertungen von Dokumentation, Präsentation und
Fachgespräch vorliegen.

Die in der Tabelle verlinkten Prozesssteckbriefe beschreiben die Kernprozesse
mit ihren Eingaben, Rollen, Regeln und Ergebnissen genauer.
