# Frontend-Richtlinie

Bei Planung, Umsetzung und Review wird die Anwendung aus Sicht der Nutzenden beurteilt. Ziel ist eine ruhige, klare und ästhetische Verwaltungsoberfläche, deren Form der Funktion folgt und die ohne Implementierungswissen verständlich ist.

## Technische und gestalterische Quellen

[Taiga UI](https://taiga-ui.dev/) ist die extern gepflegte technische Grundlage
für Komponenten, Tokens und Theming. Die Anwendung nutzt die dokumentierten
Möglichkeiten der Bibliothek; ihre Quellen werden nicht in ein lokales
Designsystem kopiert. Persönliche Codex- oder MCP-Konfigurationen können bei
der Recherche helfen, gehören aber weder in das Repository noch zu den
Voraussetzungen für Umsetzung oder Review.

Die folgenden Quellen ergänzen Taiga UI mit klar getrennten Rollen:

- [WCAG 2.2](https://www.w3.org/TR/WCAG22/) ist der Maßstab für
  Zugänglichkeit; automatisierbare Kriterien werden in den vorhandenen
  Accessibility-Prüfungen erfasst, übrige Kriterien sichtbar geprüft.
- Die [Nielsen-Heuristiken](https://www.nngroup.com/articles/ten-usability-heuristics/)
  strukturieren das Usability-Review, insbesondere Rückmeldung,
  Fehlervermeidung und verständliche Begriffe.
- Steve Krugs [*Don't Make Me Think, Revisited*](https://www.pearson.com/en-us/subject-catalog/p/dont-make-me-think-revisited-a-common-sense-approach-to-web-usability/P200000000385/9780137460434)
  schärft die Prüfung auf selbstverständliche Orientierung, scanbare
  Informationsgestaltung, eindeutige Aktionen und knappe Sprache. Fachlich
  notwendige Denkarbeit bleibt sichtbar; unnötige Denkarbeit durch die
  Oberfläche wird vermieden.
- Das [GOV.UK Design System](https://design-system.service.gov.uk/) dient als
  Musterreferenz für Informationsstruktur, Formulare und Rückmeldungen. Es
  liefert keine CSS- oder Komponentenbasis für lzug.

Diese Referenzen begründen keine zusätzlichen Frameworks oder lokalen
Gestaltungsregeln. Insbesondere werden weder GOV.UK-CSS noch weitere
CSS-Frameworks oder ein Screenshot-Regressionstest eingeführt.

- Fachliche Aufgaben, Begriffe und Folgen müssen erkennbar sein; interne API-, Status- oder Implementierungsbegriffe werden nicht ungefiltert angezeigt.
- Interaktive Elemente benötigen eindeutige Signale, erwartbare Zuordnung und unmittelbares Feedback. Beschriftung, Sichtbarkeit und Zustand vermitteln die Funktion.
- Sinnvolle Vorgaben, Einschränkungen und Validierung verhindern Fehler. Tritt ein Fehler ein, erklärt die Oberfläche Kontext und Korrekturweg.
- Informationshierarchie, Navigation und Aktionsgewichtung bleiben konsistent. Primäre, sekundäre und destruktive Aktionen unterscheiden sich visuell und semantisch.
- Ästhetik dient Lesbarkeit, Orientierung und Vertrauen; Dekoration darf keine fehlende Struktur kaschieren oder Aufmerksamkeit von der Aufgabe abziehen.
- Jeder betroffene Ablauf umfasst Laden, Leerzustand, Erfolg, Fehler, Bestätigung und Abbruch. Eine ausdrückliche UX-Prüfung betrachtet alle produktiven Hauptabläufe.
- Desktop und Mobil sowie helles und dunkles Farbschema werden auf sichtbare Hierarchie, Kontrast, Fokus, Umbruch, Überlauf und erreichbare Aktionen geprüft.
- Positives und Verbesserungsbedarf werden nach Verständlichkeit, Fehlervermeidung und Aufgabenerfolg konkret priorisiert.

## Abgrenzung zum Web-Auftritt

Diese Richtlinie betrifft die Verwaltungsanwendung. Für den späteren
öffentlichen Web-Auftritt kann Nancy Duartes Arbeit als Referenz für
Erzählführung, visuelle Dramaturgie und die Vermittlung des Produkts dienen.
Sie ist weder eine Komponenten- oder CSS-Basis noch ein Maßstab für die
aufgabenzentrierte Anwendungsoberfläche. Die konkrete Gestaltung des
Web-Auftritts wird in einer eigenen Entscheidung dokumentiert.
