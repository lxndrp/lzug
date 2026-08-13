# Licensing and release readiness

This page records the licensing evidence and the confirmed decision for the
public-source release. It is not a substitute for `LICENSE` and does not
relicense third-party material.

## Current state

The project owner confirmed `AGPL-3.0-or-later` and confirmed that the project
currently has one contributor with the authority to grant that license for the
project's own contributions. `LICENSE`, README, PEP 639 Python metadata, npm
metadata, and the project-specific copyright notice now agree. The npm package
remains marked private for now; its lockfile contains license metadata. The
Python lockfile records package versions while the installed distributions
provide the license metadata.

After `task setup`, the reproducible baseline command is:

```sh
task sbom OUTPUT=/tmp/lzug.dependencies.sbom.cdx.json
```

The task uses the repository-pinned Syft version and emits CycloneDX 1.6. It
catalogs installed Python distribution metadata from the locked `.venv`, the
complete production and development graph from `frontend/package-lock.json`,
and third-party Go modules declared by `go.mod`. The accompanying validator
checks the standard structure, generator version, expected ecosystems, npm
license metadata, and the current Go boundary. The SBOM contains package
metadata and package-manager locations, but no source contents, secrets,
environment variables, or personal data.

## Evidence from the current manifests

The production npm dependency set contains Angular packages marked MIT,
Taiga UI packages marked Apache-2.0, RxJS marked Apache-2.0, Source Sans 3
marked OFL-1.1, `tslib` marked 0BSD, and `zone.js` marked MIT. The complete
lockfile also contains development-only tooling under additional SPDX
expressions. The generated dependency SBOM is the source of the exact version
snapshot; this page intentionally does not duplicate a mutable package list.

Syft records Python `License-Expression` and legacy `License` metadata without
project-specific normalization. Missing, generic, or ambiguous values remain
visible in the CycloneDX components instead of being turned into inferred SPDX
expressions. That limitation is deliberate: the SBOM makes package metadata
reviewable, but does not determine legal compatibility.

For the locked `v0.1.0` review state, Syft deduplicates 708 npm lockfile paths
to 668 third-party name/version components plus the frontend root component;
all 669 carry license metadata. The checked environment contributes the lzug
distribution and 62 installed third-party Python distributions. Platform-
conditional packages that are locked but not installed are not presented as
runtime components; `uv.lock` remains the authority for that cross-platform
resolution boundary.

The standard metadata leaves the following Python review points visible:

- `Jinja2` 3.1.6, `markdown-it-py` 4.2.0, `pathspec` 1.1.1 and `pip-audit`
  2.10.1 do not produce a CycloneDX license value from their installed
  metadata in the pinned Syft version.
- `python-dateutil` 2.9.0.post0 declares `Dual License` and lists Apache plus a
  generic BSD classifier. The CycloneDX value preserves `Dual License`; it does
  not identify the BSD variant.

These are explicit metadata limitations, not assertions that a package is
incompatible or legally cleared. Packaged and upstream license texts remain
authoritative. A changed lockfile or distribution metadata requires a fresh
SBOM and human review.

The local CoreUI-derived SVG path definitions are a separate notice item. The
upstream CoreUI Icons Free license distinguishes SVG/JS icons (CC BY 4.0) from
non-icon code (MIT). The local comment and notice must therefore not describe
the copied icon definitions as MIT.

## Compatibility assessment (not legal advice)

The Free Software Foundation's compatibility guidance distinguishes combining
works from merely installing separate programs. AGPLv3 has the GPLv3
compatibility model for Apache-2.0 material and explicitly permits combining
with GPLv3 code; its additional section 13 network obligation applies to the
combined program. The exact obligations still depend on the way components are
combined and on preserving every third-party notice.

| Candidate for lzug  | Strategic effect                                                                | Compatibility implication for the current frontend                                                                      |
| ------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `GPL-2.0-only`      | Strong copyleft with no later-version option                                    | Does not provide a safe GPL route for a combined work containing the Apache-2.0 Taiga UI and RxJS code.                 |
| `GPL-2.0-or-later`  | Preserves GPLv2 as the default while allowing a GPLv3 distribution where needed | Technically compatible through the later-version path, but does not impose the AGPL network obligation.                 |
| `GPL-3.0-or-later`  | Strong copyleft and direct Apache-2.0 compatibility                             | No special source offer for users who only interact with a modified server remotely.                                    |
| `AGPL-3.0-or-later` | GPLv3-compatible copyleft plus a source offer for remote network users          | **Confirmed for lzug** because publicly operated modified versions should remain source-available to interacting users. |
| `Apache-2.0`        | Permissive reuse and direct compatibility with the frontend dependencies        | Would give up the current reciprocal-copyleft and network-source objectives.                                            |

### Confirmed decision

The project owner selected `AGPL-3.0-or-later`. The reason is the explicit
desire to keep source available for modified lzug versions operated as network
services, while retaining the GPLv3 compatibility path for Apache-2.0 frontend
components. This documents the project decision, not legal advice or a
determination about third-party licensing.

## Future dual licensing

The project owner may later offer the project's own code under an additional
commercial or other license. That is a separate license grant, not a removal of
the AGPL grant already made to existing recipients. It requires authority over
all project code being relicensed and cannot change the licenses of third-party
components listed in `THIRD_PARTY_NOTICES.md`.

If additional contributors are accepted, a future dual-license offer requires
an explicit rights grant or assignment that covers that option. The maintainer
must choose and document a contribution agreement before accepting outside
contributions; contributor count or commit authorship alone is not sufficient
evidence of commercial relicensing authority.

The current confirmation and rights statement were recorded in Issue #131 on
2026-07-29. This remains a project assertion and should be reviewed by legal
counsel before a commercial offer is marketed or signed.

## Inventory and SBOM responsibilities

- Dependency SBOM: `lzug.dependencies.sbom.cdx.json` is the canonical
  release- and license-review inventory. Python versions originate in
  `uv.lock` and license values in the installed locked distributions. npm
  versions, scopes and license values originate in
  `frontend/package-lock.json`. `go.mod` currently declares no third-party Go
  modules. Adding a Go module makes its absence from this SBOM a failing
  contract.
- Image SBOM: `lzug.image.sbom.cdx.json` describes only packages present in the
  exact final OCI image. It intentionally excludes npm build dependencies and
  the separate Go CLI. During a release it is a temporary input bound to the
  image digest with a signed SBOM attestation, not a separate release asset.
- Native CLI SBOM: `task sbom:cli ARTIFACT=<binary> OUTPUT=<sbom>` scans one
  already built binary and requires the Go main module, standard library and
  every third-party module declared in `go.mod`. Issue #273 owns the six
  platform builds, release-asset naming and artifact attestations. During a
  release the detailed CLI SBOMs are temporary inputs to the single aggregate
  release SBOM and are not published individually. This issue provides only
  their common Syft/CycloneDX boundary and does not build or publish a CLI
  binary.
- Documentation: original prose, diagrams, and other non-code content follow
  the explicit [`CC-BY-4.0` boundary](../LICENSE.md). Code, executable examples,
  generated code references, and third-party content are excluded from that
  grant and retain their respective licenses.
- Release: Der [Release-Prozess](releases.md) erzeugt die detaillierten
  rollenbezogenen CycloneDX-Daten mit derselben gepinnten Syft-Version, führt
  sie in genau einer sichtbaren Release-SBOM zusammen und bindet sie an die
  ausgelieferten Subjects. Die detaillierten Dateien bleiben temporär.

The dependency SBOM is preparatory review evidence. The aggregate public
release SBOM, release assets, and digest-bound attestations exist only after a
fully successful tagged release workflow.

## Primary sources

- [GNU GPL license compatibility and relicensing](https://www.gnu.org/licenses/license-compatibility.en.html)
- [GNU GPL FAQ: compatibility](https://www.gnu.org/licenses/gpl-faq.en.html)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [Angular license](https://angular.dev/license)
- [Taiga UI package metadata](https://github.com/taiga-family/taiga-ui/blob/main/package.json)
- [RxJS license](https://github.com/ReactiveX/rxjs/blob/7.8.2/LICENSE.txt)
- [CoreUI Icons Free licensing](https://github.com/coreui/coreui-icons#license)
- [Source Sans 3 upstream](https://github.com/adobe-fonts/source-sans)
- [SIL Open Font License 1.1](https://scripts.sil.org/OFL)
- [PEP 639 license metadata](https://peps.python.org/pep-0639/)
- [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
