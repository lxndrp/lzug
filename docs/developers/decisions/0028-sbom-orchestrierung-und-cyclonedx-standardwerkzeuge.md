# ADR-0028: SBOM-Orchestrierung und CycloneDX-Standardwerkzeuge abgrenzen

## Status

Akzeptiert am 29.08.2026.

## Kontext

Syft erzeugt die kanonischen CycloneDX-1.6-Inventare für Abhängigkeiten, das
OCI-Image und die sechs nativen CLI-Artefakte. `scripts/sbom.py` bindet diese
Standardfunktion in den lokalen, CI- und Releaseablauf ein. Das Skript führt
außerdem die acht detaillierten Inventare zu genau einer sichtbaren
Release-SBOM zusammen und prüft die projektspezifischen Lieferkettenverträge.

Die eigene Logik soll nicht generische CycloneDX-Funktionen nachbilden, wenn ein
gepflegtes Standardwerkzeug dieselbe Aufgabe mit weniger Code und
Wartungsaufwand reproduzierbar erfüllt. Umgekehrt darf eine Standardfunktion
weder Releaseidentität und Umfang noch Lizenz-, OCI- oder Go-Grenzen
abschwächen.

## Entscheidung

Die bestehende Orchestrierung bleibt unverändert. Syft bleibt das gepinnte
Standardwerkzeug für die Erzeugung. Für Zusammenführung, Normalisierung und
Vertragsvalidierung wird kein zusätzliches CycloneDX-Werkzeug eingeführt, weil
keiner der bewerteten Kandidaten die lzug-Verträge vollständig ersetzt und
zugleich den Gesamtaufwand senkt.

### Zuordnung der Operationen

| Operation | Verantwortung | Begründung |
| --- | --- | --- |
| Abhängigkeits-SBOM aus installierter Python-Umgebung, npm-Lockfile und `go.mod` erzeugen | Syft, durch lzug orchestriert | Syft katalogisiert die drei Ökosysteme im Standardformat; lzug legt Cataloger, Ausschlüsse, Quellidentität, Version und Offline-Konfiguration fest. |
| OCI-SBOM für das exakte finale Image erzeugen | Syft, durch lzug orchestriert | Der Scanner ist generisch; die Bindung an dasselbe gebaute Image und der Ausschluss von Build-only-Ökosystemen sind Projektverträge. |
| Je eine SBOM für sechs bereits gebaute CLI-Binärdateien erzeugen | Syft, durch lzug orchestriert | Der Dateiscan ist generisch; Anzahl, Zielmatrix, Quellnamen und erwartete eingebettete Go-Module gehören zum Releasevertrag. |
| JSON lesen und kanonisch schreiben | Python-Standardbibliothek | Eine weitere Formatkonvertierung ist nicht erforderlich; sortierte Schlüssel und ein abschließender Zeilenumbruch sind deterministisch. |
| Komponenten zusammenführen und deduplizieren | lzug-spezifische Implementierung | Gleichheit ignoriert ausschließlich die flüchtige `bom-ref`; jede Komponente erhält eine inhaltsadressierte Referenz und die sortierte Menge ihrer Detailquellen. Diese Semantik bietet kein bewertetes Standardwerkzeug. |
| Release-SBOM normalisieren | lzug-spezifische Implementierung | Seriennummer, Release-Tag, Commit-SHA, Detailanzahl, Werkzeugnachweis und Komponentenreihenfolge müssen aus unveränderlichen Releaseeingaben entstehen. |
| CycloneDX-Format und Syft-Herkunft prüfen | lzug-spezifischer Vertragscheck | Standardvalidatoren können das Schema prüfen, ersetzen aber weder den CycloneDX-1.6- und Syft-Pin noch nichtleere Komponenten und die erwartete Generatoridentität als gemeinsamen Projektvertrag. |
| Lizenz-, Go-, OCI-/CLI- und Releaseumfang prüfen | lzug-spezifische Implementierung | npm-Lizenzmetadaten, lzug-Lizenznachweis, deklarierte Go-Module, Build-only-Ausschlüsse, acht Detail-SBOMs und Releaseidentität sind keine generischen CycloneDX-Regeln. |

### Vergleich der Standardwerkzeuge

Bewertet wurden die am 29.08.2026 aktuellen offiziellen Schnittstellen:

| Kandidat | Unterstützte generische Operation | Reproduzierbarkeit und Vertragsgleichheit | Abhängigkeiten und Wartungswirkung | Ergebnis |
| --- | --- | --- | --- | --- |
| CycloneDX CLI `0.33.1` | Flache oder hierarchische Zusammenführung, Konvertierung und Schema-/Formatvalidierung bis CycloneDX 1.7 | `merge` setzt eine zufällige UUID und den aktuellen Zeitstempel. Seine Optionen kennen Gruppe, Name und Version, aber weder Release-Revision und Detailanzahl noch lzug-Quellmarkierungen und inhaltsadressierte Komponentenreferenzen. Eine Nachbearbeitung müsste die bestehende Logik erhalten. | Zusätzlich zu Syft wäre eine .NET-basierte, plattformspezifische Binärdatei in lokaler Toolchain und allen betroffenen Workflows zu pinnen. Apache-2.0 ist lizenzseitig geeignet; der neue Pin und Installationspfad erhöhen dennoch die Wartungsfläche. | Keine Ablösung |
| CycloneDX Python Library `11.12.0` | Datenmodell, Lesen/Schreiben und optionale JSON-Schemavalidierung | Die Bibliothek bietet keine passende Release-Zusammenführung. Schemavalidierung deckt die lzug-Regeln nicht ab und ändert nichts an der nötigen deterministischen Aggregation. | Eine ältere Version liegt nur transitiv über `pip-audit` vor. Eine stabile Nutzung verlangte eine direkte Abhängigkeit sowie für JSON-Validierung zusätzlich `jsonschema` und `referencing`. | Keine Ablösung |
| CycloneDX `sbom-utility` `0.19.2` | Offline-Schemavalidierung und zusätzliche deklarative Prüfungen | Die Standardprüfung ersetzt keine Umfangs- oder Releaseverträge; die projektspezifische Validierungsschnittstelle ist experimentell. Das Werkzeug führt die acht Inventare nicht mit der benötigten Semantik zusammen. | Eine weitere separat gepinnte Go-Binärdatei käme zu Syft hinzu. Apache-2.0 ist geeignet, die zusätzliche Installation spart aber weder Projektcode noch Tests. | Keine Ablösung |

Zum Entscheidungszeitpunkt umfasst `scripts/sbom.py` 576 Zeilen und der direkte
Vertragstest 11 Positiv- und Negativfälle. Die eigentliche generische
Komponentenschleife ist nur ein kleiner Teil der Aggregation. CycloneDX CLI
würde sie ersetzen, erforderte aber weiterhin Vorprüfung, deterministische
Metadaten, Quellzuordnung, Nachbearbeitung und dieselben Vertragstests. Ein
Standard-Schemavalidator könnte nur die allgemeinen Formatprüfungen ergänzen;
die projektspezifischen Tests und Prüfpfade blieben vollständig bestehen. Damit
ist weder bei Codeumfang und Tests noch bei Abhängigkeiten und Wartung eine
messbare Vereinfachung nachgewiesen.

Die vorhandenen Tests belegen die deterministische Wiederholung der
Aggregation sowie fail-closed Negativfälle für eine unvollständige
Detailmenge, fehlende Lizenzmetadaten, Go-Modulabdeckung und falsche
Ökosystemgrenzen. Lokale Tasks, CI und Release verwenden bereits denselben
`scripts/sbom.py`-Pfad und dieselbe gepinnte Syft-Version; sie bleiben deshalb
unverändert.

## Konsequenzen

- Die Dependency-, Image-, sechs CLI- und aggregierte Release-SBOM behalten
  CycloneDX 1.6 sowie ihre bisherigen Umfangs- und Herkunftsverträge.
- `scripts/sbom.py`, `Taskfile.yml`, `.mise.toml`, Lockfiles und die CI- und
  Releaseworkflows erhalten keine künstliche Werkzeug- oder Codeänderung.
- Schema-/Formatvalidatoren bleiben mögliche ergänzende Gates, sind aber keine
  Ablösung der lzug-Vertragsprüfung. Ein zusätzliches Gate benötigt einen
  eigenen Nutzen- und Abhängigkeitsnachweis.
- Eine spätere Neubewertung ist sinnvoll, wenn ein Standardwerkzeug
  deterministische Seriennummern und Zeitwerte, konfigurierbare
  Release-Metadaten, quellenbewusste Deduplizierung und inhaltsadressierte
  Komponentenreferenzen direkt unterstützt.

## Alternativen

- CycloneDX CLI nur für `merge` einführen und das Ergebnis nachbearbeiten:
  behält fast die gesamte eigene Aggregationslogik und ergänzt einen weiteren
  Toolchain- und Workflow-Pin.
- Einen Standardvalidator zusätzlich vor jeder Projektprüfung ausführen:
  stärkt möglicherweise ein separates Schema-Gate, reduziert aber keine
  bestehende Prüfung und erfüllt daher das Vereinfachungsziel nicht.
- Die projektspezifischen Regeln in experimentelle deklarative Checks eines
  Fremdwerkzeugs übertragen: verschiebt statt reduziert die Verantwortung und
  deckt Releaseaggregation sowie Go- und Artefaktgrenzen nicht vollständig ab.

## Referenzen

- [CycloneDX CLI: Befehle und Plattformen](https://github.com/CycloneDX/cyclonedx-cli/tree/v0.33.1)
- [CycloneDX CLI: Implementierung von `merge`](https://github.com/CycloneDX/cyclonedx-cli/blob/v0.33.1/src/cyclonedx/Commands/MergeCommand.cs)
- [CycloneDX Python Library](https://github.com/CycloneDX/cyclonedx-python-lib/tree/v11.12.0)
- [CycloneDX sbom-utility](https://github.com/CycloneDX/sbom-utility/tree/v0.19.2)
- [CycloneDX Tool Center](https://cyclonedx.org/tool-center/)
- [ADR-0009: Toolchain und Entwicklungs-Tasks trennen](0009-toolchain-und-entwicklungs-tasks.md)
- [ADR-0020: Minimaler Releaseablauf mit GitHub-Bordmitteln](0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
- [Veröffentlichungs- und Runtime-Sicherheit](../architecture/security-baseline.md)
