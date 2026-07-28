# Entscheidungsmatrix: Besetzung und Planbarkeit eines Prüfungstags

Diese Matrix entscheidet, ob ein vorgeschlagener Prüfungstag für einen
Tagesabschnitt fachlich bestätigbar ist. Sie konkretisiert den Prozess
[Prüfungshalbjahr planen](../processes/plan-exam-half-year.md).

Alle aktiven und verfügbaren Prüfer:innen werden unabhängig davon gleich
berücksichtigt, ob sie ordentlich oder stellvertretend berufen sind.

## Eingaben

- Prüfungstag und betroffener Tagesabschnitt
- reguläre Prüfungsslots und gegebenenfalls MEP-Slots
- Verfügbarkeit der zugeordneten Prüfer:innen
- reguläre Besetzung nach Vertretungsseite
- Fallback-Besetzung und deren Bestätigungsstatus

## Entscheidungstabelle

| Prüffrage | Wenn | Entscheidung | Folge |
| --- | --- | --- | --- |
| Enthält der Tag mindestens einen regulären Slot? | Nein | Nicht planbar | Regulären Slot ergänzen oder Tag nicht anlegen. |
| Liegt ein MEP-Slot am Ende des Tages? | Nein | Nicht planbar | Reihenfolge der Slots korrigieren. |
| Sind für den Tagesabschnitt mindestens drei reguläre Prüfer:innen verfügbar und zugeordnet? | Nein | Nicht bestätigbar | Besetzung oder Termin anpassen. |
| Sind Arbeitgeber-, Arbeitnehmer- und Schulseite jeweils vertreten? | Nein | Nicht bestätigbar | Besetzung oder Termin anpassen. |
| Ist ein zusätzlicher Fallback zugeordnet? | Nein | Nicht bestätigbar | Fallback anfragen und zuordnen. |
| Ist der Fallback zugleich reguläre:r Prüfer:in desselben Tagesabschnitts? | Ja | Nicht bestätigbar | Andere Person als Fallback zuordnen. |
| Hat der Fallback ausdrücklich bestätigt? | Nein | Noch nicht bestätigbar | Bestätigung abwarten oder Ersatzprozess auslösen. |
| Sind alle vorherigen Prüffragen erfüllt? | Ja | Bestätigbar | Prüfungstag bestätigen und Kalendereinladungen erzeugen. |

## Nicht durch diese Matrix entschieden

- Die Auswahl unter mehreren fachlich zulässigen Planungsvorschlägen.
- Die maximale Anzahl der Prüfungstage pro Woche, Tageskapazität,
  Feiertagsausschluss und Mittagspause; diese begrenzen die Planung bereits
  vor der Besetzungsprüfung.
- Der Umgang mit einem Ausfall nach Bestätigung; dafür gilt die
  [Matrix für Ausfall und Ersatzbesetzung](examiner-absence-and-replacement.md).
