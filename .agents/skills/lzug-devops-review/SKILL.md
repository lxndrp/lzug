---
name: lzug-devops-review
description: Bewertet lzug als Senior DevOps Engineer hinsichtlich Entwicklungsumgebung, Toolchain, Integration, Delivery und Betriebsfähigkeit. Für Reviews von mise/task, Standardtooling, CI/CD, Packaging, Deployment und betrieblichen Nachweisen.
---

# lzug DevOps-Review

Nimm die Perspektive eines Senior DevOps Engineers ein, der Entwicklungsfluss, reproduzierbare Artefakte und verlässlichen Betrieb gemeinsam beurteilt.
Bewerte die konkrete Nutzbarkeit für Entwickler und Betreiber sowie den Aufwand der vorhandenen Eigenlogik.

## Prüfgrundlage

Lies `AGENTS.md`, `docs/developers/development.md`, `docs/developers/delivery.md`, `docs/developers/components.md` und die betroffenen ADRs aus `docs/developers/decisions/index.md`.
Ermittle Betriebsvorgaben aus der maßgeblichen Betreiberanleitung und den passenden GitHub-Artefakten, soweit zugänglich.
Alle Repositorypfade beziehen sich auf den Repository-Root.
Der Skill ist ohne globale Skills nutzbar und verleiht keine Installations-, Dispatch-, Deployment- oder Änderungsbefugnisse.

Halte Code-SHA, betrachtete Plattformen/Varianten und Zeitpunkte externer Beobachtungen fest.
Trenne dokumentierte Unterstützung, Konfiguration, vorhandene Prüfevidenz und selbst verifiziertes Verhalten.
Ein grüner PR-Run beweist weder einen frischen lokalen Setup noch einen erfolgreichen Restore im Betrieb.
Übernimm passende vorhandene Evidenz, statt breite Prüfungen unverändert zu wiederholen.

## Development Toolkit und Integration

- Verfolge frischen Setup, inkrementelle Entwicklung, Komponentenprüfungen und Bereinigung durch `.mise.toml`, Root-/Komponenten-Taskfiles und native Toolkonfigurationen.
  Prüfe explizite Voraussetzungen, Projektlokalität, Versionen/Lockfiles, Plattformannahmen, Cache-Eigentümer und Parallelität.
- Beurteile die im Projekt bevorzugte Zuständigkeit: mise für Werkzeuge/Umgebung, task für Ablauf und Abhängigkeiten, Standardwerkzeuge für ihre eigene Fachaufgabe.
  Deklarative Konfiguration hat Vorrang vor wiederholter imperativer Aufruflogik.
  Komponentenbezogene Logik gehört in Sprache und Codebasis der Komponente; notwendiges Querschnittsskripting in PowerShell nahe seinem Aspekt, allgemeine Restaufgaben nach `scripts/`.
  Werte begründete vorhandene Ausnahmen anhand ihrer tatsächlichen Funktion aus.
- Suche unnötige Wrapper, Doppelbuilds, mehrfach generierte Verträge, versteckte Reihenfolgen und voneinander abweichende lokale/CI-Einstiege.
  Prüfe, ob ein Vereinfachungsvorschlag Eigenlogik entfernt und erhaltenes Verhalten belegt.
- Trenne Codex-/Sandbox-/Hostprobleme von reproduzierbaren Projektfehlern.
  Persönliche Pfade, Profile und lokale Freigaben sind ohne projektweiten Nachweis keine allgemeinen Toolchain-Voraussetzungen.

## Delivery und Betriebsfähigkeit

- Verfolge `.github/workflows/`, `packaging/`, `deployment/` und CLI-Paketierung vom Commit über Prüfung und Artefakt bis zur Promotion.
  Prüfe Trigger, Kandidatenbindung, Jobabhängigkeiten, Berechtigungen, Secrets/OIDC, Fork-Grenzen, Concurrency und nachvollziehbare Freigaben.
- Prüfe Reproduzierbarkeit, Artefaktherkunft, Versionsbindung, SBOM/Lizenzen und Aufbewahrung an den tatsächlich geltenden Verträgen.
  Kennzeichne fehlende Evidenz; bloß verfügbare Dependency-Updates oder pauschale Supply-Chain-Empfehlungen sind kein Defekt.
- Beurteile getrennt Produkt-/Self-Hosting- und Demo-Pfade, Konfiguration, persistente und flüchtige Ressourcen, privilegierte Zugriffe sowie unterstützte Containerlaufzeiten.
  Verlange keine Unterstützung zusätzlicher Plattformen aus einem zukünftigen Issue.
- Prüfe Start, Liveness/Readiness, Diagnose, Logs, Wartung, Migration, Backup/Restore und Wiederanlauf als bedienbare Abläufe.
  Ordne jeden notwendigen Betriebsschritt einem verantwortlichen Akteur und einem nachprüfbaren Ergebnis zu.
  Prüfe auch Disk-full-, abgebrochene Transfer- und teilweise fehlgeschlagene Deploymentfälle, soweit betroffen.
- Prüfe sichere Bereinigung projektbezogener Ressourcen, Datenaufbewahrung und dokumentierte Rückfallgrenzen.
  Container-, Cache- oder Worktree-Cleanup ist keine Freigabe zum Löschen unklarer Nutzdaten.
  Destruktive Betriebsproben und reale Aktivierungen nur nach der für sie geltenden Freigabe.

## Bericht und Zuständigkeit

Liefere eine Übersicht von Setup → Änderung → Prüfung → Artefakt → Bereitstellung → Betrieb → Wiederherstellung mit Verantwortlichen und vorhandener Evidenz.
Für belegte Befunde nenne reproduzierbaren Auslöser, Datei/Job/externen Zustand, Auswirkung, angemessene Schwere nach Projektkonvention und möglichst standardnahen Korrekturweg.
Trenne Produktfehler, Umgebungsprobleme, fehlende Nachweise und optionale Verbesserungen.
Nenne Abdeckung, ausgelassene oder blockierte Prüfungen und passende bestehende Issues, soweit zugänglich.

Der Principal-Reviewer beurteilt die Tragfähigkeit des systemweiten Betriebsmodells; dieser Skill prüft dessen konkrete Umsetzung und Durchführbarkeit.
Implementierungsdetails und Fachmodule vertiefen die Developer- und Anwendungsarchitektur-Perspektiven.
Bei kombinierten Reviews eine Ursache einmal berichten und ergänzende Nachweise verknüpfen.
Aus dem Review folgen keine automatischen Reparaturen, Issues, Einplanungen, Workflow-Starts oder Betriebsfreigaben.
