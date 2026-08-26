# Releases und GHCR

!!! danger "Keine manuelle Veröffentlichung"

    Maintainer erzeugen oder verschieben weder Release-Tags noch GitHub
    Releases oder OCI-Tags manuell. Der Workflow erstellt den annotierten Tag
    erst nach der Freigabe des geschützten GitHub-Environments `release`.
    Der veröffentlichte Release `v0.1.0` bleibt unverändert und liegt außerhalb
    des hier beschriebenen Wiederanlaufs.

## Zielvertrag

[ADR-0020](decisions/0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
trennt Planung und technische Veröffentlichung. SemVer-Milestones und
Project-Felder bleiben Planungsdaten; sie sind keine Eingaben des
Release-Workflows. Der annotierte Git-Tag ist die einzige technische Identität
eines Releases.

Der getrennte
[Demo-Snapshot-Kanal](decisions/0024-manuell-promotete-demo-snapshots.md)
verwendet ausschließlich `demo/...-SNAPSHOT.<kurze SHA>`-Tags. Diese Tags sind
keine Produkt-Releases: Sie erzeugen weder GitHub Release, Produktimage noch
Betreiber-CLI oder Self-Hosting-Artefakte und ändern den folgenden
SemVer-Vertrag nicht.

Ein normaler Commit, Branch-Build oder Pull Request verwendet die
Entwicklungsidentität `0.0.0-dev+sha.<40-stellige Commit-SHA>`. Ein Release
verwendet ausschließlich einen annotierten Tag der Form `vMAJOR.MINOR.PATCH`
oder `vMAJOR.MINOR.PATCH-rc.N`. Backend, Frontend, Betreiber-CLI und OCI-Image
erhalten daraus dieselbe Version, vollständige Revision und denselben Tag.

## Ablauf

1. Ein Release-PR verschiebt die freizugebenden Changelog-Einträge aus
   `[Unreleased]` in genau einen datierten Abschnitt `MAJOR.MINOR.PATCH`.
2. Nach dem Merge startet ein Maintainer den Workflow `Release` ausdrücklich
   auf `master` und gibt den vorgesehenen SemVer-Tag ein. Das Schließen eines
   Issues startet keinen Release.
3. Der Preflight verlangt die aktuelle `master`-SHA, den passenden
   SemVer-/Changelog-Vertrag und einen erfolgreichen vollständigen
   `Quality`-Workflow-Lauf exakt für diese SHA. Er fragt keine internen
   Jobnamen ab und pollt nicht.
4. Der Publish-Job wartet im GitHub-Environment `release`. Dessen
   Required-Reviewer-Freigabe ist das Maintainer-GO; Admin-Bypass ist
   deaktiviert und nur geschützte Branches sind zulässig.
5. Erst danach erzeugt der Job den annotierten Tag auf der vorgeprüften SHA
   oder akzeptiert beim Wiederanlauf denselben bereits vorhandenen annotierten
   Tag. Anschließend checkt er ausschließlich diesen Tag aus.
6. Aus dem Tag entstehen OCI-Image, sechs CLI-Archive, die aggregierte SBOM und
   GitHub Attestations. Der Job erstellt beziehungsweise aktualisiert einen
   Draft-Release, lädt sieben sichtbare Assets hoch und veröffentlicht den
   Draft zuletzt.
7. Nach der Veröffentlichung ruft derselbe Workflow für einen stabilen Tag den
   wiederverwendbaren Demo-Promotionspfad auf. Release Candidates bleiben
   ausgeschlossen. Die Promotion verwendet denselben bereits bestätigten
   `Quality`-Nachweis und besitzt kein zweites `release`-Environment-Gate.

Der Release-Workflow wird in der Weboberfläche oder äquivalent mit der GitHub
CLI gestartet:

```sh
gh workflow run release.yml --repo lxndrp/lzug --ref master \
  -f release_tag=v0.2.0
```

Der Start veröffentlicht noch nichts: Erst die gesonderte Freigabe des
Environments erlaubt Tag- und Publish-Schritte.

## Qualitätsnachweis und Lieferartefakte

Der Release-Workflow verwendet das Ergebnis des vollständigen Workflows
`.github/workflows/quality.yml` für dieselbe `master`-SHA. Er wiederholt weder
Unit-, Browser-, Container- oder Smoke-Tests noch Security-Scans, CodeQL oder
Trivy.

Aus dem freigegebenen Tag baut der Workflow nur die Lieferartefakte:

- ein OCI-Image mit den Tags `MAJOR.MINOR.PATCH`, `MAJOR.MINOR`, `MAJOR` und
  `sha-<Commit>`; Vorabreleases erhalten nur ihren vollständigen SemVer- und
  SHA-Tag,
- sechs Betreiber-CLI-Archive für Linux, macOS und Windows auf `amd64` und
  `arm64`,
- genau eine sichtbare aggregierte CycloneDX-Datei
  `lzug-MAJOR.MINOR.PATCH.sbom.cdx.json`.

Die CLI-Archive werden gemäß
[ADR-0021](decisions/0021-goreleaser-fuer-die-betreiber-cli.md) mit der
gepinnten GoReleaser-Version gebaut. GoReleaser ist ausschließlich für Build
und Verpackung zuständig: `release.disable` und `checksum.disable` verhindern
eine eigene Veröffentlichung und eine zusätzliche sichtbare Checksummendatei.

Damit enthält jeder neue GitHub Release genau sieben Assets. Separate
Prüfsummendateien, plattformspezifische CLI-SBOMs, Dependency-/Image-SBOMs,
Provenance-JSONs und Release-Manifeste werden nicht als Release-Assets
veröffentlicht. GitHub berechnet und zeigt für jedes Asset dessen Digest.

Syft erzeugt detaillierte Dependency-, Image- und CLI-SBOMs nur temporär. Die
verbleibende projektspezifische Aggregation führt ihre Komponenten
deterministisch in der einzigen sichtbaren Release-SBOM zusammen. GitHub
Attestations bindet diese SBOM über eine temporäre Digestliste an die sechs
Archive und den OCI-Digest. Zusätzlich werden die CLI-Provenance sowie
OCI-Provenance und OCI-SBOM attestiert; Registry-Attestations werden an den
OCI-Digest geschrieben. Der Workflow erzeugt keinen `latest`-Tag.

Den von GitHub erfassten Digest eines Release-Assets zeigt die Release-Ansicht.
Er lässt sich außerdem über die API lesen und lokal vergleichen:

```sh
version=0.2.0
archive="lzug-admin-${version}-linux-amd64.tar.gz"
expected=$(gh release view "v$version" --repo lxndrp/lzug --json assets \
  --jq ".assets[] | select(.name == \"$archive\") | .digest" | sed 's/^sha256://')
actual=$(sha256sum "$archive" | awk '{ print $1 }')
test "$actual" = "$expected"
```

Die Herkunft eines veröffentlichten OCI-Digests kann mit GitHub Attestations
geprüft werden:

```sh
gh attestation verify \
  "oci://ghcr.io/lxndrp/lzug@sha256:<64 hexadezimale Zeichen>" \
  --repo lxndrp/lzug
```

## Fehler- und Wiederanlaufverhalten

Der einzige automatisierte Retry ist der GitHub-Re-Run desselben Workflow-
Laufs. Er behält Ref, Commit-SHA und Tag-Eingabe bei und durchläuft weiterhin
den Schutz des Environments. Ein vorhandener Tag wird nur akzeptiert, wenn er
annotiert ist und exakt auf dieselbe SHA zeigt; Tags werden nie verschoben oder
ersetzt.

Ein vorhandener Draft zum Tag darf mit erneut aus diesem Tag gebauten Assets
vervollständigt werden. Ein bereits veröffentlichter Release ist terminal und
wird weder inventarisiert noch repariert oder als Erfolg eines neuen Laufs
umgedeutet. Scheitert nur die nachgelagerte Demo-Promotion, bleibt der
Produktrelease abgeschlossen. Ein Re-Run des fehlgeschlagenen Promotionsjobs
darf ein bereits vorhandenes, provenance-attestiertes und manifestseitig
passendes Demo-Paar wiederverwenden; bewegliche Paketreferenzen werden nie
überschrieben. Der Fehler wird getrennt vom Produktrelease berichtet.

Der erste GHCR-Push kann ein neues Paket zunächst privat anlegen. Seine
öffentliche Sichtbarkeit bleibt eine bewusste Maintainer-Entscheidung in den
Package-Einstellungen. Ein fehlgeschlagener Publish erzeugt keinen sichtbaren
GitHub Release, weil dieser bis zum letzten Schritt Draft bleibt.

Produkt-Backup, Restore und Rollback sind nicht Teil des Release-Retry. Die
historische Betriebsgrenze von `v0.1.0` bleibt unverändert in den
[Release-Nachweisen](release-evidence-v0.1.0.md) dokumentiert.
