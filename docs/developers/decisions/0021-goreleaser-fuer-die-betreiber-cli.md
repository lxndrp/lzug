# ADR-0021: GoReleaser für die Betreiber-CLI

## Datum

2026-08-13.

## Status

Akzeptiert.
Konkretisiert [ADR-0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) für die Verpackung der Betreiber-CLI.
Die hier genannte ursprüngliche GoReleaser-Version dokumentiert den damaligen
Beschluss, nicht den aktuellen Pin; maßgeblich ist `.mise.toml`.
Die allgemeine Release-Orchestrierung bleibt Aufgabe der aktuellen Release-
Workflows.

## Kontext

Der bisherige Python-Builder implementierte Go-Cross-Build, Archivierung und Byte-Stabilität selbst.
Im veröffentlichten Vertrag von `v0.1.0` enthält jedes der sechs Archive für Linux, macOS und Windows auf `amd64` und `arm64` genau das unversionierte Binary und `build-metadata.json`.
Die Dateinamen bleiben `lzug-admin-VERSION-BETRIEBSSYSTEM-ARCHITEKTUR` mit `tar.gz` beziehungsweise `zip` für Windows.

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
`operator-cli/.goreleaser.yml` beschreibt die sechs Builds und Archive sowie
die mitzuliefernden Dateien. Jedes Archiv enthält das Binary,
`build-metadata.json`, `LICENSE` und `THIRD_PARTY_NOTICES.md`; die beiden
Hinweisdateien werden vor dem Build aus den Repository-Quellen kopiert.
Die Konfiguration ist die maßgebliche Beschreibung des Lieferumfangs und wird
im Review anhand von Plattformen, Archivformaten und Dateien bewertet.

Der komponenteneigene Vertrag in `backend.version` erzeugt und validiert
Build-Metadaten einschließlich Entwicklungsidentität.
Aufrufer verantworten Git-Revision und Tagzielprüfung; die kanonische
Konfiguration sowie die aktuellen Build- und Paketierungsdetails stehen in
`operator-cli/.goreleaser.yml` und den dazugehörigen Tasks.

Die Reproduzierbarkeitsprüfung erzeugt zwei saubere GoReleaser-Builds und
vergleicht Archive und Binärdateien anhand des GoReleaser-Manifests.
Eine persistente oder wiederverwendete Baseline wird nicht gepflegt.
Der aktuelle Einstieg steht im Werkzeuginventar unter
[Operator-CLI-Reproduzierbarkeit](../script-inventory.md).

## Integration in #347

Die GoReleaser-Konfiguration beschreibt die CLI-Ausgaben.
Die aktuelle Release-Assetmenge und Attestierung sind Liefervertrag des
Release-Workflows, keine von diesem ADR duplizierte SBOM- oder Release-
Orchestrierungsregel.
GoReleaser erzeugt keine SBOMs oder zusätzlichen sichtbaren Prüfsummenassets;
SBOMs werden gemäß ADR-0038 ausschließlich für veröffentlichte OCI-Images
erzeugt.
Issue #347 hat die damals geplante Integration umgesetzt.

## Konsequenzen

Der eigene Builder und seine Implementierungstests entfallen.
Die verbleibende projektspezifische Logik prüft nur Produktmetadaten und beobachtbare Artefaktinvarianten.
Ein Upgrade von Go oder GoReleaser muss die Reproduzierbarkeitsprüfung mit
zwei sauberen Builds bestehen; ohne Bytegleichheit oder bei zusätzlichen
Artefakten ist es nicht zulässig.
Der aktuelle Task- und Laufzeitvertrag bleibt in nativer Konfiguration und
Werkzeuginventar maßgeblich; diese ADR-Fassung hält die ursprüngliche
GoReleaser-Entscheidung und nicht jedes aktuelle Taskdetail fest.
Die allgemeine Zuordnung verbleibender Logik und die Vorrangregel für native
Werkzeugkonfiguration folgen [ADR-0039](0039-deklarative-toolchain-zustaendigkeiten.md).

## Alternativen

- Den Python-Builder behalten: erfüllt den Vertrag, dupliziert aber
Standardfunktionen für Cross-Build und Archive.
- GoReleaser einschließlich GitHub-Publisher verwenden: würde die in ADR-0020
festgelegte Orchestrierungsgrenze verwischen und den Vertrag der sechs sichtbaren CLI-Archive unnötig gefährden.
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
