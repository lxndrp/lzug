# Code-documentation policy

## Scope and language

Code documentation is written in English. Existing German product, domain, and
architecture documents remain German. This policy applies incrementally: it
documents representative, public, and changed code without requiring a
retroactive comment sweep of the whole repository.

## Python

Use Google-style docstrings for public modules, services, repositories,
domain-relevant classes, and non-obvious functions. Describe business
invariants, observable side effects, error conditions, and transaction
boundaries where they affect callers. Do not add boilerplate docstrings to
trivial private helpers or repeat annotations that already make the contract
clear.

`PlanningService`, `CandidateDayService`, `ResourceRepository`, `Store`,
`session_scope`, `HolidayProvider`, and the HTTP handler demonstrate the
expected level of detail. The generated Python reference is part of this site.

## TypeScript and Angular

Use TSDoc comments (`/** ... */`) for exported services, models, and
domain-relevant components or methods. Explain semantics, allowed state
transitions, ownership, and side effects. Do not translate TypeScript type
information into prose or duplicate the OpenAPI contract.

`PlanningApiService`, `RoundContextService`, the API models, and the planning
component's optimistic availability flow are the reference examples. TypeDoc
generates their browser reference during `mise run docs`.

## Keeping the boundary clear

- Stable product and domain information belongs in `README.md` and the German
  domain documentation. Changing scope, priorities, and delivery planning
  belong in the GitHub Project and its issues.
- Technical decisions belong in `ARCHITECTURE.md` and future ADRs.
- HTTP paths, payloads, and responses are canonical in OpenAPI and Swagger UI.
- Comments explain why code has a particular responsibility or state boundary;
  they do not duplicate those other sources.

Changes to public interfaces should add or update documentation when their
meaning is non-obvious. No lint rule currently blocks unrelated legacy code
solely for missing documentation.
