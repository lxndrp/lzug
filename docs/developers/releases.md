# Releases und GHCR

!!! danger "Keine manuelle Veröffentlichung"

    Maintainer erzeugen oder verschieben Release-Tags, GitHub Releases,
    OCI-Tags und spätere CLI-Artefakte nicht manuell. Nur ein automatisch
    erzeugtes Release-Issue, sein berechtigtes Schließen und die getrennte
    Freigabe des GitHub-Environments `release` dürfen den Publish-Job starten.

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

Das standardisierte GitHub-Issue-Formular `Release-Freigabe` dokumentiert den
Pflichtumfang für besondere manuelle Gates. Die Kandidatenautomation erzeugt
inhaltlich äquivalente Freigabe-Issues mit einem versionierten, nicht
nachbaubaren Maschinenmarker. Pflichtfelder und einzeln verbindliche
Checkboxen verhindern, dass Kandidat, Qualitäts- und
Security-Nachweise, Betriebs- und Wiederherstellungsprüfung, Pilotbefunde,
Releaseinformationen oder die ausdrückliche Maintainer-Entscheidung
stillschweigend ausgelassen werden.

Der Release-Workflow darf einen Milestone nur auf Vollständigkeit prüfen. Er
darf dessen Namen weder als Versionsquelle noch als Build-Eingabe verwenden.
Normale Entwicklungsbuilds verwenden keine geplante Releaseversion.

## Kandidatenautomation

`.github/workflows/release-candidate.yml` reagiert auf das Schließen eines
regulären Milestone-Issues. Der Workflow pinnt den zu diesem Zeitpunkt
aktuellen `master`-Commit, wartet begrenzt auf seine sieben stabilen
Qualitätsgates und prüft das aktive strikte Ruleset. Nur wenn kein anderes
reguläres Milestone-Issue offen ist, erzeugt oder setzt er genau ein offenes
Release-Issue zurück. Er checkt ausschließlich das geschützte `master`-Tooling
ohne persistierte Zugangsdaten aus und besitzt neben Lesezugriff nur
`issues: write`.

Das automatisch erzeugte Issue enthält einen exakten Maschinenmarker, Tag,
Kandidat-SHA und auslösendes Issue. Ein vorhandenes offenes Gate wird bei einer
notwendigen Korrektur vollständig auf den neuen geprüften Kandidaten
zurückgesetzt, damit alte Nachweise und Checkboxen nicht stillschweigend für
einen anderen Commit gelten. Ein bereits abgeschlossenes Gate erzeugt keinen
zweiten Release.

## Build-Metadaten-Schnittstelle

`backend.build_metadata.BuildMetadata` definiert genau ein byte-stabiles
JSON-Objekt mit `identity`, vollständiger `revision`, `release` und optionalem
`tag`. Backend, kompiliertes Frontend, Betreiber-CLI und OCI-Image verwenden
dasselbe Objekt beziehungsweise dieselben validierten Felder. Die Runtime-
Smoke-Tests vergleichen Backend, Frontend, CLI und OCI-Labels automatisiert.

Ein normaler Commit erhält ausschließlich die Entwicklungsidentität
`0.0.0-dev+sha.<40-stellige Commit-SHA>`. Ein Release erhält seine Identität
nur aus einem Tag `vMAJOR.MINOR.PATCH` oder `vMAJOR.MINOR.PATCH-rc.N`, der auf
exakt den gebauten Commit aufgelöst wurde. Abweichende Tags, verkürzte oder
nicht hexadezimale Revisionen und widersprüchliche JSON-Felder werden
fail-closed abgewiesen. Milestones und die Paketversionen in `pyproject.toml`
und `frontend/package.json` sind keine Build-Eingaben.

Lokale Builds leiten die Metadaten reproduzierbar aus `git rev-parse HEAD` ab:

```sh
python3 scripts/build_metadata.py
npm --prefix frontend run build:ci
task quality:operator
task quality:oci
```

Das OCI-Image enthält dasselbe JSON unter `/app/build-metadata.json` und im
Frontend-Bundle. `lzug-admin --build-metadata` gibt es in derselben kanonischen
Form aus; `--version` zeigt dessen `identity`. Eine Umgebungsvariable kann
keine andere Releaseversion vortäuschen.

Öffentliche stabile Releases verwenden SemVer-Tags der Form
`vMAJOR.MINOR.PATCH`; geplante Vorabreleases verwenden ausschließlich
`vMAJOR.MINOR.PATCH-rc.N`. Die Änderungsklassen sind:

- `PATCH`: kompatible Fehler- oder Sicherheitskorrektur,
- `MINOR`: kompatible neue Funktion,
- `MAJOR`: inkompatible Änderung am veröffentlichten Vertrag.

Vor dem Tag verschiebt der Release-PR die freizugebenden Einträge aus
`[Unreleased]` in `CHANGELOG.md` nach
`[MAJOR.MINOR.PATCH] - YYYY-MM-DD` beziehungsweise
`[MAJOR.MINOR.PATCH-rc.N] - YYYY-MM-DD`. Genau dieser datierte Abschnitt wird
zu den Release Notes. Ein fehlender, leerer oder doppelter Abschnitt blockiert
die Veröffentlichung.

## Maintainer-Ablauf

1. Vor dem letzten regulären Milestone-Issue verschiebt ein eigener Release-PR
   die freizugebenden Changelog-Einträge in den datierten Versionsabschnitt.
   Normale Review- und Merge-Regeln gelten unverändert.
2. Das letzte reguläre Issue schließen und den automatisch erzeugten Kandidaten
   einschließlich SHA und Qualitätsläufen prüfen.
3. Das Release-Issue vollständig kuratieren. Es dokumentiert Scope-Freeze,
   Security, Lieferkette, Betrieb, Wiederherstellung, Befunde, Release Notes und
   die ausdrückliche `GO`-Entscheidung.
4. Nur eine Person mit `maintain` oder `admin` schließt das Release-Issue. Der
   Workflow prüft Autor, Marker, Milestone, Kandidat, Ruleset, Checks,
   Berechtigung und vorhandene Tags/Releases erneut serverseitig.
5. Den Environment-geschützten Publish-Job separat freigeben. Erst dieser Job
   erzeugt den annotierten Remote-Tag und erhält Schreibrechte auf Contents,
   Packages und Attestations.
6. Der Lauf gilt erst nach erfolgreicher anonymer Digestprüfung,
   Attestationsprüfung und Veröffentlichung des vollständigen GitHub Release
   als abgeschlossen.

Das Environment `release` verlangt derzeit `lxndrp` als Required Reviewer und
akzeptiert ausschließlich Deployments vom geschützten Branch. Weil aktuell nur
eine Maintainer-Person vorhanden ist, bleibt `prevent_self_review` gemäß
ADR-0018 deaktiviert. GitHub meldet `can_admins_bypass: true`; dieser nur in den
Environment-Einstellungen angebotene Bypass bleibt als sichtbare
Maintainer-Härtung zu deaktivieren, sobald die organisatorische Freigaberegel
dies zulässt. Sobald eine zweite unabhängige Maintainer-Rolle existiert, werden
zusätzlich Selbstfreigaben verhindert und die Reviewer-Zuordnung überprüft.

Beim allerersten Push legt GHCR ein Container-Paket zunächst privat an. Diese
Sichtbarkeit ist eine einmalige, ausdrückliche Maintainer-Entscheidung und wird
nicht mit erweiterten Tokens automatisiert: Das neu verknüpfte Paket in den
GitHub-Package-Einstellungen auf `public` setzen und den fehlgeschlagenen
Workflow erneut starten. Vor dem finalen GitHub Release meldet sich der
Workflow aus GHCR ab und prüft den Digest anonym; eine private oder nicht
abrufbare Referenz lässt den Release als unvollständig fehlschlagen.

Der Workflow akzeptiert nur einen Commit, der von `master` erreichbar ist und
für den die sieben stabilen Quality-Gates erfolgreich sind. Vor dem
Environment-Gate erzeugt er ausschließlich einen lokalen annotierten Tag als
Versionsquelle, baut das Release-Image einmal, prüft Revision, Non-Root-
Vertrag, Health/API/SPA, CLI-Identität, Laufzeithärtung und
High-/Critical-Befunde und übergibt nur die per SHA-256 und Manifest geprüften
Inputs an den Publish-Job.

Das versionierte `release-manifest.json` ist der Integrationspunkt für #273.
Die dort für `v0.1.0` erzeugten CLI-Binaries werden vor dem Environment-Gate
unter `release-assets/cli/` abgelegt, mit `task sbom:cli` einzeln inventarisiert
und im Manifest bytegenau gehasht. Der Publish-Job darf nur diese qualifizierten
Dateien zusammen mit den danach erzeugten Attestations hochladen. #328 baut
oder veröffentlicht diese Binaries nicht.

## Veröffentlichte Tags und Nachweise

Ein Release `v1.2.3` aus Commit `<40-stellige SHA>` veröffentlicht genau diese
GHCR-Referenzen:

```text
ghcr.io/lxndrp/lzug:1.2.3
ghcr.io/lxndrp/lzug:1.2
ghcr.io/lxndrp/lzug:1
ghcr.io/lxndrp/lzug:sha-<40-stellige SHA>
```

Ein Vorabrelease wie `v1.0.0-rc.1` veröffentlicht ausschließlich
`1.0.0-rc.1` und `sha-<SHA>`. Er bewegt keine stabilen Major- oder Minor-
Aliase.

Der Workflow pusht kein `latest`. Nach dem Push liest er für jeden Tag das
Registry-Manifest und verlangt denselben `sha256`-Digest. Die Qualifizierung
erzeugt mit der gepinnten Syft-Version zwei CycloneDX-1.6-Artefakte: Die
Image-SBOM beschreibt ausschließlich das geprüfte OCI-Image; die
Dependency-SBOM inventarisiert die locked Python- und npm-Abhängigkeiten sowie
vorhandene Drittmodule aus `go.mod` für Lieferketten- und Lizenzreview.
Anschließend erzeugt GitHub mit kurzlebiger OIDC-Identität zwei signierte
Sigstore-Attestations: SLSA-Build-Provenance und die Image-SBOM. Nur die
Image-SBOM wird an den OCI-Digest gebunden; die Dependency-SBOM behauptet nicht,
dass npm-Buildwerkzeuge oder eine separat gebaute CLI im Image enthalten sind.
Der Publish-Job besitzt nur die benötigten Schreibrechte für Packages,
Attestations, OIDC und den GitHub Release; Build und Prüfung laufen read-only.
Das Paket ist über das OCI-Source-Label und den Workflow-`GITHUB_TOKEN` mit dem
Repository verknüpft; die öffentliche Sichtbarkeit wird trotzdem separat und
bewusst bestätigt.

Die finalen Releaseinformationen enthalten:

- die konkrete Image-Referenz mit Digest,
- alle für die Releaseklasse vorgesehenen Tags,
- Image- und Dependency-SBOM als getrennte CycloneDX-Release-Artefakte,
- die signierten Provenance- und SBOM-Bundles,
- Links zu beiden GitHub-Attestations und zum Build-Lauf,
- SHA-256-Prüfsummen der beigefügten Nachweise.

`release-assets/cli/` und das versionierte Release-Manifest sind der
verbindliche Erweiterungspunkt für #273. Für jedes dort erzeugte native Binary
liefert `task sbom:cli` denselben gepinnten Syft-/CycloneDX-Vertrag und prüft das
Hauptmodul, die Go-Standardbibliothek sowie deklarierte Drittmodule. #273
entscheidet und implementiert Buildmatrix, Assetnamen, Manifestaufnahme,
Checksums und artefaktbezogene Attestations. Bereits unabhängig davon verlangt
die Dependency-SBOM alle Drittmodule aus `go.mod` für den Lizenzreview.

Der Herkunftsnachweis eines veröffentlichten Digests lässt sich prüfen mit:

```sh
gh attestation verify \
  "oci://ghcr.io/lxndrp/lzug@sha256:<64 hexadezimale Zeichen>" \
  --repo lxndrp/lzug
```

## Fehler- und Wiederanlaufverhalten

Dieser Abschnitt beschreibt ausschließlich Release-Recovery. Er ist kein
Produkt-Rollback: Er setzt weder SQLite, Dokumente, Authentifizierungszustand
noch ein betriebenes Image auf einen früheren konsistenten Stand zurück.
Upgrade, allgemeines Backup und Restore sowie Produkt-Rollback werden für
`v0.1.0` ausdrücklich nicht unterstützt und sind für `v0.6.0` geplant.

Vor Build, Smoke-Test, Scan, Push und Attestations existiert kein GitHub
Release. Danach erstellt oder aktualisiert der Workflow zunächst ausschließlich
einen Draft, lädt alle Nachweise hoch und veröffentlicht ihn erst im letzten
Schritt. Ein Teilfehler kann dadurch zwar bereits unveränderliche GHCR-Inhalte
oder einen Draft hinterlassen, aber keinen irreführend vollständigen GitHub
Release. Ein Wiederanlauf darf denselben Draft aktualisieren; einen bereits
veröffentlichten Release überschreibt er nicht.

Ein fehlgeschlagener oder abgebrochener Lauf öffnet das Release-Issue wieder
und verlinkt den unvollständigen Lauf. Ein bereits exakt für dieses Gate
erzeugter annotierter Tag darf beim erneuten Schließen wiederverwendet werden;
ein abweichender, leichter oder verschobener Tag blockiert fail-closed.

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

### Betreiber-CLI aus einem Release installieren und verifizieren

Jedes Release veröffentlicht genau sechs versionierte Archive unter den
Release-Assets. Die Matrix ist `linux`, `darwin` und `windows`, jeweils mit
`amd64` und `arm64`; Linux und macOS verwenden `.tar.gz`, Windows `.zip`.
Archive und die jeweils zugehörigen CycloneDX-SBOMs liegen unter
`release-assets/cli/`. Das Manifest und die Checksums werden aus demselben
Kandidaten-Commit erzeugt.

Unter Linux oder macOS werden das passende Archiv und
`lzug-admin-<version>.checksums.txt` heruntergeladen und in ein leeres
Verzeichnis gelegt. Der Checksum-Eintrag wird auf den lokalen Archivnamen
reduziert, weil GitHub Release-Assets ohne das Verzeichnispräfix speichern:

```sh
version=0.1.0
archive="lzug-admin-${version}-linux-amd64.tar.gz"
expected=$(awk -v archive="$archive" '$2 == archive { print $1; found = 1 } END { if (!found) exit 1 }' \
  "lzug-admin-${version}.checksums.txt")
actual=$(sha256sum "$archive" | awk '{ print $1 }')
test "$actual" = "$expected"
```

Der konkrete Vergleich muss den ausgegebenen Hash mit dem ersten Feld der
gefilterten Checksum-Zeile vergleichen. Für macOS kann dafür `shasum -a 256`
statt `sha256sum` verwendet werden. Anschließend wird das Archiv entpackt und
`lzug-admin --version` ausgeführt. Die sechs Archive tragen die Identität
`<version>`; `lzug-admin --build-metadata` muss zusätzlich die im Release
genannte Kandidaten-Revision und das Tag ausgeben.

Unter Windows wird die gleiche Prüfung in PowerShell ausgeführt:

```powershell
$archive = "lzug-admin-0.1.0-windows-amd64.zip"
$expected = (Get-Content "lzug-admin-0.1.0.checksums.txt" |
  Where-Object { $_ -match "  $([regex]::Escape($archive))$" }).Split()[0]
$actual = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "CLI checksum mismatch" }
Expand-Archive $archive -DestinationPath .
.\lzug-admin.exe --version
```

Nach der Checksum-Prüfung kann die signierte Herkunft des Archivs mit GitHub
CLI geprüft werden:

```sh
gh attestation verify ./lzug-admin-0.1.0-linux-amd64.tar.gz \
  --repo lxndrp/lzug
```

Ein fehlendes Archive, ein abweichender Hash, eine fehlende SBOM oder eine
fehlende Attestation ist kein teilweise nutzbarer Release, sondern ein
Fehlerfall. Das Manifest wird nicht manuell repariert; der Release-Gate-Lauf
öffnet sich wieder und muss nach der Korrektur denselben vollständigen
Kandidaten erneut qualifizieren.
