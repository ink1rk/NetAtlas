# Contributing to NetAtlas

Thank you for contributing.

## Principles

1. Prefer less functionality done correctly over incomplete breadth.
2. No mocks in production paths, no TODOs left behind, no secrets in code.
3. Device collectors must remain read-only.
4. Every module needs tests, logging, error handling, and docs.
5. Architecture changes require an ADR under `docs/adr/`.

## Development

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Frontend assets are offline-vendored under `frontend/static/vendor`.

## Commit style

Use concise imperative subjects, e.g. `feat: add LLDP neighbor correlation`.

## Pull requests

- Include tests for new behavior
- Update CHANGELOG.md
- Keep offline-first constraints intact
