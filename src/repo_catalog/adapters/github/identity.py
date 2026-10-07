"""Provider database identities, without GraphQL Node-ID aliasing or decoding."""


def database_resource_id(value: object) -> str:
    """Accept a positive decimal database ID, preserving string spelling exactly."""
    if type(value) is int and value > 0:
        return str(value)
    if (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and value.strip("0")
    ):
        return value
    raise ValueError("A canonical GitHub database ID is required")
