# lzug technische Dokumentation

Dieses technische Handbuch beschreibt den aktuellen, versionierten Stand von
`lzug`. Die öffentliche redaktionelle Handbuchoberfläche liegt im
[GitHub Wiki](https://github.com/lxndrp/lzug/wiki); seine Seiten werden nicht
in diesem Repository gespiegelt.

- **Business Domain** beschreibt Rollen, Verantwortlichkeiten, Prozesse und
  fachliche Regeln des Prüfungsausschusses als gemeinsame Grundlage.
- **Nutzer** finden die vorhandenen Abläufe für Prüfungshalbjahre, Stammdaten und Planung.
- **Administratoren** finden die Anleitung für eine lokale Entwicklungsinstanz.
- **Entwickler** finden Architektur, Schnittstellen, Datenmodell, Entscheidungen und Qualitätsregeln.

Der operative Umfang und die geplante Weiterentwicklung werden nicht hier,
sondern in den [GitHub Issues](https://github.com/lxndrp/lzug/issues) gepflegt.
Die Maintainer verwenden zusätzlich das Project `lzug Roadmap` für Status,
Priorisierung und Iterationen.

Die technische Dokumentation entsteht lokal mit `task docs`. MkDocs bleibt ein
Referenz- und Validierungsbuild; CI stellt den Build als geschütztes Artefakt
`lzug-documentation` bereit. Der Review- und Veröffentlichungsablauf für das
separate Wiki steht unter
[Wiki-Publikation](developers/wiki-publishing.md).
