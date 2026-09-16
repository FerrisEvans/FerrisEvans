#!/usr/bin/env python3
"""The scoreboard card: stars, commits, pull requests, issues, repositories and
followers, replacing the third party stats card README.md used to embed.

Commit, pull request and issue totals come from contributionsCollection, which
only covers one year per query, so one aliased query per year since the account
was created is sent in a single request. With a token that can read private
contributions, restrictedContributionsCount adds the private ones as a number
without naming any repository.

Environment:
  GH_TOKEN     token used for the API; a PAT sees private contributions too
  GH_USERNAME  the account the card is about
  OUT_DIR      where stats.svg and stats-dark.svg are written
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from github_api import graphql
from langcard import THEMES
from statscard import render

USERNAME = os.environ.get("GH_USERNAME", "")
OUT_DIR = Path(os.environ.get("OUT_DIR", "dist/stats"))
LABEL = "🏆 SCOREBOARD"

PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, first: 100,
                 orderBy: {field: STARGAZERS, direction: DESC}) {
      totalCount
      nodes { stargazerCount }
    }
  }
}
"""

YEAR_FIELDS = """
      totalCommitContributions
      restrictedContributionsCount
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoriesWithContributedCommits
"""


def years_query(years: list[int]) -> str:
    """One aliased contributionsCollection per year, in a single request."""
    slices = "\n".join(
        f'    y{year}: contributionsCollection('
        f'from: "{year}-01-01T00:00:00Z", to: "{year}-12-31T23:59:59Z") {{{YEAR_FIELDS}    }}'
        for year in years
    )
    return f'query($login: String!) {{\n  user(login: $login) {{\n{slices}\n  }}\n}}'


def collect() -> list[tuple[str, str, int]]:
    profile = graphql(PROFILE_QUERY, login=USERNAME)["user"]
    created = datetime.fromisoformat(profile["createdAt"].replace("Z", "+00:00"))
    years = list(range(created.year, datetime.now(timezone.utc).year + 1))

    totals = {field.strip(): 0 for field in YEAR_FIELDS.split()}
    contributions = graphql(years_query(years), login=USERNAME)["user"]
    for year in contributions.values():
        for field, value in year.items():
            totals[field] += value

    stars = sum(repo["stargazerCount"] for repo in profile["repositories"]["nodes"])
    return [
        ("⭐", "Total Stars", stars),
        ("📝", "Total Commits", totals["totalCommitContributions"]
                                + totals["restrictedContributionsCount"]),
        ("🔀", "Total PRs", totals["totalPullRequestContributions"]),
        ("🐛", "Total Issues", totals["totalIssueContributions"]),
        ("📦", "Public Repos", profile["repositories"]["totalCount"]),
        ("🫂", "Followers", profile["followers"]["totalCount"]),
    ]


def main() -> int:
    if not os.environ.get("GH_TOKEN") or not USERNAME:
        print("GH_TOKEN and GH_USERNAME are required", file=sys.stderr)
        return 1

    stats = collect()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        name = "stats.svg" if theme == "light" else f"stats-{theme}.svg"
        (OUT_DIR / name).write_text(render(stats, LABEL, theme))
    print("wrote " + ", ".join(f"{icon} {caption}: {value:,}" for icon, caption, value in stats))
    return 0


if __name__ == "__main__":
    sys.exit(main())
