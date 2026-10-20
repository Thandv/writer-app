"""
Per-project provider settings and API keys, saved by the UI.

Stored as `KEY="value"` lines in `<project>/.env`, inside the book folder
on this machine, with owner-only permissions (0600). The file is replaced
atomically, so it is never readable by others, not even briefly.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Mapping

ENV_FILENAME = ".env"
OWNER_ONLY = 0o600

_HEADER = "# writer-app per-project settings and API keys (owner-only, 0600)\n"
_NAME_RE = re.compile(r"[A-Z_][A-Z0-9_]*")


def _validate(name: str, value: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid key name {name!r}")
    if any(c in value for c in "\"'\r\n"):
        raise ValueError(f"value for {name} contains a quote or line break")


def load_keys(output_dir: Path) -> dict[str, str]:
    """Read `<output_dir>/.env`, first tightening an existing file to 0600.
    Returns {} if there is no file."""
    env_path = Path(output_dir) / ENV_FILENAME
    if not env_path.exists():
        return {}
    os.chmod(env_path, OWNER_ONLY)
    keys = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        keys[k.strip()] = v.strip().strip('"').strip("'")
    return keys


def save_keys(output_dir: Path, keys: Mapping[str, str]) -> Path:
    """Merge `keys` into `<output_dir>/.env` and return its path. The new file
    is written to a 0600 temp file in the same directory, then renamed over
    the old one."""
    for name, value in keys.items():
        _validate(name, value)
    output_dir = Path(output_dir)
    merged = {**load_keys(output_dir), **keys}
    body = _HEADER + "".join(f'{k}="{v}"\n' for k, v in merged.items())

    env_path = output_dir / ENV_FILENAME
    # mkstemp opens with O_CREAT | O_EXCL and mode 0600, whatever the umask.
    fd, tmp = tempfile.mkstemp(dir=output_dir, prefix=".env.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
        os.replace(tmp, env_path)
    except BaseException:
        os.unlink(tmp)
        raise
    return env_path
