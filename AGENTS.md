# OSCAR Knowledge repository instructions

## Git workflow

- Work directly on `main` during active development, as requested by the user.
- Keep the existing history and user changes. Do not create or use a separate
  `develop` workflow unless the user requests it.
- Commit completed, verified changes locally. Push only when the user requests it.

## Data and verification

- Preserve existing databases, vectors, document IDs, revisions and provenance.
- Keep credentials, downloaded course material, private content, backups and model
  weights out of Git. Curated shared sources require explicit approval.
- Follow README.md and the current readiness report for local operation. Run
  relevant tests against isolated test databases and report actual results.
