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

Damit bleiben Major-Updates, GitHub-Actions-Updates und nicht
eindeutig klassifizierte Updates in der manuellen Bearbeitung. Das gilt auch
für Security-Updates, sofern Dependabot sie nicht eindeutig als Patch oder
Minor klassifiziert. Direkte und transitive Abhängigkeiten werden gleich
behandelt.

Die Automation verwendet ausschließlich Squash-Merges. Sie aktiviert die
GitHub-Funktion Auto-Merge ohne eigene Mergebarkeitsabfrage oder Warteschleife;
sie pusht nicht nach `master` und umgeht keine Schutzregel. Der Merge findet
erst statt, wenn GitHub Konfliktfreiheit, das aktive Ruleset, aktuelle Basis,
aufgelöste Review-Konversationen und die zu diesem Pull Request ausgewählten
CI-Gates akzeptiert. Ein neuer Commit oder ein fehlerhafter Check blockiert den
Merge weiterhin.

## Sicherheitsmodell

Dependabot-Workflows mit dem Ereignis `pull_request` erhalten nur ein
schreibgeschütztes Token. Der Auto-Merge-Workflow nutzt deshalb
`pull_request_target` und die minimal erforderlichen Rechte `contents: write`
und `pull-requests: write`. Er checkt weder den Pull-Request-Branch aus noch
führt er daraus Code aus. Die Workflowdefinition stammt immer aus dem
Zielbranch; Klassifikation und Auto-Merge-Anmeldung verwenden nur verifizierte
Dependabot-Metadaten und die GitHub API.

Wird ein geeigneter Pull Request nicht automatisch angemeldet, sind zuerst der
Workflowlauf, die ausgegebenen Metadaten und die Repository-Option
`Allow auto-merge` zu prüfen. Nicht geeignete Pull Requests
bleiben normal manuell prüf- und mergebar.
