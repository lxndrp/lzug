# lzug Corporate Design

`brand/` enthält den kleinen gemeinsamen Markenvertrag für Produkt und
öffentliche Publikation.

## Quellen

- `source/logo-mark.svg` ist die kanonische Bildmarke.
- `source/key-visual.svg` ist das kanonische Key Visual.
- `tokens.css` enthält die toolkit-neutralen semantischen Design-Tokens.
- `licenses/Inter-OFL.txt` enthält die lokal mitgelieferte Fontlizenz.
- `asset-contract.json` beschreibt Quellen, Varianten und aktuell ausgelieferte
  Derivate.

Die SVG-Quellen sind eigenständige Vektorgestaltungen.
Sie enthalten zugängliche Titel und Beschreibungen sowie keine externen
Referenzen.

## Ausgelieferte Derivate

`node brand/generate-assets.mjs` erzeugt ausschließlich die im
Assetvertrag aufgeführten Dateien unter `brand/derived/`.

Das Frontend übernimmt explizit `favicon.svg`, `favicon.ico` und
`logo-mark-dark.svg`.
Die Publikation übernimmt explizit `favicon.svg`, beide Key Visuals und beide
hellen beziehungsweise dunklen horizontalen Wort-/Bildmarken.

Nicht verwendete Raster-, Monochrom-, Kompakt- und Social-Preview-Varianten
gehören nicht zum aktuellen Vertrag.

## Integration

Das Frontend verwendet die Tokens und seinen Taiga-Adapter aus
`frontend/src/`.
Die Publikation verwendet dieselben Tokens sowie die für ihre Seiten
notwendigen Brand-Derivate.
Fonts, Icons und Logos werden lokal ausgeliefert.

## Gemeinsame visuelle Grammatik

Produkt und Portal teilen eine kleine Grammatik, ohne ein gemeinsames
Komponentenframework zu benötigen:

| Rolle | Gemeinsame Regel |
| --- | --- |
| Typografie | Inter Variable, `1rem` Grundschrift, `1.5` Zeilenhöhe, abgestufte Überschriften und semantische Nebeninformation |
| Seitengitter | Inhaltsbreite bis `--lzug-role-content-max`, lesbare Textbreite bis `--lzug-role-reading-max`, `--lzug-role-page-gap` als größere Rasterlücke |
| Aktion | Primäre Aktion mit `--lzug-role-action-primary`, Hover/Pressed-Rollen und mindestens `--lzug-role-control-min` Höhe; sekundäre Aktionen bleiben konturiert |
| Karte | `--lzug-role-card-surface`, `--lzug-role-border`, `--lzug-role-card-radius` und der dezente gemeinsame Schatten |
| Hinweis | Statusfarbe und weiche Statusfläche aus den bestehenden Status-Tokens, mit sichtbarer Seitenkante und verständlichem Text |
| Fokus | `--lzug-role-focus` als sichtbarer Ring mit `--lzug-focus-width` und `--lzug-focus-offset` |
| Kopfbereich und Marke | Dunkle Markenfläche mit weißer Wort-/Bildmarke; Portalnavigation und Anwendungsshell dürfen funktional verschieden bleiben |

`frontend/src/styles.scss` und
`docs/publication/relearn/assets/css/custom.css` sind die jeweiligen Adapter.
Sie verwenden diese Rollen und dürfen nur Taiga- beziehungsweise Relearn-
Variablen ergänzen.
Navigation, Seitenaufbau und fachliche Komponenten bleiben wegen ihres
unterschiedlichen Nutzungskontexts bewusst eigenständig.

```sh
task brand:generate
task brand:check
```

Der Generator und die Brand-Prüfung validieren die Quellen, das Derivat-
Inventar, die Reproduzierbarkeit und die lokal verwendeten Font- und
Icon-Pakete.
