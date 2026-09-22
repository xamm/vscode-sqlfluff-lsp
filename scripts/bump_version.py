"""Keep npm, Python package, and runtime versions in sync."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
RUNTIME_VERSION_PATTERN = re.compile(r'^__version__ = "[^"]+"$', re.MULTILINE)
RUNTIME_VERSION_PATH = Path("sqlfluff_lsp/__init__.py")


def main() -> None:
    """Set the release version in every authoritative project file."""
    parser = argparse.ArgumentParser()
    parser.add_argument("version")
    arguments = parser.parse_args()
    version = arguments.version
    if VERSION_PATTERN.fullmatch(version) is None:
        parser.error("version must use MAJOR.MINOR.PATCH format")

    npm = shutil.which("npm")
    uv = shutil.which("uv")
    if npm is None or uv is None:
        raise RuntimeError("npm and uv must be available on PATH")

    subprocess.run(  # noqa: S603 - fixed executable with a validated version
        [
            npm,
            "version",
            version,
            "--no-git-tag-version",
            "--ignore-scripts",
            "--allow-same-version",
        ],
        check=True,
    )
    subprocess.run(  # noqa: S603 - fixed executable with a validated version
        [uv, "version", version, "--no-sync"],
        check=True,
    )

    source = RUNTIME_VERSION_PATH.read_text(encoding="utf-8")
    updated, replacements = RUNTIME_VERSION_PATTERN.subn(
        f'__version__ = "{version}"', source
    )
    if replacements != 1:
        raise RuntimeError(
            f"Expected one version assignment in {RUNTIME_VERSION_PATH}, "
            f"found {replacements}"
        )
    RUNTIME_VERSION_PATH.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
