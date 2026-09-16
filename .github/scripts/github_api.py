#!/usr/bin/env python3
"""Minimal GitHub REST client for the card scripts.

Environment:
  GH_TOKEN     token used for every request
  GH_USERNAME  account the cards are about, only used in the User-Agent here
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ.get("GH_TOKEN", "")
USERNAME = os.environ.get("GH_USERNAME", "")
TIMEOUT_S = 60


def api(path: str, params: dict | None = None) -> list | dict:
    """GET a resource; list resources are followed across every page.

    Errors that mean "nothing to see here" (no access, empty repository, rate
    limited) are logged and yield what was collected so far, so one repository
    never costs the whole card.
    """
    url = f"{API}{path}" + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else "")
    items: list = []
    while url:
        try:
            with urllib.request.urlopen(_request(url), timeout=TIMEOUT_S) as res:
                page = json.load(res)
                link = res.headers.get("Link", "")
        except urllib.error.HTTPError as err:
            if err.code in (403, 404, 409):
                print(f"  skipped {path}: HTTP {err.code}", file=sys.stderr)
                return items
            raise
        if not isinstance(page, list):
            return page
        items = [*items, *page]
        nxt = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = nxt.group(1) if nxt else None
    return items


def graphql(query: str, **variables) -> dict:
    """POST a GraphQL query and return its `data`, raising on GraphQL errors."""
    payload = json.dumps({"query": query, "variables": variables}).encode()
    req = _request(f"{API}/graphql")
    req.data = payload
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as res:
        body = json.load(res)
    if body.get("errors"):
        raise RuntimeError(f"GraphQL failed: {body['errors']}")
    return body["data"]


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": f"{USERNAME}-profile-cards",
    })
