"""Bind Context rows without widening operation-specific SQL reads or writes."""


def context_write_values(row_type, columns, values, *, null_columns=()):
    """Validate a complete write and retain the explicit statement's column order.

    Some Context statements deliberately omit nullable subtype/scope columns.
    Their callers name those implicit SQL NULLs explicitly for the row codec;
    generated columns are never supplied. This helper does not execute SQL.
    """
    record = dict(zip(columns, values, strict=True))
    for name in null_columns:
        if name in record:
            raise ValueError("explicit and omitted Context columns overlap")
        record[name] = None
    bound_columns, bound_values = row_type.insert_bindings(record)
    bound = dict(zip(bound_columns, bound_values, strict=True))
    return tuple(bound[name] for name in columns)
