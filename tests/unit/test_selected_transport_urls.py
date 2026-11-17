"""Untrusted continuation references cannot extend the HTTP credential origin."""

import httpx
import pytest

from repo_catalog.adapters.github.transport import GitHubTransport
from repo_catalog.domain.models import CatalogError


@pytest.mark.parametrize(
    "value",
    [
        12345,
        "git://api.example.test/repos",
        "git:opaque",
        "https://api.example.test:99999999/repos",
        "../path",
        "ssh://api.example.test/repos",
    ],
)
def test_unsafe_continuation_never_resolves_credentials_or_sends_http(value):
    class Credentials:
        def get(self):
            raise AssertionError("unsafe URL must not resolve credentials")

    calls = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: calls.append(request))
    ) as client:
        transport = GitHubTransport(
            {
                "rest_base_url": "https://api.example.test",
                "graphql_url": "https://api.example.test/graphql",
                "token_env_var": "UNUSED_TEST_TOKEN",
            },
            object(),
            client=client,
            credentials=Credentials(),
        )
        with pytest.raises(CatalogError) as error:
            transport.validate_url(value)
        assert error.value.code == "UNSAFE_API_URL"
        if isinstance(value, str):
            response = httpx.Response(
                200,
                request=httpx.Request("GET", "https://api.example.test/repos"),
                headers={"Link": f'<{value}>; rel="next"'},
            )
            with pytest.raises((CatalogError, httpx.InvalidURL)):
                transport.next_url(response)
    assert calls == []
