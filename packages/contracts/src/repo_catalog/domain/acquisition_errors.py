"""Typed input failure shared by acquisition integrations."""


class AcquisitionError(ValueError):
    """Typed acquisition domain or input validation error."""

    def __init__(self, code: str, scope: object, detail: str = ""):
        self.code = code
        self.scope = scope
        self.detail = detail
        super().__init__(f"{scope}:{code}: {detail}" if detail else f"{scope}:{code}")
