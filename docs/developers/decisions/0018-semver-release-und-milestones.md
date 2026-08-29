# ADR-0018: SemVer, Releases und Release-Milestones trennen

## Status

Akzeptiert.

## Kontext

Die Datei `VERSION`, Paketmetadaten, Git-Tags, GitHub Releases und drei offen
geführte thematische Milestones wurden bisher teilweise als überlappende
Versions- und Planungsquellen verstanden. Ein geplanter Milestone bezeichnet
aber keinen gebauten Stand, und ein Commit auf `master` ist noch kein
freigegebener Release. Für einen reproduzierbaren Veröffentlichungsprozess
müssen technische Identität, Freigabe und fachliche Zielmenge getrennt sein.

[ADR-0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) präzisiert
den Kandidaten- und Veröffentlichungsablauf. Die hier festgelegte Trennung von
SemVer-Tag, Release-Milestone und GitHub Project bleibt davon unberührt.

Der Bestand liefert mit `VERSION=0.1.0` einen technischen Ausgangspunkt und
mit der Wintererprobung ein fachliches Ziel für Version 1. Die bisherige
direkte Planung von `v0.1.0` auf `v1.0.0` vermischt jedoch mehrere unabhängig
abnehmbare Fachprozesse, Betriebsfähigkeit und Pilotierung. Die offenen Issues
erlauben einen belastbaren Zuschnitt entlang tatsächlich verfügbarer
Fachprozesse. Schriftliche Prüfungen (#165) sind ein eigenständig nutzbarer,
noch nicht verfeinerter Prozess und folgen deshalb erst nach Version 1.

## Entscheidung

### Verantwortlichkeiten

| Gegenstand        | Verantwortung                                                                                                        | Keine Verantwortung                                                    |
| ----------------- | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| SemVer-Tag        | unveränderliche technische Versionsquelle eines freigegebenen Commits                                                | Planung, Aufwand oder Iteration                                        |
| Kandidat-Commit   | vollständig geprüfter, auf `master` erreichbarer Commit, dessen vollständige SHA im Release-Issue festgehalten wird  | veröffentlichte Version oder beweglicher Zeiger auf den neuesten Stand |
| GitHub Release    | freigegebene Darstellung genau eines Tags mit Notes, Assets und Nachweisen                                           | Wahl des Kandidaten oder fachliche Planung                             |
| Release-Milestone | fachliche Zielmenge für genau eine geplante SemVer-Version; technische Voraussetzungen können Teil ihrer Issues sein | Build-Eingabe oder technische Versionsquelle                           |
| GitHub Project    | operative Quelle für Status, Priorität, Iteration, Termine und Aufwand                                               | Release- oder Build-Identität                                          |

Ein Release-Milestone heißt exakt wie sein vorgesehener Tag: `vMAJOR.MINOR.PATCH`
oder bei einem tatsächlich geplanten Vorabrelease
`vMAJOR.MINOR.PATCH-rc.N`. Ein Milestone darf von Build- und
Release-Automation gelesen werden, um Vollständigkeit zu prüfen; sein Name darf
aber niemals in ein Artefakt injiziert oder zum Erzeugen einer Version
verwendet werden.

### Entwicklungsstände und Release Candidates

Ein normaler Commit, Branch-Build oder Pull Request besitzt keine geplante
Release-Version. Die gemeinsame Build-Metadaten-Schnittstelle ersetzt die
frühere mehrdeutige `VERSION`-Semantik. Entwicklungsidentitäten enthalten den
vollständigen Commit und sind als `0.0.0-dev+sha.<Commit-SHA>` eindeutig als
Entwicklung markiert.

Ein Kandidat entsteht erst, wenn das letzte reguläre Issue eines
Release-Milestones geschlossen ist. Die vertrauenswürdige Automation aus #308
legt dann genau ein Release-Issue an und hält darin die vollständige SHA des zu
diesem Zeitpunkt geprüften `master`-Commits fest. Spätere Merges bewegen diesen
Kandidaten nicht. Erfordert das Gate eine Korrektur, wird sie über ein
zugehöriges Issue umgesetzt und anschließend ein neuer Kandidat bestimmt.

Ein Release Candidate ist eine veröffentlichte SemVer-Pre-Release-Version und
verwendet einen annotierten Tag `vMAJOR.MINOR.PATCH-rc.N` sowie einen GitHub
Pre-Release. Er wird nur geplant, wenn dafür ein eigener Milestone und ein
konkreter Abnahmezweck bestehen. Kandidat-Commit und Release Candidate sind
damit ausdrücklich nicht dasselbe. `v1.0.0-rc.1` dient der integrierten
Wintererprobung; `v1.0.0` folgt erst nach ausgewerteter Pilotnutzung und einem
eigenen stabilen Freigabe-Gate.

### Versionsfolge und fachliche Releasegrenzen

| Milestone     | Ein erstmals geschlossen nutzbarer Umfang                                                                      |
| ------------- | -------------------------------------------------------------------------------------------------------------- |
| `v0.1.0`      | reproduzierbare Versions-, Qualitäts- und Release-Infrastruktur; noch kein fachlicher Vollständigkeitsanspruch |
| `v0.2.0`      | Planungsvorschläge kontrolliert und barrierefrei bearbeiten                                                    |
| `v0.3.0`      | Ausfälle, Benachrichtigungen und Kalenderereignisse zusammenhängend behandeln                                  |
| `v0.4.0`      | mündliche Prüfungstage dokumentieren, bewerten und fachlich abschließen                                        |
| `v0.5.0`      | bestätigte Pläne kontrolliert ändern und Prüfungshalbjahre abschließen sowie historisch einsehen               |
| `v0.6.0`      | eine Instanz mit dokumentierten Backup-, Restore-, Upgrade- und Rollback-Pfaden selbst betreiben               |
| `v1.0.0-rc.1` | den integrierten Stand unter realen Bedingungen in der Wintererprobung abnehmen                                |
| `v1.0.0`      | den ausgewerteten Pilotstand ohne bekannte blockierende Befunde stabil freigeben                               |
| `v1.1.0`      | schriftliche Prüfungen als eigenständig nutzbaren Fachprozess organisieren                                     |

Eine Minor-Version vor `1.0.0` ist damit kein beliebiger Zwischenstand,
sondern die kleinste fachlich oder betrieblich eigenständig abnehmbare
Erweiterung. Patch-Versionen bleiben rückwärtskompatiblen Korrekturen eines
bereits veröffentlichten Umfangs vorbehalten. Für `v1.1.0` wird bis zur
Verfeinerung von #165 bewusst weder ein Datum noch eine Project-Iteration
erfunden.

### Freigabeverfahren

1. Alle regulären Issues des Release-Milestones sind geschlossen.
2. Die Kandidatenautomation erzeugt das einzige verbleibende Release-Issue,
   hält die Kandidat-SHA fest und ordnet es demselben Milestone zu.
3. Das Release-Issue dokumentiert Scope-Freeze, die stabilen Qualitätsgates
   aus dem [CI-Vertrag](../continuous-integration.md), Security- und
   Betriebsprüfung, Release Notes und die ausdrückliche Freigabe.
4. Nur das Schließen durch eine Person mit `maintain` oder `admin` startet die
   erneute serverseitige Validierung. Der Veröffentlichungsjob wartet
   zusätzlich im GitHub-Environment `release` auf einen Required Reviewer.
5. Erst danach erzeugt die Automation den annotierten Tag am unveränderten
   Kandidat-Commit, das GitHub Release und die zusammengehörigen Artefakte.

Manuell angelegte Release-Issues verwenden das standardisierte Issue-Formular
`Release-Freigabe`. Automatisch erzeugte Release-Issues aus #308 müssen
denselben Pflichtumfang abbilden. Die stabile Freigabe nach dem Winterpilot ist
als reguläres Gate #318 geplant.

#308 setzt dieses Verfahren um. Bis #308 abgeschlossen ist, wird
kein Release erzeugt. Insbesondere ist die vorhandene taggetriebene Automation
kein Ersatz für den hier beschlossenen Kandidaten- und Freigabevertrag.

### Rückwirkungsfreiheit

Ein veröffentlichter Tag wird niemals verschoben oder für einen anderen Commit
neu verwendet. Versionsidentität, GitHub Release und veröffentlichte
Artefakt-Digests werden nicht nachträglich umgedeutet. Korrekturen erscheinen
unter einer neuen höheren SemVer-Version; verworfene oder fehlerhafte Releases
bleiben nachvollziehbar dokumentiert. Historische thematische Milestones werden
nicht rückwirkend zu veröffentlichten Versionen erklärt.

## Milestone-Migration

- „Fachlich vollständiger Prototyp“ wurde unter Erhalt seiner Issue-Historie
  zunächst in `v0.1.0` umbenannt. Die offenen Issues werden anschließend
  verlustfrei auf die fachlichen Zielmengen `v0.1.0` bis `v0.6.0` verteilt;
  geschlossene Zuordnungen bleiben als Planungshistorie sichtbar.
- „Version 1 – Wintererprobung“ wird unter denselben Bedingungen in `v1.0.0`
  umbenannt. Die Pilot-Zielmenge wechselt nach `v1.0.0-rc.1`; `v1.0.0`
  bezeichnet nur noch die stabile Freigabe nach ausgewerteter Erprobung.
- Die offenen, für die erste Veröffentlichung erforderlichen Issues aus
  „Veröffentlichungs- und Betriebsfähigkeit“ wechseln nach `v0.1.0`.
  Release-unabhängige Demo-, Konzept- und nachrangige Themen verlieren ihre
  Milestone-Zuordnung. Der Themencontainer wird anschließend als historisch
  gekennzeichnet und geschlossen; seine geschlossenen Issues und externen
  Verweise bleiben erhalten.
- „Öffentlicher Quellcode-Prototyp“ bleibt unverändert geschlossen. Er
  dokumentiert eine Repository-Freigabe, keinen nachträglich erfundenen
  Produktrelease.

Die operative Zuordnung von Issues und Milestones wird im GitHub Project und
in den jeweiligen GitHub-Issues gepflegt.

## Konsequenzen

- Es existiert eine nachvollziehbare Releasefolge von `v0.1.0` bis `v1.1.0`;
  `v1.0.0-rc.1` trennt Pilotierung und stabile Freigabe.
- Offene Issues ohne belastbaren Releasebezug bleiben ausdrücklich ohne
  Milestone; Iteration, Zieltermin und Priorität werden weiterhin im Project
  gepflegt.
- Epics, deren Children mehrere oder keine Releases betreffen, erhalten selbst
  keinen Release-Milestone. Die Releasezuordnung liegt auf den tatsächlich
  auszuliefernden Arbeitspaketen.
- #307 darf Versionsdaten ausschließlich aus Tag beziehungsweise Commit
  ableiten. #308 darf Milestones nur als Vollständigkeitsgate verwenden.

## Alternativen

- Thematische Milestones parallel zu Release-Milestones weiterführen: würde
  ihre Semantik erneut vermischen und Project-Felder duplizieren.
- Jeden offenen Themencontainer einer Version zuordnen: würde nicht terminierte
  Demo-, Konzept- und Tooling-Arbeit ohne fachliche Grundlage in einen Release
  ziehen.
- Direkt von `v0.1.0` auf `v1.0.0` planen: würde mehrere eigenständig nutzbare
  Fachprozesse in ein langes, kaum belastbar prognostizierbares Release ziehen.
- Die Wintererprobung unmittelbar als stabile `v1.0.0` veröffentlichen: würde
  Pilotbefunde erst nach dem Stabilitätsversprechen sichtbar machen.
- #165 gemeinsam mit Zulassung und Anträgen (#164) bündeln: beide Prozesse sind
  unabhängig nutzbar und fachlich nicht hinreichend gekoppelt.
- `VERSION` dauerhaft als Quell- und Planungsstand verwenden: ein normaler
  Commit könnte damit weiterhin eine veröffentlichte Version vortäuschen.

## Referenzen

- [Releases und GHCR](../releases.md)
- [Stabiler Qualitätsvertrag](../continuous-integration.md)
- Issues [#301](https://github.com/lxndrp/lzug/issues/301),
  [#303](https://github.com/lxndrp/lzug/issues/303),
  [#306](https://github.com/lxndrp/lzug/issues/306),
  [#307](https://github.com/lxndrp/lzug/issues/307),
  [#308](https://github.com/lxndrp/lzug/issues/308) und
  [#273](https://github.com/lxndrp/lzug/issues/273),
  [#165](https://github.com/lxndrp/lzug/issues/165) sowie
  [#318](https://github.com/lxndrp/lzug/issues/318)
