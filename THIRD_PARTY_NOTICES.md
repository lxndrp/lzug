# Third-party notices

This file covers third-party material used by the source repository, the
installed locked Python environment, and the production frontend. Exact npm
versions and license expressions come from `frontend/package-lock.json`.
Python versions come from `uv.lock`; expressions are read from the installed,
locked distribution metadata. After `task setup`, run
`task sbom OUTPUT=/tmp/lzug.dependencies.sbom.cdx.json` for the standardized
CycloneDX snapshot. The upstream license texts remain authoritative.

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
duplicated here because they change with the lockfile. The canonical dependency
SBOM records their deduplicated name/version components and license metadata;
the release process attaches that standard artifact and must preserve the
package-provided license files in any distributable bundle.

## Python dependencies

Python runtime, development, and documentation dependencies are version-locked
in `uv.lock`. Syft catalogs the installed locked distributions and preserves
their PEP 639 or legacy license metadata without project-specific SPDX
inference. Missing, generic, or ambiguous metadata remains visible for manual
review. This standard artifact is release-review evidence, not legal advice or
a promise of license compatibility.

## Documentation content

Original lzug documentation prose, diagrams, and other non-code content are
licensed separately under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), as defined in
[`docs/LICENSE.md`](docs/LICENSE.md). Source code, executable examples, and
generated code references remain under the project software license.
Third-party material, including CoreUI icon artwork, remains under its own
license and is not relicensed by this documentation grant.

## Project license boundary

The lzug project code is licensed under
[`AGPL-3.0-or-later`](LICENSE). This notice does not relicence third-party
material under AGPL; each dependency remains under its own license. The
confirmed decision and future dual-licensing boundary are recorded in
[`docs/developers/licensing.md`](docs/developers/licensing.md).
