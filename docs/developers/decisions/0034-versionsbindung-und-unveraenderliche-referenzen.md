# ADR-0034: Versionsbindung und unveränderliche Referenzen an Risikogrenzen

## Datum

2026-09-07.

## Status

Akzeptiert am 2026-09-07.

## Kontext

Versionsnummern, Lockfile-Einträge, Git-Revisionen, OCI-Digests, Prüfsummen,
SBOMs und Attestierungen beantworten unterschiedliche Fragen.
Werden sie alle als manuell zu pflegende Bindungen behandelt,
entstehen parallele Konfiguration, Synchronisationslogik und unnötige Bedienlast.
Werden dagegen auch sicherheitskritische Grenzen nur über möglicherweise veränderbare Namen adressiert,
können Prüfung, Deployment und Wiederanlauf unterschiedliche Bytes verwenden.

lzug benötigt deshalb einen repositoryweiten Normalfall für die Auswahl von Abhängigkeiten und Produktartefakten
sowie eng begrenzte Ausnahmen für unveränderliche Byte-Referenzen.

## Entscheidung

### Auswahl, Auflösung und Nachweis

1. **Auswahl:** Menschen, Produkt- und Betreiberkonfiguration sowie Planung wählen eine veröffentlichte Version.
   Produktartefakte verwenden exakte SemVer-Versionen;
   OCI-Basisimages und Buildwerkzeuge verwenden explizite Versionstags.
   Python-, npm-, Go- und OpenTofu-Abhängigkeiten werden in den Standardmanifesten ihres Ökosystems beschrieben.
2. **Auflösung:** Paketmanager, Registry und Workflow lösen die gewählte Version auf konkrete Abhängigkeiten und Artefakte auf.
   Die Standard-Lockmechanismen des jeweiligen Ökosystems halten diese Auflösung reproduzierbar fest.
3. **Nachweis:** Lockfiles, vollständige Git-Revisionen, Digests, Prüfsummen, SBOMs und Attestierungen dokumentieren die tatsächlich verwendeten Bytes und ihre Herkunft.
   Ein solcher Nachweis ist keine zweite, von Menschen zu pflegende Versionsauswahl.
4. **Ausnahme:** Eine unveränderliche Digest- oder SHA-Referenz wird selbst zur verbindlichen Eingabe,
   wenn sie an einer konkreten Risikogrenze notwendig ist.

Unversionierte Referenzen, `latest` sowie Branchreferenzen wie `main` oder `master` sind für produktive Artefakte und Buildabhängigkeiten unzulässig.
Es entsteht weder eine zentrale Versionsdatei noch ein eigener Generator, Auflöser oder Updatebot.
Standardmanifeste, Lockfiles, Registrys und Dependabot bleiben für ihre jeweiligen Aufgaben maßgeblich.

### Risikogrenzen für Digest- und SHA-Bindung

Eine Digest- oder vollständige SHA-Referenz bleibt verbindlich,
wenn mindestens eines der folgenden Risiken besteht:

- Fremder ausführbarer Code läuft innerhalb einer privilegierten CI- oder Releasegrenze.
- Mehrere Artefakte müssen als exakt geprüftes Paar atomar deployt oder zurückgerollt werden.
- Eine veränderbare Registryreferenz könnte zwischen Prüfung, Deployment und Wiederanlauf auf andere Bytes zeigen.
- Provenance, SBOM, Attestierung oder Rollback müssen exakt ein Byte-Artefakt adressieren.
- Ein ausführbarer Download besitzt keine mindestens gleichwertige Signatur- oder Transparenzprüfung.

Damit bleiben GitHub Actions an vollständige Commit-SHAs gebunden;
die lesbare Versionsangabe und Dependabot unterstützen weiterhin Prüfung und Aktualisierung.
Die öffentliche Demo wählt zunächst eine Produktversion,
löst daraus das zusammengehörige App- und Seed-Image auf und deployt anschließend nur das geprüfte Digestpaar.
Release- und Qualitätsabläufe halten den jeweils geprüften vollständigen Git-Commit fest.
SBOM-Subjects, Provenance, Attestierungen und Artefaktprüfsummen adressieren weiterhin die nachgewiesenen Bytes.

Inhalts-Hashes für Dokumente, Backups, Exporte, Authentisierung, Seeds, Schemata oder fachliche Identitäten sind keine Versionsbindung.
Sie bleiben nach ihrem jeweiligen Inhalts- oder Integritätsvertrag bestehen und begründen keinen alternativen Versionspfad.

## Konsequenzen

- Produkt- und Betreiberoberflächen verlangen im Normalfall eine exakte veröffentlichte Version,
  nicht das manuelle Ermitteln eines Digests.
- Lockfiles und Standardwerkzeuge bleiben die Quelle für die konkrete Auflösung von Ökosystemabhängigkeiten.
- Unveränderliche Referenzen werden nur an der benannten Risikogrenze erzeugt, geprüft und weitergereicht.
  Sie werden nicht als parallele allgemeine Konfiguration dupliziert.
- Release, OCI-Assembly, Demo-Promotion und Lieferkettennachweise behalten ihre spezifischen Verträge.
  Folgeumsetzungen richten deren konkrete Referenzen an dieser Trennung aus.
- Eine neue Digest- oder SHA-Bindung benötigt eine dokumentierte Zuordnung zu einer Risikogrenze.
  Ohne diese Begründung gilt Versionsbindung als Standard.

## Alternativen

- **Digest- oder SHA-Bindung für jede Abhängigkeit:** erhöht manuelle Pflege und Synchronisationsaufwand,
  obwohl Standard-Lockmechanismen und Integritätsnachweise die konkreten Bytes bereits reproduzierbar dokumentieren.
- **Ausschließlich Versionsreferenzen:** schützt privilegierte Ausführung, atomare Deployments und bytegenaue Nachweise nicht ausreichend vor veränderbaren Auflösungen.
- **Repositoryeigene zentrale Versions- und Digestverwaltung:** dupliziert Paketmanager, Registrys, Lockfiles und Dependabot und schafft eine weitere fehleranfällige Quelle.

## Referenzen

- [ADR-0014: OCI-Einzelcontainer mit SQLite und persistentem `/data`](0014-oci-einzelcontainer-und-persistentes-data.md)
- [ADR-0020: Minimaler Releaseablauf mit GitHub-Bordmitteln](0020-minimaler-releaseablauf-mit-github-bordmitteln.md)
- [ADR-0022: Tag-gebundene Demo-Assembly und inhaltsadressierter Seed](0022-tag-gebundene-demo-assembly-und-seed.md)
- [ADR-0028: SBOM-Orchestrierung und CycloneDX-Standardwerkzeuge abgrenzen](0028-sbom-orchestrierung-und-cyclonedx-standardwerkzeuge.md)
