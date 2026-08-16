"""Minimal GitHub REST client built on the standard library only."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from autocommit import __version__

API_ROOT = "https://api.github.com"
USER_AGENT = "autocommit/{0}".format(__version__)


class GitHubError(Exception):
    """Raised for any non-successful GitHub API response."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


@dataclass
class User:
    login: str
    id: int
    name: str = ""

    @property
    def noreply_email(self) -> str:
        return "{0}+{1}@users.noreply.github.com".format(self.id, self.login)

    @property
    def display_name(self) -> str:
        return self.name or self.login


@dataclass
class Repo:
    owner: str
    name: str
    default_branch: str
    private: bool
    fork: bool
    can_push: bool
    pushed_at: str = ""

    @property
    def full_name(self) -> str:
        return "{0}/{1}".format(self.owner, self.name)


class GitHubClient:
    def __init__(self, token: str, api_root: str = API_ROOT, timeout: int = 30):
        if not token:
            raise GitHubError("No token provided.")
        self.token = token
        self.api_root = api_root.rstrip("/")
        self.timeout = timeout
        self.scopes = ""

    # -- plumbing ---------------------------------------------------------
    def _request(self, method: str, path: str, payload: "dict | None" = None):
        url = path if path.startswith("http") else self.api_root + path
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url=url, data=body, method=method)
        request.add_header("Authorization", "Bearer " + self.token)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", "2022-11-28")
        request.add_header("User-Agent", USER_AGENT)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.scopes = response.headers.get("x-oauth-scopes", "") or self.scopes
                raw = response.read().decode("utf-8") or "null"
                return json.loads(raw), response.headers
        except urllib.error.HTTPError as exc:
            raise GitHubError(_describe_http_error(exc), exc.code) from exc
        except urllib.error.URLError as exc:
            raise GitHubError("Cannot reach GitHub: {0}".format(exc.reason)) from exc

    def _paged(self, path: str, limit: int = 300):
        items = []
        url = self.api_root + path
        while url and len(items) < limit:
            data, headers = self._request("GET", url)
            if not isinstance(data, list):
                break
            items.extend(data)
            url = _next_link(headers.get("Link", ""))
        return items[:limit]

    # -- endpoints --------------------------------------------------------
    def whoami(self) -> User:
        data, _ = self._request("GET", "/user")
        return User(login=data["login"], id=int(data["id"]), name=data.get("name") or "")

    def list_repos(self, limit: int = 300):
        raw = self._paged(
            "/user/repos?per_page=100&affiliation=owner,collaborator&sort=pushed",
            limit=limit,
        )
        return [_to_repo(item) for item in raw]

    def get_repo(self, owner: str, name: str) -> Repo:
        data, _ = self._request("GET", "/repos/{0}/{1}".format(owner, name))
        return _to_repo(data)

    def create_repo(self, name: str, private: bool = True, description: str = "") -> Repo:
        payload = {
            "name": name,
            "private": private,
            "auto_init": True,
            "description": description or "Activity log",
        }
        data, _ = self._request("POST", "/user/repos", payload)
        return _to_repo(data)

    def token_scopes(self):
        if not self.scopes:
            self._request("GET", "/user")
        return [scope.strip() for scope in self.scopes.split(",") if scope.strip()]


def _to_repo(data: dict) -> Repo:
    owner = (data.get("owner") or {}).get("login", "")
    permissions = data.get("permissions") or {}
    return Repo(
        owner=owner,
        name=data.get("name", ""),
        default_branch=data.get("default_branch") or "main",
        private=bool(data.get("private")),
        fork=bool(data.get("fork")),
        can_push=bool(permissions.get("push", True)),
        pushed_at=data.get("pushed_at") or "",
    )


def _next_link(link_header: str) -> str:
    for part in (link_header or "").split(","):
        section = part.split(";")
        if len(section) < 2:
            continue
        if 'rel="next"' in section[1].replace(" ", "").replace("'", '"'):
            return section[0].strip().strip("<>")
    return ""


def _describe_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        detail = json.loads(exc.read().decode("utf-8")).get("message", "")
    except Exception:
        detail = ""
    if exc.code == 401:
        return "GitHub rejected the token (401). Sign in again."
    if exc.code == 403 and "rate limit" in detail.lower():
        return "GitHub API rate limit reached. Try again later."
    if exc.code == 403:
        return "Forbidden (403). {0}".format(detail or "The token is missing the 'repo' scope.")
    if exc.code == 404:
        return "Not found (404). {0}".format(detail or "Check the repository name and token scope.")
    if exc.code == 422:
        return "GitHub refused the request (422). {0}".format(detail)
    return "GitHub API error {0}. {1}".format(exc.code, detail).strip()
