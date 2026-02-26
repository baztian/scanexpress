# Releasing ScanExpress

## Versioning

Use semantic version tags in Git:

- `vMAJOR.MINOR.PATCH` (for example: `v0.2.1`)

Tag meanings:

- `PATCH`: bug fixes and small, backward-compatible improvements
- `MINOR`: new, backward-compatible features
- `MAJOR`: breaking changes

## Release Checklist

1. Ensure `main` is up to date and clean.
2. Run tests:
    source .venv/bin/activate && python -m unittest
    npm run test:e2e
3. Add/update release notes in [the changelog](../CHANGELOG.md) for the release version.
4. Create an annotated tag:
    git tag -a vX.Y.Z -m "Release vX.Y.Z"
5. Push commit and tags:
    git push origin main --follow-tags
6. Create a GitHub Release from tag `vX.Y.Z` with focused notes for that version only.

## Hotfix

For urgent fixes, merge the fix to `main` and publish the next patch tag (`vX.Y.Z+1` in patch position, e.g. `v0.2.1` -> `v0.2.2`).

## Quick Commands

    VERSION=0.0.1
    TAG="v${VERSION}"
    NOTES_FILE="/tmp/scanexpress-${TAG}-notes.md"
    awk -v v="${VERSION}" 'BEGIN{flag=0} $0 ~ "^## \\[" v "\\]" {flag=1} /^## \[/ && flag && $0 !~ "^## \\[" v "\\]" {exit} flag{print}' CHANGELOG.md > "${NOTES_FILE}"
    cat "${NOTES_FILE}"

    # If all looks good
    git tag -a "${TAG}" -m "Release ${TAG}"
    git push origin main --follow-tags
    gh release create "${TAG}" --title "Release ${TAG}" --notes-file "${NOTES_FILE}"
    git tag --list "v*"
