# Releases und GHCR

!!! danger "Keine manuelle Veröffentlichung"

    Maintainer erzeugen oder verschieben weder Release-Tags noch GitHub
    Releases oder OCI-Tags manuell. Der Workflow erstellt den annotierten Tag
    erst nach der Freigabe des GitHub-Environments `release`.

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
5. Der Job erzeugt den annotierten SemVer-Tag auf dem vorgeprüften Commit,
   checkt ausschließlich diesen Tag aus und baut die Release-Artefakte.
6. Der Job erstellt oder aktualisiert zuerst einen GitHub-Draft-Release, lädt
   dessen Assets hoch und veröffentlicht ihn zuletzt. Danach schließt er das
   Release-Issue mit dem Release-Link.

Ein fehlgeschlagener Lauf lässt das Gate-Issue offen. Ein Maintainer startet
den Retry über `Release` und übergibt dessen Issue-Nummer. Existiert der Tag
bereits, ist ausschließlich er die Quelle für den erneuten Lauf; der Tag wird
nicht verschoben oder ersetzt.

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
  `arm64`, jeweils mit CycloneDX-SBOM und sichtbarer SHA-256-Prüfsummendatei.
- Getrennte Dependency- und Image-SBOM sowie GitHub-Attestations für die CLI
  und das OCI-Image.

Der Workflow erzeugt keinen `latest`-Tag. Ein bereits vorhandenes
versionsbezogenes OCI-Image wird beim einmaligen `v0.1.0`-Übergang nur bei
passender Versions- und Revisionsmetadaten wiederverwendet; es wird nicht
überschrieben.

Die Prüfsumme eines heruntergeladenen CLI-Archivs lässt sich beispielsweise so
prüfen:

```sh
version=0.1.0
archive="lzug-admin-${version}-linux-amd64.tar.gz"
expected=$(awk -v archive="$archive" '$2 == archive { print $1; found = 1 } END { if (!found) exit 1 }' \
  "lzug-admin-${version}.checksums.txt")
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

`v0.1.0` ist ein Übergangsfall: Sein bereits vorhandener annotierter Tag wird
per manuellem Workflow-Dispatch als kanonische Quelle verwendet. Der Workflow
vervollständigt nur den noch fehlenden GitHub Release und überschreibt keine
bereits vorhandenen versionsbezogenen OCI-Referenzen.

Produkt-Backup, Restore und Rollback sind nicht Teil dieses
Release-Wiederanlaufs. Die fachliche Betriebsgrenze bleibt für `v0.1.0` in den
[Release-Nachweisen](release-evidence-v0.1.0.md) dokumentiert.
