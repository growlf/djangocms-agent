#!/usr/bin/env python3
"""Pin container images by digest and keep the pins current.

Rewrites every external image reference in the Dockerfile(s) and compose file(s) of the repository root
to `name:tag@sha256:<index digest>`. The human-readable tag stays in the reference, so it is clear what is
pinned; the digest is what Docker actually pulls (the multi-arch index digest, valid on every platform).

    bin/pin-images.sh              rewrite the pins in place (refuses to run with a dirty git tree)
    bin/pin-images.sh --dry-run    show what would change, write nothing
    bin/pin-images.sh --check      exit 1 if a pin is missing or stale (compares with the registry)

Skipped on purpose: references that contain a variable (`${...}`, e.g. the locally built app image),
`scratch`, and `FROM <earlier stage>` lines. A reference without an explicit tag is an error (a digest
alone says nothing about what it is).

Registry access uses only the Docker Registry HTTP API v2 (HEAD on the manifest, bearer-token flow), so no
Docker daemon and no pull is needed. For tests and offline demos set PIN_IMAGES_FAKE_DIGESTS to a JSON
file mapping "name:tag" to a digest; no network is used then.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE_GLOBS = ("Dockerfile", "Dockerfile.*", "docker-compose.yml", "docker-compose.*.yml", "compose.yml")
ACCEPT = ", ".join((
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REF_RE = re.compile(r"^(?P<name>[^\s:@]+(?::\d+(?=/))?(?:/[^\s:@]+)*)(?::(?P<tag>[^\s@]+))?(?:@(?P<digest>sha256:[0-9a-f]{64}))?$")
FROM_RE = re.compile(r"^(?P<pre>\s*FROM\s+(?:--\S+\s+)*)(?P<ref>\S+)(?P<post>.*)$", re.IGNORECASE)
IMAGE_RE = re.compile(r"""^(?P<pre>\s*image:\s*)(?P<q>['"]?)(?P<ref>[^\s'"#]+)(?P=q)(?P<post>\s*(?:#.*)?)$""")
STAGE_RE = re.compile(r"\sAS\s+(\S+)\s*$", re.IGNORECASE)


class PinError(Exception):
    pass


def split_ref(ref):
    """('name', 'tag' or None, 'sha256:..' or None) for a plain reference; PinError when unusable."""
    m = REF_RE.match(ref)
    if not m:
        raise PinError(f"cannot parse image reference {ref!r}")
    return m.group("name"), m.group("tag"), m.group("digest")


def find_references(path, text):
    """Yield (line_index, ref) for every pinnable external image reference in a Dockerfile or compose file."""
    is_docker = path.name.startswith("Dockerfile")
    stages = set()
    for i, line in enumerate(text.splitlines()):
        if is_docker:
            m = FROM_RE.match(line)
            if not m:
                continue
            ref = m.group("ref")
            stage = STAGE_RE.search(line)
            skip = ref.lower() == "scratch" or ref in stages or "$" in ref
            if stage:
                stages.add(stage.group(1))
            if not skip:
                yield i, ref
        else:
            m = IMAGE_RE.match(line)
            if m and "$" not in m.group("ref"):
                yield i, m.group("ref")


def pinned(ref, digest):
    name, tag, _old = split_ref(ref)
    if not tag:
        raise PinError(f"{ref}: no tag; write name:tag so the pin says what it is")
    return f"{name}:{tag}@{digest}"


def rewrite(path, text, resolve):
    """Return (new_text, [(ref, status, new_ref)]) with status in ok/updated/added. `resolve(name, tag)` -> digest."""
    lines = text.splitlines(keepends=True)
    report = []
    for i, ref in find_references(path, text):
        name, tag, old = split_ref(ref)
        if not tag:
            raise PinError(f"{path.name}:{i + 1}: {ref}: no tag; write name:tag so the pin says what it is")
        digest = resolve(name, tag)
        new_ref = f"{name}:{tag}@{digest}"
        status = "ok" if old == digest else ("updated" if old else "added")
        report.append((f"{name}:{tag}", status, new_ref, path.name, i + 1, old))
        lines[i] = lines[i].replace(ref, new_ref, 1)
    return "".join(lines), report


# --------------------------------------------------------------------------------------- registry

def _registry_and_repo(name):
    parts = name.split("/")
    if len(parts) > 1 and ("." in parts[0] or ":" in parts[0] or parts[0] == "localhost"):
        host, repo = parts[0], "/".join(parts[1:])
    else:
        host, repo = "registry-1.docker.io", name
    if host in ("docker.io", "index.docker.io"):
        host = "registry-1.docker.io"
    if host == "registry-1.docker.io" and "/" not in repo:
        repo = "library/" + repo
    return host, repo


def _head(url, headers):
    req = urllib.request.Request(url, method="HEAD", headers=headers)
    return urllib.request.urlopen(req, timeout=30)


def resolve_digest(name, tag):
    """The digest of name:tag as the registry serves it (the index digest for multi-arch images)."""
    fake = os.environ.get("PIN_IMAGES_FAKE_DIGESTS")
    if fake:
        table = json.loads(Path(fake).read_text())
        try:
            return table[f"{name}:{tag}"]
        except KeyError:
            raise PinError(f"{name}:{tag} is not in PIN_IMAGES_FAKE_DIGESTS")
    host, repo = _registry_and_repo(name)
    url = f"https://{host}/v2/{repo}/manifests/{tag}"
    headers = {"Accept": ACCEPT}
    try:
        try:
            resp = _head(url, headers)
        except urllib.error.HTTPError as e:
            if e.code != 401:
                raise
            challenge = e.headers.get("Www-Authenticate", "")
            fields = dict(re.findall(r'(\w+)="([^"]*)"', challenge))
            if "realm" not in fields:
                raise PinError(f"{name}:{tag}: registry demands auth I cannot do ({challenge!r})")
            token_url = f"{fields['realm']}?service={fields.get('service', '')}&scope=repository:{repo}:pull"
            with urllib.request.urlopen(token_url, timeout=30) as t:
                token = json.load(t).get("token") or ""
            resp = _head(url, {**headers, "Authorization": f"Bearer {token}"})
        digest = resp.headers.get("Docker-Content-Digest", "")
    except (urllib.error.URLError, OSError) as e:
        raise PinError(f"{name}:{tag}: registry lookup failed: {e}")
    if not DIGEST_RE.match(digest):
        raise PinError(f"{name}:{tag}: registry returned no usable digest ({digest!r})")
    return digest


# --------------------------------------------------------------------------------------- command line

def tracked_files(root):
    found = []
    for pattern in FILE_GLOBS:
        found.extend(sorted(root.glob(pattern)))
    return [p for p in dict.fromkeys(found) if p.is_file()]


def tree_is_dirty(root):
    out = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True)
    return out.returncode == 0 and bool(out.stdout.strip())


def main(argv=None, root=ROOT, resolve=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="exit 1 if a pin is missing or stale; change nothing")
    mode.add_argument("--dry-run", action="store_true", help="show the changes, write nothing")
    ap.add_argument("--allow-dirty", action="store_true", help="write mode: do not require a clean git tree")
    args = ap.parse_args(argv)
    resolve = resolve or resolve_digest

    files = tracked_files(root)
    if not files:
        print("no Dockerfile/compose files found", file=sys.stderr)
        return 2
    write = not (args.check or args.dry_run)
    if write and not args.allow_dirty and tree_is_dirty(root):
        print("Refusing to rewrite pins with a dirty working tree (commit or stash first, or --allow-dirty).", file=sys.stderr)
        return 2

    cache, problems, changed = {}, 0, 0

    def cached(name, tag):
        if (name, tag) not in cache:
            cache[(name, tag)] = resolve(name, tag)
        return cache[(name, tag)]

    for path in files:
        text = path.read_text()
        try:
            new_text, report = rewrite(path, text, cached)
        except PinError as e:
            print(f"ERROR {e}", file=sys.stderr)
            return 2
        for ref, status, new_ref, fname, lineno, old in report:
            label = {"ok": "OK     ", "updated": "STALE  " if not write else "UPDATED", "added": "MISSING" if not write else "ADDED  "}[status]
            if args.dry_run and status != "ok":
                label = {"updated": "WOULD UPDATE", "added": "WOULD ADD"}[status]
            print(f"{label} {fname}:{lineno} {new_ref}" + (f"   (was {old})" if old and status == "updated" else ""))
            if status != "ok":
                problems += 1
        if write and new_text != text:
            path.write_text(new_text)
            changed += 1
    if args.check:
        print("pins are current" if not problems else f"{problems} pin(s) missing or stale: run bin/pin-images.sh")
        return 1 if problems else 0
    if write:
        print(f"{changed} file(s) rewritten" if changed else "nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
