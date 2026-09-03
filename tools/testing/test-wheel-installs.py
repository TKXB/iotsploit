#!/usr/bin/env python3
"""Build each package and install each wheel into an isolated environment.

This is what catches a package that resolves at the workspace root but not
on its own -- a `poetry install` there sees every path dependency at once
and will happily mask a missing declaration.

Every temporary tree is created inside one `TemporaryDirectory` so a run
leaves nothing behind; a developer running this repeatedly used to
accumulate a wheelhouse plus one virtualenv per package each time.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import venv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGES = tuple(sorted(path.parent for path in ROOT.glob("iotsploit-*/pyproject.toml")))


def run(*args: str, cwd: Path = ROOT) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="iotsploit-wheels-") as workspace:
        _build_and_verify(Path(workspace))


def _build_and_verify(workspace: Path) -> None:
    wheelhouse = workspace / "wheelhouse"
    wheelhouse.mkdir()
    for package in PACKAGES:
        run("poetry", "build", "--format", "wheel", "--output", str(wheelhouse), cwd=package)

    wheels = sorted(wheelhouse.glob("*.whl"))
    if len(wheels) != len(PACKAGES):
        raise RuntimeError(f"built {len(wheels)} wheels for {len(PACKAGES)} packages")

    local_constraints = wheelhouse / "local-constraints.txt"
    local_constraints.write_text(
        "".join(
            f"{wheel.name.split('-', 1)[0]} @ {wheel.resolve().as_uri()}\n"
            for wheel in wheels
        ),
        encoding="utf-8",
    )

    for wheel in wheels:
        environment = workspace / wheel.stem
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        run(
            str(python),
            "-m",
            "pip",
            "install",
            "--constraint",
            str(local_constraints),
            str(wheel),
        )
        import_name = wheel.name.split("-", 1)[0]
        run(str(python), "-c", f"import {import_name}")


if __name__ == "__main__":
    main()
