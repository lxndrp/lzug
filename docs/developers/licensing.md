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

The reproducible baseline command is:

```sh
python3 scripts/inventory_licenses.py > /tmp/lzug-license-inventory.json
```

The command first requires `uv sync --locked --extra dev --check` to confirm
the existing environment without changing it. The report compares installed
Python versions with `uv.lock`, records every npm lockfile package, and keeps
ambiguous or unknown metadata as individual review entries. It contains only
lockfile hashes, package metadata, and aggregate source/documentation
statistics. It does not include source contents, secrets, environment
variables, or personal data.

## Evidence from the current manifests

The production npm dependency set contains Angular packages marked MIT,
Taiga UI packages marked Apache-2.0, RxJS marked Apache-2.0, Source Sans 3
marked OFL-1.1, `tslib` marked 0BSD, and `zone.js` marked MIT. The complete
lockfile also contains development-only tooling under additional SPDX
expressions. The report is the source of the exact version and count snapshot;
this page intentionally does not duplicate a mutable package list.

Python distributions declaring PEP 639 `License-Expression` are recorded
without inference. Unambiguous legacy `License` values and exact classifiers
are normalized with their source retained. Generic BSD and dual-license
metadata remain manual review entries instead of being presented as resolved.
An absent usable declaration remains `unknown`. These categories make the
metadata review reproducible; they do not determine legal compatibility.

For the locked `v0.1.0` review state, the inventory records all 708 npm package
entries with 0 unknown licenses. The checked Python environment contains 62
third-party distributions: 34 provide `License-Expression`, 26 have one
unambiguous normalized legacy result, 2 require manual review, and 0 are
unknown. `colorama` 0.4.6 is present in the cross-platform lock but is not
installed on this platform; the report keeps it visible under
`locked_but_not_installed` instead of inventing installed metadata.

The two manual Python entries are individually classified:

- `Jinja2` 3.1.6 declares only the generic classifier `BSD License`; the
  installed metadata does not identify a specific BSD variant. Its packaged
  and upstream license text remains authoritative, so the inventory does not
  synthesize an SPDX expression.
- `python-dateutil` 2.9.0.post0 declares `Dual License` and lists Apache plus a
  generic BSD classifier. `Apache-2.0` is identifiable, but the BSD variant is
  not specified by that metadata. The inventory therefore preserves both
  candidates and requires a human review of the packaged/upstream texts.

This is an explicit metadata limitation, not an assertion that either package
is incompatible or legally cleared. A changed lockfile or distribution
metadata requires a fresh report and review.

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

- Python: `uv.lock` is the version input. License expressions must be resolved
  from the installed locked distributions and reviewed before release.
- npm: `frontend/package-lock.json` is the version and license input. Production
  and development scopes must remain distinguishable.
- Documentation: original prose, diagrams, and other non-code content follow
  the explicit [`CC-BY-4.0` boundary](../LICENSE.md). Code, executable examples,
  generated code references, and third-party content are excluded from that
  grant and retain their respective licenses.
- OCI: Noch wurde kein öffentlicher Produkt-Release ausgelöst. Der
  [Release-Prozess](releases.md) erzeugt und archiviert die CycloneDX-JSON-SBOM
  aus dem exakt geprüften Image und bindet sie mit einer signierten
  Attestation an dessen Digest.

The report script is intentionally preparatory. A public-release SBOM exists
only after a fully successful tagged release workflow.

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
