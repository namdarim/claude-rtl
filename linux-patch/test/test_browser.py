#!/usr/bin/env python3
"""Load test/fixture.html with src/page.js and page.css in headless Chrome and check every element:
the ones the fixture expects marked are, and nothing else is. Optionally save a screenshot.

    python3 test/test_browser.py [--screenshot PATH]
"""
import html
import json
import os
import re
import subprocess
import sys

CHROME = '/usr/bin/google-chrome'
HERE = os.path.dirname(os.path.abspath(__file__))
URL = 'file://' + os.path.join(HERE, 'fixture.html')
FLAGS = ['--headless=new', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--virtual-time-budget=5000']


def main(argv):
    out = subprocess.run([CHROME, *FLAGS, '--dump-dom', URL], capture_output=True, text=True, timeout=120).stdout
    match = re.search(r'<pre id="report"[^>]*>(.*?)</pre>', out, re.S)
    if not match or not match.group(1).strip():
        print('FAIL: the fixture wrote no report')
        return 1
    results = json.loads(html.unescape(match.group(1)))
    failed = [r for r in results if not r['ok']]
    for r in failed:
        print(f"FAIL {r['el']}: want {r['want']}, got {r['got']}")
    print(f'{len(results) - len(failed)} of {len(results)} elements as expected')
    if len(argv) == 3 and argv[1] == '--screenshot':
        subprocess.run([CHROME, *FLAGS, '--window-size=1100,700', f'--screenshot={argv[2]}', URL],
                       capture_output=True, timeout=120, check=True)
        print(f'screenshot: {argv[2]}')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
