# ADR-0024: Manuell promotete Demo-Snapshots

## Datum

2026-08-15.

## Status

Akzeptiert.

## Kontext

[ADR-0026](0026-automatische-demo-promotion-stabiler-releases.md) übernimmt die Quality-Wiederverwendung, den gemeinsamen Deploymentworkflow und die deklarative Environment-Policy.
Tag-Trigger, Snapshot-Identität und unveränderliche OCI-Referenzen bleiben in diesem ADR verbindlich.
Dieser ADR erweitert [ADR-0022](0022-tag-gebundene-demo-assembly-und-seed.md), ohne den Produkt-Releasevertrag aus [ADR-0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) zu ändern.

Die öffentliche Demo soll einen aktuellen, vollständig geprüften Stand von `master` zeigen können, ohne dafür einen künstlichen Produkt-Patch-Release zu erzeugen.
Ein normaler Branch-, Pull-Request- oder Testlauf darf weder veröffentlichen noch deployen.
Gleichzeitig dürfen Build, Seed, Nachweise und Azure-Revision nicht aus dem veränderlichen Inhalt eines Milestones abgeleitet werden.

## Entscheidung

Ein Maintainer setzt bewusst einen neuen annotierten Tag im engen Namespace `demo/vMAJOR.MINOR.PATCH-SNAPSHOT.<7-stellige Commit-SHA>`.
Dieser Tag-Push ist die einzige manuelle Promotion.
Er startet genau den Workflow `.github/workflows/demo-snapshot.yml`; der Workflow erzeugt, verschiebt oder ersetzt den Tag nicht und besitzt keinen manuellen Dispatch.

Der Preflight akzeptiert ausschließlich einen neu erzeugten annotierten Tag, der auf die zum Prüfzeitpunkt aktuelle `master`-SHA zeigt.
Der SHA-Suffix muss mit dem vollständigen Commit übereinstimmen.
Nach diesem günstigen Source- und Policy-Preflight ruft der Snapshot-Workflow den kanonischen vollständigen `Quality`-Workflow als wiederverwendbaren Workflow für exakt diese SHA auf.
Ein früherer Push-, Pull-Request- oder Dispatch-Lauf ist keine Ersatz-Evidenz; erst der erfolgreiche commit-exakte Aufruf gibt Publish und Deployment frei.
Die Zielversion muss einen einzelnen offenen Release-Milestone mit zukünftigem Fälligkeitsdatum bezeichnen, neuer als der letzte stabile Release sein und darf weder als Produkt-Tag noch als Produkt-Release existieren.
Der Milestone ist damit nur eine semantische Zulässigkeitsprüfung; Tag und Commit bleiben die einzigen Build-Eingaben.

Die sichtbare Identität lautet `vMAJOR.MINOR.PATCH-SNAPSHOT@<kurze SHA>`.
Der OCI-Tag ersetzt `@` durch eine registry-taugliche Form und ist nur ein unveränderlicher Publikationsname; Deployment und Nachweise verwenden ausschließlich die kanonischen App- und Seed-Digests.
Beide Images werden aus dem getaggten Stand gebaut, tragen in ihren Manifesten übereinstimmend Kanal, Zielversion, Snapshot-Identität, Tag, vollständige SHA und Schemafingerprint und erhalten jeweils eine eigene CycloneDX-SBOM sowie Provenance-Attestation.
Der Seed bindet zusätzlich seine inhaltsadressierte Revision.

Nach erfolgreicher Attestierung deployt derselbe Lauf das vollständige Digestpaar per bestehender GitHub-OIDC-Identität in das Environment `demo`.
Nach dem autorisierten Tag-Push gibt es keinen weiteren manuellen Dispatch und kein Required-Reviewer-Gate.
Atomare Azure-Revision, Readiness, Liveness, Anwendungs-Readiness und der vollständige Smoke-Vertrag bleiben unverändert.
Ein Rückfall verwendet weiterhin ausschließlich ein früheres, vollständig geprüftes Digestpaar über den bestehenden manuellen Rollback-Pfad.

Das bestehende Environment verwendet dafür ausgewählte Branch-/Tag-Regeln: `master` bleibt für den manuellen Release-/Rollback-Pfad erlaubt, `demo/v*-SNAPSHOT.*` ausschließlich für die Snapshot-Tags.
Nach erfolgreicher Quality, OCI-Veröffentlichung, SBOM, Provenance und digestgebundener Manifestpaarprüfung prüft erst das Deployment-Gate diese Regeln und die Abwesenheit eines Required Reviewers.
Eine fehlende Policy verhindert damit weiterhin jede Azure-Anmeldung, nicht aber die für ihre einmalige IaC-Adoption benötigte unveränderliche Artefaktassembly.

Der reguläre releasegebundene Demo-Publish bleibt erhalten.
Er akzeptiert nur veröffentlichte SemVer-Produkt-Releases und nutzt weiterhin sein eigenes `release`-Gate.
Snapshot-Tags erzeugen weder Produktimage noch Betreiber-CLI, GitHub Release oder Self-Hosting-Artefakt.
Ein späterer Nightly-Kanal benötigt einen anderen Namen, einen zeitgesteuerten Auslöser und eine eigene Entscheidung.

## Konsequenzen

Der Snapshot-Kanal kann einen aktuellen, geprüften `master`-Stand zeigen, ohne einen Produkt-Patch-Release zu erzeugen.
Snapshot-Tags und OCI-Tags bleiben unveränderlich; ein fehlgeschlagener Lauf erfordert für einen neuen Versuch einen neuen aktuellen Commit und Tag.
Produkt-Release, Betreiber-CLI, GitHub Release und Self-Hosting-Artefakte bleiben vom Snapshot-Kanal getrennt.
Ein früheres vollständig geprüftes Digestpaar bleibt ausschließlich als kontrollierte Rollback-Quelle erhalten.

## Fehler- und Wiederanlaufvertrag

Nicht-`master`- oder überholte SHAs, unvollständige Quality-Evidenz, ungeeignete Milestones und Zielversionen, bewegte Tags sowie bereits belegte OCI-Referenzen brechen vor dem jeweils nächsten irreversiblen Schritt ab.
Eine fehlgeschlagene commit-exakte Quality-Prüfung überspringt Publish und Deployment vollständig.
Snapshot-Tags und OCI-Tags werden nie repariert oder wiederverwendet.
Scheitert ein Lauf nach einer Teilpublikation, ist der Lauf kein Deploymentnachweis; ein neuer Snapshot benötigt einen neuen aktuellen `master`-Commit und einen neuen Tag.
Scheitert Azure nach der atomaren Revisionserzeugung, dokumentiert der Lauf das vorherige Paar für den vorhandenen kontrollierten Rollback.

Reine Test-, Assertion-, Branch- oder Pull-Request-Änderungen lösen den Snapshotpfad nicht aus.
Auch ein Merge auf `master` genügt nicht: Ohne den bewussten annotierten Tag-Push erfolgen weder Publish noch Deployment.

## Referenzen

- [Öffentliche Demo](../demo-deployment.md)
- [Azure-Demo-Deployment](../demo-deployment.md)
- [Issue #380](https://github.com/lxndrp/lzug/issues/380)
