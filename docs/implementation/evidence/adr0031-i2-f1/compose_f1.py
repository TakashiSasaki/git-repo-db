"""External C-F1 proposal: unchanged Task C composition plus one report fence.

PYTHONPATH must include this directory, ../adr0031-i2-preparation and frozen src.
No product source imports this module. No schema/Resource/UDF redesign occurs.
"""
from pathlib import Path
from compose_proposal import compose as compose_before, configure

HERE = Path(__file__).resolve().parent


def compose():
    return compose_before() + '\n' + (HERE / 'fence.sql').read_text(encoding='utf-8')
