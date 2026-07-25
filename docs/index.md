# lzug developer documentation

This versioned documentation build combines the existing technical Markdown
documents with code reference generated from the current source tree.

- [Code-documentation policy](development/code-documentation.md) defines the
  incremental documentation standard.
- [Python backend reference](reference/backend.md) is generated from Google-style
  docstrings by `mkdocstrings`.
- [TypeScript frontend reference](reference/frontend.md) explains the generated
  TypeDoc output and its toolchain decision.
- [Architecture](ARCHITECTURE.md), [data model](datenmodell.md), and
  [relational schema](relationales-schema.md) remain the German conceptual
  sources of truth.

The REST contract is maintained separately as [OpenAPI JSON](/api/openapi.json)
and its local [Swagger UI](/api/docs). Start the backend with the command in the
repository README before following those two links.

Build everything locally with:

```sh
mise run docs
```

The generated site is local build output only. It is uploaded as a private
GitHub Actions artifact; no public hosting is configured.
