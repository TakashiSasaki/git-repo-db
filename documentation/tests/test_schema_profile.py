"""The baseline renderer must not silently reinterpret an all-format catalog."""

import json

import pytest

from tools.schema_viz import main


def test_reject_all_format_inventory_before_rendering(tmp_path, capsys):
    inventory = tmp_path / "inventory.json"
    inventory.write_text(json.dumps({"profile": "all"}))
    with pytest.raises(SystemExit) as error:
        main(["--ir", str(inventory), "--output-dir", str(tmp_path / "output")])
    assert error.value.code == 2
    assert "--profile normal" in capsys.readouterr().err
    assert not (tmp_path / "output").exists()
