# ADR-0017: Erstveröffentlichung ohne Kubernetes und Helm

## Datum

2026-08-08.

## Status

Akzeptiert.

## Kontext

Die erste Veröffentlichung soll für einzelne Ausschüsse mit überschaubarem Betriebsaufwand self-hostbar sein.
Dafür sind ein OCI-Image, SQLite, ein persistent eingebundenes `/data` und eine Docker-Compose-Referenzinstallation ausreichend.
Kubernetes und Helm würden für diesen Zielpfad einen zusätzlichen Cluster- und Paketierungsrahmen voraussetzen.

## Entscheidung

Kubernetes und Helm sind keine Voraussetzung, kein Pflichtbestandteil und kein Installationspfad der ersten Veröffentlichung.
Die Referenz bleibt ein einzelnes OCI-Image mit dem in [ADR-0014](0014-oci-einzelcontainer-und-persistentes-data.md) beschriebenen Datenvertrag; die dokumentierte Self-Hosting-Installation wird über Docker Compose bereitgestellt und soll auch den äquivalenten Podman- Betrieb nicht ausschließen.

Diese Entscheidung verwirft Kubernetes und Helm nicht grundsätzlich.
Ein späterer Bedarf an Clusterbetrieb wäre mit einer neuen, begründeten Architekturentscheidung zu prüfen.

## Konsequenzen

- Betreiber benötigen für die erste Installation keinen Kubernetes-Cluster
und keine Helm-Toolchain.
- Die Release-, Upgrade-, Backup- und Diagnosepfade müssen für die einzelne
Container- und `/data`-Grenze verständlich dokumentiert werden.
- Es gibt für die erste Veröffentlichung keine parallele Helm-Chart-Quelle,
die mit Compose oder dem OCI-Image synchron gehalten werden müsste.
- Ein späterer zentraler Betrieb kann unabhängig davon das Zielbild aus
[ADR-0016](0016-spaetere-mandantenflotte.md) verfolgen.

## Alternativen

- Kubernetes und Helm bereits für die erste Veröffentlichung verbindlich
machen: würde die Einstiegshürde und den Betriebsumfang ohne notwendige erste-Nutzer-Anforderung erhöhen.
- Eine eigene Orchestrierungsschicht entwickeln: würde zusätzliche
Wartungs- und Sicherheitsverantwortung schaffen.
- Nur eine manuelle Container-Installation dokumentieren: würde den
reproduzierbaren Referenzpfad schwächen; Compose bleibt deshalb die Referenzinstallation.

## Referenzen

- [Architekturübersicht](../architecture.md)
- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- [ADR-0016: Spätere getrennte Mandantenflotte](0016-spaetere-mandantenflotte.md)
- Issue [#115](https://github.com/lxndrp/lzug/issues/115)
- Issue [#119](https://github.com/lxndrp/lzug/issues/119)
