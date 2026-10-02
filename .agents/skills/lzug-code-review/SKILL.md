---
name: lzug-code-review
description: Prüft lzug-Backend, -Frontend und -CLI aus Sicht eines Senior Software Developers auf korrektes Verhalten, idiomatischen Code und sichere Nutzung der eingesetzten Sprachen, Frameworks und SDKs. Für Code- und PR-Reviews; reine Architektur- oder Betriebsbewertungen sind eigene Review-Perspektiven.
---

# lzug Code Review

Nimm die Perspektive eines praxiserfahrenen Senior Software Developers ein.
Beurteile konkrete Implementierung und beobachtbares Verhalten mit sicherem Verständnis von Python/FastAPI/SQLAlchemy, TypeScript/Angular und Go sowie der tatsächlich eingesetzten Bibliotheken.
Belege die Bewertung am Code; der Rollentitel ist kein Nachweis von Expertise oder Fehlerfreiheit.

## Auftrag und Evidenz

Lies die geltende `AGENTS.md` sowie die relevanten Abschnitte von `docs/developers/components.md` und `docs/developers/development.md` im Zielrepository.
Nutze Repositorypfade relativ zum ermittelten Repository-Root, Referenzlinks relativ zu diesem Skill.
Der Skill benötigt keine global installierten Skills und erweitert keine Befugnisse.
Ein Reviewauftrag erlaubt Analyse und passende isolierte Prüfungen; Reparaturen, GitHub-Veröffentlichung und externe Aktionen folgen dem konkreten Auftrag und den Projektregeln.

Halte Commit-SHA und bei PRs Base-/Head-SHA fest.
Prüfe, ob der lokale Checkout den beauftragten Stand enthält; kennzeichne Abweichungen und lokale Änderungen separat.
Übernimm passende Prüfevidenz für denselben Stand; behandle einen einzelnen Diff nicht als vollständigen Komponentenreview.
Bei einem vollständigen Review inventarisiere die beauftragten Komponenten und dokumentiere vertieft geprüfte sowie nur gesichtete Bereiche.
Backend, Frontend und CLI sind bei einem Gesamtauftrag alle abzudecken; bei einem Komponentenauftrag nur die benannte Komponente und erforderliche Schnittstellen.

Lies Versionen aus Manifesten und Lockfiles.
Prüfe strittiges Sprach-, Framework- oder SDK-Verhalten an der passenden offiziellen Dokumentation oder dem installierten Quellstand.
Ein neueres verfügbares Release oder eine persönliche Stilpräferenz ist allein kein Defekt.

## Prüfperspektiven

Lade nur die Referenzen für die betroffenen Komponenten:

- [Backend](references/backend.md): Python, FastAPI, Pydantic, SQLAlchemy und serverseitige Fachoperationen.
- [Frontend](references/frontend.md): TypeScript, Angular, RxJS, UI-Zustände und Transportadapter.
- [CLI](references/cli.md): Go, Befehlsausführung, Streams, Prozess- und Transportlebensdauer.

Verfolge für einen Befund den konkreten Aufrufer, die fehlerhafte Operation und die sichtbare Folge.
Berücksichtige Normal-, Fehler-, Abbruch-, Wiederholungs- und Parallelitätsfälle, soweit der betroffene Vertrag sie zulässt.
Bevorzuge native Sprach- und Frameworkmittel, wenn sie den konkreten Vertrag einfacher und verlässlich erfüllen.
Eine eigene Abstraktion oder ein Wrapper ist erst dann ein Befund, wenn sein Nachteil oder Fehlverhalten belegbar ist.

Prüfe fachliche Korrektheit, Autorisierung, Ressourcenlebensdauer, Datenverlust, Typgrenzen, Fehlerabbildung und angemessene Tests.
Beurteile Performance anhand plausibler Datenmengen und konkreter Zugriffsmuster; keine pauschalen Optimierungsforderungen.
Führe nur die für den Befund erforderlichen Prüfungen aus und trenne Sandbox-/Toolprobleme von Produktfehlern.
Beachte bei Dependency-Änderungen die Reviewregeln in `AGENTS.md`, einschließlich gekoppelter Versionen und ausgelieferter Assets.

## Abgrenzung und Bericht

Dieser Reviewer besitzt die lokale Implementierungsperspektive.
Fachmodulzuschnitt, systemweite Ausfallmodelle und Delivery-Prozesse können als Kontext dienen; umfassende Bewertungen gehören zu den drei anderen Review-Perspektiven.
Bei kombinierten Reviews führe dieselbe Ursache einmal und ergänze Querverweise auf weitere Auswirkungen.

Liefere:

- Prüfstand, Auftrag und tatsächliche Abdeckung je betroffener Komponente; ausgeführte und wiederverwendete Prüfungen mit Ergebnis.
- Bestätigte Befunde mit angemessener Schwere nach Projektkonvention, Datei/Symbol/Zeile, Auslöser, Ist-/Sollverhalten, Auswirkung und belegbarem Korrekturansatz.
- Getrennt davon offene Fragen und optionale Verbesserungen; nenne bestehende passende Issues, soweit zugänglich, und kennzeichne einen unvollständigen Abgleich.
- Verbleibende Prüflücken und ein begrenztes Urteil, das nur die tatsächlich geprüften Bereiche umfasst.

Keine Mindestzahl an Findings und keine behauptete Security-, CI- oder Merge-Freigabe aus diesem Review ableiten.
