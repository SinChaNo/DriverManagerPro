"""
PyInstaller build script for Driver Manager Pro.

Usage:
  python build.py            # builds both onefile + onedir
  python build.py --onefile  # portable single EXE only
  python build.py --onedir   # folder build only

수정 이력:
  2026-05-23 - onedir 빌드 후 중간 산출물(dist/DriverManagerPro.exe) 자동 삭제 추가
               (실행 불가한 중간 EXE가 최종 EXE와 혼동되는 문제 방지)
"""

from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
from pathlib import Path

HERE = Path(__file__).parent.resolve()
DIST = HERE / "dist"
BUILD = HERE / "build"


# ── Minimal icon generator (no Pillow dependency at build time) ────────────
def _make_ico(dest: Path) -> None:
    """Generate a minimal 32x32 blue icon programmatically."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, 60, 60], fill=(19, 91, 236, 255))
        draw.ellipse([20, 20, 44, 44], fill=(255, 255, 255, 200))
        img.save(dest, format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
        print(f"  Icon generated: {dest}")
    except ImportError:
        # Fallback: 1x1 transparent ICO (8 bytes minimum valid ICO)
        ico_data = (
            b"\x00\x00"   # reserved
            b"\x01\x00"   # ICO type
            b"\x01\x00"   # 1 image
            b"\x10"       # width=16
            b"\x10"       # height=16
            b"\x00"       # color count
            b"\x00"       # reserved
            b"\x01\x00"   # color planes
            b"\x20\x00"   # bits per pixel
            b"\x28\x00\x00\x00"  # size of image data
            b"\x16\x00\x00\x00"  # offset to image data
            # BITMAPINFOHEADER (40 bytes)
            b"\x28\x00\x00\x00"  # header size
            b"\x10\x00\x00\x00"  # width=16
            b"\x20\x00\x00\x00"  # height=32 (x2 for mask)
            b"\x01\x00"          # planes
            b"\x20\x00"          # bits per pixel
            b"\x00" * 24         # compression + rest zeroed
        )
        dest.write_bytes(ico_data)
        print(f"  Minimal icon written: {dest}")


# ── UAC manifest ────────────────────────────────────────────────────────────
MANIFEST = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <assemblyIdentity version="1.0.0.0" processorArchitecture="amd64"
    name="DriverManagerPro" type="win32"/>
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v3">
    <security>
      <requestedPrivileges>
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false"/>
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <!-- Windows 10 -->
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
      <!-- Windows 11 -->
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"/>
    </application>
  </compatibility>
</assembly>
"""


def _write_manifest(dest: Path) -> None:
    dest.write_text(MANIFEST, encoding="utf-8")
    print(f"  Manifest written: {dest}")


# ── PyInstaller spec builder ─────────────────────────────────────────────────
def _build_spec(mode: str, icon_path: Path, manifest_path: Path) -> str:
    name = "DriverManagerPro"
    onefile = mode == "onefile"

    datas = [
        (str(HERE / "ui"),     "ui"),
        (str(HERE / "config"), "config"),
        (str(HERE / "drivers" / "manifest.json"), "drivers"),
    ]
    datas_str = ", ".join(f"({repr(str(s))}, {repr(d)})" for s, d in datas)

    hidden = [
        "wmi", "psutil", "requests", "webview", "packaging",
        "win32api", "win32con", "win32gui", "pywintypes",
    ]
    hidden_str = ", ".join(repr(h) for h in hidden)

    exe_lines = [
        "exe = EXE(",
        "    pyz,",
        "    a.scripts,",
        "    a.binaries, a.zipfiles, a.datas," if onefile else "    [],",
        f"    name='{name}{'_portable' if onefile else ''}',",
        "    debug=False,",
        "    bootloader_ignore_signals=False,",
        "    strip=False,",
        "    upx=True,",
        "    console=False,",
        f"    icon=r'{icon_path}',",
        f"    manifest=r'{manifest_path}',",
        "    uac_admin=True,",
        "    onefile=True," if onefile else "",
        ")",
    ]

    coll_lines = []
    if not onefile:
        coll_lines = [
            "\n# onedir: also produce COLLECT",
            "coll = COLLECT(",
            "    exe,",
            "    a.binaries,",
            "    a.zipfiles,",
            "    a.datas,",
            "    strip=False,",
            "    upx=True,",
            f"    name='{name}',",
            ")",
        ]

    main_py_path = str(HERE / "main.py")
    here_path = str(HERE)

    return (
        "# -*- mode: python ; coding: utf-8 -*-\n"
        + "\n".join([
            "a = Analysis(",
            f"    [r'{main_py_path}'],",
            f"    pathex=[r'{here_path}'],",
            "    binaries=[],",
            f"    datas=[{datas_str}],",
            f"    hiddenimports=[{hidden_str}],",
            "    hookspath=[],",
            "    runtime_hooks=[],",
            "    excludes=['tkinter', 'matplotlib', 'scipy', 'numpy'],",
            "    win_no_prefer_redirects=False,",
            "    win_private_assemblies=False,",
            "    noarchive=False,",
            ")",
            "pyz = PYZ(a.pure, a.zipped_data)",
            *exe_lines,
            *coll_lines,
        ])
        + "\n"
    )


def _remove_stale_exe(dist_dir: Path, name: str, *, pre_build: bool) -> None:
    """onedir 빌드 시 dist/ 루트에 남는 중간 산출물 EXE를 삭제한다.

    COLLECT 단계가 최종 EXE를 dist/{name}/ 안으로 이동하므로 루트 EXE는 불필요.
    pre_build=True이면 빌드 전 선제 삭제(잠금 전 제거), False이면 빌드 후 재시도.
    """
    stale_exe = dist_dir / f"{name}.exe"
    if not stale_exe.exists():
        return
    try:
        stale_exe.unlink()
        label = "pre-build" if pre_build else "post-build"
        print(f"  Removed intermediate EXE ({label}): {stale_exe}")
    except PermissionError:
        if not pre_build:
            # 빌드 후에도 삭제 불가하면 올바른 경로를 안내
            final_exe = dist_dir / name / f"{name}.exe"
            print(f"  [WARNING] 중간 산출물 EXE 삭제 실패 (파일 잠금): {stale_exe}")
            print(f"  [WARNING] 실행할 올바른 파일: {final_exe}")


def run_build(mode: str) -> None:
    print(f"\n{'='*50}")
    print(f"  Building: {mode.upper()}")
    print(f"{'='*50}")

    icon_path    = HERE / "assets" / "icon.ico"
    manifest_path = HERE / "assets" / "app.manifest"
    (HERE / "assets").mkdir(exist_ok=True)

    _make_ico(icon_path)
    _write_manifest(manifest_path)

    spec_path = HERE / f"DriverManagerPro_{mode}.spec"
    spec_path.write_text(_build_spec(mode, icon_path, manifest_path), encoding="utf-8")
    print(f"  Spec written: {spec_path}")

    # onedir 빌드 전 중간 산출물 EXE 선제 삭제 (빌드 후 파일 잠금 방지)
    if mode == "onedir":
        _remove_stale_exe(DIST, "DriverManagerPro", pre_build=True)

    import subprocess
    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            str(spec_path),
            "--distpath", str(DIST),
            "--workpath", str(BUILD),
            "--noconfirm",
        ],
        cwd=str(HERE),
    )
    if result.returncode != 0:
        print(f"[ERROR] PyInstaller failed for {mode} build (exit {result.returncode})")
        sys.exit(result.returncode)

    # onedir 빌드 후 중간 산출물 EXE 재시도 삭제
    if mode == "onedir":
        _remove_stale_exe(DIST, "DriverManagerPro", pre_build=False)

    print(f"  Build OK - output in {DIST}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Driver Manager Pro build tool")
    parser.add_argument("--onefile", action="store_true", help="Build portable single EXE only")
    parser.add_argument("--onedir",  action="store_true", help="Build onedir folder only")
    args = parser.parse_args()

    modes: list[str] = []
    if args.onefile:
        modes = ["onefile"]
    elif args.onedir:
        modes = ["onedir"]
    else:
        modes = ["onedir", "onefile"]

    for mode in modes:
        run_build(mode)

    print("\nAll builds complete.")


if __name__ == "__main__":
    main()
