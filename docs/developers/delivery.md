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
Workflow-, Toolchain-, Abhängigkeits- und Skriptänderungen wählen alle Domänen;
unbekannte Pfade ebenfalls.
Ein nicht ausgewählter Bereich wird in seinem sichtbaren Gate ausdrücklich als
`skipped` behandelt.

Produktive Webänderungen wählen Browser-E2E und Accessibility getrennt.
Source-Scan und CodeQL ergänzen die fachlichen Gates.
Eine unveränderte CodeQL-Sprache darf nur einen validierten vollständigen
Nachweis der exakten Pull-Request-Basis wiederverwenden; fehlende oder
unvollständige Basisevidenz schlägt fehl.
Required Checks und aktive Security-Schwellen werden aus dem GitHub-Ruleset
gelesen und nicht aus Handbuchtext abgeleitet.

Ein Pull Request ist erst mergefähig, wenn alle für den letzten Commit
ausgewählten Checks erfolgreich, relevante Reviewbefunde geklärt und Threads
aufgelöst sind.
Die schließende Verknüpfung zum Issue, Assignees, Milestone und Project werden
daneben als GitHub-Metadaten geprüft.

## Vollständige Qualität

`.github/workflows/quality.yml` prüft jeden Push auf `master`, manuelle Läufe,
den Wochenplan und explizit aufgerufene Revisionen vollständig ohne
Pfadauswahl.
Der Workflow umfasst Fixtures, Backend, Frontend und npm-Sicherheitsgate,
Dokumentation, CLI, Infrastruktur, Container/Compose, Demo, SBOM, Browser-E2E,
Accessibility und die abschließenden Gates.
Ein erfolgreicher Lauf für eine konkrete `master`-SHA ist der
Qualitätsnachweis, den Release- und Demo-Promotion verwenden.

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
Azure-Readiness, Application-Readiness und der abschließende Smoke prüfen
Liveness, Readiness, Demo-Status, die geschützte OpenAPI-Grenze und die zentrale
Frontendroute.
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
Das ist eine revisionsgebundene technische Referenz und keine öffentliche
Kopie des Wiki-Handbuchs.

`task docs:publication` baut die vollständige statische Site aus drei
getrennten Quellen:

- Produkt- und Landingpage-Quellen im Hauptrepository;
- den konkret ausgecheckten kanonischen Wiki-Commit;
- technische Referenzen aus Docstrings/TSDoc, OpenAPI und `db/schema.sql`.

Der Build schreibt Repository-, Wiki- und Theme-Revision in `quellen.json`.
`task docs:publication:check` erzeugt das Artefakt zweimal und verlangt
Byte-Identität.
Browser- und Accessibility-Prüfung laufen getrennt.
`.github/workflows/publication.yml` baut bei relevanten Pull Requests und
`master`-Pushes nur ein Artefakt; ein Pages-Deployment erfolgt ausschließlich
nach manuellem Dispatch auf `master` und dem geschützten Environment
`github-pages`.

## Wiki-Publikation

Das GitHub Wiki ist ein separates Git-Repository und die einzige Quelle für
Fach-, Nutzungs- und Betreiberanleitungen.
`_Sidebar.md` ist seine vollständige Liste öffentlicher Inhaltsseiten.
Vor einer Veröffentlichung prüft `WIKI_ROOT=/path/to/lzug.wiki task wiki:check`
Sidebar-Struktur und Links des konkret ausgecheckten Stands.

Ein Maintainer prüft den Wiki-Diff und veröffentlicht exakt den freigegebenen
Commit ohne automatischen oder erzwungenen Push aus dem Hauptrepository.
Der wöchentliche beziehungsweise manuell gestartete Workflow
`wiki-post-publish.yml` prüft danach nur die erwarteten öffentlichen Routen
ohne Weiterleitungen.
Technische Verträge bleiben im Hauptrepository; Wiki-Seiten verlinken sie und
pflegen keine zweite Fassung.

## Fehlerdiagnose und sichere Wiederholung

1. Zuerst die Workflow-Zusammenfassung, ausgecheckte Revision, ausgewählte
   Domäne und den ersten fehlgeschlagenen Schritt prüfen.
2. Den lokalen Task mit demselben ausführbaren Vertrag gezielt reproduzieren.
   Unveränderte Sandbox-, Browser-, Engine- oder Netzwerkgrenzen als Umgebung
   dokumentieren und nicht durch Produktänderungen verdecken.
3. Nach einer inhaltlichen Korrektur alle betroffenen fokussierten Prüfungen
   erneut ausführen und die CI des neuen Commits vollständig abwarten.
4. Release-, Demo-, Pages- und Wiki-Publikation nur in ihrem jeweiligen
   freigegebenen Workflow beziehungsweise Repository wiederholen.
   Ein erfolgreicher Teilstand ist kein Nachweis für eine andere Stufe.
5. Keine Secrets, Environmentwerte, private Schlüssel, vollständigen
   Ressourcenantworten oder Fachdaten in Logs, Kommentare oder Artefakte
   übernehmen.

Lokale Befehle und Testauswahl stehen unter [Entwicklung](development.md).
