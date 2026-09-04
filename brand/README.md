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

```sh
task brand:generate
task brand:check
```

Der Generator und die Brand-Prüfung validieren die Quellen, das Derivat-
Inventar, die Reproduzierbarkeit und die lokal verwendeten Font- und
Icon-Pakete.
