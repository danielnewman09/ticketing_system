"""Portable web search for dependency research.

Uses DuckDuckGo (free, no API key) for package discovery and the GitHub
REST API (no auth needed for public repos) for repository metrics.
"""

import logging
import re

import requests
from ddgs import DDGS

log = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"
_GITHUB_REPO_RE = re.compile(r"github\.com/([^/]+/[^/]+)")


def search_packages(query: str, language: str, max_results: int = 8) -> list[dict]:
    """Search for software packages/libraries matching a query.

    Args:
        query: What the library should do (e.g., "linear algebra", "GUI framework").
        language: Target language (e.g., "C++", "Python").
        max_results: Maximum results to return.

    Returns:
        List of dicts with keys: title, url, snippet.
    """
    search_query = f"{language} library {query} github"
    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(search_query, max_results=max_results))
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", ""),
            }
            for r in raw
        ]
    except Exception:
        log.warning("DuckDuckGo search failed for %r", search_query, exc_info=True)
        return []


def extract_github_url(text: str) -> str | None:
    """Extract a GitHub repo URL from a string."""
    m = _GITHUB_REPO_RE.search(text)
    if m:
        owner_repo = m.group(1).rstrip("/").split("?")[0].split("#")[0]
        # Strip common suffixes
        for suffix in ("/issues", "/wiki", "/releases", "/tree", "/blob"):
            if suffix in owner_repo:
                owner_repo = owner_repo.split(suffix)[0]
        return f"https://github.com/{owner_repo}"
    return None


def fetch_github_info(repo_url: str) -> dict | None:
    """Fetch repository metrics from the GitHub REST API.

    Args:
        repo_url: Full GitHub URL (e.g., "https://github.com/eigen/eigen").

    Returns:
        Dict with keys: name, full_name, description, stars, license,
        language, last_pushed, open_issues, url.  None on failure.
    """
    m = _GITHUB_REPO_RE.search(repo_url)
    if not m:
        return None

    owner_repo = m.group(1).rstrip("/")
    api_url = f"{_GITHUB_API}/repos/{owner_repo}"

    try:
        resp = requests.get(api_url, timeout=10, headers={"Accept": "application/vnd.github.v3+json"})
        if resp.status_code != 200:
            log.debug("GitHub API %s returned %d", api_url, resp.status_code)
            return None
        data = resp.json()
        return {
            "name": data.get("name", ""),
            "full_name": data.get("full_name", ""),
            "description": data.get("description", ""),
            "stars": data.get("stargazers_count", 0),
            "license": (data.get("license") or {}).get("spdx_id", "Unknown"),
            "language": data.get("language", ""),
            "last_pushed": data.get("pushed_at", ""),
            "open_issues": data.get("open_issues_count", 0),
            "url": data.get("html_url", repo_url),
        }
    except Exception:
        log.warning("GitHub API request failed for %s", repo_url, exc_info=True)
        return None


def search_and_enrich(query: str, language: str, max_results: int = 5) -> list[dict]:
    """Search for packages and enrich results with GitHub metrics.

    Returns list of dicts with search result + GitHub info merged.
    """
    results = search_packages(query, language, max_results=max_results * 2)
    enriched = []
    seen_repos = set()

    for r in results:
        gh_url = extract_github_url(r["url"])
        if not gh_url or gh_url in seen_repos:
            continue
        seen_repos.add(gh_url)

        info = fetch_github_info(gh_url)
        if info:
            enriched.append({
                **r,
                "github_url": gh_url,
                "github": info,
            })
            if len(enriched) >= max_results:
                break

    return enriched
