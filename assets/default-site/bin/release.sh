#!/usr/bin/env bash
# Cut a release: bin/release.sh vX.Y.Z [--dry-run] [--force-branch]
#
# Every release tag refreshes the Docker image pins ("pins are updated with each vX.Y.Z release").
# Steps, in order (any failure stops before anything is committed or tagged):
#   1. validate vX.Y.Z (semver), a clean working tree, branch `main` (--force-branch to override), tag not taken
#   2. bin/pin-images.sh        refresh the name:tag@sha256 pins in Dockerfile/compose files
#   3. manage.py check, makemigrations --check, the test suite
#   4. write VERSION (X.Y.Z) and move CHANGELOG.md [Unreleased] into a dated [X.Y.Z] section
#   5. one release commit "Release vX.Y.Z" and the annotated tag vX.Y.Z
#   6. PRINT the push and image commands. It never pushes and never builds.
# --dry-run does steps 1 and a read-only pin check, and prints what the rest would do.
# Test hooks (environment): RELEASE_PIN_CMD, RELEASE_TEST_CMD replace steps 2 and 3.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() { sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
version="" ; dry=0 ; force_branch=0
for a in "$@"; do
    case "$a" in
        --dry-run) dry=1 ;;
        --force-branch) force_branch=1 ;;
        -h|--help) usage ;;
        -*) echo "unknown option $a" >&2; usage ;;
        *) [ -z "$version" ] && version="$a" || usage ;;
    esac
done
[ -n "$version" ] || usage
if ! [[ "$version" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?$ ]]; then
    echo "Version must look like v1.2.3 (semantic version with a leading v), got: $version" >&2
    exit 2
fi
plain="${version#v}"

say() { if [ "$dry" = 1 ]; then echo "[dry-run] would: $*"; else echo "== $*"; fi; }

# 1. preconditions --------------------------------------------------------------------------
if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is not clean; commit or stash first." >&2; exit 1
fi
branch=$(git rev-parse --abbrev-ref HEAD)
if [ "$branch" != "main" ] && [ "$force_branch" != 1 ]; then
    echo "Releases are cut from main (on '$branch'); use --force-branch to override." >&2; exit 1
fi
if git rev-parse -q --verify "refs/tags/$version" >/dev/null; then
    echo "Tag $version already exists." >&2; exit 1
fi
latest=$(git tag --list 'v[0-9]*' | grep -v -- '-' | sort -V | tail -1 || true)
if [ -n "$latest" ] && [ "$(printf '%s\n%s\n' "$latest" "$version" | sort -V | tail -1)" != "$version" ]; then
    echo "$version is not newer than the latest tag $latest." >&2; exit 1
fi
[ -f CHANGELOG.md ] && grep -q '^## \[Unreleased\]' CHANGELOG.md || { echo "CHANGELOG.md with an '## [Unreleased]' section is required." >&2; exit 1; }

PY=venv/bin/python; [ -x "$PY" ] || PY=$(command -v python3)
# Sites scaffolded with --no-docker have no image pins to refresh; the step is then skipped.
if [ -x bin/pin-images.sh ]; then default_pin=bin/pin-images.sh; else default_pin=true; fi
pin_cmd=${RELEASE_PIN_CMD:-$default_pin}
test_cmd=${RELEASE_TEST_CMD:-"DJANGO_DEBUG=1 DJANGO_SECRET_KEY=release-check $PY manage.py check && DJANGO_DEBUG=1 DJANGO_SECRET_KEY=release-check $PY manage.py makemigrations --check --dry-run starter && DJANGO_DEBUG=1 DJANGO_SECRET_KEY=release-check $PY manage.py test starter"}

# 2. pins -----------------------------------------------------------------------------------
if [ "$dry" = 1 ]; then
    say "refresh image pins ($pin_cmd); read-only check now:"
    if [ -n "${RELEASE_PIN_CMD:-}" ]; then eval "$RELEASE_PIN_CMD" || true
    elif [ "$default_pin" != true ]; then "$default_pin" --dry-run || true; fi
    say "run: $test_cmd"
    say "write VERSION=$plain and move CHANGELOG.md [Unreleased] to [$plain] - $(date -u +%F)"
    say "commit 'Release $version' and create annotated tag $version"
    echo "[dry-run] nothing was changed."
    exit 0
fi
say "refreshing image pins"
eval "$pin_cmd"

# 3. checks ---------------------------------------------------------------------------------
say "checks and tests"
eval "$test_cmd"

# 4. VERSION and CHANGELOG ------------------------------------------------------------------
say "writing VERSION and CHANGELOG.md"
printf '%s\n' "$plain" > VERSION
python3 - "$plain" "$(date -u +%F)" <<'PY'
import re, sys
version, day = sys.argv[1], sys.argv[2]
text = open("CHANGELOG.md").read()
marker = "## [Unreleased]"
head, _, rest = text.partition(marker)
body_end = re.search(r"^## \[", rest, re.M)
body, tail = (rest[:body_end.start()], rest[body_end.start():]) if body_end else (rest, "")
if not body.strip():
    body = "\n\n- No notable changes recorded.\n\n"
open("CHANGELOG.md", "w").write(f"{head}{marker}\n\n## [{version}] - {day}{body.rstrip()}\n\n{tail}".rstrip() + "\n")
PY

# 5. commit and tag -------------------------------------------------------------------------
say "committing and tagging $version"
git add VERSION CHANGELOG.md
for f in Dockerfile Dockerfile.* docker-compose*.yml; do [ -f "$f" ] && git add "$f"; done || true
git commit -q -m "Release $version"
git tag -a "$version" -m "Release $version"

# 6. what to do next ------------------------------------------------------------------------
cat <<NEXT

Release $version committed and tagged locally. Nothing was pushed or built. Next:

    git push origin $branch
    git push origin $version
NEXT
if [ -f Dockerfile ]; then
    cat <<NEXT

    APP_VERSION=$plain docker compose build        # tags __PROJECT_NAME__:$plain
    docker tag __PROJECT_NAME__:$plain __PROJECT_NAME__:latest   # optional
NEXT
fi
