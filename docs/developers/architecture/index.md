# Architekturübersicht

`lzug` besteht aus einem Angular-Frontend in `frontend/`, einem Python-Backend in `backend/`, einer lokalen SQLite-Datenbank und einem statischen frühen Prototypen unter `prototypes/pruefungsrunde-prototyp/`. Die produktive Weiterentwicklung findet im Frontend und Backend statt; der Prototyp bleibt ausschließlich fachliche und UX-bezogene Referenz.

Die zentralen Schichten sind:

```text
Angular-Frontend
  -> JSON-API mit OpenAPI-Vertrag
  -> HTTP-Handler, Repositories und Planungsservice
  -> SQLAlchemy-Modelle und Store
  -> SQLite-Datenbank
```

Python `3.14.6`, Node.js `26.5.0`, npm, `mise`, `uv` und Task sind projektweit festgelegt. Die Pins liegen in `.mise.toml`, `.python-version`, `.node-version`, `uv.lock` und `frontend/package-lock.json`; die lokalen Workflows stehen in `Taskfile.yml`.

Die Architekturentscheidungen stehen als [ADRs](../decisions/index.md).

## Veröffentlichungs- und Betriebsarchitektur

Die erste Veröffentlichung ist auf dezentrales Self-Hosting je Ausschuss
ausgerichtet. Eine Instanz bildet keine fachliche Mandantenflotte ab; sie
läuft als einzelnes OCI-Image mit SQLite und dem persistenten Datenverzeichnis
`/data`. Die öffentliche Azure-Demo ist davon als flüchtige, statische
Landingpage mit Demo-Instanz getrennt. Eine spätere zentral betriebene
Mandantenflotte wird aus getrennten Container Apps und getrennter
Datenhaltung bestehen.

Die verbindlichen Entscheidungen und ihre Umsetzungsschnittstellen sind:

| ADR | Geltungsbereich | Entsperrt insbesondere |
| --- | --- | --- |
| [ADR-0013](../decisions/0013-dezentrale-instanzen-je-ausschuss.md) | Instanzgrenze je Ausschuss ohne fachliche Mandantenfähigkeit | #116, #118 |
| [ADR-0014](../decisions/0014-oci-einzelcontainer-und-persistentes-data.md) | OCI-Einzelcontainer, SQLite und `/data` | #115, #116, #118 |
| [ADR-0015](../decisions/0015-fluechtige-azure-demo.md) | Flüchtige Azure-Container-Apps-Demo | #124–#129 |
| [ADR-0016](../decisions/0016-spaetere-mandantenflotte.md) | Späteres Zielbild mit getrennten Mandanteninstanzen | #133, #134 |
| [ADR-0017](../decisions/0017-erstveroeffentlichung-ohne-kubernetes.md) | Bewusster Verzicht auf Kubernetes und Helm für die erste Veröffentlichung | #115, #119 |

Die vorhandene Backend-Sprache Python bleibt von diesen Entscheidungen
unberührt. Ein Sprachwechsel ist ein separates Vorhaben und keine
Betriebsmaßnahme.

Die konkrete Einzelcontainer-Umsetzung, ihre Build-Stufen, die statische
Auslieferung und die Docker-/Podman-Smoke-Prüfung beschreibt die
[OCI-Runtime](oci-runtime.md). Die kanonische
[Docker-Compose-Referenzinstallation](compose-self-hosting.md) ergänzt den
reproduzierbaren Self-Hosting- und Persistenzpfad.
Die [Veröffentlichungs- und Runtime-Sicherheitsbaseline](security-baseline.md)
inventarisiert die öffentliche HTTP-Grenze, die blockierenden Security-Gates
und die sichere Produktionskonfiguration.

Die lokale Kontenpflege ohne Netzwerk-Admin-Endpunkt beschreibt die
[Betreiber-CLI für Authentifizierung](operator-auth-cli.md). Sie bleibt eine
separate Go-Betriebsgrenze und nutzt im Container ausschließlich den
versionierten Python-Adminvertrag.
