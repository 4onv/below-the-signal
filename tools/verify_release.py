"""Verify the shipped ZIP in a fresh directory, including a real-window render."""
from pathlib import Path
import hashlib
import os
import struct
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    archive = ROOT / "dist/BelowTheSignal-v1.0.0-Windows-x64.zip"
    expected = (ROOT / "dist/SHA256SUMS.txt").read_text().split()[0]
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == expected
    with tempfile.TemporaryDirectory(prefix="below-the-signal-release-") as temporary:
        folder = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            assert all(not Path(name).is_absolute() and ".." not in Path(name).parts for name in bundle.namelist())
            bundle.extractall(folder)
        executable = folder / "BelowTheSignal/BelowTheSignal.exe"
        assert executable.is_file()
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env.pop("SDL_VIDEODRIVER", None)
        env.pop("SDL_AUDIODRIVER", None)
        subprocess.run([str(executable), "--smoke-test"], cwd=folder, env=env, check=True, timeout=60)
        screenshots = ROOT / "build/release-verification"
        subprocess.run([str(executable), "--screenshots", str(screenshots)], cwd=folder, env=env, check=True, timeout=60)
        for name in ("title", "screenshot", "paused", "journal", "won", "lost"):
            content = (screenshots / (name + ".png")).read_bytes()
            assert content[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", content[16:24]) == (1280, 800)
        print("PASS: ZIP checksum, clean extraction, standalone launch, and six native-window rendered screens.")


if __name__ == "__main__":
    main()
