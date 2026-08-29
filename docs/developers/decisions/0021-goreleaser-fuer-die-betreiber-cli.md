# ADR-0021: GoReleaser für die Betreiber-CLI

## Status

Akzeptiert am 13.08.2026.
Konkretisiert [ADR-0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) für die Verpackung der Betreiber-CLI.
Die allgemeine Release-Orchestrierung bleibt Aufgabe von #347.

## Kontext und Evaluation

Der bisherige Python-Builder implementierte Go-Cross-Build, Archivierung und Byte-Stabilität selbst.
Der veröffentlichte Vertrag von `v0.1.0` und die zugehörigen Tests belegen sechs Archive für Linux, macOS und Windows auf `amd64` und `arm64`.
Jedes Archiv enthält genau das unversionierte Binary und `build-metadata.json`; die Dateinamen bleiben `lzug-admin-VERSION-BETRIEBSSYSTEM-ARCHITEKTUR` mit `tar.gz` beziehungsweise `zip` für Windows.

GoReleaser `2.17.1` wurde anhand des veröffentlichten SHA-256-Digests geprüft.
Das Werkzeug steht unter der MIT-Lizenz.
Zwei lokale Snapshot-Läufe bilden den vollständigen Vertrag bytegleich ab.
Deterministisch sind insbesondere die gepinnten Go- und GoReleaser-Versionen, `-trimpath`, die entfernte Go-Build-ID, der Commit-Zeitstempel und zeitunabhängige Linkerwerte.

Die standardmäßig erzeugte GoReleaser-Checksummendatei wäre ein achtes sichtbares Asset und ist daher unzulässig.
`checksum.disable: true` schaltet ihre Erzeugung und Veröffentlichung explizit ab.
`release.disable: true` begrenzt GoReleaser zusätzlich auf Build und Verpackung; dadurch kann es weder einen GitHub Release noch weitere sichtbare Assets erzeugen.

## Entscheidung

GoReleaser `2.17.1` ersetzt den projektspezifischen CLI-Builder.
Die Version ist lokal in `.mise.toml` und in CI gemeinsam mit der auf einen Commit gepinnten offiziellen GoReleaser-Action festgelegt.
`.goreleaser.yml` beschreibt ausschließlich die sechs Builds und Archive.

`scripts/build_metadata.py` bleibt die gemeinsame fail-closed Metadatengrenze.
Bei einem Release prüft sie, dass der SemVer-Tag annotiert ist und exakt auf die gebaute vollständige Revision zeigt.
GoReleaser injiziert dieselbe Version, Revision und denselben Tag in das Binary und nimmt die erzeugte `build-metadata.json` in jedes Archiv auf.
Snapshots verwenden weiterhin die Entwicklungsidentität `0.0.0-dev+sha.<vollständige Revision>`.

`task quality:operator` validiert die Konfiguration, erzeugt zweimal alle sechs Snapshot-Archive und prüft Matrix, Namen, Inhalte, Metadaten, fehlende Checksummendatei sowie Bytegleichheit der Binärdateien und Archive.
Damit wird Verhalten statt GoReleaser-interner Verdrahtung abgesichert.

## Integration in #347

- GoReleaser schreibt Archive, Binärdateien und `artifacts.json` nach `dist/`.
- Der Releaseablauf übernimmt ausschließlich die sechs Archive als sichtbare
CLI-Assets und verwendet die Binärpfade aus `artifacts.json` für temporäre Detail-SBOMs.
- GitHub Attestations attestieren die Archive weiterhin außerhalb von
GoReleaser.
Die temporäre Digestliste für Attestations ist kein Release-Asset.
- Die einzige zusätzlich sichtbare Datei bleibt die aggregierte CycloneDX-SBOM
aus #347.
GoReleaser erzeugt weder eigene SBOMs noch Checksummen- oder Provenance-Dateien.
- Auslöser, Environment-Freigabe, Tag-Erzeugung, OCI-Publish, Draft-Release und
Wiederanlauf bleiben vollständig im Umfang von #347.

## Konsequenzen

Der eigene Builder und seine Implementierungstests entfallen.
Die verbleibende projektspezifische Logik prüft nur Produktmetadaten und beobachtbare Artefaktinvarianten.
Ein Upgrade von Go oder GoReleaser muss die doppelte Snapshot-Prüfung erneut bestehen; ohne Bytegleichheit oder bei zusätzlichen Artefakten ist es nicht zulässig.

## Alternativen

- Den Python-Builder behalten: erfüllt den Vertrag, dupliziert aber
Standardfunktionen für Cross-Build und Archive.
- GoReleaser einschließlich GitHub-Publisher verwenden: würde die in ADR-0020
festgelegte Orchestrierungsgrenze verwischen und den exakt sieben sichtbaren Assets umfassenden Vertrag unnötig gefährden.
- Die GoReleaser-Checksummendatei nur beim Upload herausfiltern: wäre weniger
belastbar als ihre Erzeugung ausdrücklich zu deaktivieren.

## Referenzen

- [GoReleaser 2.17.1](https://github.com/goreleaser/goreleaser/releases/tag/v2.17.1)
- [GoReleaser-Lizenz](https://github.com/goreleaser/goreleaser/blob/v2.17.1/LICENSE.md)
- [Reproduzierbare Go-Builds](https://goreleaser.com/customization/builds/builders/go/#reproducible-builds)
- [Archive](https://goreleaser.com/customization/package/archives/)
- [Checksummen deaktivieren](https://goreleaser.com/customization/package/checksum/)
- [Snapshots](https://goreleaser.com/customization/publish/snapshots/)
- Issues [#345](https://github.com/lxndrp/lzug/issues/345) und
  [#347](https://github.com/lxndrp/lzug/issues/347)
