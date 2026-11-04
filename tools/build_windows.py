"""Build a portable Windows release with no Python installation needed by players."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata
import os
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"


def build_executable():
    if sys.platform != "win32":
        raise SystemExit("Build the Windows executable on Windows.")
    os.chdir(ROOT)
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    pygame.init()
    icon = pygame.Surface((128, 128), pygame.SRCALPHA)
    icon.fill((6, 14, 20))
    for radius in (22, 40, 56):
        pygame.draw.circle(icon, (100, 220, 186), (64, 64), radius, 3)
    pygame.draw.line(icon, (223, 235, 226), (64, 64), (102, 26), 6)
    pygame.draw.circle(icon, (229, 104, 103), (42, 83), 6)
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    png_path = build / "icon.png"
    pygame.image.save(icon, png_path)
    png = png_path.read_bytes()
    ico = struct.pack("<HHH", 0, 1, 1) + struct.pack("<BBBBHHII", 128, 128, 0, 0, 1, 32, len(png), 22) + png
    (build / "icon.ico").write_bytes(ico)
    pygame.quit()
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                    "--name", "BelowTheSignal", "--icon", str(build / "icon.ico"),
                    "--distpath", "dist", "--workpath", "build/pyinstaller", "main.py"], check=True)
    executable = ROOT / "dist/BelowTheSignal.exe"
    subprocess.run([str(executable), "--smoke-test"], check=True, timeout=60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-only", action="store_true", help="Repackage an already built executable after documentation changes")
    args = parser.parse_args()
    if not args.package_only:
        build_executable()
    executable = ROOT / "dist/BelowTheSignal.exe"
    if not executable.exists():
        raise SystemExit("Build the executable first.")
    archive = ROOT / f"dist/BelowTheSignal-v{VERSION}-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as out:
        out.write(executable, "BelowTheSignal/BelowTheSignal.exe")
        for relative in ("README.md", "LICENSE", "docs/THIRD_PARTY_NOTICES.md"):
            file = ROOT / relative
            if file.exists():
                out.write(file, "BelowTheSignal/" + file.name)
        for file in (ROOT / "docs/licenses").rglob("*"):
            if file.is_file():
                out.write(file, "BelowTheSignal/licenses/" + file.relative_to(ROOT / "docs/licenses").as_posix())
        out.writestr("BelowTheSignal/START-HERE.txt", "BELOW THE SIGNAL\n\nExtract this entire ZIP, then open BelowTheSignal.exe.\nNo Python installation is required.\n\nWASD/arrows: move | Shift: sprint | Space: sonar | E: interact\nEsc: pause | J: recordings | M: mute | F11: fullscreen\n\nRecover three recordings and return to the docking hatch.\nSonar reveals the wreck. It also attracts something nearby.\n\nSource: https://github.com/4onv/below-the-signal\n")
        dist = importlib.metadata.distribution("pygame-ce")
        for entry in dist.files or []:
            name = str(entry).replace("\\", "/")
            if "license" in name.lower() or "copying" in name.lower():
                path = dist.locate_file(entry)
                if path.is_file():
                    out.write(path, "BelowTheSignal/licenses/pygame-ce/" + name)
        for candidate in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
            if candidate.exists():
                out.write(candidate, "BelowTheSignal/licenses/PYTHON-LICENSE.txt")
                break
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    (ROOT / "dist/SHA256SUMS.txt").write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    print(f"Packaged {archive.name} ({archive.stat().st_size / 1024 / 1024:.1f} MiB)")


if __name__ == "__main__":
    main()
