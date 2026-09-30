# Architekturentscheidungen

Diese rückwirkenden ADRs fassen Entscheidungen zusammen, die bereits im Repository umgesetzt oder dokumentiert waren.
Sie ändern keine frühere Historie, machen aber Kontext, Konsequenzen und Verweise dauerhaft auffindbar.
Die [Architekturgrundlage](../architecture.md) ordnet ihren aktuellen
Systemkontext, die Sichten und die verbindlichen Prinzipien ein; dieses
Register bleibt die maßgebliche Liste langfristiger Entscheidungen und ihres
Status.

Der Index erleichtert die Suche und fasst den bekannten Status der
Entscheidungen zusammen.
Die Themen unten sind kuratierte Einstiege, keine zusätzlichen
Entscheidungsquellen; eine ADR kann in mehreren Themen relevant sein.
Die vollständige Statuszuordnung folgt in der unveränderten Nummernfolge.

## Themen

- **Anwendung, Fachlichkeit und Vertrauensgrenzen:** [Persistenz und Backend](0001-lokale-relationale-persistenz.md), [Frontend und API](0004-angular-rest-integration.md), [Instanz- und Datenverantwortung](0013-dezentrale-instanzen-je-ausschuss.md), [Runtime, Admin und Lifecycle](0033-aio-betrieb-admintransport-und-lifecycle.md) sowie [geschützte Artefakte](0031-age-huelle-in-der-betreiber-cli.md).
- **Persistenz, Administration und Betrieb:** [SQLite und SQLAlchemy](0001-lokale-relationale-persistenz.md), [Self-Hosting](0014-oci-einzelcontainer-und-persistentes-data.md), [Betriebszielbilder](0015-fluechtige-azure-demo.md), [Lifecycle](0033-aio-betrieb-admintransport-und-lifecycle.md) und [Versionen/Digests](0034-versionsbindung-und-unveraenderliche-referenzen.md).
- **Release, Artefakte und Demo:** [SemVer, Milestones und Project](0018-semver-release-und-milestones.md), [geltender Releaseablauf](0020-minimaler-releaseablauf-mit-github-bordmitteln.md), [Demo-Assembly und Seed](0022-tag-gebundene-demo-assembly-und-seed.md), [Snapshot-Promotion](0024-manuell-promotete-demo-snapshots.md) und [stabile Demo-Promotion](0026-automatische-demo-promotion-stabiler-releases.md).
- **Entwicklungstoolchain und Qualität:** [Werkzeugwahl](0003-toolchain-mise-uv-npm.md), [öffentliche Taskgrenze](0009-toolchain-und-entwicklungs-tasks.md), [CLI-Paketierung](0021-goreleaser-fuer-die-betreiber-cli.md), [Pester-Vertrag](0037-powershell-pester-testharness.md), [SBOM-Erzeugung](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md) und [aktuelle Zuständigkeitsregel](0039-deklarative-toolchain-zustaendigkeiten.md).
- **Dokumentation und Publikation:** [Dokumentationsgeneratoren](0007-dokumentation-und-code-referenz.md), [geltende Quellen- und Zielgruppentrennung](0035-getrennte-publikations-und-versionsarchitektur.md) und [ADR-Format](0029-einheitliches-nygard-format.md).
- **Künftige Architektur und offene Entscheidungen:** [getrennte Mandantenflotte als Zielbild](0016-spaetere-mandantenflotte.md).
  Browseridentität, vertraulicher Browserzustand und Relay bleiben in den offenen [Issues #904](https://github.com/lxndrp/lzug/issues/904), [#906](https://github.com/lxndrp/lzug/issues/906), [#909](https://github.com/lxndrp/lzug/issues/909), [#912](https://github.com/lxndrp/lzug/issues/912), [#913](https://github.com/lxndrp/lzug/issues/913) und [#914](https://github.com/lxndrp/lzug/issues/914) zu entscheiden; kein ADR hier erklärt sie vorzeitig für akzeptiert.

Bei einer vollständigen oder teilweisen Ablösung benennen beide ADRs den
Zusammenhang und den fortgeltenden Anteil.
Ergänzungen ohne Ablösung werden über Kontext oder Referenzen verbunden.
Die [ADR-Vorlage](TEMPLATE.md) empfiehlt eine einheitliche Orientierung,
erzwingt aber weder exakte Titel und Statuswörter noch eine Abschnittsfolge
oder eine einmalige Registerverlinkung. Review und funktionierende Links
sichern Verständlichkeit und Auffindbarkeit.

| ADR | Entscheidung | Status |
| --- | --- | --- |
| [0001](0001-lokale-relationale-persistenz.md) | Lokale relationale Persistenz | Akzeptiert |
| [0002](0002-python-backend-sqlalchemy.md) | Python-Backend mit SQLAlchemy | Akzeptiert |
| [0003](0003-toolchain-mise-uv-npm.md) | Toolchain mit mise, uv und npm | Akzeptierte Ausgangswahl; Zuständigkeit durch ADR-0039 präzisiert |
| [0004](0004-angular-rest-integration.md) | Angular und REST-Integration | Akzeptiert |
| [0005](0005-taiga-ui.md) | Taiga UI | Akzeptiert |
| [0006](0006-openapi-http-vertrag.md) | HTTP-API als OpenAPI-Vertrag | Akzeptiert |
| [0007](0007-dokumentation-und-code-referenz.md) | MkDocs und Code-Referenzen | Akzeptiert |
| [0008](0008-feiertagsprovider.md) | Kuratierte Feiertagsdaten | Akzeptiert |
| [0009](0009-toolchain-und-entwicklungs-tasks.md) | Toolchain und Entwicklungs-Tasks trennen | Taskgrenze gilt; aktuelle Zuordnung durch ADR-0039 präzisiert |
| [0010](0010-vitest-statt-karma-jasmine.md) | Vitest statt Karma und Jasmine für Frontend-Unit-Tests | Akzeptiert |
| [0011](0011-github-wiki-handbuch.md) | GitHub Wiki als redaktionelle Handbuchoberfläche | Historisch; ADR-0032 ersetzt die Wahl, ADR-0035 den geltenden Quellenstand |
| [0012](0012-wiki-single-source-of-truth.md) | Redaktionelle Single Source of Truth im GitHub Wiki | Historisch; ADR-0032 ersetzt die Wahl, ADR-0035 den geltenden Quellenstand |
| [0013](0013-dezentrale-instanzen-je-ausschuss.md) | Dezentrale Instanzen je Ausschuss | Akzeptiert |
| [0014](0014-oci-einzelcontainer-und-persistentes-data.md) | OCI-Einzelcontainer mit SQLite und persistentem `/data` | Akzeptiert |
| [0015](0015-fluechtige-azure-demo.md) | Flüchtige Azure-Container-Apps-Demo | Akzeptiert |
| [0016](0016-spaetere-mandantenflotte.md) | Spätere getrennte Mandantenflotte | Akzeptiert als Zielbild |
| [0017](0017-erstveroeffentlichung-ohne-kubernetes.md) | Erstveröffentlichung ohne Kubernetes und Helm | Akzeptiert |
| [0018](0018-semver-release-und-milestones.md) | SemVer, Releases und Release-Milestones trennen | SemVer-/Milestone-/Project-Trennung gilt; Kandidatenautomation historisch |
| [0019](0019-tag-zentrierter-releaseprozess.md) | Tag-zentrierter minimaler Releaseprozess | Historische Zwischenentscheidung; wesentliche Steuerung durch ADR-0020 abgelöst |
| [0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) | Minimaler Releaseablauf mit GitHub-Bordmitteln | Geltender Releasevertrag; Artefaktumfang durch ADR-0038 ergänzt |
| [0021](0021-goreleaser-fuer-die-betreiber-cli.md) | GoReleaser für die Betreiber-CLI | Paketierungsentscheidung gilt; aktuelle Konfiguration/Tasks maßgeblich |
| [0022](0022-tag-gebundene-demo-assembly-und-seed.md) | Tag-gebundene Demo-Assembly und inhaltsadressierter Seed | Akzeptiert |
| [0023](0023-oeffentliche-web-und-dokumentationspublikation.md) | Öffentliche Web- und Dokumentationspublikation | Historisch; Plattformwahl durch ADR-0032, geltender Publikationsvertrag durch ADR-0035 abgelöst |
| [0024](0024-manuell-promotete-demo-snapshots.md) | Manuell promotete Demo-Snapshots | Teilweise abgelöst: Snapshot-Regeln gelten; gemeinsame Gates und Abnahme durch ADR-0026 ersetzt |
| [0025](0025-kein-inspec-infrastruktur-harness.md) | Kein InSpec-Infrastruktur-Harness | Entscheidung gegen InSpec gilt; Orchestrierung teilweise durch ADR-0037 abgelöst |
| [0026](0026-automatische-demo-promotion-stabiler-releases.md) | Automatische Demo-Promotion stabiler Releases | Akzeptiert |
| [0027](0027-synchroner-fastapi-migrationskern.md) | Synchroner FastAPI-Kern für die schrittweise HTTP-Migration | Akzeptiert |
| [0028](0028-sbom-orchestrierung-und-cyclonedx-standardwerkzeuge.md) | SBOM-Orchestrierung und CycloneDX-Standardwerkzeuge abgrenzen | Vollständig abgelöst durch ADR-0038 |
| [0029](0029-einheitliches-nygard-format.md) | Einheitliches Nygard-Format für Architekturentscheidungen | Akzeptiert |
| [0030](0030-x25519-aes-gcm-fuer-geschuetzte-artefakte.md) | X25519 und AES-GCM für geschützte Artefakte | Abgelöst durch ADR-0031 |
| [0031](0031-age-huelle-in-der-betreiber-cli.md) | age-Hülle in der Betreiber-CLI | Akzeptiert |
| [0032](0032-repository-zentrierte-oeffentliche-dokumentation.md) | Repository-zentrierte öffentliche Dokumentation | Vollständig abgelöst durch ADR-0035 |
| [0033](0033-aio-betrieb-admintransport-und-lifecycle.md) | AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen | Akzeptiert |
| [0034](0034-versionsbindung-und-unveraenderliche-referenzen.md) | Versionsbindung und unveränderliche Referenzen an Risikogrenzen | Akzeptiert |
| [0035](0035-getrennte-publikations-und-versionsarchitektur.md) | Getrennte Publikations- und Versionsarchitektur | Akzeptiert |
| [0036](0036-powershell-adapter-fuer-werkzeuggrenzen.md) | PowerShell-Adapter für portable Werkzeuggrenzen | Akzeptiert |
| [0037](0037-powershell-pester-testharness.md) | PowerShell/Pester-Testharness | Akzeptiert |
| [0038](0038-syft-standardaufrufe-fuer-sbom-erzeugung.md) | SBOM-Erzeugung als direkte Syft-Standardaufrufe | Teilweise fortgeltend: Syft für Quality/stabile Releases/Demo; Snapshot-Ausnahme siehe Delivery |
| [0039](0039-deklarative-toolchain-zustaendigkeiten.md) | Deklarative Toolchain-Zuständigkeiten | Akzeptiert |
