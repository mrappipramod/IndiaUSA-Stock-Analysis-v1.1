"""
Persist analysis reports to a GitHub repository.

Streamlit Cloud's filesystem is wiped on every restart, so writing to a local
folder would silently lose data. Instead each report is committed as a JSON
file to your own GitHub repo via the GitHub REST API — a free, permanent,
version-controlled store.

Setup (one time):
  1. Create a fine-grained personal access token at
     https://github.com/settings/tokens  with "Contents: read & write"
     permission on your repo.
  2. In Streamlit Cloud -> App -> Settings -> Secrets add:

        GITHUB_TOKEN = "github_pat_..."
        GITHUB_REPO  = "yourusername/stock-validator"
        GITHUB_BRANCH = "main"
"""

from __future__ import annotations

import base64
import json

import requests

API = "https://api.github.com"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def save_report(report: dict, token: str, repo: str, branch: str = "main") -> str:
    """Commit one report as data/analyses/<TICKER>_<timestamp>.json.
    Returns the web URL of the committed file."""
    ticker = report["ticker"].replace("/", "-")
    stamp = report["generated_utc"].replace(":", "-").replace("+00-00", "Z")
    path = f"data/analyses/{ticker}_{stamp}.json"

    body = {
        "message": f"analysis: {report['ticker']} score={report.get('score')} ({report.get('verdict','')[:40]})",
        "branch": branch,
        "content": base64.b64encode(
            json.dumps(report, indent=1, ensure_ascii=False).encode()
        ).decode(),
    }
    r = requests.put(f"{API}/repos/{repo}/contents/{path}",
                     headers=_headers(token), json=body, timeout=30)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"GitHub save failed ({r.status_code}): {r.json().get('message', r.text)[:200]}")
    return r.json()["content"]["html_url"]


def list_reports(token: str, repo: str, branch: str = "main") -> list[dict]:
    """Return [{name, download_url}] for previously saved analyses."""
    r = requests.get(f"{API}/repos/{repo}/contents/data/analyses",
                     headers=_headers(token), params={"ref": branch}, timeout=30)
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return [{"name": f["name"], "download_url": f["download_url"]}
            for f in r.json() if f["name"].endswith(".json")]


def load_report(download_url: str, token: str) -> dict:
    r = requests.get(download_url, headers=_headers(token), timeout=30)
    r.raise_for_status()
    return r.json()
