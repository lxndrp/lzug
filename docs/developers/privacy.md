# Datenschutzabgrenzung für die Release-Infrastruktur

## Beanspruchter Umfang von `v0.1.0`

`v0.1.0` beansprucht ausschließlich reproduzierbare Versions-, Qualitäts- und
Release-Infrastruktur. Es ist kein produktionsreifer Anwendungsrelease und
keine Zusage, reale Ausschuss-, Prüflings- oder Authentifizierungsdaten
datenschutzkonform zu betreiben. Ein realer Pilot beginnt nicht mit dieser
Version; die Wintererprobung ist für `v1.0.0-rc.1` geplant.

Die Release-Infrastruktur verarbeitet Repository- und Lieferkettenmetadaten:
Commit-SHA, SemVer-Tag, Paketnamen und -versionen, Lizenzmetadaten,
Prüfergebnisse, OCI-Metadaten, SBOM, Prüfsummen und Attestations. Die
Lizenzinventur liest Lockfiles und installierte Distribution-Metadaten. Sie
liest weder Umgebungsvariablen noch Laufzeitdatenbank, Dokumentenspeicher,
Authentifizierungs-Secrets oder Fachdaten.

Die CI- und Runtime-Vertragstests verwenden ausschließlich die dokumentierten
[synthetischen Testdaten](synthetic-fixtures.md). Sie übertragen keine reale
Instanzdatenbank und keinen Inhalt aus `/data` an GitHub, GHCR oder andere
Release-Dienste. Diese Abgrenzung bezieht sich auf die versionierten Workflows
und Skripte; die Datenverarbeitung der verwendeten Plattformdienste richtet
sich zusätzlich nach deren eigenen Bedingungen.

## Nicht durch `v0.1.0` abgedeckt

Die Anwendung kann personenbezogene Daten wie Namen, Kontaktdaten,
Prüfungsnummern, Ausschusszuordnungen, Verfügbarkeiten, hochgeladene Dokumente
und Authentifizierungsdaten verarbeiten. Für einen realen Betrieb muss die
verantwortliche Stelle insbesondere Rechtsgrundlage, Rollen, Informations- und
Auskunftspflichten, Lösch- und Aufbewahrungsfristen, Datensicherung,
Wiederherstellung, Auftragsverarbeitung und technische Schutzmaßnahmen für
ihren konkreten Einsatz prüfen und dokumentieren.

Benachrichtigungsinhalte und Empfängerbezüge folgen der Aufbewahrung ihres
zugrunde liegenden Planungs- oder Prüfungsvorgangs. Externe Push-Vorschauen
enthalten keine Fachdaten; technische Zustellmetadaten werden getrennt vom
Inhalt gespeichert. Ein optional konfiguriertes SMTP-Relay und ein Web-Push-
Dienst sind zusätzliche Empfänger technischer Zustellungen und müssen von der
verantwortlichen Stelle in ihre konkrete Datenschutzprüfung einbezogen werden.

Diese betriebliche Datenschutzabnahme, produktive Backup-/Restore-Pfade und
ein unterstütztes Upgrade gehören nicht zum Anspruch von `v0.1.0`. Die
Self-Hosting-Betriebsfähigkeit ist für `v0.6.0`, der reale Pilot für
`v1.0.0-rc.1` geplant. Die aktuelle
[Security-Baseline](architecture/security-baseline.md) und die
[OCI-Runtime-Grenze](architecture/oci-runtime.md) liefern technische
Teilnachweise, ersetzen aber keine Datenschutz-Folgenabschätzung oder
Rechtsberatung.

Damit besteht für den bewusst technischen `v0.1.0`-Releaseumfang kein offener
Datenschutz-Nachweis zur Verarbeitung realer Betriebsdaten: Solche Verarbeitung
wird ausdrücklich nicht beansprucht. Diese Abgrenzung darf nicht als
allgemeine Datenschutzkonformität von lzug oder einer konkreten Instanz
dargestellt werden.
