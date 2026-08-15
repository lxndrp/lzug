# Öffentliche Web- und Dokumentationspublikation

Diese Seite beschreibt den mit [ADR-0023](decisions/0023-oeffentliche-web-und-dokumentationspublikation.md)
entschiedenen Schnitt. Sie ist noch keine Betriebsanleitung für eine aktive
GitHub-Pages-Site. Eine externe Publikation wird erst in einem eigenen
Umsetzungsschritt und nach Maintainer-Freigabe eingerichtet.

## Anforderungen und identische Bewertungskriterien

Alle Kandidaten werden gegen dieselben Kriterien bewertet:

1. **Produktauftritt:** eigenständiger Einstieg für Produkt, Demo und
   rechtliche Hinweise aus #127 und #356.
2. **Navigation und Suche:** durchgängige Hauptnavigation, verständliche
   Bereichstrennung und lokale Suche ohne zwingenden Drittanbieter.
3. **Barrierefreiheit:** semantisches HTML, Tastaturbedienung, Kontrast und
   automatisierbare Accessibility-Prüfungen. Kein Generator oder Hoster gilt
   ohne Prüfung als barrierefrei.
4. **Responsive Design:** nutzbare Navigation, Suche, Tabellen und
   Code-Referenzen auf schmalen und breiten Viewports.
5. **Wartungsaufwand:** Zahl der Plattformen, Konfigurationen, Updatepfade und
   Berechtigungsmodelle.
6. **Toolchain-Last:** zusätzliche Laufzeiten, Paketmanager, Lockfiles,
   Generatoren und Themes.
7. **Quell- und Versionskennzeichnung:** unveränderliche Repository- und
   Wiki-Revision je Ausgabe sowie erkennbare kanonische Quelle.
8. **Single Source of Truth:** keine eingecheckte Wiki-Kopie und keine
   redaktionelle Kopie generierter Referenzen.
9. **Build und Betrieb:** lokal und in CI reproduzierbar, atomare Ausgabe,
   nachvollziehbare Trigger, Konkurrenzschutz und Rückfallpfad.

## Plattformvergleich

| Kriterium | GitHub Pages | Netlify | Read the Docs |
| --- | --- | --- | --- |
| Produktauftritt | Beliebiges statisches Artefakt; Landingpage und Referenzen können unter einer Herkunft liegen. | Sehr flexibel, einschließlich eigener Redirects und Deploy Previews. | Dokumentationszentrierte Oberfläche; Produkt-/Demo-Einstieg ist möglich, aber nicht der Schwerpunkt. |
| Navigation und Suche | Vom gebauten Artefakt bestimmt; lokale Suche ist möglich. | Vom Artefakt bestimmt; zusätzliche Plattformfunktionen sind verfügbar, aber nicht erforderlich. | Versions- und Suchfunktionen sind stark dokumentationsorientiert. |
| Barrierefreiheit | Verantwortung bleibt bei Generator, Theme, Inhalten und Tests. | Verantwortung bleibt bei Generator, Theme, Inhalten und Tests. | Verantwortung bleibt trotz Dokumentationsfunktionen bei Theme, Inhalten und Tests. |
| Responsive Design | Vom Artefakt bestimmt. | Vom Artefakt bestimmt. | Vom verwendeten Dokumentationsgenerator und Theme bestimmt. |
| Wartungsaufwand | Ein GitHub-Repository, GitHub Actions und ein später geschütztes `github-pages`-Environment. | Zusätzliche externe Projekt-, Berechtigungs- und Abrechnungsoberfläche. | Zusätzliches Projekt und eigener Versions-/Buildvertrag. |
| Toolchain-Last | Keine Generatorvorgabe; vorhandene gelockte Tools können bleiben. | Keine Generatorvorgabe; Plattformkonfiguration kommt hinzu. | Unterstützt MkDocs direkt, komplexe Misch-Artefakte benötigen jedoch eigene Build-Jobs. |
| Quellen/Versionen | Frei gestaltbares Manifest aus Repository- und Wiki-SHA. | Frei gestaltbares Manifest; Deploy-ID kommt als weitere Identität hinzu. | Git-Tags und Branches sind gut sichtbar, der separate Wiki-Stand braucht weiterhin ein eigenes Manifest. |
| Single Source of Truth | Wiki kann beim Build unverändert aus exaktem Commit projiziert werden; keine Quellkopie im Hauptrepository. | Technisch gleich möglich, aber mit zusätzlicher Plattformkopplung. | Hauptrepository-zentrierter Versionsbau passt schlecht zu zwei unabhängigen Git-Quellen. |
| Build/Betrieb | Custom Workflows können beliebige statische Generatoren bauen, ein Artefakt hochladen und getrennt deployen. | Starke Vorschauen und komfortabler Betrieb, aber für den aktuellen Umfang zusätzliche Außenabhängigkeit. | Reproduzierbare Builds sind konfigurierbar; die gemischte Produkt-/Wiki-/Referenz-Site ist kein natürlicher Standardschnitt. |

**Ergebnis:** GitHub Pages ist das Ziel. Es hält Repository, Reviews,
Actions-Artefakt und spätere Deployment-Freigabe in GitHub und verlangt keinen
zusätzlichen Hostingvertrag. Netlify bleibt eine Rückfalloption, wenn #127
später zwingend plattformspezifische Vorschau- oder Routingfunktionen benötigt.
Read the Docs bleibt geeignet für eine eigenständige, versionierte
Dokumentationssite, nicht aber für den gemeinsamen Produkt-, Wiki- und
Referenzeinstieg.

Offizielle Betriebsgrundlagen:

- [GitHub Pages mit Custom Workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub-Actions-Ereignis `gollum`](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#gollum)
- [Netlify Deploy Previews](https://docs.netlify.com/deploy/deploy-types/deploy-previews/)
- [Read-the-Docs-Konfiguration v2](https://docs.readthedocs.com/platform/stable/config-file/v2.html)

## Generatorvergleich

Generator und Theme sind getrennte Entscheidungen. Relearn und Docsy sind
Hugo-Themes; Doks ist ein auf Hugo Extended und npm aufbauendes Framework.

| Kriterium | MkDocs | Hugo Extended |
| --- | --- | --- |
| Produktauftritt | Das vorhandene Basistheme ist für das interne Entwicklerhandbuch zweckmäßig, trägt aber keinen attraktiven gemeinsamen Produkt- und Dokumentationsauftritt. | Flexible Root-Layouts, Inhaltsbereiche und Asset-Pipeline in einem statischen Artefakt. |
| Navigation und Suche | Bewährte Dokumentationsnavigation und lokaler Suchindex. | Themeabhängig; Doks und Relearn bieten lokale Suche und responsive Navigation. |
| Barrierefreiheit | Das Basistheme braucht ebenso projektspezifische Tests. | Eigene Layouts und Theme-Ausgabe müssen semantisch, per Tastatur, Kontrast- und axe-geprüft werden. |
| Responsive Design | Für das technische Handbuch ausreichend, für einen Produktauftritt nur mit erheblicher eigener Gestaltung. | Beide realen Kandidaten waren bei 390 px ohne horizontalen Überlauf nutzbar. |
| Wartungsaufwand | Bereits vorhanden, bleibt für interne technische Dokumentation und Python-Referenz bestehen. | Zusätzlicher gepinnter Generator und Theme-Updatepfad. |
| Toolchain-Last | Python und `uv.lock` sind vorhanden. | Hugo Extended ist eine einzelne Binärdatei; Doks ergänzt npm, Relearn nicht. |
| Quellen/Versionen | Temporäres Staging ist möglich. | Temporäres Staging und sichtbare Quellrevisionen sind ebenso möglich. |
| Single Source of Truth | Löst den Zwei-Repository-Schnitt nicht selbst. | Löst ihn ebenfalls nicht selbst; der Assembler bleibt verantwortlich. |
| Build/Betrieb | Bleibt ein unabhängiger Referenzgenerator. | Baut die öffentliche Hülle und montiert unabhängige Referenzausgaben. |

**Ergebnis:** Hugo Extended erzeugt die öffentliche Hülle. MkDocs wird nicht
ersetzt: Es bleibt der gelockte Generator für das interne Entwicklerhandbuch
und die Python-Referenz. TypeDoc, Redoc und die Schemaansicht bleiben ebenfalls
unabhängige Generatoren; Hugo montiert ihre statischen Ausgaben in ein einziges
Pages-Artefakt.

## Themevergleich und Spike-Evidenz

Doks und Relearn wurden mit identischem deutschen Hero, denselben drei
Inhaltsbereichen und denselben Einstiegslinks lokal gebaut. Geprüft wurden
Desktop und 390 × 844 px, Navigation, Suche, semantische Landmarks,
Browser-Konsole, Buildzeit und Abhängigkeitsbaum. Die Browser-MCP-Auswertung
war einmal transient nicht verfügbar; Screenshots, eine anschließende
Playwright-DOM-Auswertung und statische Artefaktanalyse lieferten den
reproduzierbaren Fallback. Beide Server wurden danach beendet.

| Kriterium | Hugo Relearn 9.0.3 | Doks 1.9.1 | Docsy 0.16 als Referenz |
| --- | --- | --- | --- |
| Produktauftritt | Sehr klares Handbuch mit Sidebar, aber ohne umfangreiches eigenes Layout kein überzeugender Produkt-Hero. | Im direkten Vergleich der deutlich stärkste gemeinsame Produkt-, Demo- und Dokumentationseinstieg. | Portalartig und leistungsfähig, für Umfang und Zielgruppe von lzug schwerer als nötig. |
| Navigation und Suche | Ausgereifte Sidebar und lokale Lunr-Suche, offline und ohne Drittanbieter. | Moderne Topnavigation, Dokumentationsnavigation und lokale FlexSearch-Suche. | Umfangreiche Navigation sowie lokale oder externe Suchvarianten. |
| Barrierefreiheit | Semantische `header`-, `nav`-, `main`-, `aside`- und `footer`-Landmarks waren vorhanden. | Der Starter hatte auf der Homepage kein explizites `main`; der Spike behebt dies im eigenen Layout. Vollständige Tastatur-, Kontrast- und axe-Prüfung bleibt Aktivierungsgate. | Viele Bootstrap-Komponenten vergrößern den projektspezifischen Prüfumfang. |
| Responsive Design | Bei 390 px lesbar, kein horizontaler Überlauf; die große Überschrift brach weniger günstig um. | Bei 390 px klare Einspaltenstruktur, gestapelte CTAs und kein horizontaler Überlauf. | Konzeptionell responsiv, in #206 bewusst kein dritter Implementierungsspike. |
| Wartungsaufwand | Hugo plus ein Theme; einfachster Updatepfad. | Hugo Extended plus Thulite-/npm-Updatepfad und eigene Layout-Overrides. | Hugo Extended, Go Modules, Bootstrap sowie optional npm/PostCSS. |
| Toolchain-Last | Reiner Hugo-Build; der isolierte Vergleich baute in rund 0,15 s. | Der Vergleich installierte 394 Pakete und baute in rund 1,4 bis 5,8 s. Der aktuelle Audit des offiziellen Lockfiles meldete 95 transitive Befunde, davon 9 hoch. | Größte Kette der Kandidaten; für den aktuellen Umfang nicht gerechtfertigt. |
| Quellen/Versionen | Eigene Provenienz-Templates nötig. | Eigene Provenienz-Templates nötig und im Spike belegt. | Eigene Provenienz-Templates nötig. |
| Single Source of Truth | Theme-neutral durch temporäre Wiki-Projektion lösbar. | Theme-neutral durch temporäre Wiki-Projektion gelöst. | Theme-neutral, aber ohne Vorteil für den Quellschnitt. |
| Build/Betrieb | Gewähltes schlankes Ziel mit guter Dokumentations-UX und kleinem eigenen Root-Layout. | Visuell stärkste Fertiglösung, deren Toolchain-Aufwand die Übernahme ausschließt. | Keine erkennbare Gegenleistung für die zusätzliche Komplexität. |

**Ergebnis:** Relearn ist das gewählte Zielbild. Es wahrt die einfache
Hugo-Toolchain ohne zusätzlichen Paketmanager und liefert die stärkste
Handbuch-, Navigations- und Suchbasis. Ein kleines repository-eigenes
Root-Layout übernimmt die hochwertige Produktwirkung, die Doks im visuellen
Vergleich besser vormachte. Doks bleibt deshalb Gestaltungsreferenz, wird wegen
des unverhältnismäßigen npm- und Security-Aufwands aber nicht Teil der
Produktionsarchitektur. Docsy bleibt konzeptionelle Referenz.

Der endgültige Relearn-Spike wurde zusätzlich automatisiert mit Chromium und
axe geprüft. Auf 1440 × 1000 px und 390 × 844 px enthielt er jeweils genau ein
`h1`- und `main`-Landmark, Navigation und Suche, keinen horizontalen Überlauf,
keine Browser-Konsolenfehler und keine axe-Befunde. Der kurzlebige lokale
Prüfserver wird auch im Fehlerfall beendet.

Offizielle Theme-Grundlagen:

- [MkDocs-Konfiguration und Theme-Anpassung](https://www.mkdocs.org/user-guide/configuration/#theme)
- [Hugo Relearn](https://mcshelby.github.io/hugo-theme-relearn/)
- [Doks](https://getdoks.org/)
- [Docsy](https://www.docsy.dev/docs/)

## Kanonische Quellen und erzeugte Projektionen

| Inhalt | Kanonische Quelle | Öffentliche Ausgabe |
| --- | --- | --- |
| Produkt- und Demo-Einstieg | Hauptrepository, später #127 | `/` |
| Fachlichkeit, Nutzung, Administration und redaktionelles Handbuch | Default-Branch des separaten GitHub-Wikis | beim Build erzeugte Projektion unter `/handbuch/` |
| ADRs und technische Architektur | `docs/` im Hauptrepository | unter `/referenz/` verlinkt beziehungsweise gerendert |
| Python-Referenz | Python-Docstrings im Hauptrepository | `/referenz/backend/` |
| Frontend-Referenz | TSDoc im Hauptrepository | `/referenz/frontend/` |
| API-Vertrag | `backend/openapi.py` | `/referenz/api/openapi.json` und statisch gebündelte Redoc-Ansicht |
| Datenbankvertrag | `db/schema.sql` und Migrationen | `/referenz/datenbank/` |
| Buildidentität | Repository- und Wiki-Commit | `/quellen/` und `/quellen.json` |

Eine erzeugte HTML-, JSON- oder Suchindexdatei ist niemals kanonische Quelle.
Insbesondere werden Wiki-Markdown und generierte Referenzen weder in einen
Pages-Branch noch in `docs/` eingecheckt.

## Task-basierter Buildschnitt

Der Spike implementiert bereits den Orchestrierungsschnitt
`task docs:publication-spike`. Die produktive Ausbaustufe verwendet folgende
unabhängige, cachebare Tasks:

```text
docs:publication
├── docs:publication:stage-wiki       WIKI_ROOT + WIKI_REVISION
├── docs:publication:shell            Hugo Extended + Relearn
├── docs:publication:landing          Inhalte und CTAs aus #127
├── docs:reference:backend            MkDocs + mkdocstrings
├── docs:reference:frontend           TypeDoc aus package-lock.json
├── docs:reference:api                OpenAPI-Export + gelockter Redoc-Bundler
├── docs:reference:database           db/schema.sql + deterministische Ansicht
├── docs:publication:assemble         genau ein statisches Artefakt
└── docs:publication:verify           Links, Quellen, Suche und erwartete Routen
```

Die Tasks erhalten Ein- und Ausgabepfade explizit. Kein Generator schreibt in
die Quelle eines anderen Generators. Der Redoc-Bundler wird erst beim
produktiven Ausbau als gelockte npm-Entwicklungsabhängigkeit aufgenommen; der
Spike exportiert bereits deterministisch `openapi.json` und belegt damit die
Generatorgrenze ohne eine vorgezogene Abhängigkeit.

## Trigger, Konkurrenzschutz und Konsistenz

Der Workflow `Public site` baut und prüft ein einziges Artefakt und trennt
diesen repositoryseitigen Vertrag vom noch nicht aktivierten Deployment:

- `pull_request`: baut und prüft mit dem beim Start aufgelösten Wiki-Commit;
  keine öffentliche Mutation.
- `push` auf `master`: baut aus dem exakten `GITHUB_SHA` und dem beim Start
  aufgelösten Wiki-Commit und legt das geprüfte Artefakt nur im Workflow ab.
- `gollum` bleibt Teil eines späteren Ausbaus. `workflow_dispatch` ist nur auf
  `master` mit explizitem Bestätigungsinput zulässig und bildet das separat
  freizugebende Aktivierungsgate; frei wählbare Quell-Refs sind ausgeschlossen.

Eine repoübergreifende Concurrency-Gruppe verwirft überholte Builds. Vor einem
Deployment wird geprüft, dass die im Artefakt gespeicherten SHAs noch den für
den Trigger erwarteten Ständen entsprechen. Ein einzelnes Deployment ersetzt
die Site atomar; Teilpublikationen einzelner Referenzen sind ausgeschlossen.
`quellen.json` und der sichtbare Bereich `/quellen/` nennen beide SHAs. Jede
Wiki-Seite verlinkt zusätzlich ihre kanonische Wiki-Route.

Der vorbereitete Deployment-Job erhält ausschließlich `pages: write` und
`id-token: write`, hängt vom erfolgreichen Neuaufbau ab und verwendet das
Environment `github-pages`. Er läuft nur über `workflow_dispatch` auf
`master`, wenn `confirm_publication=true` ausdrücklich gesetzt wurde.
`configure-pages` verwendet `enablement: false` und kann Pages daher nicht
selbst aktivieren. Ein Maintainer muss die Pages-Quelle einmalig separat auf
GitHub Actions konfigurieren und den ersten Dispatch ausdrücklich freigeben.
Pull Requests und Pushes auf `master` bauen und prüfen nur; sie veröffentlichen
nicht.

## Lokaler Build

```sh
task docs:publication-spike
task docs:publication-spike:check
task docs:publication
task docs:publication:check
task docs:publication:browser
```

Der erste Task erzeugt unter `build/publication-spike/` die vollständige
Zielstruktur. Der zweite baut zweimal in getrennten temporären Verzeichnissen
und vergleicht alle Dateien bytegenau. Mit `WIKI_ROOT=/path/to/lzug.wiki` kann
anstelle der synthetischen Fixture ein sauberer Wiki-Clone verwendet werden.

Der Build pinnt Hugo Extended 0.165.0 und Relearn-Commit
`8bb66fa674351f3a0b0917a7552caac686eca920`. Er nutzt echte Generatorgrenzen,
aktiviert aber keine Pages-, Netlify- oder Read-the-Docs-Ressource. Der
Produkt- und Demo-Einstieg bindet die Demo-URL beim Build, erklärt den
Scale-to-zero-Kaltstart und verwendet einen begrenzten Health-Warm-up. Der
Browsercheck prüft Desktop und Mobil in hellem und dunklem Farbschema,
Landmarks, Überlauf, blockierende axe-Befunde sowie die erfolgreiche
Health-Weiterleitung.
