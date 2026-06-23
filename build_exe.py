"""Build Windows executable with PyInstaller.

Usage:
    python build_exe.py

Or just double-click build_exe.bat for a one-click build.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = 'MidLowSpectrumPlayer'


def main():
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--noconfirm',
        '--clean',
        '--windowed',
        '--name', NAME,
        # Collect entire packages so DLLs and data files are included
        '--collect-all', 'sounddevice',
        '--collect-all', 'soundfile',
        '--collect-all', 'mutagen',
        '--collect-all', 'numpy',
        # Hidden imports not auto-detected
        '--hidden-import', 'windnd',
        '--hidden-import', 'scipy.special._cdflib',
        '--hidden-import', 'scipy.special._ufuncs',
        '--hidden-import', 'ctypes.wintypes',
        str(ROOT / 'main_midlow.py'),
    ]
    print('Running:', ' '.join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)

    dist = ROOT / 'dist' / NAME
    exe = dist / f'{NAME}.exe'
    if exe.is_file():
        print(f'\n✓ 打包完成：{exe}')
        print(f'  将整个文件夹复制到其他电脑即可运行：{dist}')
    else:
        print('Build finished; check dist folder.')


if __name__ == '__main__':
    main()
