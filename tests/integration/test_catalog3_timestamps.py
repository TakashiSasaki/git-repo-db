"""Exact timestamp boundaries and the persisted Catalog3/workspace time contract."""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from importlib.resources import files

import pytest

from repo_catalog.domain import time as catalog_time
from repo_catalog.domain.time import (
    datetime_to_us,
    format_iso8601_us,
    now_us,
    parse_iso8601_us,
    unix_seconds_to_us,
    validate_epoch_us,
)

MIN_INT64 = -(1 << 63)
MAX_INT64 = (1 << 63) - 1


@pytest.mark.parametrize(
    "iso_utc,expected",
    [
        ("1970-01-01T00:00:00.000000Z", 0),
        ("1969-12-31T23:59:59.999999Z", -1),
        ("1970-01-01T00:00:00.000001Z", 1),
        ("2026-10-07T09:00:00.123456Z", 1_791_363_600_123_456),
        ("0001-01-01T00:00:00.000001Z", -62_135_596_799_999_999),
        ("9999-12-31T23:59:59.999999Z", 253_402_300_799_999_999),
    ],
)
def test_exact_calendar_conversion_and_roundtrip(iso_utc, expected):
    assert parse_iso8601_us(iso_utc) == expected
    assert datetime_to_us(datetime.fromisoformat(iso_utc)) == expected
    assert format_iso8601_us(expected) == iso_utc


@pytest.mark.parametrize(
    "same_instant",
    [
        "2026-10-07T09:00:00.123456Z",
        "2026-10-07T18:00:00.123456+09:00",
        "2026-10-07T03:30:00.123456-05:30",
        "2026-10-07T09:00:00.123456000Z",
    ],
)
def test_offset_and_extra_zero_digits_do_not_change_absolute_time(same_instant):
    assert parse_iso8601_us(same_instant) == 1_791_363_600_123_456


@pytest.mark.parametrize(
    "same_instant",
    [
        "19700101T000000Z",
        "1970-W01-4T00:00:00Z",
        "1970W014T000000Z",
        "1970-01-01 00:00:00,0000000+00:00",
        "1970-01-01t00Z",
        "1970-01-01T00:00+00",
        "19700101T0000-0000",
        "1970-01-01T00:00:30+000030",
        "1969-12-31T23:59:30-00:00:30",
    ],
)
def test_supported_iso_spellings_keep_the_same_instant(same_instant):
    assert parse_iso8601_us(same_instant) == 0


@pytest.mark.parametrize("clock", ["01.5", "01,5", "01:30.5", "0130,5"])
def test_fractional_hours_and_minutes_are_not_misread_as_fractional_seconds(clock):
    with pytest.raises(ValueError, match="Fractional hours and minutes"):
        parse_iso8601_us(f"1970-01-01T{clock}Z")


@pytest.mark.parametrize("offset", ["00:60", "0060", "00:00:60", "000060", "24"])
@pytest.mark.parametrize("sign", ["+", "-"])
def test_invalid_offset_components_cannot_be_normalized(offset, sign):
    with pytest.raises(ValueError, match="Invalid timezone offset component"):
        parse_iso8601_us(f"1970-01-01T00:00:00{sign}{offset}")


def test_adjacent_microseconds_remain_distinct():
    first = parse_iso8601_us("2026-10-07T09:00:00.123456Z")
    second = parse_iso8601_us("2026-10-07T09:00:00.123457Z")
    assert second - first == 1
    assert format_iso8601_us(first) != format_iso8601_us(second)


@pytest.mark.parametrize(
    "invalid",
    [
        "2026-10-07",
        "2026-10-07T09:00:00",
        "2026-10-07T09:00:00.123456",
        "2026-10-07T09:00:00.1234567Z",
        "2026-10-07T09:00:00.123456001Z",
        "1970-01-01T00:00:00+00:00:00.000001",
        "1970-01-01T00:00:00-00:00:00.000001",
        "1970-01-01T00:00:00+00:00:00.000000",
        "not-a-timestamp",
    ],
)
def test_iso_boundary_rejects_missing_timezone_or_unrepresentable_time(invalid):
    with pytest.raises(ValueError):
        parse_iso8601_us(invalid)


def test_datetime_boundary_requires_timezone():
    with pytest.raises(ValueError):
        datetime_to_us(datetime(1970, 1, 1))
    assert datetime_to_us(datetime(1970, 1, 1, tzinfo=UTC)) == 0


@pytest.mark.parametrize("offset", ["00", "0000", "00:00", "000000", "00:00:00"])
@pytest.mark.parametrize("sign", ["+", "-"])
@pytest.mark.parametrize("fraction", [".000001", ",000001"])
def test_all_fractional_offset_spellings_are_explicitly_rejected(
    offset, sign, fraction
):
    value = f"1970-01-01T00:00:00{sign}{offset}{fraction}"
    with pytest.raises(ValueError, match="Fractional timezone offsets"):
        parse_iso8601_us(value)


@pytest.mark.parametrize("offset", ["00", "00:00:00"])
@pytest.mark.parametrize("sign", ["+", "-"])
def test_nul_cannot_bypass_fractional_offset_validation(offset, sign):
    with pytest.raises(ValueError):
        parse_iso8601_us(f"1970-01-01T00:00:00{sign}{offset}.000001\x00")


@pytest.mark.parametrize("value", [MIN_INT64, -1, 0, 1, MAX_INT64])
def test_internal_timestamp_accepts_the_entire_signed_int64_range(value):
    assert validate_epoch_us(value) == value


@pytest.mark.parametrize("value", [MIN_INT64 - 1, MAX_INT64 + 1])
def test_internal_timestamp_rejects_int64_overflow(value):
    with pytest.raises(ValueError):
        validate_epoch_us(value)


@pytest.mark.parametrize("value", [True, False, None, 0.0, 1.5, "0", Decimal("0")])
def test_internal_timestamp_does_not_coerce_non_integer_values(value):
    with pytest.raises(TypeError):
        validate_epoch_us(value)
    with pytest.raises(TypeError):
        format_iso8601_us(value)


@pytest.mark.parametrize("value", [MIN_INT64, MAX_INT64])
def test_calendar_formatting_rejects_valid_storage_times_outside_datetime_range(value):
    assert validate_epoch_us(value) == value
    with pytest.raises(ValueError):
        format_iso8601_us(value)


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (0, 0),
        (-1, -1_000_000),
        (0.000001, 1),
        (-0.000001, -1),
        (1.234567, 1_234_567),
        ("1791363600.123456", 1_791_363_600_123_456),
        (Decimal("1791363600.123456"), 1_791_363_600_123_456),
        ("0.0000009", 0),
        ("-0.0000001", -1),
        ("1791363600.123455999999999999999999999999", 1_791_363_600_123_455),
        ("-1791363600.123456000000000000000000000001", -1_791_363_600_123_457),
        ("-1e-999999999999999999", -1),
        ("9223372036854.775807", MAX_INT64),
        ("-9223372036854.775808", MIN_INT64),
    ],
)
def test_external_seconds_conversion_is_exact_and_floors_submicroseconds(
    seconds, expected
):
    assert unix_seconds_to_us(seconds) == expected


@pytest.mark.parametrize(
    "seconds",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "not-seconds",
        "1e999999999999999999",
        "9223372036854.775808",
        "-9223372036854.775809",
    ],
)
def test_external_seconds_rejects_invalid_nonfinite_or_out_of_range_values(seconds):
    with pytest.raises(ValueError):
        unix_seconds_to_us(seconds)


def test_external_seconds_are_independent_of_ambient_decimal_precision():
    with localcontext() as context:
        context.prec = 6
        assert unix_seconds_to_us("1791363600.123456") == 1_791_363_600_123_456
        assert unix_seconds_to_us("9223372036854.775807") == MAX_INT64


@pytest.mark.parametrize("value", [True, None, b"0"])
def test_external_boundaries_reject_incorrect_input_types(value):
    with pytest.raises(TypeError):
        unix_seconds_to_us(value)
    with pytest.raises(TypeError):
        parse_iso8601_us(value)
    with pytest.raises(TypeError):
        datetime_to_us(value)


@pytest.mark.parametrize(
    "nanoseconds,expected",
    [(0, 0), (-1, -1), (1_791_363_600_123_456_999, 1_791_363_600_123_456)],
)
def test_current_clock_keeps_integer_microseconds(monkeypatch, nanoseconds, expected):
    monkeypatch.setattr(catalog_time.time, "time_ns", lambda: nanoseconds)
    assert now_us() == expected
    assert type(now_us()) is int


@pytest.fixture(params=["catalog3.sql", "import_v2/workspace.sql"])
def timestamp_database(request):
    with sqlite3.connect(":memory:") as db:
        sql = files("repo_catalog").joinpath("resources", request.param).read_text()
        db.executescript(sql)
        yield db, request.param


def test_all_persisted_absolute_time_columns_have_units_and_integer_types(
    timestamp_database,
):
    db, resource = timestamp_database
    irregular_names = {
        "safe_watermark",
        "last_used",
        "not_before",
        "first_seen",
        "last_seen",
    }
    temporal_columns = []
    for (table,) in db.execute("SELECT name FROM sqlite_schema WHERE type='table'"):
        for column in db.execute(f'PRAGMA table_info("{table}")'):
            name, kind = column[1:3]
            base_name = name.removesuffix("_us")
            if base_name.endswith("_at") or base_name in irregular_names:
                temporal_columns.append((table, name))
                assert name.endswith("_us"), (resource, table, name)
                assert kind == "INTEGER", (resource, table, name, kind)
    assert temporal_columns, resource


def test_sqlite_preserves_integer_range_order_and_rejects_other_storage_types(
    timestamp_database,
):
    db, resource = timestamp_database
    if resource == "catalog3.sql":
        insert = "INSERT INTO contents(content_id,byte_length,text_state,created_at_us) VALUES(?,0,'unknown',?)"
        table, column = "contents", "created_at_us"
    else:
        insert = "INSERT INTO reanalysis_runs(reanalysis_run_id,parser_version,parsed_at_us,evidence) VALUES(?,'timestamp-test',?,'{}')"
        table, column = "reanalysis_runs", "parsed_at_us"
    values = [MAX_INT64, 0, -1, MIN_INT64, 1]
    for index, value in enumerate(values):
        key = index if resource == "catalog3.sql" else str(index)
        db.execute(insert, (key, value))
    assert db.execute(
        f"SELECT {column},typeof({column}) FROM {table} ORDER BY {column}"
    ).fetchall() == [(value, "integer") for value in sorted(values)]
    assert db.execute(f"SELECT MAX({column}) FROM {table}").fetchone()[0] == MAX_INT64
    for index, invalid in enumerate((1.5, "2026-10-07T09:00:00Z", b"0"), start=5):
        key = index if resource == "catalog3.sql" else str(index)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(insert, (key, invalid))
