# Copilot-Pilotphase

GitHub Copilot Cloud Automations werden im Repository unter **Agents →
Automations** eingerichtet. Sie liegen außerhalb von Git und werden daher hier
als reproduzierbare Konfiguration beschrieben.

Voraussetzung sind ein privates oder internes Repository sowie aktivierte
Copilot-Cloud-Agents und Automationen. Vor dem Pilotstart ist diese Freigabe in
den Repository- und Organisationsrichtlinien zu prüfen.

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
```

**Erlaubte Werkzeuge:** Repository, Issues, Pull Requests, Actions- und
Workflow-Ergebnisse lesen; das laufende Health-Issue kommentieren; erforderliche
monatliche oder quartalsweise Health-Issues anlegen.

**Nicht erlauben:** Code pushen, Branches oder Pull Requests erstellen, Labels
anlegen oder ändern, Issues schließen, Pull Requests freigeben oder mergen.
Die in der Oberfläche benannten Werkzeuge können sich ändern; die Freigabe ist
nach Wirkung zu prüfen und auf diese Liste zu beschränken.

### Erster Testlauf

1. Automation manuell starten und den erzeugten Agent-Log auf eingehaltene Werkzeuge prüfen.
2. Kontrollieren, dass genau das aktuelle Health-Issue kommentiert oder bei Bedarf angelegt wird.
3. Drei Befunde gegen Fundstelle, Unsicherheit, Duplikate und Labelvorschlag prüfen.
4. Kein Label darf ohne menschliche Entscheidung verändert sein.

## Copilot Code Review für Pull Requests

Aktiviere automatische Reviews beim Öffnen eines Pull Requests und beim ersten
Wechsel von Draft zu „Ready for review“. Wähle zunächst **Low** als
Reviewaufwand. Deaktiviere automatische Reviews für Draft-PRs und für neue
Pushes. Bei komplexen oder fachlich kritischen Änderungen wird ein weiterer
Review bewusst manuell angefordert. Auch PR-Reviews folgen der Review Policy
und ersetzen keine menschliche Freigabe.

## Budget und Auswertung

Nach aktuellem GitHub-Planstand enthält Copilot Pro monatlich 1.500 AI Credits;
Cloud-Automationen und Code Reviews verbrauchen dasselbe Kontingent. Die
Automation-Oberfläche dokumentiert keine eigene `max-ai-credits`-Option wie die
Copilot CLI. Die Begrenzung erfolgt daher durch einen wöchentlichen Lauf,
inkrementelle Analyse und nur einen automatischen Review pro freigegebenem PR.

Nach dem ersten vollständigen Monat werden Läufe, verbrauchte AI Credits, neue,
bestätigte und verworfene Befunde, Duplikate, Priorisierung, Pflegeaufwand sowie
das Restbudget für Code Reviews und andere Copilot-Nutzung ausgewertet. Erst
danach wird über höhere Prüftiefe, automatische Labelvergabe oder Copilot Pro+
entschieden.

Aktuelle Produktgrenzen und Preise sind vor der Einrichtung in der
[GitHub-Dokumentation zu Automationen](https://docs.github.com/en/copilot/concepts/agents/cloud-agent/about-automations),
[Code Review](https://docs.github.com/en/copilot/concepts/agents/code-review)
und [AI Credits](https://docs.github.com/en/copilot/concepts/billing/usage-based-billing-for-individuals)
zu prüfen.
