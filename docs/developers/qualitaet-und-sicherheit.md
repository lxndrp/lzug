# Qualität und Sicherheitsprozess

Qualitätssicherung und das npm-Sicherheitsgate sind Arbeits- und Prüfprozesse, keine eigenständigen Architekturentscheidungen.

## Lokale und kontinuierliche Prüfung

Die lokale Qualitätssicherung ist der erste Prüfpunkt. Bei klar eingegrenzten Änderungen sind passende Teilprüfungen möglich; wenn weitere Bereiche berührt sind oder die Ursache nicht vollständig eingegrenzt ist, folgt `mise quality`. Erst nach erfolgreicher lokaler Prüfung wird CI als finale Abnahme herangezogen.

Neue fachliche Änderungen ergänzen Tests schichtweise: Domain- und Repository-Regeln, HTTP- und OpenAPI-Vertrag einschließlich Fehlern, Frontend-Komponenten und API-Service mit Fixtures sowie mindestens ein Browser-Szenario. Die Pipeline in `.github/workflows/ci.yml` prüft Backend, Frontend, npm-Sicherheit, Dokumentation sowie Browser und Accessibility.

Wenn eine bekannte Codex-Sandbox-Grenze eine Vollprüfung blockiert, ist die Änderung nicht lokal verifiziert. Der Befund wird als Umgebungsproblem dokumentiert; Produktcode wird nicht an reine Sandbox-Symptome angepasst.

## npm-Sicherheitsgate und Dependabot

`mise run quality:security` und der CI-Job verwenden `npm audit --omit=dev --audit-level=critical`. Damit blockieren nur kritische Befunde im produktiv installierten npm-Baum. Nichtkritische oder reine Development-Befunde bleiben sichtbar und werden risikobasiert über Dependabot bewertet.

Kritische produktiv relevante Befunde werden sofort behandelt, hohe produktive innerhalb von sieben Tagen, hohe Development-Befunde innerhalb von 14 Tagen, mittlere innerhalb von 30 Tagen und niedrige bei regulären Updates mindestens quartalsweise. Für einen nicht kompatibel behebbaren transitiven Befund dokumentiert ein Issue Pfad, Ausnutzbarkeit und Mitigation. `npm audit fix --force` und pauschale `overrides` nur zur Befundsenkung sind nicht zulässig.
