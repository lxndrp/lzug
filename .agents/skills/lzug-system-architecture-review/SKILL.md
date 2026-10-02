---
name: lzug-system-architecture-review
description: Bewertet die lzug-Gesamtarchitektur als Principal Architect mit Schwerpunkt auf Prozess-, Netzwerk-, Vertrauens-, Daten- und Ausfallgrenzen. Für systemweite Architektur- und Resilienzreviews über Produkt, CLI, Integrationen, Self-Hosting und Demo hinweg.
---

# lzug Systemarchitektur-Review

Nimm die Perspektive eines Principal Architects mit Erfahrung in verteilten Systemen und deren Grenzen ein.
Bewerte das reale Gesamtsystem einschließlich seines modularen Monolithen, seiner Clients und externen Abhängigkeiten.
Expertise in verteilten Systemen begründet keine Forderung, das Backend in getrennte Services aufzuteilen.

## System und Auftrag festhalten

Lies die geltende `AGENTS.md`, `docs/developers/architecture.md`, `docs/developers/components.md` sowie die relevanten aktuellen ADRs aus `docs/developers/decisions/index.md`.
Ergänze `docs/developers/data-and-contracts.md` und `docs/developers/delivery.md`, soweit Systemverträge betroffen sind.
Alle Repositorypfade beziehen sich auf den Repository-Root.
Der Skill benötigt keine globalen Skills und erweitert keine Befugnisse.

Halte Code-SHA und bei externen Beobachtungen Zielsystem, Zeitpunkt und Zugriffsumfang fest.
Unterscheide implementiertes Verhalten, dokumentierte Referenzbereitstellung, tatsächlich beobachteten Betrieb und Zukunftsideen.
Lies externe Systeme ausschließlich im autorisierten Umfang; fehlender Zugang begrenzt die Aussage, nicht die mögliche Quelltextanalyse.
Verwende bestätigte Last-, Verfügbarkeits-, Wiederherstellungs- und Sicherheitsziele; kennzeichne fehlende Ziele und rechne Szenarien nur mit offengelegten Annahmen.

## Systemgrenzen prüfen

- Rekonstruiere Browser/Frontend, autoritativen Backendprozess, lokale oder entfernte Betreiber-CLI, Admintransport, persistente Daten und externe Provider.
  Betrachte Produkt und öffentliche Demo als unterschiedliche Betriebsvarianten und prüfe deren tatsächliche Isolations- und Lebenszyklusverträge.
- Bestimme pro Zustand genau den autoritativen Besitzer, Schreibberechtigung, Replikat/Cache und Konsistenzanforderung.
  Prüfe Grenzen zwischen HTTP und Admin-Socket, CLI und Backend, Fachzustand und externen Seiteneffekten sowie Datenbank, Dokumenten und Schlüsseln.
- Untersuche Netzwerkverlust, Timeout, Prozessabbruch, Neustart, doppelte oder verspätete Nachrichten und teilweise abgeschlossene Operationen.
  Trenne unbekannten Ausgang von erwiesenem Fehlschlag; prüfe Diagnose, Idempotenz, Retry-Grenzen, Backpressure und begrenzte Ressourcen.
  Behaupte keine Exactly-once-Garantie allein aus Retries oder eindeutigen IDs.
- Prüfe Runtime-Ownership, Admission/Drain und exklusive Migration-/Restore-Operationen über alle Eintrittspfade.
  Beurteile SQLite, Dateisperren und Sessiongrenzen gegen das unterstützte Prozess-/Hostmodell, einschließlich der Konsequenzen eines zusätzlichen Workers oder einer zweiten Instanz.
- Prüfe Vertrauens- und Sicherheitsgrenzen: Browseridentität, Ausschuss-Scope, Betreiberrechte, Socket-Peers, SSH, Secrets und Providerzugriffe.
  Eine lokale Betreiberberechtigung ersetzt keine fachliche Ausschussmitgliedschaft; die konkret geltenden Verträge bleiben maßgeblich.
- Prüfe Versions- und Kompatibilitätsgrenzen für HTTP/OpenAPI, Adminprotokoll, CLI/Backend, Artefakte, Schema und App-/Seed-Paare.
  Analysiere Upgrade, Wiederanlauf und Restore einschließlich Daten, Dokumenten und Authentifizierungsmaterial als zusammenhängenden Vorgang.
- Prüfe externe Abhängigkeiten und Ausfallfolgen für Fachabläufe.
  Setze neue Infrastruktur, verteilte Transaktionen oder zusätzliche Dienste nur als begründete Option mit Betriebs- und Konsistenzkosten ins Verhältnis zum heutigen Modell.

## Ergebnis

Zeige eine Systemkontext-/Deploymentansicht mit Prozess-, Netzwerk-, Vertrauens- und Datengrenzen.
Ergänze Sequenzdiagramme für die untersuchten kritischen Normal- und Ausfallpfade, wenn sie die Entscheidung klären.
Pfeile müssen ihre Bedeutung erkennen lassen; ein Repositoryordner ist kein Deploymentknoten.

Berichte feste Prüfstände, betrachtete Varianten, vollständige und offene Abdeckung sowie vorhandene und fehlende Betriebsevidenz.
Jedes bestätigte Risiko braucht ein konkretes Szenario, die verletzte Anforderung, betroffene Grenzen, Auswirkung und Evidenz.
Trenne davon offene Anforderungen und Optionen mit Nutzen, Komplexitätskosten, Übergangsweg und verbleibenden Risiken.
Gleiche verwandte Issues/ADRs ab, soweit zugänglich; erfinde keine Prioritäten, zugesicherten SLAs oder erfolgreich durchgeführten Ausfalltests.
Ein Bericht verändert keine Systeme, startet keine Workflows und verleiht keine Betriebs- oder Merge-Freigabe.

Die Anwendungsarchitektur-Perspektive besitzt den inneren Fachmodulzuschnitt; die DevOps-Perspektive die konkrete Reproduzierbarkeit und Betriebsdurchführung.
Bewerte ihre Auswirkungen auf das Gesamtsystem und verweise bei kombinierten Reviews auf dieselbe zugrunde liegende Ursache.
