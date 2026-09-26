# ADR-0038: SBOM-Erzeugung als direkte Syft-Standardaufrufe

## Datum

2026-09-17.

## Status

Akzeptiert.

## Kontext

Syft erzeugt die kanonischen CycloneDX-1.6-Inventare für die veröffentlichten OCI-Images.
Bislang orchestrierte `scripts/sbom.py` die Befehlszusammenstellung, die Binary-Auswahl, die Offline-Konfiguration und den `subprocess`-Start von Syft sowie eigene Detail- und Release-SBOM-Verträge.
Diese rein generische Erzeugung ist keine projektspezifische Grenze.
Issue [#811](https://github.com/lxndrp/lzug/issues/811) und der zugehörige Review fordern, dass Standardwerkzeuge alle generischen Build-, SBOM-, Dokumentations- und Paketprüfungen direkt übernehmen und Eigenlogik nur für konkrete lzug-Verträge bleibt.

## Entscheidung

Image-SBOMs werden als direkte, gepinnte Syft-Aufrufe in `Taskfile.yml` sowie in den Quality- und Publish-Workflows erzeugt.
`scripts/sbom.py` entfällt vollständig.
Die stabile scannerweite Policy liegt deklarativ in `.syft.yaml` und wird bei jedem Aufruf explizit über `--config .syft.yaml` geladen.
Die allgemeine Trennung aus nativer Werkzeug-Policy und dynamischen
Aufrufdaten folgt [ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md).

Der direkte Syft-Aufruf:

- respektiert die Umgebungsvariable `SYFT_BINARY` für den gepinnten CI-Pfad,
- bezieht Updateprüfung, Ausgabeformat, Dateimetadaten und JavaScript-Dev-Abhängigkeiten aus der versionierten `.syft.yaml`,
- hält Scan-Ziel, Ausgabe und den flüchtigen `SYFT_CACHE_DIR` am jeweiligen Task- oder Workflow-Aufruf sichtbar.

`scripts/verify_cli_release.py` entfällt; der Packaging-Build wird zugleich als erster von zwei bytegleichen GoReleaser-Snapshot-Läufen im Quality- und PR-Packaging-Ablauf genutzt, ergänzt um den Go-Vertragstest für die Build-Metadaten.
[ADR-0028](0028-sbom-orchestrierung-und-cyclonedx-standardwerkzeuge.md) wird hierdurch vollständig abgelöst.

## Konsequenzen

- Die OCI-Image-SBOMs bleiben bei unverändertem Syft, Quellen, Flaggen und Umgebung inhaltsgleich.
- Die Erzeugung bleibt in Taskfile und Workflows sichtbar wie die übrigen Standardwerkzeug-Aufrufe.
- `.syft.yaml` bündelt nur die portable, scannerweite Policy; sie enthält weder Artefaktpfade noch Quellidentität, Zielauswahl oder einen benutzerspezifischen Cachepfad.
- Repository-Dependency-, native CLI- und aggregierte Release-SBOMs entfallen, weil sie keinen eigenständigen Vulnerability-Management-Verbraucher bedienen.
- Normale CLI-Fachänderungen lösen keinen pauschalen Doppel-Archivbau aus; die Reproduzierbarkeitsprüfung läuft nur im vollständigen Quality-Gate und bei packaging-relevanten Pull Requests.
- Der direkt ausführbare kanonische FastAPI-Assembly-Einstieg erzeugt das OpenAPI-Dokument für die Publikation; ein separates Exportskript entfällt, ohne den davon getrennten internen Transportgenerator zusammenzuführen.

## Alternativen

- Die Syft-Orchestrierung in `scripts/sbom.py` belassen: hält die Erzeugung unsichtbar hinter einer Projektskriptgrenze, statt sie den Standardwerkzeugen zuzuordnen.
- Die Syft-Aufrufe in eigene Task-Wrapper oder Docker-Adapter verlagern: hätte erneut eine Projektgrenze erzeugt, statt den unveränderten Standardaufruf sichtbar zu machen.
- Den Publikations- und Transportgenerator vollständig zusammenführen: verbindet getrennte Konfigurationsverträge (Publication-Cookie-Name und In-Memory-Cache vs. lokalen Cookie-Transport).

## Referenzen

- [Issue #811](https://github.com/lxndrp/lzug/issues/811): Standardwerkzeuge für generische Prüfungen
- [Review #837](https://github.com/lxndrp/lzug/pull/837): Bestätigung der Standardwerkzeuggrenzen
- [ADR-0020: Minimaler Releaseablauf mit GitHub-Bordmitteln](0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
- [ADR-0021: GoReleaser für die Betreiber-CLI](0021-goreleaser-fuer-die-betreiber-cli.md)
- [ADR-0028: SBOM-Orchestrierung und CycloneDX-Standardwerkzeuge abgrenzen](0028-sbom-orchestrierung-und-cyclonedx-standardwerkzeuge.md)
