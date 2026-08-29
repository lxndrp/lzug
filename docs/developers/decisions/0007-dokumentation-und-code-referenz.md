# ADR-0007: MkDocs und Code-Referenzen

## Status

Akzeptiert.

## Kontext und Entscheidung

Versionierte Markdown-Dokumentation wird mit MkDocs und `mkdocstrings` für Python gebaut. Exportierte TypeScript-Schnittstellen erhalten TSDoc; TypeDoc erzeugt daraus die Frontend-Referenz. Compodoc wurde nicht gewählt, weil seine eingebettete TypeScript-Version vom gelockten Projektcompiler abwich.

[ADR-0023](0023-oeffentliche-web-und-dokumentationspublikation.md) trifft die
ergänzende Entscheidung für die öffentliche Publikationsarchitektur. MkDocs,
mkdocstrings und TypeDoc bleiben davon unabhängige Referenzgeneratoren.

## Konsequenzen

`task docs` baut MkDocs zuerst und erzeugt anschließend TypeDoc unter `site/developers/reference/frontend/`. Der Build wird nicht eingecheckt und nicht öffentlich gehostet; CI veröffentlicht `site/` als geschütztes Artefakt `lzug-documentation`. Konvention und Toolentscheidung stehen unter [Dokumentation](../documentation.md).
