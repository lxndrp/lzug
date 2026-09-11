# Hinweise für Coding Agents

Diese Datei enthält die verbindlichen Regeln für Codex und andere Coding Agents
in diesem Repository. Anleitungen für Menschen stehen im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki/Entwicklung), technische
Details im [Entwicklerhandbuch](docs/developers/index.md).

## 1. Kanonischer Stand

- GitHub ist die kanonische Quelle für Aufgaben, Entscheidungen, Abhängigkeiten
und Status.
Der versionierte Code und die technische Dokumentation im Repository sowie der reale Zustand externer Systeme bleiben jeweils für ihren Gegenstand maßgeblich.
Chat-Inhalte werden erst durch Dokumentation im passenden GitHub-Artefakt zum Projektstand.
- Das Issue ist der vollständige Umsetzungsauftrag: Ziel, Scope und Nicht-Scope,
Akzeptanzkriterien, Entscheidungen, Abhängigkeiten und Blocker sowie betroffene Tests, Dokumentation, Pages, Wiki, Migration und Betrieb.
- Das GitHub Project enthält Planungsmetadaten. Pull Request und CI belegen
Umsetzung und Prüfung.
Repository, Pages und Wiki enthalten die dauerhafte Dokumentation.
- Inhalte nicht zwischen Artefakten oder Chats duplizieren. Issue- und
Pull-Request-Beschreibungen sowie Kommentare bleiben kurz und zweckbezogen; Kommentare halten nur neue Entscheidungen, Befunde, Blocker oder Statusänderungen fest.
- Vor Planung, Umsetzung und Statusauskunft den aktuellen GitHub- und Git-Stand
lesen.
Frühere Chat-Inhalte sind kein Ersatz dafür.

## 2. Arbeitskontexte

- Planung, Refinement und Review bleiben gegenüber dem Produktcode read-only.
- Übergaben zwischen Koordination, Umsetzung und Projektplanung sind
asynchrone Aufträge.
Ein Link zum maßgeblichen Issue oder Pull Request und nur die notwendigen neuen
Angaben genügen;
der Sender fordert keine Empfangsbestätigung oder Rückversicherungsrunde an und
prüft nicht den Empfänger-Task.
Eine erfolgreiche Zustellung ist kein Umsetzungsnachweis;
den tatsächlichen Stand zeigen die GitHub-Artefakte.
- Rückfragen sind auf unklare Entscheidungen, fehlende Berechtigungen, Blocker
und benötigte Modellhochstufungen begrenzt.
Bereits beauftragte Schritte benötigen keine erneute Freigabe.
Jeder Task hält seinen Abschluss am maßgeblichen GitHub-Artefakt fest und
übergibt nur einen tatsächlich nötigen Folgeschritt genau einmal an dessen
zuständigen Task;
es gibt keine Berichtskette zurück durch alle beteiligten Tasks.
Eine fehlgeschlagene Zustellung wird gezielt behandelt, eine unklare Zustellung
vor einer Wiederholung geklärt.
Laufende Tasks und Nutzerarbeit bleiben ungestört.
- Die Cloud-Chats `Fachlichkeit strukturieren`, `Projektablauf planen` und
`Codebasis reviewen` dienen ausschließlich der fachlichen Strukturierung, Projektplanung und Codebasisbewertung.
Sie ändern weder Produktcode noch lokale Repository-Dateien, Branches oder Worktrees.
- `Codebasis reviewen` prüft vor der ersten regulären Umsetzung eines neuen
SemVer-Milestones den vollständigen aktuellen Codebestand.
Ein eigener Review-Anker dokumentiert geprüfte Revision, Umfang, Abschluss und
verknüpfte Befunde, trägt aber selbst kein `review:`-Label;
bestätigte Befunde werden als präzise GitHub Issues erfasst.
- `Fachlichkeit strukturieren` darf Ergebnisse fachlicher Klärungen in GitHub
Issues dokumentieren sowie bestehende Issues fachlich refinen.
Technische Umsetzungen und Produktcode bleiben ausgeschlossen.
- `Projektplan aktualisieren` überführt bestätigte Planungsentscheidungen aus
den Cloud-Chats lokal mittels `gh` in GitHub Project, Issues, Abhängigkeiten und Unteraufgaben.
Beim Umsetzungs-Closeout übernimmt der Chat ausschließlich belegbare finale
Codex-Goal-Metriken in `Factual effort (h)` und `Cost (Tokens)`;
fehlende Werte bleiben leer.
Weitergehende Planungs- oder Project-README-Änderungen erfolgen nur bei
belegbarem Bedarf und bestätigter Entscheidung.
Der Chat ändert keine Repository-Dateien, Branches oder Worktrees.
- `Weiterentwicklung koordinieren` prüft Umsetzungsreife, Review-Gate und
`Complexity` einmal, startet issuebezogene Umsetzungen und verantwortet nach
ausdrücklicher Freigabe Merge und lokalen Closeout.
Der Issue-Task übernimmt diese Startevidenz und bearbeitet Code, Tests, Pull
Request und neue Reviewbefunde.
Der Chat implementiert nicht in seinem eigenen Arbeitsbereich.
- Vor der ersten regulären Issue-Umsetzung jedes neuen SemVer-Milestones
prüft `Weiterentwicklung koordinieren`, ob `Codebasis reviewen` den aktuellen
Codebestand vollständig geprüft und den Abschluss im zugehörigen
Review-Anker dokumentiert hat.
Ohne diesen Nachweis beginnt keine reguläre Umsetzung des Milestones.
- `Entwicklungsumgebung anpassen` pflegt die lokale Entwicklungsumgebung. Nicht
triviale Repository-Änderungen folgen ebenfalls dem Issue-Verfahren.
- Externe Systeme zunächst read-only prüfen. Azure-, DNS-, GitHub-Environment-,
Secret-, OIDC-, Deployment- und OpenTofu-`apply`-Änderungen erfolgen nur nach ausdrücklicher Freigabe des Maintainers.
- Die sechs permanenten Chats `Fachlichkeit strukturieren`, `Projektablauf
planen`, `Codebasis reviewen`, `Weiterentwicklung koordinieren`, `Projektplan aktualisieren` und `Entwicklungsumgebung anpassen` weder umbenennen noch für eine Umsetzung verwenden oder archivieren.

## 3. Umsetzungsreife und Arbeitsbereich

- `Implementiere Issue #<nummer>.` ist ein vollständiger Auftrag, wenn das Issue
umsetzungsreif ist.
Das Issue bleibt maßgeblich; eine Übergabe ergänzt nur noch nicht dort dokumentierte, entscheidungsrelevante Randbedingungen.
- Vor der Beauftragung prüft `Weiterentwicklung koordinieren` Issue, Kommentare,
Labels, Milestone, Parent-/Sub-Issues, verknüpfte Pull Requests, Abhängigkeiten,
Blocker, erreichbare Project-Felder und bei einem SemVer-Milestone den
abgeschlossenen Codebasis-Review.
Der Issue-Task verwendet die mit Issue-Link übergebene Startevidenz und liest
sie nur bei Lücke, Widerspruch oder relevanter Änderung erneut.
Bei einem direkten Issue-Auftrag ohne Koordinationsübergabe führt der
Issue-Task diese Prüfung einmal selbst durch.
- Fehlt der abgeschlossene, dokumentierte Codebasis-Review des Milestones,
keine reguläre Umsetzung beginnen und das Gate an `Codebasis reviewen`
zurückgeben;
der Review-Anker sowie reine Planungs- und Review-Arbeit sind selbst keine
regulären Umsetzungen.
- Nicht beginnen, solange das Issue ein `needs:*`-Label trägt. Dasselbe gilt bei
fehlendem Ziel, Scope oder Akzeptanzkriterien, ungelösten Blockern, widersprüchlichen Angaben oder einer konkurrierenden Umsetzung.
- Voraussetzungen nicht erfinden. Bei fehlender Reife stoppen und den konkreten
Klärungsbedarf im vorgesehenen GitHub-Artefakt dokumentieren.
- Für nicht triviale Änderungen gilt: ein Issue entspricht genau einem
temporären Umsetzungschat, einem Feature-Branch und einem Worktree.
- Einen Umsetzungschat unabhängig neu anlegen, nicht durch Umbenennen,
Delegation oder Übergabe eines permanenten Chats.
- Für jede temporäre Issue-Umsetzung zu Beginn ein eigenes Codex-Goal anlegen.
Kein Tokenbudget und keine Messwerte erfinden.
Das Goal erst nach Umsetzung und lokaler Prüfung abschließen;
nicht verfügbare Goal-Metriken bleiben als nicht verfügbar ausgewiesen.
- Den Arbeitsbereich mit dem vorgesehenen lokalen Skill anlegen, soweit
verfügbar.
Der Umsetzungschat heißt `<issue> (<type>): <title>`, der Branch `codex/<issue>-<kurzer-name>`.
- Der Umsetzungschat bezieht seinen Auftrag unmittelbar aus GitHub. Übergaben
dürfen das Issue weder ersetzen noch abweichend erweitern.

### Review-Gate für SemVer-Milestones

- Der vollständige Codebasis-Review läuft im permanenten Chat
`Codebasis reviewen` gegen den aktuellen kanonischen Stand.
Der Review-Anker dokumentiert mindestens Milestone, geprüfte Revision, Umfang
und Abschluss des Reviews; er trägt selbst kein `review:*`-Label.
- Bestätigte Befunde werden als präzise GitHub-Issues erfasst, vor Duplikaten
geschützt und nur mit den jeweils sachlich passenden `review:*`-Labels
klassifiziert.
Sie durchlaufen anschließend die normale Planung und können bei tatsächlicher
Abhängigkeit ein reguläres Issue blockieren.
- Für spätere reguläre Umsetzungen desselben Milestones genügt der vorhandene
abgeschlossene Review-Anker.
Ein neuer vollständiger Review wird erst für den nächsten SemVer-Milestone
zum Gate, sofern ein neuer wesentlicher Befund nicht schon vorher einen Review
erfordert.

## 4. Umsetzung und Prüfung

- `Complexity` bleibt ein live zu lesendes Planungsmetadatum und steuert die
angemessene Prüfung, nicht automatisch Modellgröße oder Reasoning.
Bei fehlendem, unbekanntem oder widersprüchlichem Wert wird keine Einstufung
erfunden; die Einplanung klärt den konkreten Mangel.
Eine direkte, klar beschriebene Umsetzung startet standardmäßig mit Luna und
medium.
Spark und low sind für mechanische Aufgaben möglich; Terra bei konkretem
Mehrbedarf, Sol/high bei schwieriger Ursachen- und Wechselwirkungsanalyse und
Astra/high bei besonders anspruchsvoller Analyse.
xhigh wird nur gezielt eingesetzt.
- Eine Hochstufung erfolgt nicht automatisch.
Bei fachlicher Unsicherheit oder einem wiederholten inhaltlichen Fehlversuch
fragt der Umsetzungstask den Nutzer knapp nach Freigabe und nennt Grund sowie
vorgeschlagenes Modell und Reasoning.
Sandboxfehler, Berechtigungen und CI-Wartezeit sind keine Modelleskalation.
Routinefolgen dürfen heruntergestuft werden.
- Die Complexity-Einstufung bleibt unverändert, sofern keine ausdrücklich
bestätigte Planungsänderung vorliegt.
Bestehende C4-Zerlegungs- und menschliche Reviewregeln bleiben erhalten.
Komponentenübergreifende, öffentliche, sicherheitsrelevante, irreversible
oder produktionsnahe Risiken begründen weiterhin eine entsprechend gründliche
Prüfung, aber keine automatische Modellwahl.

- Ausschließlich im issuebezogenen Worktree arbeiten und niemals direkt auf
`master` committen.
Fremde oder ungefragte Änderungen nicht zurücksetzen und nur auftragsbezogene Dateien stagen.
- Die kleinste Änderung umsetzen, die das Issue vollständig erfüllt. Nicht zum
Scope gehörende Refactorings vermeiden.
Geforderte Tests, Dokumentation, Pages-, Wiki-, Migrations- und Betriebsänderungen gehören zur Umsetzung.
- Commit-Nachrichten sind Englisch; deutsche Prosa verwendet korrekte Umlaute.
- Eigene gepflegte Markdown-Prosa wird mit Semantic Line Breaks geschrieben:
Sätze und sinnvolle Gedankeneinheiten beginnen in neuen Quellzeilen.
Tabellen, Listenstruktur, Codeblöcke, Front Matter, URLs und technische Zeichenketten bleiben unverändert; Drittmaterial, Lizenztexte und generierte Inhalte werden nicht rein redaktionell umgebrochen.
- Prüfungen am Änderungsrisiko ausrichten. Eng begrenzte Änderungen erhalten
mindestens `git diff --check` und die betroffenen Format-, Link- oder Fachprüfungen.
- `task quality` ist für querschnittliche, Toolchain-, Abhängigkeits-, CI-,
Migrations-, sicherheitsrelevante oder breite Backend-/Frontend-Änderungen vorgesehen.
Die finale Abnahme bleibt der CI vorbehalten.
- Sandbox-Probleme als Umgebungsthema dokumentieren und von Produktfehlern
trennen.
Unverändert fehlschlagende breite Prüfungen nicht wiederholen.

## 5. Pull Request und Review

- Der Issue-Task liest Assignees, Milestone und Project-Zuordnung unmittelbar
vor dem Pull Request einmal und übergibt nur gesetzte Werte an
`task pr:create`.
- Vollständige Umsetzungen enthalten eine eigene Zeile `Closes #<nummer>`.
Eine eindeutige erfolgreiche Werkzeugantwort genügt;
nur bei Lücke, Widerspruch oder relevanter Änderung werden Metadaten oder
schließende Verknüpfung gezielt nachgelesen.
- Pull Request und Abschluss nennen knapp wesentliche Modellabweichungen oder
Eskalationen, relevante Befunde, die ausgeführte Verifikation sowie nur
belegbare Goal-Metriken.
Keine Secrets, personenbezogenen Daten, Prompts, internen Gedankengänge oder
Reasoning-Protokolle aufnehmen.
- Nach relevanten Änderungen die betroffenen lokalen Prüfungen wiederholen und
CI sowie Review erneut abwarten.
Review-Threads, allgemeine Kommentare, Security-Audits, Code-Scanning-Alerts und automatisierte Prüfhinweise mit Pull-Request-Bezug vollständig prüfen.
Übergaben und administrative Sammelabgleiche ersetzen weder Code- und
CI-Prüfungen noch einen erforderlichen menschlichen Review.
- Sinnvolle Hinweise im Issue-Scope umsetzen. Threads erst danach als
`Resolved` markieren.
Unklare, unzutreffende oder sachfremde Hinweise beantworten oder eskalieren.
- Erst mergen, wenn die CI nach den letzten Änderungen erfolgreich ist, alle
relevanten Befunde geklärt und die Akzeptanzkriterien erfüllt sind.
- Merge, Release, Workflow-Dispatch und externe Aktivierung erfolgen nur nach
ausdrücklicher Freigabe des Maintainers.
Den freigegebenen Merge führt `Weiterentwicklung koordinieren` aus;
der Issue-Task führt ihn nicht selbst aus.
- Qualifizierte Dependabot-Pull-Requests werden nur durch den vorgesehenen
Squash-Auto-Merge-Workflow angemeldet.
Major-, GitHub-Actions-, konfliktäre oder nicht eindeutig klassifizierte Updates bleiben manuell.

## 6. Statusprüfung und Closeout

- Fortschritt und Abschluss im zugehörigen Issue kurz dokumentieren.
- Beim Abschluss eines Codex-Goals ausschließlich dessen tatsächlich
ausgewiesene Laufzeit und Tokenzahl übernehmen.
Die Laufzeit wird rechnerisch in Stunden in `Factual effort (h)`, die Tokenzahl
unverändert in `Cost (Tokens)` übertragen.
Fehlt eine der Metriken, bleibt das entsprechende Project-Feld leer;
historische oder nicht messbare Werte werden nicht geschätzt.
- Der Umsetzungschat übergibt Issue, Pull Request, Goal-Status und verfügbare
Goal-Metriken einmal an `Projektplan aktualisieren`.
Dieser Chat pflegt nur die belegten Project-Felder, prüft Schätzung,
Milestone-Planung und Kapazität gegen den aktuellen Project-Stand und ändert
Project-README oder Planung nur bei belegbarem Bedarf und bestätigter
Entscheidung.
- Reifeprüfung, Metadatenmutation und Closeout haben jeweils genau eine
zuständige Stelle.
Eindeutige erfolgreiche Werkzeugantworten genügen für routinemäßige
reversible Operationen; Nachprüfungen erfolgen nur bei Lücke, Widerspruch,
neuem Commit, neuem Befund oder relevanter Umweltänderung.
- Bei `Prüfe den Stand von Issue #<nummer>.` den Live-Stand von Issue,
Akzeptanzkriterien, Pull Request, Reviews, CI, Dokumentation, Pages/Wiki sowie Branch und Worktree prüfen; nicht aus dem Chatverlauf auf den Status schließen.
- Nach freigegebenem Merge, finaler CI und geklärten Reviews führt
`Weiterentwicklung koordinieren` den Closeout aus.
Vor dem Entfernen des issuebezogenen Worktrees prüft die Koordination auch
lokale und ignorierte Daten.
Bei Reständerungen stoppt sie, benennt die Dateien und verwirft oder sichert
nichts ohne ausdrückliche Entscheidung.
Ist der Worktree sauber, entfernt sie ausschließlich den zugehörigen Worktree
sowie lokalen und Remote-Feature-Branch.
Der temporäre Umsetzungschat wird nicht automatisch archiviert.

### Sammelabgleich

- Am Ende jeder Iteration und vor jedem Release-Abschluss führt
`Weiterentwicklung koordinieren` einen ereignisgesteuerten Sammelabgleich aus;
fallen beide Anlässe zusammen, erfolgt er nur einmal.
Der Abgleich gehört zum bestehenden Iterations- und Release-Closeout und ist
kein zeitgesteuerter Scheduler.
- Die Koordination bearbeitet offene Pull-Request-, CI- und Closeout-Reste sowie
verwaiste Issue-Arbeitsbereiche.
Routinekorrekturen mit eindeutiger Evidenz erfolgen im bestehenden Auftrag;
unklare Lücken werden gebündelt benannt.
Bestehende Merge- und externe Freigaben gelten unverändert.
- Genau ein gebündelter Auftrag an `Projektplan aktualisieren` prüft
abgeschlossene Issues auf fehlende Project-Zuordnung, Status und vorhandene
Istwerte sowie daraus folgende Planungs- oder Project-README-Abweichungen.
Vorhandene Goal-Werte werden weder erneut gemessen noch doppelt gezählt;
fehlende Werte werden nicht erfunden und Planänderungen benötigen weiterhin
eine bestätigte Entscheidung.

## 7. Codex-Sandbox

- Vor Browserprüfungen `task doctor` verwenden. Den gemeinsamen uv-Cache unter
`~/.cache/uv` nur über die globale Codex-Konfiguration freigeben; keine benutzerspezifische Konfiguration versionieren.
- Browser-E2E- und A11y-Prüfungen getrennt halten. Nicht reproduzierbare
Browserfehler gezielt lokal freigeben oder durch CI abnehmen lassen.
Chromium nie mit `--no-sandbox` starten.
- Bei störendem Git-Fsmonitor
`git -c core.fsmonitor=false status ...` verwenden.

Ergänzend gelten die Frontend- und Reviewregeln unter
[Komponenten](docs/developers/components.md) und
[Entwicklung](docs/developers/development.md) sowie das
[Entwicklerhandbuch](docs/developers/index.md).
