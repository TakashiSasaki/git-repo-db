from typing import Protocol


class CredentialProvider(Protocol):
    def get(self) -> str | None: ...


class Clock(Protocol):
    def time(self) -> float: ...


class HttpTransport(Protocol):
    def request(self, method: str, url: str, **kwargs): ...
