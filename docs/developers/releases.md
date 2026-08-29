# Releases und GHCR

Releases entstehen ausschließlich über `.github/workflows/release.yml`.
Ein annotierter SemVer-Tag ist die technische Release-Identität; Milestones und Project-Felder sind keine Workfloweingaben.
Weder Tags, GitHub Releases noch OCI-Tags werden manuell erstellt oder verschoben.

## Voraussetzungen

- Der Release-PR enthält einen datierten Changelog-Abschnitt für den geplanten
SemVer-Tag und ist in `master` gemergt.
- Für genau die aktuelle `master`-SHA ist der vollständige Workflow `Quality`
erfolgreich.
- Der Maintainer hat den Tag und die Veröffentlichung freigegeben.

## Veröffentlichung

Der Maintainer startet `Release` auf `master` mit dem vorgesehenen Tag:

```sh
gh workflow run release.yml --repo lxndrp/lzug --ref master \
  -f release_tag=v0.2.0
```

Der Preflight prüft aktuelle `master`-SHA, SemVer, Changelog und Qualitätsnachweis.
Der Publish-Job wartet anschließend im geschützten Environment `release`; erst dessen Freigabe erlaubt die Veröffentlichung.
Aus dem geprüften Tag entstehen OCI-Image, CLI-Archive, aggregierte SBOM und Attestationen.
Der Draft-Release wird erst nach dem Upload aller Artefakte veröffentlicht.
Ein stabiles Release stößt danach die getrennte [Demo-Promotion](demo-deployment.md) an; Release Candidates nicht.

## Ergebnis und Wiederanlauf

Die GitHub-Release-Ansicht liefert die sichtbaren Artefakte und deren Digests.
Die Herkunft eines OCI-Digests lässt sich bei Bedarf prüfen:

```sh
gh attestation verify \
  "oci://ghcr.io/lxndrp/lzug@sha256:<digest>" --repo lxndrp/lzug
```

Bei einem Fehler wird derselbe Workflow-Lauf erneut gestartet.
Ein vorhandener Tag ist nur zulässig, wenn er annotiert ist und auf dieselbe vorgeprüfte SHA zeigt; veröffentlichte Releases und Tags bleiben unveränderlich.
Scheitert nur die Demo-Promotion, bleibt der Produktrelease abgeschlossen und wird getrennt diagnostiziert.
Produkt-Backup, Restore und Instanzrollback gehören nicht zu diesem Veröffentlichungsablauf.
