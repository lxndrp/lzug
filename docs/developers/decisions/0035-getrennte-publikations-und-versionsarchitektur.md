# ADR-0035: Getrennte Publikations- und Versionsarchitektur

## Datum

2026-09-08.

## Status

Akzeptiert am 2026-09-08.
Supersedes: ADR-0032.

## Kontext

ADR-0032 bündelt Produktinformation, redaktionelle Handbücher und technische Referenzen
in einer aus dem Hauptrepository erzeugten GitHub-Pages-Site.
Der Betrieb dieser vollständigen Dokumentationssite schafft für die redaktionellen Handbücher
jedoch keinen ausreichenden Vorteil gegenüber dem GitHub Wiki.
Zugleich sind kanonische Quelle, Zielgruppe und Versionsbezug zwischen Produktseite,
Handbüchern und technischen Referenzen schwer erkennbar.

lzug benötigt deshalb getrennte Oberflächen für Produktinformation, redaktionelle Handbücher
und revisionsgebundene technische Dokumentation.
Die Trennung darf keine parallel gepflegten Vollfassungen erzeugen,
und Theme sowie Generator dürfen nicht Teil der Quellenentscheidung werden.

## Entscheidung

### Kanonische Quellen und Zielgruppen

Jeder Inhalt besitzt genau eine kanonische Quelle.
Andere Oberflächen dürfen einen kurzen zielgruppengerechten Einstieg anbieten und auf diese Quelle verweisen,
aber keine gekürzte, ausführlichere oder als Arbeitskopie bezeichnete Vollfassung pflegen.

Die Verantwortungen sind wie folgt getrennt:

| Oberfläche | Zielgruppe und kanonische Verantwortung |
| --- | --- |
| GitHub Pages | Öffentliche Produkt- und Einstiegsseite sowie Host für automatisch erzeugte technische Referenzen |
| GitHub Wiki | Kanonische redaktionelle Oberfläche für Fachlichkeit, Nutzerhandbuch und Betreiberhandbuch |
| Hauptrepository | Entwicklerdokumentation, Mitwirkung, Architektur, ADRs, technische Verträge und eng an Code, CI, Release oder Infrastruktur gebundene Betriebsinhalte |

Produkt-, Support- und Security-Wege bleiben semantisch getrennt.
Ein Wechsel zwischen Pages, Wiki, Hauptrepository und einer externen Referenz wird für Nutzende erkennbar beschriftet.

### GitHub Pages und technische Referenzen

GitHub Pages führt öffentlich zu Produktinformation, Demo, Dokumentation, Quellcode, Support und Sicherheit.
Pages ist keine kanonische Oberfläche für redaktionelle Fach-, Nutzer-, Betreiber- oder Entwicklerhandbücher.

Die mindestens dauerhaft verantworteten Routen sind:

```text
/                         Produkt- und Demo-Einstieg
/referenz/                Einstieg in technische Referenzen
/referenz/api/            OpenAPI/Redoc
/referenz/backend/        Python-Referenz
/referenz/frontend/       TypeDoc
/referenz/datenbank/      Schema-/ER-Referenz
```

Die Referenzen werden aus den API-, Quelltext- und Schemaquellen des Hauptrepositories erzeugt.
Sie weisen die zugehörige Produktversion oder vollständige Quellrevision aus
und werden zusammen mit der Produktseite als konsistentes revisionsgebundenes Artefakt veröffentlicht.
Ein unvollständiger Teilstand darf nicht als vollständiger aktueller Stand erscheinen.

Generierte Referenzen veröffentlichen keine Secrets, internen Adressen
oder nicht ausdrücklich öffentlichen Diagnoseinformationen.
Eine interaktive API-Darstellung darf Schreiboperationen gegen eine öffentliche Demo
oder produktive Instanz nur nach einem eigenen ausdrücklich freigegebenen Sicherheitsvertrag ermöglichen.

Navigation und Corporate Design dürfen Produktseite und Referenzen verbinden.
Hugo, MkDocs, Redoc, mkdocstrings, TypeDoc, ein Theme und ihre möglichen Nachfolger
sind austauschbare Darstellungsschichten.
Ein Generator- oder Theme-Wechsel verändert weder die kanonische Quelle noch die Verantwortung der festgelegten Routen.

### GitHub Wiki

Das öffentliche GitHub Wiki ist ein fortlaufend gepflegtes redaktionelles Handbuch
für den aktuellen stabilen Produktstand.
Es enthält Fachlichkeit, Nutzerhandbuch und Betreiberhandbuch vollständig
und wird nicht in getrennten Bäumen pro Release geführt.
Es ist öffentlich lesbar, aber nur durch berechtigte Repository-Mitwirkende bearbeitbar.

Wiki-Seiten tragen global eindeutige, flache Namen.
Interne Links verwenden keine Dateiendung und öffnen gerenderte Wiki-Seiten statt Rohdateien.
Diese Regeln sind Autorenkonventionen und kein eigener maschineller Wiki-Vertrag.
`Home` ist der verbindliche Einstieg;
eine Seite `Versionshinweise` erklärt den Versionsbezug.
`_Sidebar.md` bietet eine kuratierte Navigation und ist kein vollständiges Seitenregister.

`Home` nennt klar, dass das Wiki grundsätzlich den aktuellen stabilen Stand beschreibt.
`Versionshinweise` beschreibt diesen Versionsbezug verständlich,
gegebenenfalls noch unterstützte ältere Stände,
verweist auf Changelog und Releases
und erklärt die verwendeten Versionshinweise.
Eine mit Changelog oder Releases maschinell synchronisierte Versionsnummer ist nicht erforderlich.

Redaktionelle Korrekturen, Erläuterungen und Ergänzungen ohne abweichendes Produktverhalten
benötigen keine Versionsmarkierung.
Unterscheidet sich beschriebenes Verhalten relevant nach Version,
steht die Abweichung unmittelbar an der betroffenen Stelle.
Der Standard für einen einzelnen Einführungspunkt ist eine kurze Textzeile:

```markdown
**Seit lzug 0.7.2:** …
```

GitHub-Markdown-Alerts werden sparsam nur für besonders wichtige,
sicherheitsrelevante oder brechende Unterschiede eingesetzt.
Tabellen werden nur verwendet,
wenn mehrere gleichzeitig relevante Versionen tatsächlich unterschiedliches Verhalten besitzen.

Nicht verwendet werden Versions-Badges, eigenes CSS,
`<kbd>` als optische Ersatzformatierung,
ausschließlich durch Emoji vermittelte Bedeutung oder Fußnoten.
Die gerenderte GitHub-Darstellung der verwendeten Textzeilen, Alerts und Tabellen
wird beim öffentlichen Cutover am tatsächlichen GitHub Wiki geprüft.

Wiki-Tags oder festgehaltene Wiki-Commit-SHAs dürfen einen forensischen
oder betrieblichen Schnappschuss bezeichnen.
Sie sind weder nutzerseitige Versionsnavigation noch Voraussetzung jedes Produkt-Releases.

### Hauptrepository

Das Hauptrepository bleibt kanonisch für:

- Entwicklerdokumentation und Mitwirkung;
- technische Architektur und ADRs;
- API-, Schema-, Migrations- und Quelltextverträge;
- technische Betriebs- und Runbook-Inhalte mit enger Bindung an Code, CI, Release oder Infrastruktur;
- Generatoren, Qualitätsprüfungen und Publikationskonfiguration.

Produkt-Releases und technische Referenzen bleiben streng an die jeweilige Produktrevision gebunden.
Das redaktionelle Wiki darf dagegen unabhängig fortgeschrieben werden,
solange sein Versionsvertrag den beschriebenen stabilen Produktstand eindeutig erkennen lässt.

## Konsequenzen

- Fachliche, Nutzer- und Betreiberinhalte können redaktionell gepflegt werden,
  ohne einen vollständigen Pages-Build oder ein Produkt-Release auszulösen.
- Technische Verträge und Referenzen bleiben mit dem Code prüfbar und revisionsgebunden.
- Die Produktseite bleibt ein stabiler öffentlicher Einstieg,
  ohne als zweite Handbuchoberfläche zu dienen.
- Querverweise ersetzen keine Inhalte und halten die Grenzen zwischen Produkt,
  Support, Security, Wiki und technischen Quellen sichtbar.
- Änderungen am Theme oder an einem Generator bleiben innerhalb der Darstellungsschicht
  und benötigen keine neue Entscheidung über Quellen oder URL-Verantwortung.
- Redaktionelle Aktualität, versionsabhängiges Verhalten und releasegebundene Referenzen
  besitzen unterschiedliche, ausdrücklich erkennbare Versionssignale.

## Risiken und Gegenmaßnahmen

- Ein organisch gepflegtes Wiki kann dem stabilen Produktstand vorauslaufen.
  `Home`, `Versionshinweise` und lokale Hinweise an tatsächlich abweichenden Stellen begrenzen dieses Risiko.
- Getrennte Oberflächen können Links und Navigation driften lassen.
  Kontrollierte Einstiege, kuratierte Navigation, generische Linkprüfung
  und ein menschlicher Review beim öffentlichen Cutover sichern die Übergänge.
- Ein ungeprüfter älterer Wiki-Bestand kann veraltete oder widersprüchliche Aussagen enthalten.
  Er wird vor der Umschaltung vollständig gegen den aktuellen Produkt-, Rollen-, Betriebs-
  und Architekturstand geprüft und nicht als kanonisch vorausgesetzt.
- Generierte Referenzen können unbeabsichtigt interne oder schreibende Schnittstellen offenlegen.
  Die Publikationsprüfung kontrolliert sensible Inhalte und die API-Interaktionsgrenze vor jedem Deployment.
- Eine parallele Migration kann vorübergehend zwei erreichbare Fassungen erzeugen.
  Die Umschaltung hält deshalb eine explizite Abnahmegrenze ein und entfernt Duplikate unmittelbar danach.

## Migrationsrichtung und Rückfallgrenze

Die eigentliche Inhaltsmigration, die Reaktivierung des Wikis
und die Reduktion des Pages-Builds erfolgen in getrennten Umsetzungsschritten.
Ein einmaliges, reviewbares Issue-/Pull-Request-Inventar ordnet die heutigen Inhalte
genau einer Zieloberfläche zu und wird nicht als generiertes Datenformat fortgeführt.

Der Wiki-Kandidat besteht aus zielfertigen Markdown-Dateien,
die aus einer festen Repository-Revision unverändert in einen flachen Baum kopiert werden.
Lychee prüft einmalig vorhandene Ziele und Fragmente.
Ein lokaler Gollum-Nachbau, ein eigener Markdown- oder Sidebar-Parser,
ein eigener HTTP-Client und dauerhaftes Post-Publish-Monitoring sind nicht Teil des Vertrags.
GitHub selbst verantwortet Dateinamen und Rendering;
der öffentliche Cutover mit anschließendem menschlichem Review ist die Abnahmegrenze.
Ein Schreib-Token, eine GitHub App oder ein automatischer Push aus dem Hauptrepository
sind keine Voraussetzung des Dauerbetriebs.

ADR-0012 bleibt als abgelöste historische Entscheidung erhalten.
Seine Forderung nach einer vollständig synchronisierten Sidebar wird nicht erneut übernommen.

Vor der Umschaltung bleiben die bestehenden kanonischen Quellen und das letzte konsistente Pages-Artefakt erhalten.
Erst nach erfolgreicher öffentlicher Wiki-Prüfung werden migrierte Vollfassungen
aus Hauptrepository, Pages-Build und Navigation entfernt.
README, CONTRIBUTING, Anwendungseinstiege, Dokumentationsindizes und Publikationsdokumentation
verweisen danach jeweils auf die hier festgelegte kanonische Oberfläche.

Scheitert die Umschaltung vor dieser Abnahme,
bleibt der bisherige konsistente Publikationsstand maßgeblich.
Scheitert sie danach,
können Wiki-Zugriff und Pages-Auslieferung auf den letzten gemeinsam geprüften Stand zurückgeführt werden.
Konkrete Repository- und Wiki-SHAs, GitHub-Artifact-Metadaten und Git-Historie
belegen und bewahren die früheren Stände;
zusätzliche dauerhafte Arbeits-, Render- oder Archivkopien entstehen nicht.

## Alternativen

- **Vollständiges Pages-Portal aus dem Hauptrepository:** bindet redaktionelle Handbuchpflege unnötig an den Produkt- und Referenzbuild
  und macht Zielgruppen sowie Versionsmodelle schwer erkennbar.
- **Handbuchprojektion aus dem Wiki nach Pages:** schafft erneut zwei öffentliche Handbuchoberflächen
  und eine zusätzliche Synchronisations- und Revisionsgrenze.
- **Pro Release eingefrorene Wiki-Bäume:** erhöhen Pflege- und Navigationsaufwand
  und passen nicht zu einem organisch gepflegten Handbuch des stabilen Stands.
- **Eigene Dokumentationsplattform:** schafft eine weitere Betriebs-, Berechtigungs-
  und Migrationsoberfläche ohne notwendigen Produktnutzen.

## Referenzen

- [ADR-0007: MkDocs und Code-Referenzen](0007-dokumentation-und-code-referenz.md)
- [ADR-0011: GitHub Wiki als redaktionelle Handbuchoberfläche](0011-github-wiki-handbuch.md)
- [ADR-0012: Redaktionelle Single Source of Truth im GitHub Wiki](0012-wiki-single-source-of-truth.md)
- [ADR-0023: Öffentliche Web- und Dokumentationspublikation](0023-oeffentliche-web-und-dokumentationspublikation.md)
- [ADR-0032: Repository-zentrierte öffentliche Dokumentation](0032-repository-zentrierte-oeffentliche-dokumentation.md)
- [Delivery und Veröffentlichung](../delivery.md)
