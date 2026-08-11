# Releases und GHCR

!!! warning "Übergang bis #307 und #308"

    [ADR-0018](decisions/0018-semver-release-und-milestones.md) ersetzt den
    bisherigen manuellen Tag-Ablauf durch einen festgehaltenen
    Kandidat-Commit, ein Release-Issue und ein zusätzliches Environment-Gate.
    Die vorhandene Automation bildet diesen Vertrag noch nicht ab. Bis #307
    und #308 abgeschlossen sind, darf kein Release-Tag erzeugt und keine
    Produktveröffentlichung ausgelöst werden. `VERSION` ist in diesem
    Übergang nur ein abzulösender Bestandswert, keine Quelle für einen
    veröffentlichten oder geplanten Stand.

## Zielvertrag

Der [SemVer- und Release-Vertrag](decisions/0018-semver-release-und-milestones.md)
trennt fünf Zuständigkeiten: Der SemVer-Milestone plant die Zielmenge, der
Kandidat-Commit fixiert den geprüften Quellstand, der annotierte Tag ist die
technische Versionsquelle, der GitHub Release veröffentlicht Notes und Assets,
und das Project steuert Status, Priorität, Iteration, Termine und Aufwand. Die
[kontrollierte Zuordnung](release-milestones.md) schneidet die Vorabversionen
entlang eigenständig nutzbarer Fachprozesse, trennt `v1.0.0-rc.1` als
Winterpilot von der stabilen `v1.0.0` und plant schriftliche Prüfungen mit
`v1.1.0` erst nach der stabilen Freigabe.

Jedes manuell angelegte Freigabe-Issue verwendet das standardisierte
GitHub-Issue-Formular `Release-Freigabe`. #308 muss automatisch erzeugte
Freigabe-Issues inhaltlich äquivalent aufbauen. Pflichtfelder und einzeln
verbindliche Checkboxen verhindern, dass Kandidat, Qualitäts- und
Security-Nachweise, Betriebs- und Wiederherstellungsprüfung, Pilotbefunde,
Releaseinformationen oder die ausdrückliche Maintainer-Entscheidung
stillschweigend ausgelassen werden.

Der Release-Workflow darf einen Milestone nur auf Vollständigkeit prüfen. Er
darf dessen Namen weder als Versionsquelle noch als Build-Eingabe verwenden.
Normale Entwicklungsbuilds verwenden keine geplante Releaseversion. #307
implementiert die Build-Metadaten-Schnittstelle, #308 den Kandidaten- und
Freigabeablauf.

## Noch vorhandener Bestandsprozess

Der derzeitige, ausgesetzte Prozess veröffentlicht ein geprüftes
lzug-OCI-Image nachvollziehbar in GHCR und erzeugt dazu einen GitHub Release.
Ein Merge allein veröffentlicht nichts. Nur ein Maintainer darf nach
abgeschlossener Qualitätssicherung einen Release-Tag pushen; der Workflow
bietet keinen manuellen Dispatch und erzeugt selbst keinen Git-Tag.

## Noch vorhandener Versionsvertrag

Öffentliche Releases verwenden ausschließlich stabile SemVer-Tags der Form
`vMAJOR.MINOR.PATCH`. Pre-Releases und abweichende Tags werden fail-closed
abgewiesen. Die Änderungsklassen sind:

- `PATCH`: kompatible Fehler- oder Sicherheitskorrektur,
- `MINOR`: kompatible neue Funktion,
- `MAJOR`: inkompatible Änderung am veröffentlichten Vertrag.

Vor dem Tag verschiebt der Release-PR die freizugebenden Einträge aus
`[Unreleased]` in `CHANGELOG.md` nach
`[MAJOR.MINOR.PATCH] - YYYY-MM-DD`. Genau dieser datierte Abschnitt wird zu den
Release Notes. Ein fehlender, leerer oder doppelter Abschnitt blockiert die
Veröffentlichung.

Der folgende Absatz beschreibt den noch vorhandenen, durch #307 abzulösenden
Bestandsvertrag: `VERSION` ist derzeit die Anwendungsversion im Source-Code.
Der Release-PR
gleicht damit die Python-Metadaten in `pyproject.toml` und die privaten
Frontend-Metadaten in `frontend/package.json` samt Lockfile ab. Der Workflow
weist einen Tag zurück, sobald Tag, `VERSION` und beide Paketmetadaten
voneinander abweichen. Backend, OpenAPI, öffentlicher Health-Endpunkt und die
angemeldete Oberfläche verwenden denselben Wert; das OCI-Image ergänzt die
Commit-Revision. Portable Builds von `lzug-admin` erhalten die Version über
Go-Linker-Metadaten und zeigen sie mit `lzug-admin --version` an.

## Ausgesetzter Maintainer-Ablauf

Dieser Ablauf ist bis zur Umsetzung des in ADR-0018 festgelegten Verfahrens
ausgesetzt. Der spätere Normablauf beginnt mit dem automatisiert erzeugten
Release-Issue für einen unveränderlich festgehaltenen Kandidat-Commit; das
Schließen durch einen berechtigten Maintainer und die Freigabe des GitHub-
Environments `release` sind getrennte Gates.

1. Einen eigenen Release-PR erstellen, `VERSION`, Python-/Frontend-Metadaten
   und Lockfile angleichen und den datierten Changelog-Abschnitt ergänzen.
   Normale Review- und Merge-Regeln gelten unverändert.
2. Nach dem Merge prüfen, dass für exakt diesen `master`-Commit die Workflows
   `CI`, `OCI`, `Security` und `Operator CLI` erfolgreich abgeschlossen sind.
3. Nach ausdrücklicher Freigabe einen annotierten, nach Möglichkeit signierten
   Tag `vMAJOR.MINOR.PATCH` auf diesen Commit setzen und ausschließlich diesen
   Tag pushen.
4. Den Workflow `Release` beobachten. Er muss vollständig grün sein, bevor der
   Release als veröffentlicht gilt.

Beim allerersten Push legt GHCR ein Container-Paket zunächst privat an. Diese
Sichtbarkeit ist eine einmalige, ausdrückliche Maintainer-Entscheidung und wird
nicht mit erweiterten Tokens automatisiert: Das neu verknüpfte Paket in den
GitHub-Package-Einstellungen auf `public` setzen und den fehlgeschlagenen
Workflow erneut starten. Vor dem finalen GitHub Release meldet sich der
Workflow aus GHCR ab und prüft den Digest anonym; eine private oder nicht
abrufbare Referenz lässt den Release als unvollständig fehlschlagen.

Der Workflow akzeptiert nur einen Commit, der von `master` erreichbar ist und
für den alle vier Push-Workflows erfolgreich waren. Er baut das Release-Image
danach einmal, prüft an genau diesem Image Revision, Non-Root-Vertrag,
Health/API/SPA, Laufzeithärtung und High-/Critical-Befunde und übergibt nur das
per SHA-256 geprüfte Image an den Publish-Job.

## Veröffentlichte Tags und Nachweise

Ein Release `v1.2.3` aus Commit `<40-stellige SHA>` veröffentlicht genau diese
GHCR-Referenzen:

```text
ghcr.io/lxndrp/lzug:1.2.3
ghcr.io/lxndrp/lzug:1.2
ghcr.io/lxndrp/lzug:1
ghcr.io/lxndrp/lzug:sha-<40-stellige SHA>
```

Der Workflow pusht kein `latest`. Nach dem Push liest er für jeden Tag das
Registry-Manifest und verlangt denselben `sha256`-Digest. Anschließend erzeugt
GitHub mit kurzlebiger OIDC-Identität zwei signierte Sigstore-Attestations:
SLSA-Build-Provenance und die CycloneDX-SBOM des geprüften Images. Der
Publish-Job besitzt nur die benötigten Schreibrechte für Packages,
Attestations, OIDC und den GitHub Release; Build und Prüfung laufen read-only.
Das Paket ist über das OCI-Source-Label und den Workflow-`GITHUB_TOKEN` mit dem
Repository verknüpft; die öffentliche Sichtbarkeit wird trotzdem separat und
bewusst bestätigt.

Die finalen Releaseinformationen enthalten:

- die konkrete Image-Referenz mit Digest,
- alle vier Tags,
- die CycloneDX-SBOM als Release-Artefakt,
- die signierten Provenance- und SBOM-Bundles,
- Links zu beiden GitHub-Attestations und zum Build-Lauf,
- SHA-256-Prüfsummen der beigefügten Nachweise.

Der Herkunftsnachweis eines veröffentlichten Digests lässt sich prüfen mit:

```sh
gh attestation verify \
  "oci://ghcr.io/lxndrp/lzug@sha256:<64 hexadezimale Zeichen>" \
  --repo lxndrp/lzug
```

## Fehler- und Wiederanlaufverhalten

Vor Build, Smoke-Test, Scan, Push und Attestations existiert kein GitHub
Release. Danach erstellt oder aktualisiert der Workflow zunächst ausschließlich
einen Draft, lädt alle Nachweise hoch und veröffentlicht ihn erst im letzten
Schritt. Ein Teilfehler kann dadurch zwar bereits unveränderliche GHCR-Inhalte
oder einen Draft hinterlassen, aber keinen irreführend vollständigen GitHub
Release. Ein Wiederanlauf darf denselben Draft aktualisieren; einen bereits
veröffentlichten Release überschreibt er nicht.

Fehlgeschlagene Läufe werden nicht durch einen neuen Versions- oder bewegten
Major-/Minor-Tag kaschiert. Ursache beheben, dieselbe Workflow-Ausführung erneut
starten und Digest sowie alle Nachweise kontrollieren. Tags oder veröffentlichte
Releases werden nur nach einer ausdrücklichen Maintainer-Entscheidung entfernt
oder ersetzt.

## Installation

Die Compose-Referenz akzeptiert ein lokales Test-Image, einen konkreten
veröffentlichten `MAJOR.MINOR.PATCH`-Tag oder vorzugsweise den Digest aus den
Releaseinformationen. Sie verwendet niemals `latest`. Beispiele stehen unter
[Docker-Compose-Referenzinstallation](architecture/compose-self-hosting.md).
