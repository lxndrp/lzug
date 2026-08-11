# Changelog

Alle wesentlichen Änderungen an `lzug` werden in dieser Datei dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de-DE/1.1.0/),
Versionen folgen [Semantic Versioning](https://semver.org/lang/de/). Vor dem
ersten freigegebenen Release existiert bewusst noch kein datierter
Versionsabschnitt.

## [Unreleased]

### Added

- Nachvollziehbarer SemVer-, GitHub-Release- und GHCR-Prozess mit SBOM und
  signierten Herkunftsnachweisen.
- Dokumentierte Compose-Referenzen für konkrete GHCR-Versionen und Digests.

Bei einer Release-Vorbereitung verschiebt ein Maintainer die freigegebenen
Einträge in genau einen Abschnitt `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`. Der
Release-Workflow übernimmt ausschließlich diesen Abschnitt als Release Notes
und weist einen Tag ohne passenden Abschnitt oder ohne dieselbe Version in
`VERSION`, Python- und Frontend-Metadaten ab.
