from __future__ import annotations

import os
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import httpx

from repo_catalog import __version__
from repo_catalog.domain.models import CatalogError, Waiting
from repo_catalog.domain.time import (
    datetime_to_us,
    now_us,
    unix_seconds_to_us,
    validate_epoch_us,
)


class EnvCredentials:
    def __init__(self, name):
        self.name = name

    def get(self):
        return os.environ.get(self.name)


class GitHubTransport:
    def __init__(
        self, config, token, *, client=None, credentials=None, clock_us=now_us
    ):
        """The optional wall clock returns integer Unix epoch microseconds."""
        self.cfg = config
        self.token = token
        self.credentials = credentials or EnvCredentials(config["token_env_var"])
        self.clock_us = clock_us
        self.base = config["rest_base_url"].rstrip("/")
        self.graphql = config["graphql_url"]
        self.origins = {self.origin(self.base), self.origin(self.graphql)}
        local = all(
            origin[1] in ("127.0.0.1", "localhost", "::1") for origin in self.origins
        )
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(
                config["read_timeout_seconds"],
                connect=config["connect_timeout_seconds"],
            ),
            follow_redirects=False,
            trust_env=not local,
        )
        self.owned = client is None

    @staticmethod
    def origin(url):
        u = urlsplit(url)
        return u.scheme, u.hostname, u.port or (443 if u.scheme == "https" else 80)

    def close(self):
        if self.owned:
            self.client.close()

    def validate_url(self, url):
        u = urlsplit(url)
        if (
            self.origin(url) not in self.origins
            or u.username
            or u.password
            or u.fragment
            or ".." in u.path.split("/")
            or not u.path.startswith("/")
        ):
            raise CatalogError(
                "UNSAFE_API_URL",
                "Refusing credential propagation outside configured API origin",
            )
        if u.scheme != "https" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise CatalogError("UNSAFE_API_URL", "Remote API requests require TLS")

    def request(self, method, url, **kwargs):
        self.validate_url(url)
        self.token.check()
        if method not in ("GET", "POST") or method == "POST" and url != self.graphql:
            raise CatalogError(
                "INVALID_ARGUMENT", "Only GET and static GraphQL queries are supported"
            )
        secret = self.credentials.get()
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": self.cfg["rest_api_version"],
            "User-Agent": "repo-catalog/" + __version__,
        }
        if secret:
            headers["Authorization"] = "Bearer " + secret
        headers.update(kwargs.pop("headers", {}))
        for attempt in range(self.cfg["max_attempts"]):
            self.token.check()
            try:
                with self.client.stream(
                    method, url, headers=headers, **kwargs
                ) as response:
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        self.token.check()
                        body.extend(chunk)
                        if len(body) > 32 * 1024 * 1024:
                            raise CatalogError(
                                "API_RESPONSE_LIMIT",
                                "API response exceeded safe page memory limit",
                            )
                    raw = bytes(body)
                    decoded_headers = dict(response.headers)
                    decoded_headers.pop("content-encoding", None)
                    decoded_headers["content-length"] = str(len(raw))
                    response = httpx.Response(
                        response.status_code,
                        headers=decoded_headers,
                        content=raw,
                        request=response.request,
                    )
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt + 1 == self.cfg["max_attempts"]:
                    raise CatalogError(
                        "API_NETWORK", "API transport failed", retryable=True
                    )
                continue
            limited = (
                response.status_code == 429
                or response.status_code == 403
                and (
                    response.headers.get("x-ratelimit-remaining") == "0"
                    or "retry-after" in response.headers
                )
            )
            if limited:
                retry = response.headers.get("retry-after")
                reset = response.headers.get("x-ratelimit-reset")
                current_us = validate_epoch_us(self.clock_us())
                try:
                    if retry:
                        try:
                            # Retry-After is a duration in seconds, or an HTTP date.
                            delay_us = unix_seconds_to_us(retry)
                        except ValueError:
                            not_before_us = datetime_to_us(parsedate_to_datetime(retry))
                        else:
                            not_before_us = current_us + delay_us
                        not_before_us = max(current_us, not_before_us)
                    elif reset:
                        not_before_us = max(
                            current_us + 1_000_000, unix_seconds_to_us(reset)
                        )
                    else:
                        not_before_us = current_us + 60_000_000
                    validate_epoch_us(not_before_us)
                except (TypeError, ValueError, OverflowError):
                    not_before_us = validate_epoch_us(current_us + 60_000_000)
                raise Waiting(
                    "RATE_LIMIT",
                    "API rate limit requires a later resume",
                    {"not_before_us": not_before_us},
                    True,
                )
            if response.status_code >= 500:
                if attempt + 1 == self.cfg["max_attempts"]:
                    raise CatalogError(
                        "API_SERVER", "API server failed", retryable=True
                    )
                continue
            if response.status_code == 401:
                raise CatalogError(
                    "CREDENTIALS_MISSING", "API authentication is absent or unusable"
                )
            if response.status_code in (403, 404):
                raise CatalogError(
                    "API_ACCESS",
                    "API resource inaccessible; deletion is not established",
                    {"status": response.status_code},
                )
            if response.status_code not in (200, 301, 302, 304):
                raise CatalogError(
                    "API_HTTP",
                    "Unexpected API status",
                    {"status": response.status_code},
                )
            return response

    def next_url(self, response):
        next_link = response.links.get("next", {}).get("url")
        if next_link:
            self.validate_url(next_link)
        return next_link
