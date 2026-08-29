# ADR-0022: Tag-gebundene Demo-Assembly und inhaltsadressierter Seed

## Status

Akzeptiert am 14.08.2026.
Konkretisiert [ADR-0015](0015-fluechtige-azure-demo.md) und grenzt die Demo vom persistenten Produktimage aus [ADR-0014](0014-oci-einzelcontainer-und-persistentes-data.md) ab.

## Kontext

Die öffentliche Demo soll denselben fachlichen Produktstand wie ein veröffentlichtes lzug-Produkt zeigen, ohne Eingaben oder Sitzungen dauerhaft zu speichern.
Ihr Seed muss auch für image-basierte E2E-, Preview- und Devcontainer-Umgebungen wiederverwendbar sein.
Gleichzeitig dürfen Demo-Login, Demo-Hinweise und eingeschränkte Schreibrechte nicht versehentlich Teil der Self-Hosting-Assembly werden.

Ein periodischer Reset muss unabhängig von Zugriffsaktivität funktionieren.
Scale-to-zero genügt dafür nicht.
Ein bloßer Container- oder Revisionsneustart ist ebenfalls kein ausreichender Löschbeweis, weil ein Azure-Container-Apps-`EmptyDir` bis zum Ende der Replica lebt.

## Entscheidung

Produkt- und Demo-Anwendung entstehen als getrennte Assemblies aus demselben unveränderlichen Produkt-Tag und Commit.
Digest-Gleichheit ist nicht erforderlich.
Das Produktimage behält seine persistente Self-Hosting-Komposition; das Demo-App-Image enthält exklusiv Demo-Provider, Rollenwahl und Hinweise.

Ein zweites OCI-Image initialisiert den synthetischen Seed.
Dessen Manifest bindet Produkt-Tag und -Commit, den Fingerprint aus Schema und geordneten Migrationen, Fixture-, Generator-, Seed-SQL- und Init-Logik-Digests sowie den Digest des vollständig migrierten SQLite-Snapshots.
Die daraus berechnete Seed-Revision ist inhaltsadressiert; mehrere Revisionen dürfen denselben Produktstand adressieren.

Demo-App und Seed-Init teilen ein replica-scoped `EmptyDir` unter `/data`.
Die Azure Container App läuft als Single Revision mit `minReplicas = 0` und `maxReplicas = 1`.
Eine Consumption Logic App mit eng berechtigter Managed Identity stoppt und startet die gesamte Container App täglich um 03:00 Uhr `Europe/Berlin`.
Dadurch enden alle Replicas und ihre flüchtigen Volumes.
E2E-, Preview- und Devcontainer-Umgebungen resetten stattdessen durch Neuerzeugung.

Ein neutraler Runtime-Policy-Erweiterungspunkt bleibt im gemeinsamen Backend.
Die Produktpolicy verändert das bisherige Verhalten nicht.
Nur das Demo-Image enthält die Default-Deny-Policy und die öffentlichen Demo-Routen.
Sie erzeugt 60 Minuten gültige normale Sitzungen für `Testperson Alpha` als Vorsitz oder `Testperson Gamma` als Prüfperson.
Fachliche Schreibfunktionen sind serverseitig allowlist-basiert; Lösch-, Konto-, Betreiber- und Stammdatenänderungen bleiben gesperrt.
Neue Mutationen sind standardmäßig verboten.
Dokumentuploads werden erst mit einer entsprechenden Fachlichkeit entschieden; ausgehende Benachrichtigungszugänge existieren in der Demo nicht.

Beide Images werden nur per Digest deployt und erhalten jeweils SBOM und Provenance.
Ein Rückfall verwendet stets ein zuvor gemeinsam geprüftes App-/Seed-Digest-Paar.
Bewegliche Demo- oder Latest-Tags sind kein Deploymentvertrag.

## Konsequenzen

- Die konkrete Demo-Assembly und ihr Seed lassen sich lokal, in CI und in
Azure mit denselben OCI-Grenzen prüfen.
- Das Produktimage enthält weder Demo-Endpunkte noch Demo-Provider oder
Seed-Inhalte; gemeinsame Erweiterungspunkte bleiben neutral.
- Der Initialzustand ist ohne Download und ohne Migration beim App-Start
verfügbar.
Inkompatible Bindungen brechen fail-closed ab.
- Der öffentliche Reset hat ein kurzes akzeptiertes Wartungsfenster und
beendet sämtliche laufenden Sitzungen.
- Zwei GHCR-Pakete und zwei Attestationsketten müssen gemeinsam kuratiert
werden.
Ein separates Controller-Image ist nicht erforderlich.
- #125 bleibt als abgeschlossene generische ACA-Grundlage unverändert. Ein
enges Infrastruktur-Folgeissue (#358) ergänzt Init Container, `EmptyDir`, Logic App, Managed Identity und RBAC vor #126.
- Das erste vorgesehene Produkt-Tag ist `v0.1.1`; Veröffentlichung und
Deployment benötigen weiterhin ihre eigenen Freigaben.

## Alternativen

- **Demo-Funktionen im Produktimage per Laufzeitschalter:** verworfen, weil
Demo-Login, Seed und Fehlkonfigurationen Teil der produktiven Angriffsfläche würden.
- **Ein abgeleitetes Demo-Image mit eingebettetem Seed:** verworfen, weil der
generische Init-Vertrag für E2E, Previews und Devcontainer verloren ginge und App und Seed nicht unabhängig inhaltsadressiert wären.
- **Controller-Image für den Reset:** verworfen, weil Logic App, Managed
Identity und ACA Stop/Start denselben Plattformablauf ohne weiteres kuratiertes Artefakt ermöglichen.
- **Angular Static Web Apps, Python App Service oder Functions und Managed
Database:** für #124 verworfen.
Diese Variante verteilt Build, Rollback und Nachweise auf mehrere Plattformgrenzen, erfordert eine eigenständige Datenbankmigration und kann wegen Provider-Backups keine physische Löschung aller Eingaben zum Resetzeitpunkt zusagen.
Für ein späteres dauerhaftes Hosting- oder SaaS-Ziel kann sie in einem eigenen Architekturvorhaben erneut bewertet werden.
- **Angular statisch und Backend in ACA:** verworfen, weil zusätzliche Origin-,
Cookie- und CORS-Grenzen für die eigentliche Demo wenig Nutzen bringen.
Die statische Landingpage aus #127 bleibt davon unabhängig.

## Referenzen

- [Öffentliche Demo](../demo-deployment.md)
- [Azure Container Apps: Storage Mounts](https://learn.microsoft.com/azure/container-apps/storage-mounts)
- [Issue #124](https://github.com/lxndrp/lzug/issues/124)
- [Issues #125](https://github.com/lxndrp/lzug/issues/125) und
  [#126](https://github.com/lxndrp/lzug/issues/126)
- [Infrastruktur-Folgeissue #358](https://github.com/lxndrp/lzug/issues/358)
