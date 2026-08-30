# Reviewkriterien

Diese Kriterien lenken Reviewaufmerksamkeit auf überprüfbare Projektrisiken.
Sie ersetzen keine deterministischen CI-Regeln.

## Architektur

- Architekturübersicht, Schichtengrenzen und ADRs stimmen mit der Implementierung überein.
- Neue Kopplungen, parallele Muster, Komplexität und Abhängigkeiten sind begründet und angemessen.
- Architektur- und Produktdokumentation beschreiben denselben aktuellen Stand.

### Risikobasierte Architekturprüfung

Die folgenden Fragen gelten, soweit eine Änderung Architektur, Verträge oder Betriebsgrenzen berührt.
Sie konkretisieren die verbindlichen [Architekturprinzipien](../architecture/principles.md), ohne eine zusätzliche Freigabe oder pauschale Compliance-Prüfung einzuführen.

- Bleiben Systemgrenze, Schichten, Verantwortungen und betroffene ADRs
  widerspruchsfrei, oder ist eine neue langfristige Entscheidung erforderlich?
- Sind neue Abhängigkeiten, Netzwerkgrenzen, Transaktionen, Seiteneffekte und
  Fehlerpfade begründet und mit ihrer Auswirkung beschrieben?
- Bleiben Identität, Autorisierung, Ausschuss-Scope, Datenminimierung und
  Betreibergrenzen serverseitig durchgesetzt?
- Sind Datenänderung, Migration, Rückwärtsverträglichkeit, Wiederanlauf sowie
  gegebenenfalls Backup und Restore nachvollziehbar?
- Passen Konfiguration, Deployment, Readiness, Diagnose und Rückfallgrenze zum
  betroffenen Betriebsmodell?
- Decken Tests und Dokumentation das konkrete Risiko und die Auswirkungsbreite
  ab, einschließlich aktualisierter Architekturansichten bei geänderten Grenzen?

Der [OWASP Application Security Verification Standard](https://owasp.org/www-project-application-security-verification-standard/) wird nur bei berührten Anwendungssicherheitsrisiken herangezogen, etwa für Authentifizierung, Autorisierung, Session, Eingabevalidierung, Geheimnisse oder sensible Daten.
Konkrete Anforderungen werden mit ihrer ASVS-Version benannt; es wird keine pauschale ASVS-Konformität behauptet.

Das [Azure Well-Architected Framework](https://learn.microsoft.com/azure/well-architected/what-is-well-architected-framework) ist nur für Änderungen an der Azure-Demo oder ihrer Betriebsgrenze relevant.
Dann werden ausschließlich betroffene Aspekte von Zuverlässigkeit, Sicherheit, Kosten, Betrieb und Leistung einschließlich ihrer Zielkonflikte geprüft; das Framework wird nicht zum allgemeinen Produkt-Gate.

## Codequalität und Tests

- Verantwortlichkeiten, Fehlerbehandlung und kritische Pfade bleiben verständlich und wartbar.
- Duplikation, ungenutzter oder überholter Code und technische Schulden haben eine konkrete Folgewirkung.
- Fachlich oder technisch kritische Änderungen haben angemessene Tests auf Domain-, HTTP-, Frontend- und Browser-Ebene.
- Fehlende oder auffällig geschwächte Tests und Coverage werden nur mit nachvollziehbarer Evidenz benannt.

## Dokumentation

- README, Handbuch, Architektur, ADRs, Konfiguration und Code widersprechen sich nicht.
- Setup-, Build-, Betriebs- und Schnittstellenanweisungen sowie Links sind aktuell und nutzbar.
- Neue Entscheidungen und relevante Konfigurationen sind dort dokumentiert, wo sie dauerhaft auffindbar sind.

## Fachliche Konsistenz und Drift

- Begriffe, Datenmodell, Statusübergänge, Invarianten und dokumentierte Abläufe stimmen mit dem Verhalten überein.
- Roadmap, Issues, Dokumentation und Produktziel bleiben konsistent.
- `lzug` bleibt ein Werkzeug für die Arbeit der Prüfungsausschüsse; eine unbeabsichtigte Ausweitung zur internen IHK-Sachbearbeitung ist als belegter Drift zu benennen.
- Fehlende fachliche Dokumentation ist selbst ein Befund. Nicht dokumentierte Regeln werden nicht angenommen.

## Betrieb, Abhängigkeiten und Sicherheit

- Start, Konfiguration, Migration, Diagnose, Wiederanlauf und Datenverträglichkeit sind im Repository nachvollziehbar.
- Secrets, externe Dienste, Runtime- und Toolchain-Versionen sowie technische Obsoleszenz werden risikobasiert betrachtet.
- Backup, Restore und Produktbetrieb werden nur beurteilt, soweit Tests, Konfiguration oder dokumentierte Evidenz vorliegen; fehlende Telemetrie ist keine Aussage über den tatsächlichen Betrieb.
- Sicherheits- und Abhängigkeitsbefunde werden mit Pfad, Ausnutzbarkeit, betroffener Laufzeit und vorhandener Mitigation eingeordnet.
