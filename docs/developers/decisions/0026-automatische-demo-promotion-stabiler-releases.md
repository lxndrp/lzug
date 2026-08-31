# ADR-0026: Automatische Demo-Promotion stabiler Releases

## Datum

2026-08-25.

## Status

Akzeptiert.

## Kontext

Diese Entscheidung konkretisiert [ADR-0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) und [ADR-0022](0022-tag-gebundene-demo-assembly-und-seed.md).
Für [ADR-0024](0024-manuell-promotete-demo-snapshots.md) übernimmt sie nur die Quality-Wiederverwendung und die Laufzeitprüfung der GitHub-Environment-Policy; die dort verbleibenden Snapshot-Verträge bleiben gültig.

Ein veröffentlichter stabiler Produktrelease soll ohne zweiten manuellen Dispatch als aktuelle öffentliche Demo sichtbar werden.
Ein durch das repositoryeigene `GITHUB_TOKEN` erzeugtes `release: published`-Ereignis startet jedoch keinen weiteren Workflow zuverlässig.
Zusätzliche PATs oder eine GitHub App allein für diese Ereignisverkettung würden eine unnötige Credential-Grenze einführen.
Der Demo-Pfad darf außerdem weder bereits bestätigte Quality-Evidenz noch deklarative GitHub-Konfiguration erneut prüfen.

## Entscheidung

Der Releaseworkflow veröffentlicht den GitHub Release zuerst und ruft danach für stabile SemVer-Tags direkt den wiederverwendbaren Workflow `.github/workflows/demo-promote.yml` über `workflow_call` auf.
Release Candidates werden nicht promotet.
Der Pfad besitzt kein zweites `release`-Environment; dessen Freigabe bleibt das einzige menschliche Gate des stabilen Produktpfads.
Ein Demo-Fehler lässt Tag, Produktimage, CLI-Archive, SBOM und GitHub Release unverändert und erscheint als eigener nachgelagerter Jobfehler.

Die Promotionslogik besteht aus zwei wiederverwendbaren Verträgen:

- `.github/workflows/demo-publish.yml` veröffentlicht neue unveränderliche
Demo-Pakete oder verifiziert ein bei einem Retry bereits vollständig vorhandenes Paar.
- `.github/workflows/demo-deploy.yml` prüft und deployt dieses Paar. Derselbe
Workflow bleibt per `workflow_dispatch` für manuellen Deploy und Rollback verfügbar und wird vom Snapshotpfad wiederverwendet.

Der stabile Produkt-Tag ist der einzige Einstiegspunkt der Paarauflösung.
Nach dem Publish wird zunächst der versionierte App-Paketname aufgelöst und dessen Registry-Digest festgeschrieben.
Das aus genau diesem Digest gelesene App-Manifest bindet Produkt-Tag, Commit, Runtimevertrag, Schemafingerprint und Seed-Revision.
Erst daraus wird der versionierte Seed-Paketname abgeleitet und ebenfalls auf einen Digest festgeschrieben.
Ab dann werden ausschließlich die beiden Digestreferenzen verwendet.
Ein separates Pair-Deskriptor-Artefakt ist nicht erforderlich.

Vor Azure bleiben die Provenance beider Digests, der gemeinsame Manifestvertrag, GitHub OIDC, die atomare ACA-Revision, Azure-Readiness, Application-Readiness und der abschließende öffentliche Smoke verpflichtend.
SBOM-Attestierungen werden weiterhin für beide Images erzeugt, sind aber kein zusätzliches Deployment-Gate.
Der finale Smoke umfasst `/api/health`; ein separates vorgelagertes Health-Polling entfällt.

Der Snapshotpfad startet keine zweite vollständige Quality-Pipeline.
Er akzeptiert nur vorhandene erfolgreiche vollständige Quality-Evidenz für dieselbe aktuelle `master`-SHA und verwendet danach den gemeinsamen Deploymentworkflow.
Milestone-, Release- und GitHub-Environment-Policy-Abfragen gehören nicht in seinen Laufzeitpfad.
Die Environment-Regeln für `master`, `demo/v*-SNAPSHOT.*` und stabile `v*`-Tags bleiben deklarativ in OpenTofu; ihre reale Aktivierung erfordert weiterhin ein gesondertes Maintainer-GO.

## Fehler- und Wiederanlaufvertrag

Versionierte Demo-Paketreferenzen werden nie überschrieben.
Sind App und Seed noch nicht vorhanden, werden beide gebaut, publiziert, mit SBOM und Provenance attestiert und anschließend erneut über ihre Digests geprüft.
Sind beide bereits vorhanden, darf ein Retry sie nur wiederverwenden, wenn App-zu-Seed- Auflösung, Provenance und Manifestpaar vollständig passen.
Eine Teilpublikation oder ein widersprüchliches Paar bricht fail-closed ab.
Bereits erfolgreiche Deployments bleiben für den manuellen Rollback eine Quelle bekannter Paare, ersetzen aber nicht die erneute Provenance- und Manifestprüfung.

## Konsequenzen

- Produktveröffentlichung und Demo-Promotion bleiben im selben nachvollziehbaren
Workflowlauf, aber mit getrenntem Fehlerstatus.
- Die Triggerarchitektur benötigt kein langlebiges zusätzliches Credential.
- Stable, Snapshot und manueller Rollback teilen dieselbe Azure-Mutationsgrenze.
- App-Manifest und Seed-Manifest binden dieselbe Seed-Revision; die
paketbasierte Auflösung ist damit ohne bewegliche Deploymentidentität möglich.
- OpenTofu bereitet die stabile Tag-Regel nur deklarativ vor. Dieses ADR
autorisiert weder einen Apply noch eine GitHub-Environment- oder Azure-Änderung.

## Referenzen

- [Release und Artefakte](../delivery.md#release-und-artefakte)
- [Demo-Promotion und Deployment](../delivery.md#demo-promotion-und-deployment)
- [GitHub: Reusable workflows](https://docs.github.com/actions/using-workflows/reusing-workflows)
- [GitHub: Aktionen mit `GITHUB_TOKEN` auslösen](https://docs.github.com/actions/using-workflows/triggering-a-workflow#triggering-a-workflow-from-a-workflow)
- [Issue #444](https://github.com/lxndrp/lzug/issues/444)
