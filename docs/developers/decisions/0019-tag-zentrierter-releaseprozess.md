# ADR-0019: Tag-zentrierter minimaler Releaseprozess

## Status

Akzeptiert am 13.08.2026. Löst ADR-0018 hinsichtlich Kandidaten- und
Veröffentlichungsablauf ab; die Trennung von SemVer-Milestones, Project und
technischer Versionsidentität bleibt bestehen.

## Kontext

Der bisherige Ablauf hielt denselben Quellstand als Kandidaten-SHA im
Release-Issue, lokalen Qualifizierungstag und späteren Remote-Tag fest. Er
wiederholte außerdem CI-Abfragen, Runtime-Tests und Security-Scans, die bereits
in Pull-Request- und `master`-CI durchgeführt worden waren. Das erhöhte Dauer
und Recovery-Komplexität ohne eine zusätzliche fachliche Aussage.

## Entscheidung

- Ein SemVer-Milestone bleibt die fachliche Freigabegrenze. Sein letztes
  reguläres geschlossenes Issue erzeugt automatisch ein offenes Release-Issue.
- Der Workflow bestimmt einmalig den aktuellen `master`-Commit und liest nur
  dessen sieben erfolgreichen verpflichtenden CI-Gates. Er pollt nicht und
  wiederholt keine Qualitäts- oder Security-Prüfungen.
- Die Required-Reviewer-Freigabe des Environments `release` ist die einzige
  menschliche GO-Entscheidung. Danach erzeugt der Workflow den annotierten
  SemVer-Tag auf dem vorgeprüften Commit.
- Der Tag ist ab seiner Erzeugung die einzige technische Release-Identität.
  Build-Metadaten, OCI-Image, CLI-Archive, SBOMs, Attestations und GitHub
  Release werden ausschließlich aus ihm abgeleitet.
- Ein fehlgeschlagener Lauf lässt das Gate-Issue offen. Der Dispatch-Retry
  verwendet einen vorhandenen annotierten Tag unverändert und erzeugt keine
  abweichende Version.
- Release-Issue-Abhängigkeiten werden nicht synchronisiert. Die direkte,
  einmalige Abfrage der offenen regulären Milestone-Issues ist maßgeblich.

## Konsequenzen

- `scripts/release_gate.py`, `scripts/release.py`, der Candidate-Workflow und
  das manuelle Gate-Formular entfallen.
- `build_metadata.py`, `build_cli_release.py` und `sbom.py` bleiben erhalten,
  weil sie gemeinsame Build- beziehungsweise Lieferartefaktverträge abbilden
  und auch außerhalb der Release-Steuerung verwendet werden.
- Der Publish-Job baut weiterhin die auszuliefernden Artefakte, führt aber
  keine Smoke-Tests, Trivy-Scans, interne Artefaktübergaben oder
  Attestation-Wiederholungen aus.
- Künftige GitHub Releases veröffentlichen genau sechs installierbare
  CLI-Archive und eine aggregierte CycloneDX-SBOM. Detaillierte SBOMs und
  Subject-Prüfsummen bleiben temporäre Eingaben signierter Attestations;
  GitHubs Asset-Digests ersetzen eine eigene sichtbare Prüfsummendatei.
- Ein bereits veröffentlichter Release schließt einen Retry nur bei seinem
  generationsspezifisch vollständigen Bestand idempotent ab. Der historische
  Release `v0.1.0` bleibt dabei unverändert.
- Ein Milestone ist kein technischer Inhaltsfilter: Der Tag markiert den
  erfolgreich geprüften `master`-Stand zum Zeitpunkt der Freigabe.

## Alternativen

- Kandidaten-SHA, lokaler Tag und Remote-Tag parallel fortführen: bietet keine
  zusätzliche Identität gegenüber einem annotierten Tag.
- Alle Tests und Scans beim Release wiederholen: wiederholt die maßgebliche CI
  und verlängert die Freigabe ohne neue Quellgrundlage.
- Release-Branches pro Milestone: würde Milestone-Inhalte strikt isolieren,
  widerspricht aber dem bewusst einfachen `master`-basierten Entwicklungsfluss.

## Referenzen

- [Releases und GHCR](../releases.md)
- [Stabiler Qualitätsvertrag](../continuous-integration.md)
- [ADR-0018](0018-semver-release-und-milestones.md)
- Issue [#339](https://github.com/lxndrp/lzug/issues/339)
