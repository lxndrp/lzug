# Taiga-UI-Prototyp fuer Issue #56

## Zweck und Abgrenzung

Der Prototyp ist die visuelle Entscheidungsschranke vor der Gesamtmigration aus
#57 bis #61. Er verwendet ausschliesslich lokale Beispieldaten und veraendert
weder Backend noch API-Vertraege oder bestehende Routen. CoreUI und Taiga UI
laufen auf diesem Branch bewusst parallel.

## Entscheidungspunkt

Stand: 17. Juli 2026. Nach der visuellen Pruefung wurde ein Go fuer eine
inkrementelle Migration erteilt. Die Entscheidung bezieht sich auf die
technische und gestalterische Richtung, nicht auf einen ungesteuerten
Big-Bang-Umbau: Backend, API-Vertraege, Routen und fachliche Ablaeufe bleiben
unveraendert.

Die Migration startet deshalb mit #57 (Anwendungsrahmen und Designsystem). Die
Stories #58 bis #60 folgen in fachlich getrennten Schritten; #61 wird erst nach
der vollstaendigen visuellen und technischen Abschlusspruefung umgesetzt.

## Start und visueller Pruefpunkt

```sh
cd frontend
npm install
npm start
```

Danach `http://127.0.0.1:4200` oeffnen und in der Seitenleiste
`Taiga-Prototyp` waehlen. Das Backend ist fuer die Beispieldaten des Prototyps
nicht erforderlich; eine fehlende Backend-Verbindung kann im bestehenden
App-Header erscheinen.

Folgende Zustaende gezielt beurteilen:

1. Desktop bei etwa 1440 px: Grundanmutung, Informationsdichte, vertikaler
   Stepper, Formular und dreispaltige Planungsdarstellung.
2. Prototyp-Navigation `Prueflinge`: Taiga-Tabelle, Statusdarstellung und
   Zeilenaktionen.
3. `Taiga-Dialog oeffnen`: Dialoggroesse, Fokus und Lesbarkeit.
4. Formular leeren und `Formular pruefen`: Pflichtfeld- und Fehlerzustaende.
5. Passwort eingeben und Sichtbarkeitssymbol pruefen.
6. Mobile bei 390 px sowie schmal bei 320 px: horizontale Prototyp-Navigation,
   einspaltiges Formular und horizontal durchblaetterbare Planungstage.
7. Datum- und Wocheneingabe insbesondere in Safari pruefen, weil native
   `date`-/`week`-Picker je Browser und Betriebssystem unterschiedlich wirken.

## Enthaltener repraesentativer Ausschnitt

- Desktop- und mobile App-Navigation mit aktivem Zustand
- Taiga-Textfelder mit Pflichtfeldern, Validierung und Erfolgsmeldung
- native ISO-Wochenauswahl innerhalb eines Taiga-Textfelds
- Taiga-Datumseingabe mit mobilem nativen Picker
- Taiga-Dialog ohne Seiteneffekt
- Taiga-Tabelle mit Status und Aktionen
- responsive Planungsdarstellung mit drei Tagen, Terminen und Konfliktstatus
- Taiga-Stepper und Taiga-Passwortanzeige als Komponentenprobe

## Komponentenbewertung

### Stepper

Der Taiga-Stepper bildet einen kuenftigen mehrstufigen Planungsablauf klar ab,
unterstuetzt horizontale und vertikale Darstellung und liefert verstaendliche
aktive sowie abgeschlossene Zustaende. Fuer die aktuelle Anwendung sollte er
erst eingesetzt werden, wenn die fachlichen Statusuebergaenge und die
Rueckwaertsnavigation einer eigenen Story geklaert sind. Im Prototyp ist er
daher bewusst nur eine Vorschau.

### Passworteingabe

Das Passwortfeld integriert sich ohne Sonderlayout in das Formular und bringt
eine standardisierte Sichtbarkeitsaktion mit. Es ist fuer einen kuenftigen
Login grundsaetzlich geeignet. Vor einem produktiven Einsatz sind noch
Passwortmanager, Autocomplete-Verhalten, Fehlermeldungen und der konkrete
Authentifizierungsablauf zu testen.

### Datum und Kalenderwoche

Taiga UI deckt Datumseingaben samt mobiler Strategie ab. Eine eigene
Kalenderwochen-Komponente ist im verwendeten Satz nicht erforderlich; der
vorhandene fachliche ISO-Wert `YYYY-Www` bleibt ueber `input[type=week]`
unveraendert. Dieser hybride Ansatz verhindert eine Aenderung am API-Vertrag,
muss aber visuell in Safari bewertet werden.

## Technische Eignung und Verifikation

Stand: 17. Juli 2026.

| Pruefung          | Ergebnis                                                                                                                                                                         |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Version           | Taiga UI 5.15.0 fuer Core, Kit, i18n, Table und Icons installiert                                                                                                                |
| Angular 22        | Paket-Peers verlangen Angular >=19; `ngc` kompiliert App und Templates mit Angular 22.0.6 fehlerfrei                                                                             |
| TypeScript        | `npx tsc --noEmit -p tsconfig.app.json` erfolgreich                                                                                                                              |
| Angular-Templates | `npx ngc -p tsconfig.app.json --noEmit` erfolgreich                                                                                                                              |
| ESLint            | `npm run lint` erfolgreich                                                                                                                                                       |
| Unit-Tests        | Prototyp- und App-Tests ergaenzt; Karma-Bundle in Codex durch bekannten esbuild-Deadlock blockiert                                                                               |
| Produktion-Build  | In Codex vor Ausgabe der Bundle-Dateien durch denselben esbuild-Deadlock mit Exit 134 blockiert                                                                                  |
| Bundle-Groesse    | Neue Produktionsgroesse deshalb in Codex nicht belastbar messbar; letzter vorhandener Vor-Prototyp-Artefaktstand: 882.900 Byte JS+CSS, nicht als Vergleichsergebnis verwenden    |
| Accessibility     | Semantische Desktop-Pruefung erfolgreich; Axe-Test fuer den Prototyp ergaenzt, Ausfuehrung zusammen mit Browser-Bundle in Codex blockiert                                        |
| Desktop-Smoke     | In-App-Chromium: Navigation, vier Taiga-Textfelder, drei Planungstage, Tabelle mit drei Zeilen und Dialog interaktiv bestaetigt                                                  |
| Mobile-Smoke      | 390 px ohne dokumentweiten horizontalen Ueberlauf bestaetigt; abschliessender erneuter Live-Smoke nach Root-Kapselung durch gesperrte localhost-Browserverbindung nicht moeglich |
| Edge              | In dieser Umgebung nicht installiert/verfuegbar; manueller Smoke offen                                                                                                           |
| Safari/WebKit     | In dieser Umgebung nicht automatisierbar; manueller Smoke offen, besonders fuer `input[type=week]`                                                                               |

## Migrationsfolge nach dem Go

1. **#57 App-Shell und Designsystem:** Taiga-Root, Navigation, globale
   Rueckmeldungen, Tokens und Fokusfuehrung als belastbare Grundlage umsetzen.
2. **#58 Dashboard und Stammdaten:** Dashboard, Prueflinge und Pruefungsorte
   migrieren; API-Services und Routen unveraendert weiterverwenden.
3. **#59 Ausschussverwaltung:** Listen, Rollen-/Statusdarstellung und
   Bearbeitungsaktionen migrieren.
4. **#60 Planung:** Planungsparameter, Verfuegbarkeitsmatrix und komplexe
   responsive Planung migrieren; diese Story bekommt die strengste
   Accessibility- und Browserpruefung.
5. **#61 Abschluss:** CoreUI-Abhaengigkeiten und temporaere Adapter entfernen,
   Bundle, Browser, Accessibility und `mise run quality` abschliessend pruefen.

Jede Stufe wird separat verifiziert und reviewbar abgeschlossen. Ein Rueckfall
auf CoreUI bleibt bis zum Abschluss von #61 moeglich; produktive Backend- oder
API-Aenderungen sind kein Bestandteil dieser Migration.

Die verbindliche lokale Gesamtpruefung bleibt:

```sh
mise run quality
```

Fuer die Bundle-Bewertung muss `npm run build:ci` ausserhalb der Codex-Sandbox
erfolgreich laufen. Die Angular-Ausgabe ist gegen die vorhandenen Budgets von
700 kB Warnung und 1 MB Fehler zu dokumentieren. Fuer die Browser-Smokes:

```sh
cd frontend
npm run test:e2e
```

Edge und Safari sollen anschliessend manuell mit denselben Pruefpunkten aus dem
Abschnitt oben betrachtet werden. Erst danach ist die Go-/No-Go-Entscheidung
fuer #57 bis #61 zu dokumentieren.

## Quellen und Kompatibilitaetsannahmen

- [Taiga UI Getting started](https://taiga-ui.dev/getting-started/)
- [Taiga UI InputDate](https://taiga-ui.dev/components/input-date/)
- [Taiga UI Stepper](https://taiga-ui.dev/navigation/stepper/)
- [Taiga UI Table](https://taiga-ui.dev/components/table/)
- [Taiga UI Form und Passworteingabe](https://taiga-ui.dev/layout/form/)

Taiga UI 5 verlangt laut offizieller Migrationsdokumentation Angular 19 oder
neuer. Die installierten 5.15.0-Pakete deklarieren ebenfalls Angular >=19 als
Peer-Abhaengigkeit. Das ist eine formale Kompatibilitaetsaussage; die
projektspezifische Eignung bleibt Gegenstand dieses Prototyps und der
anschliessenden Nutzerentscheidung.
