# Review Policy

## Zweck und Geltungsbereich

Reviews ergänzen die deterministischen Prüfungen in CI und `task quality`. Sie
beurteilen nachvollziehbar Architektur, Wartbarkeit, Teststrategie,
Dokumentation, fachliche Konsistenz, Betriebsfähigkeit, Abhängigkeiten sowie
den Abgleich von Roadmap, Zielbild und Umsetzung. Diese Policy gilt
gleichermaßen für menschliche und agentische Reviewer.

Linting, Formatierung, Build, automatisierte Tests, Coverage und Security-Gates
bleiben Aufgabe der vorhandenen lokalen Prüfungen und der CI. Ein Review
wiederholt diese Checks nicht, sondern bewertet ihre Aussagekraft, erkennbare
Lücken und Folgen für das Projekt.

## Rollen und Grenzen

Autoren und Reviewer prüfen Befunde; Maintainer entscheiden über Priorität,
Issue-Anlage, Umsetzung und Merge. Agentische Reviews liefern Hinweise, aber
keine Freigabe, keine verbindliche fachliche Auslegung und keinen Merge. Sie
dürfen keine nicht dokumentierten fachlichen Regeln erfinden. Fehlt belastbarer
Kontext, kennzeichnen sie dies ausdrücklich als Unsicherheit oder offene Frage.

Ein Review kann nur Repository-Inhalte, GitHub-Artefakte und vorhandene
CI-Ergebnisse beurteilen. Produktiver Betriebszustand, Telemetrie, Backups und
Wiederherstellungen sind ohne entsprechende Evidenz nicht belegbar.

## UX- und Gestaltungsreview

Bei Änderungen an sichtbaren Abläufen wird die folgende Checkliste bezogen auf
den betroffenen Hauptablauf angewendet. Sie ergänzt, aber ersetzt weder die
automatisierten Prüfungen noch die fachliche Freigabe.

| Prüfaspekt | Art der Prüfung | Nachweis und Grenze |
| --- | --- | --- |
| Semantik, programmatischer Name, Tastaturbedienung und technisch messbarer Kontrast | Automatisierte Accessibility-Prüfung, soweit der Prüfumfang dies abdeckt | Test- oder CI-Ergebnis; ein grünes Ergebnis bestätigt keine verständliche Gestaltung oder alle WCAG-Kriterien. |
| Informationshierarchie, Beschriftung, Aktionsgewichtung, Zustände sowie Umbruch und Überlauf auf Desktop und Mobil | Visuelle und UX-Prüfung | Konkrete Betrachtung des geänderten Ablaufs einschließlich Laden, Leerzustand, Erfolg, Fehler, Bestätigung und Abbruch; keine Screenshot-Regression. |
| Fachlich verständliche Begriffe, angemessene Fehlervermeidung und Aufgabenerfolg | Menschliche Bestätigung | Autor:in oder zuständige fachliche Person bestätigt den Kontext; ein Review kann diese Entscheidung nicht stellvertretend treffen. |

Die [Frontend-Richtlinie](../frontend-guidelines.md) benennt die technischen
und gestalterischen Quellen für diese Prüfung. Fehlt ein geeigneter sichtbarer
oder fachlicher Nachweis, wird dies als offene Frage dokumentiert statt aus
Automatisierung oder Designpräferenz abzuleiten.

## Belastbare Befunde und Nachverfolgung

Jeder Befund enthält Qualitätsdimension, konkrete Fundstelle oder Evidenz,
Problem, mögliche Auswirkung, Priorität oder Schwere, Handlungsempfehlung und
Unsicherheit. Bestehende Issues, ADRs und frühere Health-Befunde werden
verlinkt. Allgemeine Stilpräferenzen, unbelegte Vermutungen und bereits
nachverfolgte Duplikate bleiben aus.

Bestätigte oder zur Klärung aufgenommene Befunde werden als normale GitHub
Issues nachverfolgt. Das laufende monatliche Health-Issue mit dem Titel
`Repository Health YYYY-MM` ist der stabile Ort für periodische
Zusammenfassungen; bekannte Befunde werden dort aktualisiert, nicht wöchentlich
neu angelegt. Menschen bestätigen, verwerfen oder schneiden Maßnahmen-Issues.
Zurückweisungen halten kurz die Begründung fest.

Die thematischen Labels klassifizieren ausschließlich den Gegenstand eines
bestätigten oder zur Klärung aufgenommenen Befunds:

| Label | Gegenstand |
| --- | --- |
| `review:architecture` | Architektur, Schichtengrenzen, ADRs, Kopplung und Grundsatzentscheidungen |
| `review:code-quality` | Wartbarkeit, Komplexität, Duplikation, Fehlerbehandlung und technische Schulden |
| `review:documentation` | Fehlende, veraltete oder widersprüchliche Dokumentation |
| `review:domain-drift` | Fachliche Inkonsistenzen sowie Abweichungen von Begriffen, Invarianten oder Abläufen |
| `review:operations` | Betriebsfähigkeit, Konfiguration, Migration, Diagnose, Wiederanlauf und Obsoleszenz |
| `review:usability` | Gebrauchstauglichkeit, Informationshierarchie, Interaktion, Rückmeldung und visuelle Konsistenz |

Die Auswahl bleibt sparsam; mehrere Labels sind nur bei tatsächlich mehreren
Dimensionen zulässig. Labels erfassen weder Autorenschaft noch Bestätigung,
Bearbeitungsstatus, Priorität, Schwere oder PR-Freigabe. Dafür dienen die
normalen GitHub-Mechanismen, Project-Felder, Milestones und Verknüpfungen.

## Rhythmen

Eine wöchentliche Automation ist der einzige periodische Auslöser und arbeitet
gestuft:

- **Wöchentlich:** inkrementeller Abgleich der Änderungen auf `master`, neuer
  ADRs, Dokumentation, Tests, Coverage, Abhängigkeiten, CI-Auffälligkeiten und
  möglicher fachlicher Inkonsistenzen seit dem letzten Lauf.
- **Beim ersten Lauf eines Monats:** zusätzlich vollständiger Health-Review,
  Verdichtung der Wochenbefunde, Abgleich mit Roadmap und offenen Issues sowie
  Abschluss oder Zusammenfassung des Vormonats. Das Health-Issue des neuen
  Monats wird angelegt oder fortgeschrieben.
- **Beim ersten Lauf eines Quartals:** zusätzlich strategischer
  Architektur-, ADR-, Obsoleszenz-, Zielbild-, Fach- und Betriebsabgleich.
  Vorschläge bleiben Vorschläge und ändern weder Dokumentation noch
  Entscheidungen automatisch.

Nach jedem vollständigen Monat werden Anzahl und Qualität der Befunde,
Duplikate, Priorisierung, Pflegeaufwand, AI-Credit-Verbrauch und verbleibendes
Budget ausgewertet. Daraus können Reviewkriterien und Prüftiefe angepasst
werden.

Die konkreten Prüfpunkte stehen in den [Reviewkriterien](kriterien.md).
