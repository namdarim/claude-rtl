#!/usr/bin/env python3
"""Patch the Claude desktop app's app.asar so its main entry is src/loader.js.

    patch_asar.py SRC_ASAR DST_ASAR SRC_DIR   write a patched copy of SRC_ASAR to DST_ASAR
    patch_asar.py --check ASAR                exit 0 when ASAR is patched, 1 when it is not

The patch adds three files next to the app's main entry (rtl-patch-loader.js, rtl-patch-page.js,
rtl-patch-page.css) and a new package.json whose "main" is the loader and whose "rtlPatch" records
the original main. Every other file keeps its bytes and its offset: the new files go after the old
data, and only the header grows. The result is read back and compared with the source before this
exits 0. Standard library only.
"""
import hashlib
import json
import os
import struct
import sys

PATCH_VERSION = 1
BLOCK = 4 * 1024 * 1024
LOADER, PAGE_JS, PAGE_CSS = 'rtl-patch-loader.js', 'rtl-patch-page.js', 'rtl-patch-page.css'


def read_header(path):
    """The archive's header (parsed JSON) and the offset where file data starts."""
    with open(path, 'rb') as f:
        head = f.read(16)
        if len(head) < 16 or struct.unpack('<I', head[:4])[0] != 4:
            raise ValueError(f'{path}: not an asar archive')
        pickle_size = struct.unpack('<I', head[4:8])[0]
        json_size = struct.unpack('<I', head[12:16])[0]
        header = json.loads(f.read(json_size).decode('utf-8'))
    return header, 8 + pickle_size


def entry(header, rel):
    node = header
    for part in rel.split('/'):
        node = node['files'][part]
    return node


def read_file(path, base, node):
    with open(path, 'rb') as f:
        f.seek(base + int(node['offset']))
        return f.read(node['size'])


def walk(node, prefix=''):
    """Yield (path, entry) for every packed file in the tree."""
    for name, child in node.get('files', {}).items():
        rel = f'{prefix}{name}'
        if 'files' in child:
            yield from walk(child, rel + '/')
        elif 'offset' in child and not child.get('unpacked'):
            yield rel, child


def integrity(data):
    blocks = [hashlib.sha256(data[i:i + BLOCK]).hexdigest() for i in range(0, max(len(data), 1), BLOCK)]
    return {'algorithm': 'SHA256', 'hash': hashlib.sha256(data).hexdigest(), 'blockSize': BLOCK, 'blocks': blocks}


def is_patched(path):
    header, base = read_header(path)
    package = json.loads(read_file(path, base, entry(header, 'package.json')))
    return 'rtlPatch' in package


def patch(src, dst, src_dir):
    header, base = read_header(src)
    package = json.loads(read_file(src, base, entry(header, 'package.json')))
    if 'rtlPatch' in package:
        raise ValueError(f'{src} is already patched')
    main = package['main']
    folder = os.path.dirname(main)
    with open(os.path.join(src_dir, 'loader.js'), encoding='utf-8') as f:
        loader = f.read()
    if '__ORIGINAL_MAIN__' not in loader:
        raise ValueError('loader.js has no __ORIGINAL_MAIN__ placeholder')
    loader = loader.replace('__ORIGINAL_MAIN__', './' + os.path.basename(main))
    package['main'] = f'{folder}/{LOADER}'
    package['rtlPatch'] = {'version': PATCH_VERSION, 'originalMain': main}
    new_files = {
        'package.json': (json.dumps(package, indent=2, ensure_ascii=False) + '\n').encode('utf-8'),
        f'{folder}/{LOADER}': loader.encode('utf-8'),
        f'{folder}/{PAGE_JS}': open(os.path.join(src_dir, 'page.js'), 'rb').read(),
        f'{folder}/{PAGE_CSS}': open(os.path.join(src_dir, 'page.css'), 'rb').read(),
    }

    data_size = os.path.getsize(src) - base
    cursor = data_size
    for rel, data in new_files.items():
        parent = entry(header, os.path.dirname(rel)) if '/' in rel else header
        parent['files'][os.path.basename(rel)] = {'size': len(data), 'offset': str(cursor), 'integrity': integrity(data)}
        cursor += len(data)

    text = json.dumps(header, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    payload = struct.pack('<I', len(text)) + text + b'\0' * (-len(text) % 4)
    header_pickle = struct.pack('<I', len(payload)) + payload
    tmp = dst + '.tmp'
    try:
        with open(src, 'rb') as fin, open(tmp, 'wb') as out:
            out.write(struct.pack('<II', 4, len(header_pickle)) + header_pickle)
            fin.seek(base)
            while chunk := fin.read(BLOCK):
                out.write(chunk)
            for data in new_files.values():
                out.write(data)
        verify(src, tmp, new_files)
        os.replace(tmp, dst)
    except BaseException:
        # A failed run leaves nothing next to the installed app.asar
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def verify(src, dst, new_files):
    """Every file of SRC is in DST with the same bytes, except the ones the patch replaced or added."""
    old_header, old_base = read_header(src)
    new_header, new_base = read_header(dst)
    count = 0
    for rel, node in walk(old_header):
        if rel in new_files:
            continue
        if read_file(src, old_base, node) != read_file(dst, new_base, entry(new_header, rel)):
            raise ValueError(f'{rel} differs after patching')
        count += 1
    for rel, data in new_files.items():
        if read_file(dst, new_base, entry(new_header, rel)) != data:
            raise ValueError(f'{rel} was not written as intended')
    print(f'verified: {count} files unchanged, {len(new_files)} written')


def main(argv):
    if len(argv) == 3 and argv[1] == '--check':
        return 0 if is_patched(argv[2]) else 1
    if len(argv) == 4:
        patch(argv[1], argv[2], argv[3])
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
