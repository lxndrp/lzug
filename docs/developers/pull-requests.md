# Pull-Request-Lifecycle

Issue-Arbeit wird auf einem eigenen Feature-Branch gegen `master` eingereicht.
Die GitHub CLI bildet Titel, Beschreibung, Assignees, Milestone, Project und
Draft-Status nativ ab. `task pr:create` legt dafür nur die einheitlichen
Projektparameter fest und prüft die gewählte Issue-Verknüpfung; ein
zusätzliches Script oder Token ist nicht erforderlich.

## Pull Request erstellen

Zuerst werden die Zuordnungen des Quell-Issues gelesen:

```bash
gh issue view 329 \
  --json assignees,milestone,projectItems \
  --jq '{assignees: [.assignees[].login], milestone: .milestone.title, projects: [.projectItems[].title]}'
```

Die Beschreibung wird aus `.github/pull_request_template.md` abgeleitet. Eine
vollständige Umsetzung enthält eine eigene, ausgefüllte Zeile `Closes #329`.
Bleibt ein ausdrücklich dokumentiertes externes Aktivierungs- oder
Abnahmegate offen, wird stattdessen `Tracks #329` verwendet und
`LINK_MODE=tracks` an `task pr:create` übergeben; der Task akzeptiert nie beide
Varianten stillschweigend.
Bei einer Teilumsetzung wird der Pull Request direkt mit `gh pr create` und
einer nicht schließenden Verknüpfung wie `Related to #329` erstellt; die Task
ist absichtlich vollständigen Issue-Umsetzungen vorbehalten.

Gesetzte Assignees und der Milestone werden als Task-Variablen übergeben. Leere
Issue-Felder werden weggelassen:

```bash
task pr:create \
  ISSUE=329 \
  TITLE='PR-Erstellung standardisieren' \
  BODY_FILE=/tmp/pr-body.md \
  ASSIGNEES=lxndrp \
  MILESTONE=v0.2.0 \
  DRAFT=true
```

`ASSIGNEES`, `MILESTONE` und `DRAFT` sind optional; mehrere Assignees werden
kommasepariert angegeben. Die Task ruft `gh pr create --base master` auf und
ordnet den Pull Request immer dem Project `lzug Roadmap` zu. Sie setzt keine
Project-Felder und erfindet keine im Issue fehlenden Zuordnungen.

Danach werden Verknüpfung und Metadaten am erzeugten Pull Request geprüft:

```bash
gh pr view \
  --json closingIssuesReferences,assignees,milestone,projectItems \
  --jq '{issues: [.closingIssuesReferences[].number], assignees: [.assignees[].login], milestone: .milestone.title, projects: [.projectItems[].title]}'
```

## CI, Review und Closeout

Der Pull Request bleibt bis zum Abschluss der lokalen Prüfungen als Draft
geöffnet. Nach jeder inhaltlichen Änderung werden die betroffenen lokalen
Prüfungen wiederholt und die CI erneut abgewartet. Vor dem Merge sind alle
Review-Threads, allgemeinen Kommentare, Security-Audits, Code-Scanning-Befunde
und automatisierten Hinweise zu prüfen. Sinnvolle Befunde im Issue-Scope werden
umgesetzt; unklare oder sachfremde Befunde werden beantwortet oder eskaliert.

Erst wenn die CI nach den letzten Änderungen erfolgreich ist und alle
relevanten Hinweise geklärt sind, darf ein Maintainer mergen. Agents mergen
nicht selbst. Nach bestätigt erfolgreichem Merge wird zuerst der Issue-Worktree
auf Reständerungen geprüft. Nur ein sauberer Worktree wird entfernt; danach
werden ausschließlich der zugehörige lokale und Remote-Feature-Branch gelöscht
und der Umsetzungstask archiviert.
