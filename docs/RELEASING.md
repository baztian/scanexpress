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

    git checkout main
    git pull --ff-only
    git status --short

2. Run tests:
    source .venv/bin/activate && python -m unittest
    npm run test:e2e

3. Add/update release notes in [the changelog](../CHANGELOG.md) for the release version, then prepare release variables and notes:

    VERSION=0.0.1
    TAG="v${VERSION}"
    NOTES_FILE="/tmp/scanexpress-${TAG}-notes.md"
    awk -v v="${VERSION}" 'BEGIN{flag=0} $0 ~ "^## \\[" v "\\]" {flag=1} /^## \[/ && flag && $0 !~ "^## \\[" v "\\]" {exit} flag{print}' CHANGELOG.md > "${NOTES_FILE}"
    cat "${NOTES_FILE}"

4. Create an annotated tag:

    git tag -a "${TAG}" -m "Release ${TAG}"

5. Push commit and tags:

    git push origin main --follow-tags

6. Verify Docker Hub publish workflow succeeds for tag `vX.Y.Z` (workflow: `Docker Release`).

7. Create a GitHub Release from tag `vX.Y.Z` with focused notes for that version only.

    gh release create "${TAG}" --title "Release ${TAG}" --notes-file "${NOTES_FILE}"

8. Verify the tag exists locally.

    git tag --list "v*"

## Docker Hub Release Setup

Create these GitHub repository settings once:

- Secret `DOCKERHUB_USERNAME`: Docker Hub account name.
- Secret `DOCKERHUB_TOKEN`: Docker Hub access token with push permissions.
- Variable `DOCKERHUB_REPOSITORY`: full Docker Hub image path, for example `baztian/scanexpress`.

Release behavior:

- Pushing a tag in format `vMAJOR.MINOR.PATCH` publishes Docker image tags:
- Pushing a tag in format `vMAJOR.MINOR.PATCH` publishes Docker image tags `MAJOR.MINOR.PATCH`, `MAJOR.MINOR`, `MAJOR`, and `latest`.
- Workflow file: `.github/workflows/docker-release.yml`

## Hotfix

For urgent fixes, merge the fix to `main` and publish the next patch tag (`vX.Y.Z+1` in patch position, e.g. `v0.2.1` -> `v0.2.2`).

