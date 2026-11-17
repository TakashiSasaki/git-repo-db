"""Explicit synthetic transport settings, independent of retired catalog.toml."""

TRANSPORT_SETTINGS = {
    "rest_base_url": "https://api.github.com",
    "graphql_url": "https://api.github.com/graphql",
    "token_env_var": "GH_TOKEN",
    "rest_api_version": "2026-03-10",
    "rest_page_size": 100,
    "graphql_page_size": 100,
    "connect_timeout_seconds": 10,
    "read_timeout_seconds": 60,
    "max_attempts": 5,
    "record_messages": False,
}
