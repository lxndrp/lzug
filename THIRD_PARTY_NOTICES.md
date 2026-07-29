# Third-party notices

This file covers third-party material used by the source repository and the
production frontend. Exact versions and license expressions are derived from
`frontend/package-lock.json`; run `python3 scripts/inventory_licenses.py` for a
reproducible snapshot. The upstream license texts remain authoritative.

## CoreUI Icons Free

The selected SVG path definitions in
[`frontend/src/app/app-icons.ts`](frontend/src/app/app-icons.ts) are derived
from CoreUI Icons Free 3.1.0.

- Icon artwork packaged as SVG or JavaScript: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Non-icon CoreUI code: [MIT](https://opensource.org/license/mit/).
- Attribution: CoreUI Icons Free, creativeLabs Łukasz Holeczek.
- Upstream license and scope: [CoreUI Icons Free licensing](https://github.com/coreui/coreui-icons#license).

The copied material here is icon artwork, so it is recorded as CC BY 4.0;
the MIT terms for non-icon code do not change that classification.

## Source Sans 3

The frontend imports Source Sans 3 5.2.9 through
`@fontsource/source-sans-3`.

- License: [SIL Open Font License 1.1](https://scripts.sil.org/OFL).
- Upstream family and authorship metadata:
  [Adobe Source Sans](https://github.com/adobe-fonts/source-sans).
- Package metadata: [`@fontsource/source-sans-3`](https://www.npmjs.com/package/@fontsource/source-sans-3).

The package's `OFL.txt` and upstream authorship file are authoritative for
font-specific copyright and reserved-name terms.

## Production JavaScript dependencies

These are direct runtime dependencies from the lockfile. Their package
licenses must remain separately acknowledged when a bundled frontend is
distributed.

| Package family | Locked license |
| --- | --- |
| Angular (`@angular/*`) | MIT |
| Taiga UI (`@taiga-ui/*`) | Apache-2.0 |
| `rxjs` | Apache-2.0 |
| `tslib` | 0BSD |
| `zone.js` | MIT |
| `@fontsource/source-sans-3` | OFL-1.1 |

The transitive production closure and all development packages are not
duplicated here because they change with the lockfile. The inventory report
records every lockfile package, version, license expression, and unknown entry;
the release process must attach the report and preserve the package-provided
license files in any distributable bundle.

## Python and documentation dependencies

Python and documentation dependencies are version-locked in `uv.lock`, but
that file does not carry license expressions. Their installed distribution
metadata must be resolved and reviewed before a public release. Documentation
content is not automatically covered by the software license; its copyright
and reuse terms must be decided together with the project copyright notice.

## Project license boundary

The lzug project code is licensed under
[`AGPL-3.0-or-later`](LICENSE). This notice does not relicence third-party
material under AGPL; each dependency remains under its own license. The
confirmed decision and future dual-licensing boundary are recorded in
[`docs/developers/licensing.md`](docs/developers/licensing.md).
