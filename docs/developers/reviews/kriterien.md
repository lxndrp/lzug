# Reviewkriterien

Diese Kriterien lenken Reviewaufmerksamkeit auf überprüfbare Projektrisiken.
Sie ersetzen keine deterministischen CI-Regeln.

## Architektur

- Architekturübersicht, Schichtengrenzen und ADRs stimmen mit der Implementierung überein.
- Neue Kopplungen, parallele Muster, Komplexität und Abhängigkeiten sind begründet und angemessen.
- Architektur- und Produktdokumentation beschreiben denselben aktuellen Stand.

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
