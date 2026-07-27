# Copilot-Pilotphase

GitHub Copilot Cloud Automations werden im Repository unter **Agents →
Automations** eingerichtet. Sie liegen außerhalb von Git und werden daher hier
als reproduzierbare Konfiguration beschrieben.

Voraussetzung sind ein privates oder internes Repository sowie aktivierte
Copilot-Cloud-Agents und Automationen. Die Freigaben in den Repository- und
Organisationsrichtlinien bleiben vor jeder wesentlichen Änderung zu prüfen.

## Wöchentliche Automation

Empfohlen ist ein wöchentlicher Lauf am Dienstagvormittag um 09:00 Uhr
Europe/Berlin. Er reduziert Kollisionsrisiken mit Wochenbeginn und hält genügend
Zeit für die Auswertung im selben Arbeitszyklus.

**Name:** `lzug repository health review`

**Prompt:**

```text
Führe den gestuften Repository-Health-Review nach
docs/developers/reviews/index.md und docs/developers/reviews/kriterien.md aus.
Prüfe wöchentlich nur Änderungen seit dem letzten Lauf auf master. Ergänze beim
ersten Lauf eines Monats den vollständigen Monatsreview und beim ersten Lauf
eines Quartals den strategischen Quartalsreview. Aktualisiere das laufende
Health-Issue statt Duplikate anzulegen; verwende konkrete Evidenz, benenne
Unsicherheit und verlinke bestehende Issues oder ADRs. Schlage für bestätigte
Befunde passende review:-Labels vor, vergib oder ändere sie aber nicht. Nimm
keine Repositoryänderungen vor und erstelle oder merge keine Pull Requests.
Prüfe Quellenverweise vor der Befundableitung auf Nummer, Titel und fachlichen
Zusammenhang. Wiederhole keine bereits durch bestehende Issues abgedeckten
Befunde. Mangelnde Evidenz, ungeprüfte Dokumentationsbereiche oder vermutete
Termine sind offene Fragen oder Hinweise, keine bestätigten Befunde.
```

**Erlaubte Werkzeuge:** Repository, Issues, Pull Requests, Actions- und
Workflow-Ergebnisse lesen; das laufende Health-Issue kommentieren; erforderliche
monatliche oder quartalsweise Health-Issues anlegen.

**Nicht erlauben:** Code pushen, Branches oder Pull Requests erstellen, Labels
anlegen oder ändern, Issues schließen, Pull Requests freigeben oder mergen.
Die in der Oberfläche benannten Werkzeuge können sich ändern; die Freigabe ist
nach Wirkung zu prüfen und auf diese Liste zu beschränken.

## Copilot Code Review für Pull Requests

Für dieses private Repository im persönlichen GitHub-Konto ist ein
Repository-Ruleset nicht durchsetzbar. Die automatischen Reviews werden deshalb
über die persönliche Copilot-Einstellung **Automatic Copilot code review**
ausgelöst und gelten für eigene neue Pull Requests. Der Reviewaufwand ist
**Low**, und die Repository-Instruktionen sind aktiviert. Entwurfs-PRs und neue
Pushes erhalten keinen automatischen erneuten Review. Bei komplexen oder
fachlich kritischen Änderungen wird ein weiterer Review bewusst manuell
angefordert. Auch PR-Reviews folgen der Review Policy und ersetzen keine
menschliche Freigabe.

## Laufender Pilotbetrieb

Nach jedem Lauf wird der Bericht im aktuellen Health-Issue menschlich
triagiert. Nur konkret belegte, nicht bereits abgedeckte Befunde werden als
Maßnahmen-Issue erfasst oder an einem bestehenden Issue klassifiziert.
Verworfene Hinweise, Duplikate und fehlerhafte Quellenverweise erhalten dort
eine kurze Begründung.

Am Ende jedes vollständigen Monats wird zusätzlich ausgewertet:

- Anzahl der Läufe und der verbrauchten AI Credits,
- bestätigte, verworfene und doppelte Befunde,
- Zeitaufwand für die Triage,
- Qualität der Quellenverweise und der Unsicherheitskennzeichnung,
- verbleibendes Budget für PR-Reviews und andere Copilot-Nutzung.

## Budget und Auswertung

Nach aktuellem GitHub-Planstand enthält Copilot Pro monatlich 1.500 AI Credits;
Cloud-Automationen und Code Reviews verbrauchen dasselbe Kontingent. Die
Automation-Oberfläche dokumentiert keine eigene `max-ai-credits`-Option wie die
Copilot CLI. Die Begrenzung erfolgt daher durch einen wöchentlichen Lauf,
inkrementelle Analyse und nur einen automatischen Review pro freigegebenem PR.

Erst nach der Monatsauswertung wird über höhere Prüftiefe, automatische
Labelvergabe oder Copilot Pro+ entschieden.

Aktuelle Produktgrenzen und Preise sind vor der Einrichtung in der
[GitHub-Dokumentation zu Automationen](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-automations),
[Code Review](https://docs.github.com/en/copilot/concepts/agents/code-review)
und [AI Credits](https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals)
zu prüfen.
