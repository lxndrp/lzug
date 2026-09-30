# ADR-0020: Minimaler Releaseablauf mit GitHub-Bordmitteln

## Datum

2026-08-13.

## Status

Akzeptiert.
Geltender Releasevertrag; spätere SBOM- und Artefaktänderungen aus ADR-0038
sowie die aktuellen Workflow- und Delivery-Verträge ergänzen diese Entscheidung.

## Kontext

ADR-0019 beseitigte die getrennte Kandidatenautomation, ließ aber eine eigene Release-Steuerung bestehen.
Der Workflow reagiert auf jedes geschlossene Issue, ermittelt den Zustand eines Milestones, erzeugt und schließt ein Release-Issue, fragt sieben einzelne Check-Namen ab und bildet mehrere historische Wiederanlauffälle nach.
`scripts/release_assets.py` inventarisiert dafür sogar bereits veröffentlichte Releases generationsabhängig.
Verdrahtungsnahe Tests schreiben Schrittfolgen und Sonderfälle des Workflows fest.

Diese Entscheidung präzisiert ADR-0019 hinsichtlich Auslöser, Milestone-/Issue-Steuerung, CI-Nachweis und Wiederanlauf.
Der annotierte Tag als einzige technische Release-Identität und die Freigabe über das GitHub-Environment `release` bleiben bestehen.
Die technische Migration erfolgt ausschließlich in #347; der veröffentlichte Release `v0.1.0` bleibt unverändert.

Diese Mechanismen duplizieren Zustände, die GitHub bereits führt: den vollständigen Workflow-Lauf eines Commits, die manuelle Freigabe eines geschützten Environments, den unveränderlichen Tag, den Draft- beziehungsweise veröffentlichten Release und die Attestations der ausgelieferten Artefakte.
Die Vereinfachung der Qualitätsworkflows aus #344 schafft zudem einen einzigen vollständigen `master`-Lauf als stabilen Qualitätsnachweis.
Eine eigene Kandidaten- oder Gate-Domäne erzeugt danach keinen zusätzlichen Nutzen.

## Entscheidung

### Planungs- und Releasegrenze

- SemVer-Milestones bleiben die fachliche Zielmenge. Project-Felder bleiben die
operative Planung.
Weder Milestone noch Project sind technische Eingaben des Release-Workflows.
- Das Schließen von Issues startet keine Veröffentlichung und erzeugt kein
Release-Issue.
Release-Issues, besondere Release-Labels und synchronisierte Abhängigkeiten entfallen als Steuerungsmechanismen.
- Ein Release-PR bereitet Changelog und Version vor. Nach seinem Merge startet
ein Maintainer den Release-Workflow ausdrücklich per `workflow_dispatch` auf `master` und übergibt den vorgesehenen annotierten SemVer-Tag.
- Der Commit des gestarteten Workflow-Laufs ist der einzige freizugebende
Quellstand.
Der Preflight akzeptiert ihn nur auf `master`, bei passendem SemVer-/Changelog-Vertrag und mit einem erfolgreichen vollständigen `master`-Qualitätslauf exakt für diese SHA.
Die vollständige SHA ist dabei gemäß [ADR-0034](0034-versionsbindung-und-unveraenderliche-referenzen.md) der bytegenaue Nachweis des geprüften Quellstands,
nicht eine parallele Produktversionsauswahl.
- Der Preflight liest den einen vollständigen Workflow-Lauf. Er fragt weder
einzelne interne Jobnamen ab noch pollt er und führt keine Quality-, Security-, Browser-, Container- oder Smoke-Prüfung erneut aus.

### Ablauf ab dem Maintainer-GO

1. Der Publish-Job wartet im GitHub-Environment `release`; dessen
Required-Reviewer-Freigabe ist das Maintainer-GO.
2. Nach der Freigabe erzeugt der Job den annotierten SemVer-Tag auf der im
Workflow-Lauf festgehaltenen SHA und pusht ihn.
3. Der Job checkt den Tag aus. Ab diesem Schritt werden Version, Revision,
OCI-Referenzen, CLI-Archive, SBOM und Release Notes ausschließlich aus dem Tag und seinem Commit abgeleitet.
4. Die wiederverwendbaren Publish-Workflows bauen und attestieren die für
den Release freigegebenen Produkt- und CLI-Artefakte und veröffentlichen den
GitHub Release.
Die genaue Artefaktmenge und die zugehörigen Attestierungen folgen den
aktuellen Release-Workflows und [Delivery-Verträgen](../delivery.md#release-und-artefakte).

Der freigegebene Tag bindet die Produktauslieferung und den GitHub Release.
Milestone und Project begründen die menschliche Releaseentscheidung, werden
aber nicht in eine zweite technische Zustandskette übersetzt.
Workflow-Lauf, Environment-Deployment, Tag, Attestations und GitHub Release
bilden den Audit-Trail der Plattform.
SBOMs werden ausschließlich für ausgelieferte OCI-Images erzeugt.
Es gibt keine Dependency-, native CLI- oder aggregierte Release-SBOM und keine
separate sichtbare SBOM als Produktrelease-Asset.

### Kleiner, fail-closed Wiederanlauf

- Der normale Wiederanlauf ist ausschließlich der GitHub-Re-Run desselben
Workflow-Laufs.
Er behält Ref, Commit-SHA und SemVer-Eingabe bei und erfordert weiterhin die Schutzregeln des Environments, wenn der Publish-Job wieder ausgeführt wird; der Wiederanlauf darf sie nicht umgehen.
- Ein bei diesem Lauf bereits erzeugter Tag darf nur wiederverwendet werden,
wenn er annotiert ist und exakt auf dieselbe SHA zeigt.
Andernfalls bricht der Lauf ab; Tags werden niemals verschoben oder ersetzt.
- Ein vorhandener Draft zum selben Tag darf mit den erneut aus genau diesem Tag
gebauten Assets vervollständigt werden.
Ein bereits veröffentlichter Release ist ein terminaler Zustand und wird weder inventarisiert noch repariert oder als nachträglicher Erfolg eines neuen Laufs umgedeutet.
- Historische Release-Generationen, abweichende veröffentlichte Assets und
manuelle Wiederherstellung werden nicht im Workflow modelliert.
Ein Fehler nach einer sichtbaren Veröffentlichung wird als eigener Vorfall bewertet und grundsätzlich durch eine neue Version korrigiert.

### Historische Umsetzungsvorgaben für #347 (abgeschlossen)

Die folgende Tabelle dokumentiert den ursprünglichen Implementierungsauftrag.
Sie ist keine Liste offener Arbeiten oder ein Ersatz für die geltenden
Workflow- und Artefaktverträge.

| Bestandteil | Entscheidung für die Folgeumsetzung |
| --- | --- |
| `.github/workflows/release.yml` | Auf `workflow_dispatch`, einen vollständigen Master-CI-Nachweis, Environment-GO und taggebundenes Publish reduzieren |
| Issue-Closure-Trigger, Milestone-Abfragen, Gate-Erzeugung und Gate-Abschluss | Entfernen |
| Abfrage der sieben einzelnen Quality-Check-Namen | Nach #344 durch den erfolgreichen vollständigen Master-Workflow für exakt dieselbe SHA ersetzen |
| `scripts/release_assets.py` | Entfernen; keine generationsabhängige Bestandsvalidierung veröffentlichter Releases mehr |
| `v0.1.0`-Sonderpfade für vorhandene Releases und OCI-Images | Entfernen; `v0.1.0` bleibt außerhalb des neuen Ablaufs unverändert |
| `tests/delivery/test_release_process.py` | Verdrahtungs- und Sonderfalltests entfernen; nur wenige Verhaltensinvarianten des Zielvertrags prüfen |
| Release-Anteile in `tests/delivery/test_sbom.py` | Auf den verbleibenden sichtbaren SBOM-Vertrag begrenzen; keine Workflow- oder Retry-Steuerung testen |
| SBOM-Erzeugung | Direkte, gepinnte Syft-Aufrufe erzeugen nur SBOMs veröffentlichter OCI-Images; siehe ADR-0038 |
| Build-Identität | Das Backend-Modul `backend.version` besitzt den komponenteneigenen Metadatenvertrag; kein separates `scripts/build_metadata.py` |
| CLI-Verpackung | Nach der positiven Entscheidung in [ADR-0021](0021-goreleaser-fuer-die-betreiber-cli.md) mit GoReleaser bauen; Release und Attestations wurden integriert. Die damalige aggregierte SBOM-Erwartung ist durch ADR-0038 abgelöst. |

Release-Notes-Extraktion, OCI-Tag-Semantik und die deklarativ beschriebene
CLI-Paketierung bleiben den dafür zuständigen Komponenten- und Lieferverträgen
zugeordnet.
Die Syft-Auswahl und der Umfang der SBOMs folgen ADR-0038.
Eigene Release-Logik darf konkrete Verträge abbilden, aber keine parallele
Release-Zustandsmaschine aufbauen.

## Konsequenzen

- Die Releasebereitschaft wird nicht mehr indirekt durch das Schließen eines
beliebigen letzten Issues signalisiert.
Der manuelle Start und das Environment-GO sind zwei sichtbare, absichtliche Maintainer-Aktionen.
- Die in der damaligen Umsetzungsvorbereitung genannte Reihenfolge #344 vor
#347 ist abgeschlossen; sie ist historische Umsetzungskontext, kein offener
Voraussetzungsauftrag.
- [ADR-0021](0021-goreleaser-fuer-die-betreiber-cli.md) führt GoReleaser nur
für Build und Verpackung der Betreiber-CLI ein.
Das Ergebnis ändert weder Auslöser noch Freigabe- und Taggrenze dieses ADRs.
- #347 hat den Zielablauf implementiert; die issuegesteuerte Automation ist
entfernt.
Die aktuellen wiederverwendbaren Release- und Publish-Workflows sind der
maßgebliche ausführbare Vertrag.
- Milestone-Zuordnungen und Releasefolge aus ADR-0018 bleiben unverändert; sie
werden lediglich nicht mehr von der Veröffentlichungsautomation gelesen.

## Alternativen

- Das letzte Milestone-Issue weiterhin automatisch als Releaseauslöser nutzen:
koppelt fachliche Planung an eine schreibende Veröffentlichung und benötigt erneut Gate-Deduplizierung sowie Sonderfälle für verspätete Issues.
- Ein Release-Issue als zweite Freigabeinstanz beibehalten: dupliziert das
geschützte Environment, ohne Tag oder Artefakte stärker zu binden.
- Alle einzelnen Quality-Checks abfragen: koppelt den Release an interne
CI-Verdrahtung und wird mit #344 erneut veralten.
- Veröffentlichung allein durch das Pushen eines Tags starten: der Tag müsste
vor dem Environment-GO existieren und wäre damit schon vor der Freigabe die endgültige Release-Identität.
- Eine allgemeine Recovery-Maschine für veröffentlichte Releases und frühere
Asset-Generationen behalten: vergrößert den normalen Pfad für seltene historische Zustände und lädt zur nachträglichen Veränderung sichtbarer Releases ein.

## Referenzen

- [ADR-0018](0018-semver-release-und-milestones.md)
- [ADR-0019](0019-tag-zentrierter-releaseprozess.md)
- [ADR-0034](0034-versionsbindung-und-unveraenderliche-referenzen.md)
- [Release und Artefakte](../delivery.md#release-und-artefakte)
- [Vollständige Qualität](../delivery.md#vollstandige-qualitat)
- [Manuell gestartete Workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow)
- [Geschützte Environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [Workflow-Läufe erneut ausführen](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)
- [GitHub-CLI für Releases](https://cli.github.com/manual/gh_release)
- Issues [#339](https://github.com/lxndrp/lzug/issues/339),
  [#344](https://github.com/lxndrp/lzug/issues/344),
  [#345](https://github.com/lxndrp/lzug/issues/345),
  [#346](https://github.com/lxndrp/lzug/issues/346) und
  [#347](https://github.com/lxndrp/lzug/issues/347)
