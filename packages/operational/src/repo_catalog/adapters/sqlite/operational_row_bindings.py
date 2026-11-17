"""Pure row bindings for this store; SQL and transactions stay in its adapters."""

from .operational_rows import ROW_TYPES


def insert_values(table, values, *, columns=None, constants=None):
    """Validate a complete insert while preserving its explicit parameter order.

    SQL literals participate in row validation, and only SQL-defaulted columns
    may be omitted. This function never opens a database or executes SQL.
    """
    row_type = ROW_TYPES[table]
    constants = {} if constants is None else constants
    if columns is None:
        columns = tuple(c for c in row_type.WRITE_COLUMNS if c not in constants)
    record = dict(zip(columns, values, strict=True))
    if record.keys() & constants.keys():
        raise ValueError("bound columns overlap SQL literals")
    record.update(constants)
    bound_columns, bound_values = row_type.insert_bindings(record)
    bound = dict(zip(bound_columns, bound_values, strict=True))
    return tuple(bound[column] for column in columns)


def read_record(table, record):
    """Decode existing full-row reads without broadening partial projections."""
    row_type = ROW_TYPES[table]
    if not hasattr(record, "keys"):
        record = dict(zip(row_type.COLUMNS, record, strict=True))
    row = row_type.from_record(record)
    return {column: getattr(row, column) for column in row_type.COLUMNS}


def read_values(table, record):
    return tuple(read_record(table, record).values())
