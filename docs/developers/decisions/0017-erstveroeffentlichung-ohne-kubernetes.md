# ADR-0017: Erstveröffentlichung ohne Kubernetes und Helm

## Datum

2026-08-08.

## Status

Akzeptiert.

## Kontext

Die erste Veröffentlichung soll für einzelne Ausschüsse mit überschaubarem Betriebsaufwand self-hostbar sein.
Dafür sind das OCI-Image `lzug-app`, SQLite, ein persistent eingebundenes
`/data` und ein knapper Docker-Compose-Referenzweg ausreichend.
Kubernetes und Helm würden für diesen Zielpfad einen zusätzlichen Cluster- und Paketierungsrahmen voraussetzen.

## Entscheidung

Kubernetes und Helm sind keine Voraussetzung, kein Pflichtbestandteil und kein Installationspfad der ersten Veröffentlichung.
Die Referenz bleibt ein einzelnes OCI-Image mit dem in
[ADR-0014](0014-oci-einzelcontainer-und-persistentes-data.md) beschriebenen
Datenvertrag.
Docker Engine auf Linux ist die qualifizierte Self-Hosting-Referenz.
Compose bleibt ein optionaler, knapper Docker-Referenzweg für den einen
`lzug-app`-Service und keine plattformneutrale Produktbeschreibung.
Weitere konkrete Runtimes gehören nicht zum unterstützten oder geprüften Umfang.
Die Prozess-, Transport- und Lifecyclegrenzen beschreibt
[ADR-0033](0033-aio-betrieb-admintransport-und-lifecycle.md).

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
  reproduzierbaren Referenzpfad schwächen; Compose bleibt deshalb der optionale
  Docker-Referenzweg.

## Referenzen

- [Architekturübersicht](../architecture.md)
- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- [ADR-0016: Spätere getrennte Mandantenflotte](0016-spaetere-mandantenflotte.md)
- [ADR-0033: AIO-Betrieb, Admintransport und Lifecycle gemeinsam begrenzen](0033-aio-betrieb-admintransport-und-lifecycle.md)
- Issue [#115](https://github.com/lxndrp/lzug/issues/115)
- Issue [#119](https://github.com/lxndrp/lzug/issues/119)
