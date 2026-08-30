# Dependabot-Aktualisierungen

Dependabot erstellt wöchentlich Pull Requests für uv, npm und GitHub Actions.
Angular und Taiga UI bleiben in den in `.github/dependabot.yml` definierten Gruppen gebündelt.

Technisch gekoppelte Versions- und Sicherheitsupdates werden ebenfalls gemeinsam vorgeschlagen:

- Die Gruppen `codeql` und `codeql-security` bündeln alle verwendeten `github/codeql-action/*`-Komponenten.
- Die Gruppen `frontend-linting` und `frontend-linting-security` bündeln `eslint`,
  `@eslint/js`, `eslint-config-prettier`, `typescript-eslint`,
  `@typescript-eslint/eslint-plugin` und `@typescript-eslint/parser`.
- Die Gruppen `vitest` und `vitest-security` bündeln `vitest` und `@vitest/coverage-v8`.

Versions- und Sicherheitsupdates der jeweiligen Familie bleiben damit konsistent,
ohne Angular, Taiga UI oder unabhängige Werkzeuge zusammenzufassen.
Die Gruppierung ändert nicht die Auto-Merge-Regel:
GitHub-Actions-Updates bleiben manuell,
während qualifizierte npm-Patch- und -Minor-Updates den bestehenden Auto-Merge-Weg nutzen dürfen.

## Ablösung veralteter Einzel-PRs

Eine Änderung an `.github/dependabot.yml` aktualisiert bestehende Einzel-PRs nicht rückwirkend.
Für die aktuelle Umstellung sind deshalb #428, #515 und #518 als von der CodeQL-Gruppe #544
abzulösende Einzel-PRs zu behandeln.
Die Einzel-PRs #519 und #520 werden erst durch einen künftig erscheinenden
`frontend-linting`-Gruppen-PR abgelöst.

Der jeweilige Gruppen-PR wird kontrolliert geprüft:

1. Der PR enthält alle erwarteten Komponenten der jeweiligen Familie.
2. Die Zielversionen und der Diff decken die jeweils veralteten Einzel-PRs vollständig ab.
3. CI ist erfolgreich,
   und bei der CodeQL-Gruppe bleibt der Auto-Merge-Workflow übersprungen.

Erst danach werden die ersetzten Einzel-PRs mit einem Verweis auf den Gruppen-PR geschlossen.
Die Einzel-PRs werden nicht manuell editiert oder vorzeitig geschlossen,
damit kein Update verloren geht und Dependabot den Ersatz eindeutig nachvollziehen kann.

## Automatischer Lebenszyklus

Der Workflow `Dependabot auto-merge` meldet ausschließlich Pull Requests für Auto-Merge an, die alle folgenden Bedingungen erfüllen:

- Autor und auslösender Akteur sind `dependabot[bot]`.
- Das Ziel ist der Standardbranch des Repositorys.
- Die verifizierten Dependabot-Metadaten nennen das Ecosystem `npm` oder `uv`.
- Der höchste SemVer-Sprung des Pull Requests ist Patch oder Minor.

Damit bleiben Major-Updates, GitHub-Actions-Updates und nicht eindeutig klassifizierte Updates in der manuellen Bearbeitung.
Das gilt auch für Security-Updates, sofern Dependabot sie nicht eindeutig als Patch oder Minor klassifiziert.
Direkte und transitive Abhängigkeiten werden gleich behandelt.

Die Automation verwendet ausschließlich Squash-Merges.
Sie aktiviert die GitHub-Funktion Auto-Merge ohne eigene Mergebarkeitsabfrage oder Warteschleife; sie pusht nicht nach `master` und umgeht keine Schutzregel.
Der Merge findet erst statt, wenn GitHub Konfliktfreiheit, das aktive Ruleset, aktuelle Basis, aufgelöste Review-Konversationen und die zu diesem Pull Request ausgewählten CI-Gates akzeptiert.
Ein neuer Commit oder ein fehlerhafter Check blockiert den Merge weiterhin.

## Sicherheitsmodell

Dependabot-Workflows mit dem Ereignis `pull_request` erhalten nur ein schreibgeschütztes Token.
Der Auto-Merge-Workflow nutzt deshalb `pull_request_target` und die minimal erforderlichen Rechte `contents: write` und `pull-requests: write`.
Er checkt weder den Pull-Request-Branch aus noch führt er daraus Code aus.
Die Workflowdefinition stammt immer aus dem Zielbranch; Klassifikation und Auto-Merge-Anmeldung verwenden nur verifizierte Dependabot-Metadaten und die GitHub API.

Wird ein geeigneter Pull Request nicht automatisch angemeldet, sind zuerst der Workflowlauf, die ausgegebenen Metadaten und die Repository-Option `Allow auto-merge` zu prüfen.
Nicht geeignete Pull Requests bleiben normal manuell prüf- und mergebar.
