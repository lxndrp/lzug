# Delivery und Veröffentlichung

Workflows und `Taskfile.yml` sind die ausführbaren Quellen für Auswahl, Gates
und Befehle.
Diese Seite verbindet die einzelnen Stufen und beschreibt, welche Evidenz ein
erfolgreicher Lauf liefert, wie Fehler eingeordnet werden und welche
Wiederholung sicher ist.

## Pull-Request-Gates

`.github/workflows/pull-request.yml` ordnet geänderte Pfade konservativ den
Domänen Fixtures, Dokumentation, Backend, Frontend, CLI, Container, Browser und
Infrastruktur zu.
Workflow-, Toolchain-, Abhängigkeitsänderungen und `Taskfile.yml` wählen alle
Domänen; unbekannte Pfade ebenfalls.
Bekannte Skripte wählen ihren Verantwortungsbereich gemäß Werkzeuginventar.
Neue Skripte fallen ohne explizite Zuordnung in die vollständige Domänenauswahl.
Ein nicht ausgewählter Bereich wird in seinem sichtbaren Gate ausdrücklich als
`skipped` behandelt.

Produktive Webänderungen wählen Browser-E2E und Accessibility getrennt.
Source-Scan und CodeQL ergänzen die fachlichen Gates.
CodeQL analysiert nur betroffene Sprachen; globale und unbekannte Änderungen
wählen alle drei Sprachen.
Unveränderte SARIF-Baselines werden nicht auf den PR übertragen.
Source-Scan überspringt reine Dokumentationsprosa; ausführbare Quellen,
Konfiguration und unbekannte Änderungen bleiben prüfpflichtig.
Die fünf stabilen Gates akzeptieren ausschließlich erfolgreiche ausgewählte
Jobs oder ausdrücklich nicht ausgewählte, übersprungene Jobs.
Fehlende Auswahl, Abbruch und unerwartetes Überspringen blockieren.

Die visuelle Chromium-/Firefox-/WebKit-Matrix läuft im PR nur bei Templates,
Styles, Komponenten mit möglichen Inline-Templates, Brand-/Public-Assets und
Demo-Overlays sowie Änderungen des Matrix-Tests oder seiner Konfiguration.
API-, Routing- und sonstige Browseränderungen erhalten E2E und A11y in Chromium.
Ein PR baut das Produktimage und prüft seine HTTP-/Sicherheitsgrenzen sowie die
Compose-Konfiguration.
Die vollständige Compose-Laufzeit-, CLI-Container-, Upgrade-/Restore- und
Demo-Paarintegration sowie die doppelte CLI-Archive-Erzeugung gehören zur
nächtlichen Integration; fachliche Unit- und Autorisierungstests bleiben im PR.
Required Checks und aktive Security-Schwellen werden aus dem GitHub-Ruleset
gelesen und nicht aus Handbuchtext abgeleitet.

Ein Pull Request ist erst mergefähig, wenn alle für den letzten Commit
ausgewählten Checks erfolgreich, relevante Reviewbefunde geklärt und Threads
aufgelöst sind.
Die schließende Verknüpfung zum Issue, Assignees, Milestone und Project werden
daneben als GitHub-Metadaten geprüft.

## Vollständige Qualität

`.github/workflows/quality.yml` prüft `master` täglich um 03:17 UTC und nach
manuellem Dispatch vollständig ohne Pfadauswahl.
Ein Push oder Dependabot-Merge startet keine zweite Integrationskette.
Der Workflow umfasst Fixtures, Brand, alle Komponenten- und Deliverytests,
Backend, Frontend und npm-Sicherheitsgate, Dokumentation, CLI-Artefakte,
Infrastruktur, Container/Compose, Demo, SBOM, Browser-E2E, Accessibility und
die vollständige visuelle Matrix.

Für einen Release wird zuerst die aktuelle `master`-SHA ermittelt.
Fehlt dafür ein erfolgreicher nächtlicher Lauf, startet der Maintainer
`Quality` auf `master` mit dieser SHA als `expected_sha`.
Der Workflow lehnt eine inzwischen veränderte Revision ab und verwendet
überall die im GitHub-Lauf verzeichnete SHA; es gibt keinen abweichenden
Checkout über eine Revisionseingabe.
Erst nach dessen Erfolg wird `Release` auf demselben Stand gestartet.
Release, stabile Demo-Promotion und Snapshot-Promotion lesen ausschließlich
vollständige erfolgreiche Schedule-/Dispatch-Evidenz für diese `master`-SHA.
Fehlende Evidenz stoppt vor Veröffentlichung und wird außerhalb der
Lieferkette erzeugt.

`task quality` ist die lokale Entsprechung für querschnittliche Änderungen.
Fokussierte Tasks dürfen vorausgehen, wenn sie das Risiko klar eingrenzen.
Die CI bleibt finale Abnahme, insbesondere für GitHub-Rulesets, CodeQL,
Source-Scanning und Plattformkombinationen, die lokal nicht vollständig
verfügbar sind.

## Release und Artefakte

`.github/workflows/release.yml` ist der einzige Releasepfad.
Der Maintainer startet ihn für einen vorgesehenen annotierten SemVer-Tag auf
`master`; Milestone und Project-Felder sind keine Workfloweingaben.
Der Preflight bindet Tag, Changelog und den erfolgreichen vollständigen
`Quality`-Lauf an dieselbe aktuelle `master`-SHA.
Der Publish-Job wartet anschließend im geschützten Environment `release`.

Aus der geprüften Revision entstehen:

- ein OCI-Image mit SemVer-, Major-, Major.Minor- und Commit-SHA-Referenzen auf
  denselben Registry-Digest, aber ohne `latest`;
- sechs portable `lzug-admin`-Archive für Linux, macOS und Windows auf amd64
  und arm64;
- genau eine aggregierte CycloneDX-Release-SBOM als siebtes sichtbares
  GitHub-Release-Asset;
- Provenance-Attestations für OCI-Digest, CLI-Archive und SBOM sowie eine
  detaillierte Image-SBOM als Attestation.

Der GitHub Release bleibt Draft, bis alle sieben Assets hochgeladen sind, und
wird zuletzt veröffentlicht.
Ein vorhandener Tag darf nur wiederverwendet werden, wenn er annotiert und an
dieselbe vorgeprüfte SHA gebunden ist.
Veröffentlichte Tags und Releases werden nicht verschoben.

Bei einem Fehler wird der fehlgeschlagene Lauf erst nach Einordnung seiner
Phase erneut gestartet.
Ein Pull Request, Merge oder fehlgeschlagenes Demo-Deployment allein löst kein
neues Release aus.
Die sichtbaren Release-Assets, Digests und GitHub Attestations sind der
Nachweis für veröffentlichte Versionen.

## Demo-Promotion und Deployment

Ein stabiler Release ruft nach der Veröffentlichung
`.github/workflows/demo-promote.yml` auf; Release Candidates überspringen die
Promotion.
`demo-publish.yml` erzeugt oder verwendet ein unveränderliches App-/Seed-Paar
mit gemeinsamem Produkt-Tag, Commit, Runtimevertrag, Schemafingerprint und
Seed-Revision.
`demo-deploy.yml` validiert beide Manifeste und Provenance-Attestations vor der
Azure-Anmeldung und aktualisiert sie als eine Container-Apps-Revision.

Die echte Mutation läuft ausschließlich im geschützten Environment `demo` mit
GitHub OIDC.
Azure-Readiness bindet die aktive Plattformrevision an beide erwarteten Digests.
Der anschließende Smoke wartet einmal auf die öffentliche, commitgebundene
Application-Readiness und prüft dann Demo-Status, die geschützte OpenAPI-Grenze
und die zentrale Frontendroute.
Ein zusätzlicher Liveness-Aufruf und eine erneute Readiness-Abfrage entfallen.
Provenance und App-/Seed-Paarprüfung bleiben eigenständige Sicherheitsgrenzen
vor der Azure-Anmeldung, auch beim manuellen Retry.
Die anonyme OpenAPI-Anfrage muss HTTP 401 mit
`{"error": "Authentication required."}` liefern.

Vor der ersten öffentlichen Auslieferung der Athener Ortsreferenzen und bei
jeder späteren Änderung ihrer Quellen oder des Kartenproviders muss die
Freigabe den sichtbaren Delta-Stand erneut prüfen.
Dazu gehören Quellen und Abrufdaten, synthetische Kennzeichnung,
OpenStreetMap-Tile-Policy, OSMF-Datenschutzhinweis sowie das Verhalten bei
Providerfehlern.
Die organisatorisch-rechtliche Freigabe #584 bleibt ein eigenständiges Gate;
Merge, Release oder vorhandene technische Qualität ersetzen sie nicht.
Ohne diese Freigabe darf kein Demo-Deployment mit dem geänderten
Deployment-Digest aktiviert werden.

Ein manueller Snapshot benötigt einen neuen annotierten, revisionsgebundenen
Tag nach erfolgreicher vollständiger Qualität.
Ein manueller Deploy oder Rollback benötigt ein ausdrücklich freigegebenes,
vollständiges Sieben-Werte-Paar; App- oder Seed-Digest werden nie einzeln
ausgetauscht.
Bei einem Fehler bleibt der Lauf rot, sammelt nur nicht sensible Diagnose und
verweist auf den ersten fehlgeschlagenen Readiness- oder Smoke-Schritt.
Eine Wiederholung liest Quellen und Digests erneut; ein Rollback ist ein
eigener kontrollierter Deploy eines früher geprüften vollständigen Paars.

Die Demo skaliert auf null und besitzt ein deklaratives monatliches
Resource-Group-Budget von genau 1 EUR.
Das Budget warnt verzögert und ist keine Kosten- oder Verbrauchsgrenze.
Der technische Kostenvertrag liegt in `infra/demo/`; reale Aussagen benötigen
vollständige, nach Resource und Meter aufgeschlüsselte Cost-Management-Daten
für den abgeschlossenen Zeitraum.
Preisannahmen oder ein unvollständiger Abrechnungsstand gelten nicht als
Betriebsnachweis.

## Technische Referenz und öffentliche Site

`task docs` führt zuerst den projektspezifischen Strukturcheck aus, baut MkDocs
mit `--strict` und erzeugt die TypeDoc-Referenz.
Der Pull-Request- und der vollständige Quality-Workflow laden `site/` als
geschütztes Artefakt `lzug-documentation` hoch.
Das ist eine revisionsgebundene technische Referenz und Teil der
repository-zentrierten öffentlichen Dokumentation.

`task docs:publication` baut die vollständige statische Site ausschließlich
aus dem Hauptrepository:

- Produkt- und Landingpage-Quellen;
- Nutzer-, Betreiber- und Fachhandbuch unter `docs/handbook/` und `docs/portal/`;
- technische Referenzen aus Docstrings/TSDoc, OpenAPI und
  `backend/db/schema.sql`.

Der Build schreibt Repository- und Theme-Revision in `quellen.json`.
`task docs:publication:check` erzeugt das Artefakt zweimal und verlangt
Byte-Identität.
Browser- und Accessibility-Prüfung laufen getrennt.
`.github/workflows/publication.yml` baut bei relevanten Pull Requests und
`master`-Pushes nur ein Artefakt; ein Pages-Deployment erfolgt ausschließlich
nach manuellem Dispatch auf `master` und dem geschützten Environment
`github-pages`.
Master-Pushes erzeugen nur das Folgeartefakt; Browser- und A11y-Nachweise werden
im PR und vor manueller Veröffentlichung erbracht.
Der geplante Site-Lauf prüft die Byte-Reproduzierbarkeit.

## Eigenständige Fehlergrenzen und kleinste Prüfebenen

| Grenze | Realistischer Fehlerfall | Kleinste ausreichende Prüfung |
| --- | --- | --- |
| Backend, Demo-Policy und Fixtures | Falsche Autorisierung, Datenintegrität, Reset-/Isolationsregel oder Adapterdrift | Komponenten-Unit-/Repositorytests und Fixture-Compiler |
| Frontend und Brand | Ungültige Typen, Zustände, Assets oder Produktionsassembly | Lint, Vitest/Coverage, Angular-Build und Asset-Driftcheck |
| Browser / A11y / visuelle Matrix | Gestörter Nutzerablauf / fehlende Semantik / enginespezifisches Layout | Jeweils getrennte Playwright-Prüfung |
| Produktimage | Fehlende Wheel-Ressourcen, falsche Buildidentität, unsichere HTTP-Grenze | Ein Produktimage-Build und öffentlicher HTTP-Smoke |
| Compose | Fehlerhafte Port-/Volume-Konfiguration oder Datenverlust beim Restart/Stop-Start | Standard-Konfiguration plus lzug-Policy; nachts echter Lifecycle mit öffentlichem `/api/ready` und Persistenzmarker |
| Betreiber-CLI | Falsche Befehlssemantik oder fehlerhaftes Archiv | Go-Tests/Vet und GoReleaser-Konfiguration; nachts zwei Builds mit Archivvergleich |
| CLI / Produktimage | Inkompatibles Admin-Protokoll, fehlerhafter Upgrade-/Restore-Pfad | Nächtlicher CLI-Container- und unterstützter v0.6.0-Kompatibilitäts-Smoke |
| Demo-App / Seed | Fehlender Overlay-Code, falsche Assembly oder persistenter Besucherzustand nach Reset | Ein tatsächlicher App-/Seed-Build und Paar-Smoke; Snapshot-/Release-Tags als schnelle Identitäts- und Manifesttests |
| Dependency-, Image- und CLI-SBOM | Fehlende installierte Abhängigkeit, OS-Paket oder einkompiliertes Go-Modul | Je ein Scan des unterschiedlichen Eingabeartefakts samt CycloneDX-/Identitätsprüfung; Release scannt seine sechs tatsächlich gelieferten CLI-Binaries |
| Infrastruktur | Ungültiger Ressourcenvertrag oder unerwartete Planänderung | OpenTofu-Format, Validierung und Mock-Plan ohne Cloudänderung |
| Demo-Deployment | Fremde Herkunft / unpassendes Paar / falsche aktive Revision / defekter öffentlicher Ablauf | Provenance / Manifestbindung / Azure-Revision / Application-Smoke, jeweils an ihrer eigenen Grenze |
| Dokumentation / Site | Ungültige Referenz, Assembly, Navigation oder Builddrift | Strukturcheck und strikter Generator; Site-Browser und geplante Byte-Reproduktion |
| Sicherheit / Release-Evidenz | Neue Schwachstelle, Secret, unsichere Konfiguration oder Freigabe für falsche SHA | Abhängigkeitsaudit, ausgewähltes CodeQL, Source-/Image-Scan und exakte revisionsgebundene Evidenz |

Prüfungen von GitHub-, Docker- oder GoReleaser-Implementierungsdetails sind
kein lzug-Produktnachweis.
Reine Aufruf- und Schrittzähltests, Baseline-Übertragungen und Tests auf
historisch entfernte Wrapper entfallen.
Die verbleibenden Workflow-Verträge sichern eigene Regeln wie
Freigabegrenzen, unveränderliche Artefaktbindung und die Auswahlentscheidung;
Shell-/jq-Entscheidungen werden mit falschen und fehlenden Nachweisen geprüft.
Ob GitHub einen abhängigen Job startet oder Docker einen Container anlegt,
wird nicht nochmals als eigenes Testziel nachgebildet.
Der reale Compose-Persistenztest bleibt, weil er das Zusammenwirken unserer
Volume-, Benutzer- und Anwendungskonfiguration nach einem Neustart beweist.

Die Go-Dependency-SBOM muss die in `go.mod` deklarierten Module enthalten;
zusätzliche transitive Einträge müssen im aufgelösten, gelockten Graph liegen.
Die CLI-SBOM wird dagegen direkt gegen `go version -m -json` der gescannten
Binärdatei geprüft und bereits beim Erzeugen validiert.
Upstream-Testabhängigkeiten sind keine Pflichtbestandteile eines Binaries;
fehlende oder zusätzlich behauptete eingebettete Module schlagen fehl.

Release und Snapshot verwenden dieselben Docker-Stages ohne kanalabhängige
Packagingpfade.
Der lokale und nächtliche Demo-Smoke baut deshalb einmal das Paar mit der
komplexeren Snapshot-Identität.
Die stabilen Tags, Kanalableitungen und ungültigen Kombinationen bleiben durch
Identitäts- und Manifesttests abgedeckt.
`quality:image` erzeugt und validiert seine Image-SBOM einmal; `quality:sbom`
verwendet den gemeinsamen Dependency-SBOM-Task.
Die CI lädt diese Ergebnisse hoch, ohne denselben Input erneut zu scannen.

## Fehlerdiagnose und sichere Wiederholung

1. Zuerst die Workflow-Zusammenfassung, ausgecheckte Revision, ausgewählte
   Domäne und den ersten fehlgeschlagenen Schritt prüfen.
2. Den lokalen Task mit demselben ausführbaren Vertrag gezielt reproduzieren.
   Unveränderte Sandbox-, Browser-, Engine- oder Netzwerkgrenzen als Umgebung
   dokumentieren und nicht durch Produktänderungen verdecken.
3. Nach einer inhaltlichen Korrektur alle betroffenen fokussierten Prüfungen
   erneut ausführen und die CI des neuen Commits vollständig abwarten.
4. Release-, Demo- und Pages-Publikation nur in ihrem jeweiligen
   freigegebenen Workflow wiederholen.
   Ein erfolgreicher Teilstand ist kein Nachweis für eine andere Stufe.
5. Keine Secrets, Environmentwerte, private Schlüssel, vollständigen
   Ressourcenantworten oder Fachdaten in Logs, Kommentare oder Artefakte
   übernehmen.

Lokale Befehle und Testauswahl stehen unter [Entwicklung](development.md).
