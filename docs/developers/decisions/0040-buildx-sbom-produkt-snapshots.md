# ADR-0040: Buildx-SBOM für Produkt-Snapshots

## Datum

2026-09-13.

## Status

Akzeptiert in [PR #805](https://github.com/lxndrp/lzug/pull/805).
Rückwirkend dokumentiert.
Supersedes [ADR-0038](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md)
ausschließlich für SBOMs des Produkt-Snapshot-Images.

## Kontext

[Issue #700](https://github.com/lxndrp/lzug/issues/700) und PR #805
etablieren einen eigenen Snapshot-Kanal für unveränderliche, attestierte
Produktkandidaten ohne GitHub Release oder stabile Produktreferenz.
Der eingeführte Workflow erzeugt für das Produkt-Snapshot-Image eine SBOM
über `docker/build-push-action`.
Die bereits geltende
[Syft-Entscheidung in ADR-0038](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md)
beschreibt dagegen direkte, gepinnte Syft-Aufrufe mit `.syft.yaml`.
Die beiden Veröffentlichungskanäle besitzen damit unterschiedliche
SBOM-Erzeugungspfade.

## Entscheidung

Der Snapshot-Zweig in `.github/workflows/product-publish.yml` aktiviert die
SBOM-Erzeugung des Buildx-Aufrufs mit `sbom: true`.
Die Workflow-Ausgabe bindet die SBOM an den veröffentlichten Snapshot-Digest.
Der Workflow lädt zwar das gepinnte Syft-Binary herunter, verwendet es für
diese SBOM aber nicht und lädt `.syft.yaml` nicht explizit.

Diese Entscheidung gilt ausschließlich für das Produkt-Snapshot-Image.
Das lokale Quality-Image, stabile Produkt-Releases und Demo-Images bleiben
beim Syft-Vertrag aus ADR-0038.
Der Buildx-Pfad behauptet weder gleiche Scanner-Policy noch gleiche
SBOM-Inventare wie der Syft-Pfad.

## Konsequenzen

- Produkt-Snapshot-Kandidaten erhalten weiterhin eine SBOM, ohne dass der
  Workflow dafür den Syft-Aufruf aus ADR-0038 verwendet.
- Die scannerweite Policy aus `.syft.yaml` gilt für diesen Snapshot-Pfad nicht.
- Ein späterer Wechsel des Snapshot-Pfads zu Syft oder einer anderen
  Erzeugungsart benötigt eine eigene Verhaltensänderung und eine Aktualisierung
  dieses ADRs.
- Der aktuelle Ablauf und seine Artefaktnachweise stehen unter
  [Delivery und Veröffentlichung](../delivery.md#release-und-artefakte).

## Referenzen

- [Issue #700](https://github.com/lxndrp/lzug/issues/700)
- [PR #805](https://github.com/lxndrp/lzug/pull/805)
- [ADR-0038: SBOM-Erzeugung als direkte Syft-Standardaufrufe](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md)
