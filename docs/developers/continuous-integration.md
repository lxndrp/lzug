# Continuous Integration

Die Workflows sind die ausführbare Quelle für Auswahl, Gates und konkrete Prüfkommandos.
Diese Übersicht erklärt nur, wann welcher Nachweis gilt und wie ein Fehler eingeordnet wird.

## Pull Requests

`.github/workflows/pull-request.yml` ordnet geänderte Dateien konservativ den Domänen Dokumentation, Backend, Frontend, CLI, Container und Infrastruktur zu.
Workflow-, Toolchain-, Abhängigkeits- und Skriptänderungen wählen alle Domänen; unbekannte Pfade ebenso.
Produktive Webänderungen wählen Browser-E2E und Accessibility getrennt.
Jeder sichtbare Gate-Job behandelt eine nicht ausgewählte Domäne ausdrücklich als `skipped`, nicht als stillschweigenden Erfolg.

Der Workflow prüft außerdem Source-Scan und CodeQL.
Nicht geänderte Sprachen übernehmen nur einen validierten Nachweis für die exakte Pull-Request-Basis; eine fehlende oder unvollständige Basis schlägt fehl.
Die aktuelle Required- Check-Konfiguration und die jeweiligen Jobnamen werden aus dem aktiven GitHub-Ruleset gelesen, nicht aus dieser Dokumentation abgeleitet.

## `master` und Releases

`.github/workflows/quality.yml` prüft jeden Push auf `master`, manuelle Starts und den Zeitplan vollständig, ohne Pfadauswahl.
Sein erfolgreicher Lauf für eine konkrete SHA ist der Qualitätsnachweis für den [Releaseablauf](releases.md).
Release- und Snapshot-Promotion wiederholen diesen Nachweis nicht und fragen keine internen Jobnamen ab.

## Lokale Auswahl und Diagnose

Für eine begrenzte Änderung wird der direkt betroffene Task verwendet, etwa `task docs`, `task quality:backend` oder `task quality:infra`.
Der breite `task quality` ist für Workflow-, Toolchain-, Abhängigkeits-, Sicherheits- und andere querschnittliche Änderungen bestimmt.
E2E und Accessibility bleiben getrennt; vor einer lokalen Browserprüfung läuft `task doctor`.

Bei einem Fehler zuerst die ausführende Workflow-Zusammenfassung und die betroffene Task-Ausgabe vergleichen.
Unveränderte Sandbox- oder Browserprobleme werden als Umgebungsgrenze dokumentiert und nicht durch Wiederholung verschleiert.
Gehostete CodeQL- und Source-Scans bleiben eine CI-Ergänzung.
