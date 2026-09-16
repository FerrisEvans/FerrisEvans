#!/usr/bin/env python3
"""Aggregate the languages of the code *you* wrote, across every repository you
can reach - your own public repos plus private ones owned by organizations you
belong to.

The public language cards can only see public repos, and they count every byte
in a repo no matter who wrote it. This counts lines added by commits GitHub
attributes to one account, so vendored code and other people's work stay out.

Commits are located through the REST API (GitHub maps a commit to an account
regardless of the git email configured at the time), then measured locally in a
bare clone, which is far cheaper than asking the API for every commit's diff.

Environment:
  GH_TOKEN  classic PAT with the `repo` scope (needed to read private org repos)
  GH_USERNAME  the account whose commits are counted (not USERNAME: the shell
               already defines that on macOS and Linux)
  EXTRA_EMAILS  comma separated commit emails that are not registered on the
                GitHub account, so their commits count too
  OUT_DIR   where languages.json and languages.svg are written
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")
USERNAME = os.environ.get("GH_USERNAME", "")
OUT_DIR = Path(os.environ.get("OUT_DIR", "dist/langs"))
# Commit emails that are not registered on the GitHub account; see own_commits().
EXTRA_EMAILS = [e.strip() for e in os.environ.get("EXTRA_EMAILS", "").split(",") if e.strip()]

# Languages that are noise on a profile card, matching the `hide` list of the
# byte based card in README.md.
HIDE = {"HTML", "CSS", "CMake", "Less", "Jupyter Notebook", "Markdown", "Text",
        "JSON", "YAML"}  # markup and data, not code

# Third party or generated code that no .gitattributes marks as vendored.
VENDOR = re.compile(
    r"(^|/)(sdk|Plugins|node_modules|vendor|third[_-]?party|external|deps|dist|build|Pods|"
    r"Packages|wwwroot/lib|\.venv|venv|site-packages|migrations)(/|$)"
    r"|\.min\.(js|css)$|\.g\.cs$|\.Designer\.cs$|(^|/)package-lock\.json$|(^|/)yarn\.lock$"
    r"|(^|/)poetry\.lock$|(^|/)Cargo\.lock$|\.pb\.go$|_pb2\.py$",
    re.I,
)

EXT_LANG = {
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".cxx": "C++", ".hpp": "C++",
    ".hh": "C++", ".inl": "C++", ".cs": "C#", ".swift": "Swift", ".py": "Python",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".mts": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".vue": "Vue",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".java": "Java", ".kt": "Kotlin",
    ".m": "Objective-C", ".mm": "Objective-C++", ".sh": "Shell", ".bash": "Shell",
    ".zsh": "Shell", ".gd": "GDScript", ".sol": "Solidity", ".lua": "Lua",
    ".sql": "SQL", ".php": "PHP", ".dart": "Dart", ".scala": "Scala", ".ex": "Elixir",
    ".exs": "Elixir", ".hs": "Haskell", ".ml": "OCaml", ".r": "R", ".jl": "Julia",
    ".pl": "Perl", ".vim": "Vim Script", ".ps1": "PowerShell", ".yml": "YAML",
    ".yaml": "YAML", ".json": "JSON", ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".less": "Less", ".md": "Markdown", ".ipynb": "Jupyter Notebook",
}

# github-linguist colors, only for the languages this account actually uses;
# anything else falls back to a neutral grey.
COLORS = {
    "C": "#555555", "C++": "#f34b7d", "C#": "#178600", "Swift": "#F05138",
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Go": "#00ADD8", "Rust": "#dea584", "Ruby": "#701516", "Java": "#b07219",
    "Kotlin": "#A97BFF", "Objective-C": "#438eff", "Shell": "#89e051",
    "GDScript": "#355570", "Solidity": "#AA6746", "Lua": "#000080", "SQL": "#e38c00",
    "PHP": "#4F5D95", "Dart": "#00B4AB", "Vue": "#41b883", "SCSS": "#c6538c",
    "YAML": "#cb171e", "JSON": "#292929", "Elixir": "#6e4a7e", "Haskell": "#5e5086",
}
FALLBACK_COLOR = "#8b949e"

# Only ask git for files we can attribute to a language we display.
CODE_PATHSPEC = [f"*{ext}" for ext, lang in EXT_LANG.items() if lang not in HIDE]

# Prefetch hint only, see added_lines(): changing it changes download size and
# runtime, never the numbers on the card.
BLOB_PREFETCH_LIMIT = "200k"


def api(path: str, params: dict | None = None) -> list:
    """GET every page of a REST collection."""
    items: list = []
    url = f"{API}{path}"
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    while url:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{USERNAME}-own-languages",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                items.extend(json.load(res))
                link = res.headers.get("Link", "")
        except urllib.error.HTTPError as err:
            if err.code in (403, 404, 409):  # no access, empty repo, rate limited
                print(f"  skipped {path}: HTTP {err.code}", file=sys.stderr)
                return items
            raise
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt else None
    return items


def list_repos() -> list[dict]:
    """Every non-fork repo the token can reach, including private org ones."""
    repos = api("/user/repos", {
        "affiliation": "owner,organization_member,collaborator",
        "per_page": "100",
    })
    return [r for r in repos if not r["fork"]]


def own_commits(full_name: str) -> list[str]:
    """SHAs of commits in this repo written by the account.

    GitHub only attributes a commit to an account when the commit's email is
    registered on it, so old commits made with an unregistered email are
    invisible to a `?author=<login>` query. The `author` parameter also accepts
    a raw email, so every address in EXTRA_EMAILS is queried as well and the
    results merged.
    """
    shas: dict[str, None] = {}  # dict keeps the order while removing duplicates
    for author in [USERNAME, *EXTRA_EMAILS]:
        for commit in api(f"/repos/{full_name}/commits", {"author": author, "per_page": "100"}):
            shas[commit["sha"]] = None
    return list(shas)


def run(cmd: list[str], **kw) -> str:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw).stdout


def added_lines(clone_url: str, shas: list[str], workdir: Path) -> dict[str, int]:
    """Lines added per language by the given commits, ignoring vendored paths."""
    if not shas:  # `git log --no-walk` with no revision would fall back to HEAD
        return {}
    repo = workdir / "repo.git"
    # The token never reaches the process table: git reads it from a credential
    # helper on stdin instead of the URL.
    helper = "!f(){ echo username=x-access-token; echo password=$GH_TOKEN; };f"
    # What counts is decided by CODE_PATHSPEC and VENDOR below; this filter only
    # decides what git bothers to download up front, and never what we measure -
    # a blob the diff needs is fetched on demand regardless. GitHub's transfer
    # protocol has no path-aware filter (it accepts only blob:none, blob:limit
    # and tree:0), so size is the only prefetch hint available. Skipping blobs
    # over 200 KB drops the game art and vendored binaries (113 MB -> 6 MB on the
    # heaviest repo) while keeping every source file; going further with
    # blob:none costs one round trip per file (569s vs 4s on the largest repo).
    run(["git", "-c", f"credential.helper={helper}", "clone", "--bare", "--quiet",
         "--no-tags", f"--filter=blob:limit={BLOB_PREFETCH_LIMIT}", clone_url, str(repo)])

    per_lang: dict[str, int] = defaultdict(int)
    # One git call for all commits: --stdin keeps this to a single process even
    # for accounts with thousands of commits. The pathspec keeps the diff (and
    # therefore any on-demand blob fetch) to files we can actually attribute.
    out = run(["git", "--git-dir", str(repo), "log", "--no-walk", "--stdin", "--numstat",
               "--format=", "--no-renames", "--", *CODE_PATHSPEC], input="\n".join(shas))
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or parts[0] == "-":  # binary files report "-"
            continue
        add, _, path = parts
        if VENDOR.search(path):
            continue
        lang = EXT_LANG.get(os.path.splitext(path)[1].lower())
        if lang and lang not in HIDE:
            per_lang[lang] += int(add)
    return per_lang


def svg(langs: list[tuple[str, int]], total: int) -> str:
    """A compact card in the same pink palette as the other cards in README.md."""
    width, pad, bar_y, bar_h = 300, 25, 55, 8
    rows = (len(langs) + 1) // 2
    height = bar_y + bar_h + 22 + rows * 25
    inner = width - pad * 2

    segments, x = [], pad
    for name, lines in langs:
        w = inner * lines / total
        segments.append(
            f'<rect x="{x:.2f}" y="{bar_y}" width="{max(w, 1):.2f}" height="{bar_h}" '
            f'fill="{COLORS.get(name, FALLBACK_COLOR)}" />'
        )
        x += w

    entries = []
    for i, (name, lines) in enumerate(langs):
        col, row = i % 2, i // 2
        cx = pad + col * (inner / 2)
        cy = bar_y + bar_h + 28 + row * 25
        pct = 100 * lines / total
        entries.append(
            f'<circle cx="{cx + 5:.1f}" cy="{cy - 4:.1f}" r="5" '
            f'fill="{COLORS.get(name, FALLBACK_COLOR)}" />'
            f'<text x="{cx + 16:.1f}" y="{cy:.1f}" class="lang">{name} {pct:.2f}%</text>'
        )

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" \
xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bg" gradientTransform="rotate(0)">
      <stop offset="0%" stop-color="#ffc2e0" />
      <stop offset="100%" stop-color="#ff9ecd" />
    </linearGradient>
  </defs>
  <style>
    .title {{ font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; fill: #5c1046; }}
    .lang {{ font: 400 12px 'Segoe UI', Ubuntu, Sans-Serif; fill: #5c1046; }}
  </style>
  <rect width="{width}" height="{height}" rx="4.5" fill="url(#bg)" />
  <text x="{pad}" y="35" class="title">Lines I wrote, by language</text>
  <g>{''.join(segments)}</g>
  <g>{''.join(entries)}</g>
</svg>
"""


def main() -> int:
    if not TOKEN or not USERNAME:
        print("GH_TOKEN and GH_USERNAME are required", file=sys.stderr)
        return 1

    totals: dict[str, int] = defaultdict(int)
    counted: list[dict] = []
    failures: list[str] = []
    for repo in list_repos():
        shas = own_commits(repo["full_name"])
        if not shas:
            continue
        try:
            with tempfile.TemporaryDirectory() as tmp:
                per_lang = added_lines(repo["clone_url"], shas, Path(tmp))
        except subprocess.CalledProcessError as err:
            # One unreachable repository must not cost us the whole card.
            print(f"  skipped {repo['full_name']}: git failed "
                  f"({(err.stderr or '').strip().splitlines()[-1:] or ['no output']})",
                  file=sys.stderr)
            failures.append(repo["full_name"])
            continue
        for lang, lines in per_lang.items():
            totals[lang] += lines
        counted.append({
            "repo": repo["full_name"], "private": repo["private"],
            "commits": len(shas), "lines": sum(per_lang.values()),
        })
        print(f"  {repo['full_name']}: {len(shas)} commits, "
              f"{sum(per_lang.values())} lines", file=sys.stderr)

    if not totals:
        print("no commits found - is the token allowed to read the repos?", file=sys.stderr)
        return 1

    ranked = sorted(totals.items(), key=lambda kv: -kv[1])[:12]
    total = sum(lines for _, lines in ranked)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "languages.json").write_text(json.dumps(
        {"languages": dict(ranked), "repositories": counted, "skipped": failures},
        indent=2, ensure_ascii=False))
    (OUT_DIR / "languages.svg").write_text(svg(ranked, total))
    print(f"wrote {OUT_DIR}/languages.svg from {len(counted)} repositories"
          + (f", {len(failures)} skipped: {', '.join(failures)}" if failures else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
