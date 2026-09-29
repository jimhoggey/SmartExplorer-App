import pytest

import config


@pytest.fixture(autouse=True)
def own_config(tmp_path, monkeypatch):
    """Every test gets an empty config, never the real ~/.smart-explorer one
    (saved prompt edits there would change what the prompts say)."""
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
