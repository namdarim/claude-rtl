#!/usr/bin/env python3
"""Patch a copy of the installed app.asar into build/ and check the result; the installed file is
only read. Run with: python3 test/test_patch.py"""
import json
import os
import shutil
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

    # Every src/addons/*.js is packed next to the loader with the add-on prefix; the public patch has none
    addon_dir = os.path.join(ROOT, 'src', 'addons')
    addons = [f'{pa.ADDON_PREFIX}{name}' for name in sorted(os.listdir(addon_dir) if os.path.isdir(addon_dir) else [])
              if name.endswith('.js')]
    packed = sorted(name for name in pa.entry(header, folder)['files'] if name.startswith(pa.ADDON_PREFIX))
    assert packed == addons, (packed, addons)

    # The scripts must parse as the app's Node and Chromium will read them
    for name in (pa.LOADER, pa.PAGE_JS, *addons):
        path = os.path.join(build, name)
        with open(path, 'wb') as f:
            f.write(pa.read_file(out, base, pa.entry(header, f'{folder}/{name}')))
        subprocess.run(['node', '--check', path], check=True)

    # A sample add-on gets packed too, and the loader runs every add-on, then the app's main entry,
    # even when one of them fails
    sample_src = os.path.join(build, 'src-with-addon')
    shutil.rmtree(sample_src, ignore_errors=True)
    shutil.copytree(os.path.join(ROOT, 'src'), sample_src)
    os.makedirs(os.path.join(sample_src, 'addons'), exist_ok=True)
    with open(os.path.join(sample_src, 'addons', 'sample.js'), 'w') as f:
        f.write("console.log('sample')\n")
    with_addon = os.path.join(build, 'with-addon.asar')
    pa.patch(original_asar(), with_addon, sample_src)
    addon_header, addon_base = pa.read_header(with_addon)
    assert pa.read_file(with_addon, addon_base, pa.entry(addon_header, f'{folder}/{pa.ADDON_PREFIX}sample.js')) \
        == b"console.log('sample')\n", 'the sample add-on was not packed'
    run = os.path.join(build, 'loader-run')
    shutil.rmtree(run, ignore_errors=True)
    os.makedirs(os.path.join(run, 'node_modules', 'electron'))
    files = {
        'node_modules/electron/index.js': 'module.exports = { app: { on() {} } }\n',
        pa.LOADER: loader.replace(f"const ORIGINAL_MAIN = './{os.path.basename(original)}'",
                                  "const ORIGINAL_MAIN = './main.js'"),
        pa.PAGE_JS: '', pa.PAGE_CSS: '',
        f'{pa.ADDON_PREFIX}a.js': "console.log('a')\n",
        f'{pa.ADDON_PREFIX}b.js': "throw new Error('broken add-on')\n",
        f'{pa.ADDON_PREFIX}c.js': "console.log('c')\n",
        'main.js': "console.log('main')\n",
    }
    for name, text in files.items():
        with open(os.path.join(run, name), 'w') as f:
            f.write(text)
    result = subprocess.run(['node', os.path.join(run, pa.LOADER)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ['a', 'c', 'main'], result.stdout
    assert 'add-on rtl-patch-addon-b.js failed' in result.stderr and 'broken add-on' in result.stderr, result.stderr

    try:
        pa.patch(out, out + '.again', os.path.join(ROOT, 'src'))
        raise AssertionError('patching a patched archive must fail')
    except ValueError:
        pass

    # A patch that fails after writing leaves nothing behind, not even its temporary file: the apt hook
    # runs this unattended next to the installed app.asar
    failed = os.path.join(build, 'failed.asar')

    def broken_verify(*_):
        raise ValueError('simulated mismatch')
    real_verify, pa.verify = pa.verify, broken_verify
    try:
        pa.patch(original_asar(), failed, os.path.join(ROOT, 'src'))
        raise AssertionError('a failed check must fail the patch')
    except ValueError:
        pass
    finally:
        pa.verify = real_verify
    assert not os.path.exists(failed) and not os.path.exists(failed + '.tmp'), 'a failed patch left files'
    print('ok')


if __name__ == '__main__':
    main()
