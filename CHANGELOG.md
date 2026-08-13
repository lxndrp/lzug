# Changelog

Alle wesentlichen Änderungen an `lzug` werden in dieser Datei dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de-DE/1.1.0/),
Versionen folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

Bei einer Release-Vorbereitung verschiebt ein Maintainer die freizugebenden
Einträge in genau einen Abschnitt `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`. Der
Release-Workflow übernimmt ausschließlich diesen Abschnitt als Release Notes
und veröffentlicht nur aus dem nach der Environment-Freigabe erzeugten,
annotierten SemVer-Tag.

## [0.1.0] - 2026-08-12

### Added

- Reproduzierbare, commitgebundene Versions- und Build-Identität für Backend,
  Frontend, Betreiber-CLI und OCI-Image.
- Sieben stabile Quality-Gates für Backend, Frontend, Betreiber-CLI, OCI,
  Dokumentation, Security und den Gesamtstatus.
- Fail-closed Release-Infrastruktur mit annotiertem SemVer-Tag als kanonischer
  Identität, Environment-Gate und kuratierten Release Notes.
- Qualifizierte Lieferkettennachweise für GHCR-Digest, getrennte
  CycloneDX-Image-/Dependency-SBOMs, Provenance, Attestations und Prüfsummen,
  die der Release-Workflow bei einer späteren Veröffentlichung an diese Notes
  anhängt.
- Compose-Referenz für konkrete GHCR-Versionen und vorzugsweise unveränderliche
  Digests einschließlich Non-Root-, Health- und `/data`-Persistenzvertrag.

### Scope and compatibility

- `v0.1.0` beansprucht ausschließlich die reproduzierbare Versions-, Qualitäts-
  und Release-Infrastruktur. Es ist weder ein fachlich vollständiges noch ein
  produktionsreifes lzug-Release.
- Es gibt keinen veröffentlichten Vorgänger und daher keine Breaking Changes
  oder unterstützte Upgrade-Migration gegenüber einem früheren Release.
- Upgrade, allgemeines Backup und Restore sowie Produkt-Rollback werden für
  `v0.1.0` nicht unterstützt; dieser Betriebsumfang ist für `v0.6.0` geplant.
  Migrationsschutzkopien und der Wiederanlauf eines fehlgeschlagenen
  Release-Workflows ersetzen diese Produktpfade nicht.
- Ein realer Pilot oder veröffentlichter Release Candidate wird nicht
  beansprucht. Die integrierte Wintererprobung ist für `v1.0.0-rc.1` geplant.
- Lizenzinventur, Datenschutzabgrenzung und testgestützte Betriebsgrenzen sind
  im [Entwicklerhandbuch](docs/developers/release-evidence-v0.1.0.md)
  nachvollziehbar dokumentiert. Diese Nachweise sind keine Rechtsberatung und
  keine Zusage für einen produktiven Betrieb.
