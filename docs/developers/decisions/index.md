# Architekturentscheidungen

Diese rückwirkenden ADRs fassen Entscheidungen zusammen, die bereits im Repository umgesetzt oder dokumentiert waren.
Sie ändern keine frühere Historie, machen aber Kontext, Konsequenzen und Verweise dauerhaft auffindbar.

Der Index führt den aktuellen Status jeder Entscheidung.
Bei einer vollständigen Ablösung verweisen alter und neuer ADR im jeweiligen Abschnitt `Status` aufeinander (`Superseded by` beziehungsweise `Supersedes`).
Eine Ergänzung oder Präzisierung ohne vollständige Ablösung bleibt ein Verweis im Kontext oder bei den Referenzen.
Alle ADRs folgen der verbindlichen Nygard-Grundstruktur.
Die [ADR-Vorlage](TEMPLATE.md) beschreibt die Pflicht- und optionalen Abschnitte;
die Formatentscheidung steht im Registereintrag für ADR-0029.

| ADR | Entscheidung | Status |
| --- | --- | --- |
| [0001](0001-lokale-relationale-persistenz.md) | Lokale relationale Persistenz | Akzeptiert |
| [0002](0002-python-backend-sqlalchemy.md) | Python-Backend mit SQLAlchemy | Akzeptiert |
| [0003](0003-toolchain-mise-uv-npm.md) | Toolchain mit mise, uv und npm | Akzeptiert |
| [0004](0004-angular-rest-integration.md) | Angular und REST-Integration | Akzeptiert |
| [0005](0005-taiga-ui.md) | Taiga UI | Akzeptiert |
| [0006](0006-openapi-http-vertrag.md) | HTTP-API als OpenAPI-Vertrag | Akzeptiert |
| [0007](0007-dokumentation-und-code-referenz.md) | MkDocs und Code-Referenzen | Akzeptiert |
| [0008](0008-feiertagsprovider.md) | Kuratierte Feiertagsdaten | Akzeptiert |
| [0009](0009-toolchain-und-entwicklungs-tasks.md) | Toolchain und Entwicklungs-Tasks trennen | Akzeptiert |
| [0010](0010-vitest-statt-karma-jasmine.md) | Vitest statt Karma und Jasmine für Frontend-Unit-Tests | Akzeptiert |
| [0011](0011-github-wiki-handbuch.md) | GitHub Wiki als redaktionelle Handbuchoberfläche | Akzeptiert |
| [0012](0012-wiki-single-source-of-truth.md) | Redaktionelle Single Source of Truth im GitHub Wiki | Akzeptiert |
| [0013](0013-dezentrale-instanzen-je-ausschuss.md) | Dezentrale Instanzen je Ausschuss | Akzeptiert |
| [0014](0014-oci-einzelcontainer-und-persistentes-data.md) | OCI-Einzelcontainer mit SQLite und persistentem `/data` | Akzeptiert |
| [0015](0015-fluechtige-azure-demo.md) | Flüchtige Azure-Container-Apps-Demo | Akzeptiert |
| [0016](0016-spaetere-mandantenflotte.md) | Spätere getrennte Mandantenflotte | Akzeptiert als Zielbild |
| [0017](0017-erstveroeffentlichung-ohne-kubernetes.md) | Erstveröffentlichung ohne Kubernetes und Helm | Akzeptiert |
| [0018](0018-semver-release-und-milestones.md) | SemVer, Releases und Release-Milestones trennen | Akzeptiert |
| [0019](0019-tag-zentrierter-releaseprozess.md) | Tag-zentrierter minimaler Releaseprozess | Akzeptiert |
| [0020](0020-minimaler-releaseablauf-mit-github-bordmitteln.md) | Minimaler Releaseablauf mit GitHub-Bordmitteln | Akzeptiert |
| [0021](0021-goreleaser-fuer-die-betreiber-cli.md) | GoReleaser für die Betreiber-CLI | Akzeptiert |
| [0022](0022-tag-gebundene-demo-assembly-und-seed.md) | Tag-gebundene Demo-Assembly und inhaltsadressierter Seed | Akzeptiert |
| [0023](0023-oeffentliche-web-und-dokumentationspublikation.md) | Öffentliche Web- und Dokumentationspublikation | Akzeptiert |
| [0024](0024-manuell-promotete-demo-snapshots.md) | Manuell promotete Demo-Snapshots | Akzeptiert |
| [0025](0025-kein-inspec-infrastruktur-harness.md) | Kein InSpec-Infrastruktur-Harness | Abgelehnt |
| [0026](0026-automatische-demo-promotion-stabiler-releases.md) | Automatische Demo-Promotion stabiler Releases | Akzeptiert |
| [0027](0027-synchroner-fastapi-migrationskern.md) | Synchroner FastAPI-Kern für die schrittweise HTTP-Migration | Akzeptiert |
| [0028](0028-sbom-orchestrierung-und-cyclonedx-standardwerkzeuge.md) | SBOM-Orchestrierung und CycloneDX-Standardwerkzeuge abgrenzen | Akzeptiert |
| [0029](0029-einheitliches-nygard-format.md) | Einheitliches Nygard-Format für Architekturentscheidungen | Akzeptiert |
