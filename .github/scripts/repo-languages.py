#!/usr/bin/env python3
"""Languages of the public repositories this account owns, by bytes, the way
the public language cards count them: every byte in the repository, whoever
wrote it, with vendored paths excluded by linguist (.gitattributes in the
source repositories).

A repository count weight is mixed in so a language used across many
repositories ranks above one that appears in a single huge repository.

Environment:
  GH_TOKEN     any token that can read public repositories (GITHUB_TOKEN is enough)
  GH_USERNAME  the account whose repositories are listed
  OUT_DIR      where repos.svg and repos-dark.svg are written
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

from github_api import api
from langcard import HIDE, MAX_LANGS, THEMES, rank, render

USERNAME = os.environ.get("GH_USERNAME", "")
OUT_DIR = Path(os.environ.get("OUT_DIR", "dist/langs"))
LABEL = "📦 IN MY REPOS"
SIZE_WEIGHT, COUNT_WEIGHT = 1.0, 0.2


def list_public_repos() -> list[dict]:
    repos = api(f"/users/{USERNAME}/repos", {"type": "owner", "per_page": "100"})
    return [r for r in repos if not r["fork"]]


def repo_languages(full_name: str) -> dict[str, int]:
    langs = api(f"/repos/{full_name}/languages")
    return {lang: size for lang, size in langs.items() if lang not in HIDE} if isinstance(langs, dict) else {}


def main() -> int:
    if not os.environ.get("GH_TOKEN") or not USERNAME:
        print("GH_TOKEN and GH_USERNAME are required", file=sys.stderr)
        return 1

    per_repo = {repo["full_name"]: repo_languages(repo["full_name"]) for repo in list_public_repos()}
    sizes = Counter()
    counts = Counter()
    for langs in per_repo.values():
        sizes.update(langs)
        counts.update(langs.keys())
    if not sizes:
        print("no languages found - does the account own any public repositories?", file=sys.stderr)
        return 1

    ranked = rank(sizes, counts, SIZE_WEIGHT, COUNT_WEIGHT)[:MAX_LANGS]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        name = "repos.svg" if theme == "light" else f"repos-{theme}.svg"
        (OUT_DIR / name).write_text(render(ranked, LABEL, theme))
    print(f"wrote {OUT_DIR}/repos.svg from {len(per_repo)} repositories, "
          f"{len(sizes)} languages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
