# ADR-0037: PowerShell/Pester-Testharness

## Datum

2026-09-15.

## Status

Akzeptiert.

## Kontext

Die OCI-, Compose- und Kompatibilitätsverträge wurden zuvor über getrennte Shell-
und Python-Einstiege orchestriert.
Das erschwerte plattformübergreifende Ausführung und erzeugte parallele
Selbsttests.

## Entscheidung

PowerShell verbindet Docker und Compose mit Pester.
Die Pester-Version ist in `tests/pester/requirements.psd1` gepinnt und wird über
`scripts/run-pester.ps1` geladen.
`tests/pester/LzugHarness.ps1` kapselt ausschließlich native Aufrufe, Docker-
Voraussetzungen und Readiness-Wartezyklen.
Die Verträge bleiben komponentennah in den Pester-Testdateien.
Pester erzeugt NUnit-XML unter `build/quality/pester/pester.xml`, damit CI die
Ergebnisse als Standardtestreport weiterverarbeiten kann.

PowerShell ersetzt weder Task als öffentliche Workflow-Schnittstelle noch
Docker/Compose als Runtime und auch nicht fachliche Backend- oder CLI-Tests.
InSpec bleibt bewusst ausgeschlossen.

## Supersession

Dieser ADR löst ADR-0025 ab.
ADR-0025 verweist seinerseits auf diesen ADR.

## Konsequenzen

Die lokalen und CI-Einstiege sind einheitlich.
Die Runtime-Verträge benötigen weiterhin Docker und bleiben auf die unterstützte
Linux-Referenzplattform angewiesen.
Die Pester-Modulauflösung ist reproduzierbar gepinnt, aber kein Produkt-
Runtimebestandteil.

## Präzisierung des Umsetzungsumfangs

Die Ablösung von ADR-0025 betrifft die Shell-/Python-Orchestrierung der
Produkt-, Compose- und Kompatibilitätsverträge.
Die Entscheidung gegen einen zusätzlichen InSpec-Harness bleibt bestehen;
Demo-Smokes und OpenTofu-Prüfungen behalten ihre komponenteneigenen Aufgaben.
Pester ersetzt keine Laufzeitnachweise durch Image-Metadaten oder Textmuster.
Der gemeinsame Lifecycle umfasst isolierte Ressourcen und Cleanup;
fachliche Assertions bleiben in den Testdateien.
Der tatsächlich ausführbare Umfang steht unter
[OCI-Runtime und Infrastruktur](../components.md#oci-runtime-und-infrastruktur).
