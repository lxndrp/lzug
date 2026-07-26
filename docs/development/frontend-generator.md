# Frontend generator decision

The frontend reference uses TypeDoc. The decision was made by executing both
candidates against the locked project toolchain on 25 July 2026:

| Tool | Result | Decision |
| --- | --- | --- |
| TypeDoc 0.28.20 | Generated HTML from the Angular source with Node.js 26.5.0 and the project's TypeScript 6.0.3. | Adopted as a development dependency. |
| Compodoc 2.0.0 | Parsed the application, but bundled TypeScript 6.0.2 while the project locks 6.0.3. | Rejected to avoid a parallel compiler runtime. |

TypeDoc is run by `mise run docs` after MkDocs has built the shared Markdown and
Python reference. Its output is placed under
`site/developers/reference/frontend/`; the
<a href="../developers/reference/frontend/index.html">Generated TypeScript reference</a>
is therefore available in the local site and CI artifact.

The generated material is not committed and is not deployed. Its only initial
distribution is the access-controlled GitHub Actions artifact. Selecting a
hosting platform, visibility, and access protection remains a separate
decision.
