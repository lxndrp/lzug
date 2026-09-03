# Third-party notices

This file covers third-party material used by the source repository, the
installed locked Python environment, and the production frontend. Exact npm
versions and license expressions come from `frontend/package-lock.json`.
Python versions come from `uv.lock`; expressions are read from the installed,
locked distribution metadata. After `task setup`, run
`task sbom OUTPUT=/tmp/lzug.dependencies.sbom.cdx.json` for the standardized
CycloneDX snapshot. The upstream license texts remain authoritative.

## Inter

The production frontend and public publication use Inter v20 through the
exactly locked `@fontsource-variable/inter` 5.3.0 package.

- License: [SIL Open Font License 1.1](https://openfontlicense.org/).
- Upstream family and authorship metadata: [Inter](https://github.com/rsms/inter).
- Package metadata: [`@fontsource-variable/inter`](https://www.npmjs.com/package/@fontsource-variable/inter).

The locally retained license text is [`brand/licenses/Inter-OFL.txt`](brand/licenses/Inter-OFL.txt).
The production bundles contain only the required Latin, Greek, and Greek Extended WOFF2 subsets.

## Lucide

The product's functional icons use the exactly locked `lucide` 0.468.0 package.
The stable semantic mapping is documented in [`brand/icon-contract.json`](brand/icon-contract.json).

- License: [ISC](https://github.com/lucide-icons/lucide/blob/main/LICENSE).
- Upstream: [Lucide](https://lucide.dev/).

## resvg-js

`@resvg/resvg-js` 2.6.2 renders reproducible SVG-derived raster assets during development and CI.

- License: [MPL-2.0](https://www.mozilla.org/MPL/2.0/).
- Upstream: [resvg-js](https://github.com/thx/resvg-js).

## Production JavaScript dependencies

These are direct runtime dependencies from the lockfile. Their package
licenses must remain separately acknowledged when a bundled frontend is
distributed.

| Package family               | Locked license |
| ---------------------------- | -------------- |
| Angular (`@angular/*`)       | MIT            |
| Taiga UI (`@taiga-ui/*`)     | Apache-2.0     |
| `rxjs`                       | Apache-2.0     |
| `tslib`                      | 0BSD           |
| `zone.js`                    | MIT            |
| `@fontsource-variable/inter` | OFL-1.1        |
| `lucide`                     | ISC            |

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

- Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.
- Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
- Neither the name of Google LLC nor the names of its contributors may be used
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
Third-party material remains under its own license and is not relicensed by
this documentation grant.

## Project license boundary

The lzug project code is licensed under
[`AGPL-3.0-or-later`](LICENSE). This notice does not relicence third-party
material under AGPL; each dependency remains under its own license. The
project license is authoritative for the project's own code.
