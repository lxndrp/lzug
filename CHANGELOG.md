# Changelog

Alle wesentlichen Änderungen an `lzug` werden in dieser Datei dokumentiert.
Das Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de-DE/1.1.0/),
Versionen folgen [Semantic Versioning](https://semver.org/lang/de/).

## [Unreleased]

Bei einer Release-Vorbereitung verschiebt ein Maintainer die freizugebenden Einträge in genau einen Abschnitt `## [MAJOR.MINOR.PATCH] - YYYY-MM-DD`.
Der Release-Workflow übernimmt ausschließlich diesen Abschnitt als Release Notes und veröffentlicht nur aus dem nach der Environment-Freigabe erzeugten, annotierten SemVer-Tag.

## [0.3.0] - 2026-08-28

### Added

- Ein Ausfall- und Ersatzprozess für bestätigte Besetzungen erfasst
autorisierte Ausfallmeldungen, Fristen, Ersatzantworten, Audit-Ereignisse und Korrekturpfade.
Tagesansicht und Prozessübersicht führen durch die jeweils zulässigen Aufgaben; Persistenz, OpenAPI, Migration und Benachrichtigungen bleiben dabei konsistent.
- Ein kanalneutraler Benachrichtigungsvertrag unterstützt idempotente Ereignisse,
rollenbezogene Einsicht, Web Push, optionalen SMTP-Fallback, Retry- und Fehlerzustände sowie die Betreiber-CLI und einen Demo-Sink.
- Prüfungstermine können als persönliche, provider-neutrale Kalenderfeeds und
einzelne ICS-Ereignisse bereitgestellt werden.
Stabile Identitäten, Versionen, Ersetzungen und Absagen vermeiden dabei unnötige personenbezogene Daten; Feed-Lebenszyklus, API, Migration, Oberfläche und Dokumentation sind eingeschlossen.

### Changed

- Stabile Produkt-Releases können nach ihrer Veröffentlichung automatisch als
unveränderliches, provenance-geprüftes App-/Seed-Paar in die öffentliche Demo promotet werden.
Release Candidates bleiben ausgeschlossen; Readiness, OIDC, SBOM- und Public-Site-Grenzen bleiben erhalten.
- Pull-Request-Sicherheitsprüfungen und Public-Site-/Wiki-Prüfungen werden nur
für relevante Änderungen ausgeführt.
Workflowtests prüfen die fachlichen Invarianten, ohne sich an Schrittbezeichnungen oder Reihenfolgen zu binden; die vollständigen Quality- und Security-Nachweise bleiben bestehen.
- Die öffentliche Demo verwendet eine reduzierte Überwachungsgrundlast ohne
periodischen Readiness-Warm-up.
Landingpage-, Fehler- und Dokumentations- nachweise bleiben getrennt, reproduzierbar und auf die tatsächlich benötigten Prüfungen begrenzt.
- Build-, Test- und GitHub-Actions-Abhängigkeiten wurden kontrolliert
aktualisiert.
Die Betriebs- und Self-Hosting-Abgrenzung dokumentiert zudem den evidenzbasierten Verzicht auf InSpec als gemeinsamen Infrastruktur-Harness.

### Security

- Benachrichtigungen und Kalenderfeeds verwenden rollenbezogene beziehungsweise
datensparsame Verträge; der Ausfall- und Ersatzprozess prüft Autorisierung, Fristen und Auditierbarkeit.
- Die selektive Pull-Request-Analyse bewahrt vollständige Quality-CodeQL- und
unabhängige Trivy-Prüfungen für relevante Änderungen, ohne leere Auswahlpfade oder fehlerhafte Sicherheitsprüfungen als erfolgreich zu behandeln.

### Scope and compatibility

- `v0.3.0` ist ein kompatibler Funktionsrelease seit `v0.2.0` und umfasst den
zusammenhängenden Ausfall-, Benachrichtigungs- und Kalenderprozess aus #28, #29 und #30 sowie die dafür gemergten releasebegleitenden Korrekturen.
- Dieser Vorbereitungseintrag beansprucht weder den Produkt-Tag noch einen
veröffentlichten GitHub Release, neue GHCR- oder CLI-Artefakte, Attestations, eine öffentliche Demo-Promotion oder eine erneute externe Environment-Freigabe.
Diese Schritte entstehen erst nach separatem Maintainer-GO.
- Allgemeines Upgrade, Backup, Restore und Produkt-Rollback sowie Änderungen an
bestätigten Plänen und produktive Self-Hosting-Reife bleiben außerhalb dieses Releaseumfangs und sind für spätere Milestones vorgesehen.

## [0.2.0] - 2026-08-24

### Added

- Vorsitz und Stellvertretung können einen Planungsvorschlag in der
Bestätigungsstufe vollständig per Tastatur, Mobilgerät und Screenreader bearbeiten.
Tageszuordnung und Reihenfolge der Slots, Prüfungsorte sowie Prüfer und Fallbacks bleiben bis zum ausdrücklichen Speichern lokal; Validierungs-, Berechtigungs- und Revisionskonflikte werden verständlich angezeigt, ohne fremde Änderungen zu überschreiben.
- Die öffentliche Demo macht Person, Rolle und den daraus folgenden
Aufgabenpfad dauerhaft sichtbar.
Navigation, Direktaufrufe und Aktionen folgen den effektiven Fähigkeiten; Prüfpersonen bearbeiten ausschließlich ihre eigene Verfügbarkeit und Anwesenheit.
- Eine reproduzierbare statische Landingpage führt mit einem begrenzten
Scale-to-zero-Warm-up zur Demo.
Manuell freigegebene, unveränderliche Demo-Snapshots sind an die exakte `master`-Revision, den vollständigen Quality-Nachweis und ein zusammengehöriges, attestiertes App-/Seed-Paar gebunden.

### Changed

- Demo und Landingpage verwenden kanonische HTTPS-Origins sowie fail-closed
Verträge für Custom Domains, TLS, CORS, Publication und Deployment.
Browser- Tests leiten die konfigurierte Demo-Origin aus dem gebauten Artefakt ab, statt eine zweite feste URL vorauszusetzen.
- Prozess-Liveness und datenbankgebundene Readiness sind getrennt. Die
Betriebsgrundlage umfasst datensparsame strukturierte Logs, rate-limitierte same-origin Frontend-Fehlerannahme, Aufbewahrungs- und Kostenbegrenzungen sowie vorbereitete Uptime-, Fehler- und Budgetalarme; externes Monitoring bleibt standardmäßig deaktiviert und an die kanonische Demo-Domain gebunden.
- Build-, Analyse- und Laufzeitabhängigkeiten wurden kontrolliert aktualisiert,
darunter Angular, Taiga UI, SQLAlchemy, Ruff sowie die verwendeten GitHub- Actions.
Die Regeln für Dependabot-Auto-Merge und die dauerhaften Planungs- und Umsetzungskontexte sind präzisiert.

### Fixed

- Wiederholte Tabellen- und Kartenaktionen besitzen objektspezifische
Accessible Names; Löschdialoge benennen dasselbe Ziel wie die auslösende Aktion.
- Optimierte Frontend-Builds laden globale Styles unter der Backend-CSP
vollständig.
Demo-Hinweis, Desktop-Sidebar, mobile Navigation und Sticky-Header überlagern sich auch bei umbrochenem Hinweistext nicht.
- Demo-Snapshot- und Deploymentverträge prüfen die commitgenaue Quality-
Evidenz, Bootstrap-Reihenfolge, Environment-Aktivierungsgrenze und digestgebundene Runtime-Kompatibilität fail-closed.
Der Compose-Lifecycle- Smoke diagnostiziert Stop/Start und Readiness zuverlässig.
- Publication und Betrieb validieren die tatsächlich aufgelöste Demo-URL, den
geschützten OpenAPI-Pfad, Favicons unter dem Pages-Basepath und zustandsbehaftete Fehleralarme korrekt.
Automatisch erzeugte Smart-Detection-Regeln werden datensparsam deaktiviert.

### Security

- Die gesperrte `pip`-Version enthält die verfügbare Sicherheitskorrektur;
Produktionsabhängigkeiten und Lieferkettenprüfungen wurden ohne bekannte kritische Schwachstellen verifiziert.
- Anonyme Deployment-Smokes erwarten am geschützten OpenAPI-Endpunkt
ausdrücklich `401 Unauthorized`; unsichere, abweichende oder generierte Demo-Origins werden vor Publication, Monitoring oder Deployment abgewiesen.

### Scope and compatibility

- `v0.2.0` ist ein kompatibler Funktionsrelease seit `v0.1.2`. Der Planeditor
bearbeitet ausschließlich noch nicht bestätigte Planungsvorschläge; Änderungen bestätigter Pläne, Kandidaten- oder Slot-Struktur sowie Benachrichtigungs- und Kalenderfolgen sind nicht enthalten.
- Die Demo-, Publication- und Betriebsverträge sind lokal und in CI prüfbar.
Dieser Vorbereitungseintrag beansprucht weder den Produkt-Tag noch einen veröffentlichten GitHub Release, neue GHCR- oder CLI-Artefakte, Attestations oder eine erneute externe Aktivierung; diese entstehen erst nach separatem Maintainer-GO.
- Allgemeines Upgrade, Backup, Restore und Produkt-Rollback sowie produktive
Self-Hosting-Reife bleiben außerhalb dieses Releaseumfangs.

## [0.1.2] - 2026-08-15

### Fixed

- Erfolgreiche Azure-REST-Antworten ohne JSON-Body werden korrekt
statusbasiert verarbeitet, ohne die leere Ausgabe als JSON zu parsen.
- Das Demo-Seed-Image wird genau einmal gebaut, vor Belegung des
unveränderlichen Tags anhand der eingebetteten Datenbank, des Manifests, des Schemafingerprints und der Seed-Revision fail-closed geprüft und anschließend als exakt dasselbe Image veröffentlicht.

### Scope and compatibility

- `v0.1.2` bereitet ausschließlich diese kompatiblen Korrekturen seit
`v0.1.1` vor.
Der Abschnitt beansprucht weder eine bereits erfolgte Veröffentlichung noch neue Digests; Tag, Veröffentlichung und Deployment bleiben getrennten Maintainer-Freigaben vorbehalten.

## [0.1.1] - 2026-08-14

### Added

- Eine taggebundene, flüchtige Demo-Assembly aus getrenntem Anwendungs- und
Seed-Image mit synthetischen Daten, übereinstimmenden Produkt-, Commit- und Schemainformationen, eingeschränkten Demo-Sitzungen und einem Default-Deny-Schreibvertrag.
Lokale Vertrags- und Smoke-Tests prüfen Artefaktpaar, Initialisierung und Reset-Grenzen.
- Reproduzierbare OpenTofu-Infrastruktur für eine öffentliche Demo in Azure
Container Apps mit minimalen Identitäten, flüchtigem Datenvolume, Scale-to-zero und einem geplanten täglichen Neuaufbau aus dem gebundenen Seed-Artefakt.
- Ein OIDC-basierter Deploymentvertrag, der ausschließlich attestierte,
unveränderliche Digests des zusammengehörigen Demo-Artefaktpaars akzeptiert, das Deployment prüft und einen digestgebundenen Rollback vorbereitet.
- Eine beschlossene Publikationsarchitektur für Landingpage,
Entwicklerhandbuch, Code-Referenz und Wiki sowie ein reproduzierbarer lokaler Hugo-Spike.
Er erstellt keine öffentliche Hosting-Ressource.

### Changed

- Pull Requests verwenden selektive, merge-blockierende Prüfdomänen; der
vollständige `Quality`-Workflow auf `master` bleibt der kanonische Release-Nachweis.
Compose-Standardvalidierung und projektspezifische Self-Hosting-Policy werden dabei getrennt geprüft.
- Der Release-Workflow wird ausdrücklich auf dem aktuellen `master` mit dem
vorgesehenen SemVer-Tag gestartet, verwendet den vollständigen `Quality`-Lauf derselben SHA und veröffentlicht nach Environment-Freigabe ausschließlich taggebundene OCI-, CLI-, SBOM- und Attestationsartefakte.
- Issue-/Milestone-Gates, einzelne Quality-Check-Abfragen, historische
Bestandsvalidierung und `v0.1.0`-Sonderpfade wurden aus der aktiven Release-Automation entfernt.
- GoReleaser baut und verpackt die sechs reproduzierbaren Archive der
Betreiber-CLI; der Release behält genau diese Archive und eine aggregierte CycloneDX-SBOM als sichtbare Assets und attestiert die gebundenen Lieferartefakte über GitHub.
- Pull-Request-Erstellung und Wiki-Publikation verwenden die direkten,
dokumentierten GitHub- und Task-Schnittstellen ohne eigene parallele Zustands- oder Vorab-Publikationsautomation.

### Scope and compatibility

- `v0.1.1` ist ein kompatibler technischer Folgerelease für die vereinfachte
Quality-, Release- und CLI-Lieferkette sowie die vorbereiteten Demo- und Publikationsverträge.
Der offene fachliche Umfang von `v0.2.0`, insbesondere #25 und #315, ist nicht enthalten.
- Die Demo-Artefakte, Azure-Infrastruktur und Deploymentabläufe sind
implementiert und lokal beziehungsweise in CI prüfbar, aber mit diesem Release noch nicht veröffentlicht oder ausgerollt.
Es werden weder Artefakt-Digests noch eine öffentliche URL oder ein Live-Nachweis beansprucht; die Veröffentlichung und das Deployment bleiben getrennten, ausdrücklich freizugebenden Schritten vorbehalten.
- Die Publikationsarchitektur ist eine technische Entscheidung mit lokalem
Spike.
Landingpage, Handbuch, Code-Referenz und Wiki sind noch nicht über die vorgesehenen öffentlichen Plattformen bereitgestellt.
- `v0.1.1` beansprucht weder fachliche Vollständigkeit noch produktive
Self-Hosting-Reife.
Allgemeines Backup, Restore, Upgrade und Produkt-Rollback bleiben außerhalb dieses Releaseumfangs.

## [0.1.0] - 2026-08-12

### Added

- Reproduzierbare, commitgebundene Versions- und Build-Identität für Backend,
Frontend, Betreiber-CLI und OCI-Image.
- Sieben stabile Quality-Gates für Backend, Frontend, Betreiber-CLI, OCI,
Dokumentation, Security und den Gesamtstatus.
- Fail-closed Release-Infrastruktur mit annotiertem SemVer-Tag als kanonischer
Identität, Environment-Gate und kuratierten Release Notes.
- Qualifizierte Lieferkettennachweise für GHCR-Digest, getrennte
CycloneDX-Image-/Dependency-SBOMs, Provenance, Attestations und Prüfsummen, die der Release-Workflow bei einer späteren Veröffentlichung an diese Notes anhängt.
- Compose-Referenz für konkrete GHCR-Versionen und vorzugsweise unveränderliche
Digests einschließlich Non-Root-, Health- und `/data`-Persistenzvertrag.

### Scope and compatibility

- `v0.1.0` beansprucht ausschließlich die reproduzierbare Versions-, Qualitäts-
und Release-Infrastruktur.
Es ist weder ein fachlich vollständiges noch ein produktionsreifes lzug-Release.
- Es gibt keinen veröffentlichten Vorgänger und daher keine Breaking Changes
oder unterstützte Upgrade-Migration gegenüber einem früheren Release.
- Upgrade, allgemeines Backup und Restore sowie Produkt-Rollback werden für
`v0.1.0` nicht unterstützt; dieser Betriebsumfang ist für `v0.6.0` geplant.
Migrationsschutzkopien und der Wiederanlauf eines fehlgeschlagenen Release-Workflows ersetzen diese Produktpfade nicht.
- Ein realer Pilot oder veröffentlichter Release Candidate wird nicht
beansprucht.
Die integrierte Wintererprobung ist für `v1.0.0-rc.1` geplant.
- Lizenztexte, Abhängigkeitsnachweise und Sicherheitsgrenzen bleiben in ihren
jeweiligen maßgeblichen Quellen nachvollziehbar.
Sie sind keine Rechtsberatung und keine Zusage für einen produktiven Betrieb.
