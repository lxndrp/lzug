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

## Go CLI dependencies

The operator CLI uses `golang.org/x/term` and its transitive
`golang.org/x/sys` module to read terminal secrets without echo on Linux,
macOS, and Windows. Both modules are distributed under the BSD 3-Clause
License and carry the following notice:

Copyright 2009 The Go Authors.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
* Neither the name of Google LLC nor the names of its contributors may be used
  to endorse or promote products derived from this software without specific
  prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

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
project license is authoritative for the project's own code.
