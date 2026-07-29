# Sicherheitsmeldungen

lzug ist derzeit ein privates Repository und ein ausdrücklich nicht
produktionsreifer Quellcode-Prototyp. Es gibt deshalb keine zugesicherte
Sicherheits- oder Supportabdeckung für produktive Installationen.

## Unterstützte Stände

Aktuell wird ausschließlich der jeweils freigegebene Stand von `master` im
Rahmen der Entwicklung bewertet. Es gibt noch keine veröffentlichten Releases
und keine zugesicherten Sicherheitsupdates für ältere Stände.

## Sicherheitslücken melden

Bitte veröffentliche vermutete Sicherheitslücken nicht als GitHub Issue und
teile sie nicht in öffentlichen Pull Requests oder Diskussionen. Nutze nach
Aktivierung der Repository-Funktion den privaten Meldeweg für
Sicherheitslücken (GitHub Private Vulnerability Reporting). Bis dahin wende
dich vertraulich an den Repository-Maintainer über GitHub und veröffentliche
keine technischen Details.

Eine Meldung sollte, soweit ohne Gefährdung möglich, den betroffenen Commit
oder Pfad, eine Beschreibung der Auswirkung, reproduzierbare Schritte und eine
Einschätzung der Schwere enthalten. Zugangsdaten, Tokens und personenbezogene
Daten dürfen nicht mitgesendet werden.

Meldungen werden nach bestem Vermögen geprüft. Eine Eingangsbestätigung,
zeitliche Behebung oder Veröffentlichung eines Advisories kann derzeit nicht
zugesichert werden.

## Technische Baseline

- Der CI-Workflow besitzt ausschließlich die für den Lauf erforderlichen
  lesenden Repository-Rechte.
- Die externe Action `astral-sh/setup-uv` ist auf einen konkreten Commit-SHA
  gepinnt. GitHub-eigene Actions folgen ihren gepflegten Major-Tags.
- Dependabot überwacht Python-, npm- und GitHub-Action-Abhängigkeiten.
- Der Produktionsaudit für npm-Abhängigkeiten ist Bestandteil der CI. Eine
  offene Warnung in einer ausschließlich für die Entwicklungsumgebung
  verwendeten transitiven Abhängigkeit ist bewertet und wird nicht durch eine
  gelockerte Prüfung verborgen.
- Secret Scanning, Push Protection und Code Scanning werden vor dem
  Sichtbarkeitswechsel geprüft und, sobald die Repository-Sichtbarkeit und der
  GitHub-Tarif dies erlauben, aktiviert. Der abschließende Nachweis gehört zu
  #194 und #195.

Vor einer öffentlichen Freigabe werden außerdem Repository-Einstellungen,
Actions-Berechtigungen, Secrets, Environments, Deploy Keys, Webhooks,
Collaborators, Logs und Artefakte separat geprüft. Dieses Dokument ersetzt
keine produktive Betriebs- oder Datenschutzfreigabe.

## Sicherheitsgrenzen des Prototyps

- Die Anwendung enthält keine produktive Authentifizierung oder Autorisierung.
- Demo- und Testdaten müssen synthetisch bleiben.
- Das Projekt ist keine offizielle Anwendung oder Veröffentlichung einer IHK.
- Self-Hosting, Containerbetrieb, öffentliche Demo und produktive Nutzung sind
  durch dieses Dokument nicht zugesichert; sie gehören zum getrennten Release-
  und Betriebsgate in Epic #113.
