# Dependabot-Aktualisierungen

Dependabot erstellt wöchentlich Pull Requests für uv, npm und GitHub Actions.
Angular und Taiga UI bleiben in den in `.github/dependabot.yml` definierten
Gruppen gebündelt.

## Automatischer Lebenszyklus

Der Workflow `Dependabot auto-merge` meldet ausschließlich Pull Requests für
Auto-Merge an, die alle folgenden Bedingungen erfüllen:

- Autor und auslösender Akteur sind `dependabot[bot]`.
- Das Ziel ist der Standardbranch des Repositorys.
- Die verifizierten Dependabot-Metadaten nennen das Ecosystem `npm` oder `uv`.
- Der höchste SemVer-Sprung des Pull Requests ist Patch oder Minor.
- GitHub meldet den Pull Request als konfliktfrei.

Damit bleiben Major-Updates, GitHub-Actions-Updates, Konflikte und nicht
eindeutig klassifizierte Updates in der manuellen Bearbeitung. Das gilt auch
für Security-Updates, sofern Dependabot sie nicht eindeutig als Patch oder
Minor klassifiziert. Direkte und transitive Abhängigkeiten werden gleich
behandelt.

Die Automation verwendet ausschließlich Squash-Merges. Sie aktiviert nur die
GitHub-Funktion Auto-Merge; sie pusht nicht nach `master` und umgeht keine
Schutzregel. Der Merge findet erst statt, wenn das aktive Ruleset den Pull
Request, die Aktualität gegenüber `master`, aufgelöste Review-Konversationen
und alle sechs CI-Checks akzeptiert:

- Backend
- Frontend
- Documentation
- Browser E2E
- Accessibility
- npm production security gate

Ein neuer Commit oder ein fehlerhafter Check blockiert den Merge weiterhin.

## Sicherheitsmodell

Dependabot-Workflows mit dem Ereignis `pull_request` erhalten nur ein
schreibgeschütztes Token. Der Auto-Merge-Workflow nutzt deshalb
`pull_request_target` und die minimal erforderlichen Rechte `contents: write`
und `pull-requests: write`. Er checkt weder den Pull-Request-Branch aus noch
führt er daraus Code aus. Die Workflowdefinition stammt immer aus dem
Zielbranch; Klassifikation, Konfliktprüfung und Auto-Merge-Anmeldung verwenden
nur verifizierte Dependabot-Metadaten und die GitHub API.

Wird ein geeigneter Pull Request nicht automatisch angemeldet, sind zuerst der
Workflowlauf, die ausgegebenen Metadaten, die Mergebarkeit und die
Repository-Option `Allow auto-merge` zu prüfen. Nicht geeignete Pull Requests
bleiben normal manuell prüf- und mergebar.
