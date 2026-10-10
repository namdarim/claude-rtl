#!/usr/bin/env python3
"""Patch a copy of the installed app.asar into build/ and check the result; the installed file is
only read. Run with: python3 test/test_patch.py"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import patch_asar as pa  # noqa: E402

INSTALLED = '/usr/lib/claude-desktop/resources/app.asar'
BACKUPS = '/var/backups/claude-desktop-patch'


def original_asar():
    """The app's unpatched app.asar: the installed one, or the saved original once it is patched."""
    if not pa.is_patched(INSTALLED):
        return INSTALLED
    version = subprocess.run(['dpkg-query', '-W', '-f=${Version}', 'claude-desktop'],
                             capture_output=True, text=True, check=True).stdout.strip()
    saved = os.path.join(BACKUPS, f'app.asar.{version}')
    assert os.path.exists(saved), f'the installed app.asar is patched and {saved} is missing'
    return saved


def main():
    build = os.path.join(ROOT, 'build')
    os.makedirs(build, exist_ok=True)
    out = os.path.join(build, 'app.asar')
    pa.patch(original_asar(), out, os.path.join(ROOT, 'src'))
    assert pa.is_patched(out)

    header, base = pa.read_header(out)
    package = json.loads(pa.read_file(out, base, pa.entry(header, 'package.json')))
    original = package['rtlPatch']['originalMain']
    folder = os.path.dirname(original)
    assert package['main'] == f'{folder}/{pa.LOADER}', package['main']
    loader = pa.read_file(out, base, pa.entry(header, f'{folder}/{pa.LOADER}')).decode('utf-8')
    assert f"require('./{os.path.basename(original)}')" not in loader  # the constant is used, not inlined
    assert f"const ORIGINAL_MAIN = './{os.path.basename(original)}'" in loader, 'loader names the wrong main'

    # Both scripts must parse as the app's Node and Chromium will read them
    for name in (pa.LOADER, pa.PAGE_JS):
        path = os.path.join(build, name)
        with open(path, 'wb') as f:
            f.write(pa.read_file(out, base, pa.entry(header, f'{folder}/{name}')))
        subprocess.run(['node', '--check', path], check=True)

    try:
        pa.patch(out, out + '.again', os.path.join(ROOT, 'src'))
        raise AssertionError('patching a patched archive must fail')
    except ValueError:
        pass
    print('ok')


if __name__ == '__main__':
    main()
