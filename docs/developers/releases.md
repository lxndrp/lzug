# Releases und GHCR

!!! danger "Keine manuelle Veröffentlichung"

    Maintainer erzeugen oder verschieben weder Release-Tags noch GitHub
    Releases oder OCI-Tags manuell. Der Workflow erstellt den annotierten Tag
    erst nach der Freigabe des GitHub-Environments `release`.

!!! info "Beschlossener Zielablauf"

    [ADR-0020](decisions/0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
    ersetzt die Issue- und Milestone-gesteuerte Release-Automation durch einen
    ausdrücklich auf `master` gestarteten, environment-geschützten Ablauf.
    Bis zur technischen Migration in #347 beschreibt diese Seite darunter den
    operativen Bestand. `v0.1.0` wird durch die Migration nicht verändert.

## Zielvertrag

Der [SemVer- und Release-Vertrag](decisions/0019-tag-zentrierter-releaseprozess.md)
trennt Planung und technische Identität: Der SemVer-Milestone beschreibt die
fachliche Zielmenge, das Project steuert die operative Planung und der
annotierte Git-Tag ist die einzige technische Identität eines Releases.

Ein normaler Commit, Branch-Build oder Pull Request verwendet die
Entwicklungsidentität `0.0.0-dev+sha.<40-stellige Commit-SHA>`. Ein Release
verwendet ausschließlich einen annotierten Tag der Form `vMAJOR.MINOR.PATCH`
oder `vMAJOR.MINOR.PATCH-rc.N`. Backend, Frontend, Betreiber-CLI und OCI-Image
erhalten daraus dieselbe Build-Metadatenstruktur mit Version, vollständiger
Revision und Tag.

Milestones sind keine Build-Eingabe. Ihr Name bestimmt nur den Namen des Tags,
der nach der Freigabe erzeugt wird. Weil `master` der getaggte Quellstand ist,
kann ein Release auch bereits gemergte, spätere Milestone-Arbeit enthalten;
der Milestone ist ein Freigabe-Gate, kein technischer Inhaltsfilter.

## Ablauf

1. Ein Release-PR verschiebt die freizugebenden Changelog-Einträge aus
   `[Unreleased]` in den datierten Abschnitt `MAJOR.MINOR.PATCH`.
2. Das letzte reguläre Issue eines SemVer-Milestones wird geschlossen. Der
   Workflow erzeugt genau ein offenes Release-Issue im selben Milestone.
3. Der Preflight bestimmt einmalig den aktuellen `master`-Commit und liest die
   erfolgreichen verpflichtenden CI-Gates dieses Commits. Fehlende oder
   fehlgeschlagene CI beendet den Lauf ohne Polling; das Gate-Issue bleibt offen.
4. Der Publish-Job wartet auf die Required-Reviewer-Freigabe des Environments
   `release`. Das ist die einzige menschliche GO-Entscheidung.
5. Der Job erzeugt den annotierten SemVer-Tag auf dem vorgeprüften Commit und
   checkt ausschließlich diesen Tag aus.
6. Existiert zu diesem Tag bereits ein veröffentlichter Release, akzeptiert der
   Workflow ihn nur bei passendem Release- und Vorabversionsstatus sowie einem
   vollständigen Satz nichtleerer, hochgeladener und SHA-256-digestierter
   Kern-Assets. Dann überspringt er alle Build-, SBOM-, Attestation- und
   Upload-Schritte und schließt nur noch das Release-Issue.
7. Andernfalls baut der Job die Release-Artefakte, erstellt oder aktualisiert
   zuerst einen GitHub-Draft-Release, lädt dessen Assets hoch und veröffentlicht
   ihn zuletzt. Danach schließt er das Release-Issue mit dem Release-Link.

Ein fehlgeschlagener Lauf lässt das Gate-Issue offen. Ein Maintainer startet
den Retry über `Release` und übergibt dessen Issue-Nummer. Existiert der Tag
bereits, ist ausschließlich er die Quelle für den erneuten Lauf; der Tag wird
nicht verschoben oder ersetzt. Ein abweichender oder unvollständiger bereits
veröffentlichter Release wird nicht repariert oder überschrieben, sondern
beendet den Retry fail-closed. Ein vorhandener Draft wird weiterhin aus dem
kanonischen Tag neu aufgebaut und erst nach dem vollständigen Upload sichtbar.

## CI und Lieferartefakte

Der Release-Workflow wiederholt weder Unit-, Browser-, Container- oder
Security-Tests noch CodeQL oder Trivy. Er liest ausschließlich die sieben
erfolgreichen Quality-Gates des Tag-Ziels:

- `Quality / Backend`
- `Quality / Frontend`
- `Quality / Operator CLI`
- `Quality / OCI`
- `Quality / Documentation`
- `Quality / Security`
- `Quality / Overall`

Der Workflow baut aus dem Tag nur die zu veröffentlichenden Artefakte:

- OCI-Image mit den Tags `MAJOR.MINOR.PATCH`, `MAJOR.MINOR`, `MAJOR` und
  `sha-<Commit>`; Vorabreleases erhalten nur ihren vollständigen SemVer- und
  SHA-Tag.
- Sechs Betreiber-CLI-Archive für Linux, macOS und Windows auf `amd64` und
  `arm64`.
- Genau eine zusammengefasste sichtbare CycloneDX-Datei
  `lzug-MAJOR.MINOR.PATCH.sbom.cdx.json`. Sie inventarisiert die sechs Archive,
  das OCI-Image und die aus den detaillierten Scans zusammengeführten
  Laufzeit- und Build-Abhängigkeiten.

Damit enthält ein künftiger GitHub Release genau sieben Assets. Separate
Prüfsummendateien, plattformspezifische CLI-SBOMs, Dependency-/Image-SBOMs,
Provenance-JSONs und Release-Manifeste werden nicht als Release-Assets
veröffentlicht. GitHub berechnet und zeigt für jedes Asset dessen SHA-256-Digest.

Der Workflow erzeugt die detaillierten Dependency-, Image- und CLI-SBOMs nur
temporär. Aus ihnen entsteht die aggregierte Release-SBOM. Eine signierte
SBOM-Attestation bindet diese über eine ebenfalls nur temporäre Subjectliste
gemeinsam an die sechs Archiv-Digests und den OCI-Digest. Die detaillierte
Image-SBOM wird zusätzlich direkt an den OCI-Digest attestiert und mit der
Attestation in die Registry geschrieben. Die aggregierte SBOM ist damit kein
ungebundener Begleittext; Attestations sind die kanonischen Herkunfts- und
Integritätsnachweise.

Der Workflow erzeugt keinen `latest`-Tag. Ein bereits vorhandenes
versionsbezogenes OCI-Image wird beim einmaligen `v0.1.0`-Übergang nur bei
passender Versions- und Revisionsmetadaten wiederverwendet; es wird nicht
überschrieben.

Den von GitHub erfassten Digest eines Release-Assets zeigt die Release-Ansicht.
Er lässt sich außerdem über die API lesen und lokal vergleichen:

```sh
version=0.1.0
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

Der erste GHCR-Push kann ein neues Paket zunächst privat anlegen. Seine
öffentliche Sichtbarkeit bleibt eine bewusste Maintainer-Entscheidung in den
Package-Einstellungen. Ein fehlgeschlagener Publish erzeugt keinen sichtbaren
GitHub Release, weil dieser bis zum letzten Schritt Draft bleibt.

`v0.1.0` ist ein unveränderter Übergangsbestand aus der vorigen
Release-Generation. Der idempotente Retry akzeptiert ihn nur mit seinem exakten
historischen Satz aus 20 vollständig hochgeladenen und SHA-256-digestierten
Assets. Er löscht, ersetzt oder ergänzt dort keine Assets und überschreibt auch
keine versionsbezogenen OCI-Referenzen. Der Sieben-Asset-Vertrag gilt erst für
nachfolgende Releases.

Produkt-Backup, Restore und Rollback sind nicht Teil dieses
Release-Wiederanlaufs. Die fachliche Betriebsgrenze bleibt für `v0.1.0` in den
[Release-Nachweisen](release-evidence-v0.1.0.md) dokumentiert.
