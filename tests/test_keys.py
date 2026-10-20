"""writer_app.shared.keys: the UI's .env is owner-only (0600). Dummy keys only."""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from writer_app.shared import keys as keys_mod
from writer_app.shared.keys import load_keys, save_keys

REPO = Path(__file__).resolve().parent.parent
DUMMY = {"GROQ_API_KEY": "gsk_dummy_0000", "WRITER_DRAFT_PROVIDER": "groq"}


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.fixture
def umask_022():
    old = os.umask(0o022)
    yield
    os.umask(old)


def test_save_creates_owner_only_file_under_umask_022(tmp_path, umask_022):
    env_path = save_keys(tmp_path, DUMMY)
    assert env_path == tmp_path / ".env"
    assert _mode(env_path) & 0o777 == 0o600
    assert load_keys(tmp_path) == DUMMY


def test_save_over_existing_world_readable_file_is_0600(tmp_path, umask_022):
    env_path = tmp_path / ".env"
    env_path.write_text('CEREBRAS_API_KEY="csk-dummy"\n', encoding="utf-8")
    os.chmod(env_path, 0o644)
    save_keys(tmp_path, DUMMY)
    assert _mode(env_path) == 0o600
    assert load_keys(tmp_path) == {"CEREBRAS_API_KEY": "csk-dummy", **DUMMY}
    assert [p.name for p in tmp_path.iterdir()] == [".env"]   # no temp file left


def test_load_tightens_existing_0644_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text('# old file\nGROQ_API_KEY="gsk_dummy_0000"\n'
                        "WRITER_DRAFT_PROVIDER='groq'\n", encoding="utf-8")
    os.chmod(env_path, 0o644)
    assert load_keys(tmp_path) == DUMMY
    assert _mode(env_path) == 0o600


def test_load_without_file_returns_empty(tmp_path):
    assert load_keys(tmp_path) == {}


@pytest.mark.parametrize("bad", [
    {"GROQ_API_KEY": 'gsk"dummy'},
    {"GROQ_API_KEY": "gsk'dummy"},
    {"GROQ_API_KEY": "gsk_dummy\nEVIL=1"},
    {"lower-case": "x"},
])
def test_save_rejects_values_that_break_the_format(tmp_path, bad):
    with pytest.raises(ValueError):
        save_keys(tmp_path, bad)
    assert not (tmp_path / ".env").exists()


def test_failed_write_leaves_no_temp_file(tmp_path, monkeypatch):
    def boom(src, dst):
        raise OSError("disk full")
    monkeypatch.setattr(keys_mod.os, "replace", boom)
    with pytest.raises(OSError):
        save_keys(tmp_path, DUMMY)
    assert list(tmp_path.iterdir()) == []


def test_keys_module_imports_without_streamlit():
    code = ("import sys; sys.modules['streamlit'] = None\n"
            "import writer_app.shared.keys\n"
            "assert 'streamlit' not in [m for m in sys.modules if sys.modules[m]]\n")
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    subprocess.run([sys.executable, "-c", code], env=env, check=True)
    assert "streamlit" not in Path(keys_mod.__file__).read_text(encoding="utf-8")


def test_ui_delegates_env_file_to_keys_module():
    src = (REPO / "ui" / "app.py").read_text(encoding="utf-8")
    assert "save_keys(" in src and "load_keys(" in src
    assert 'output_dir / ".env"' not in src
