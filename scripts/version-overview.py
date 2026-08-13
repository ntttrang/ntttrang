#!/usr/bin/env python3
"""Version the overview image by content hash and point the README at it.

GitHub's /raw/ redirect strips ?query= strings, so the cache-busting version
has to live in the FILENAME: a new filename is a genuinely new URL to every
cache (browser, CDN, camo), so the README can never display a stale card. The
hash is derived from overview.svg, so it only changes when the card actually
changes (no churn otherwise).

Run after compose-overview.py has written profile/overview.svg. Idempotent:
deletes every prior profile/overview-*.svg before writing the current one, so
old versions never accumulate.
"""
import glob
import hashlib
import pathlib
import re

OVERVIEW = pathlib.Path("profile/overview.svg")
content = OVERVIEW.read_bytes()
digest = hashlib.sha1(content).hexdigest()[:10]
name = f"overview-{digest}.svg"

for f in glob.glob("profile/overview-*.svg"):            # drop every prior version
    pathlib.Path(f).unlink()

(pathlib.Path("profile") / name).write_bytes(content)    # versioned copy

readme = pathlib.Path("README.md")
text = readme.read_text()
new_text, n = re.subn(r'src="\./profile/overview[^"]*"', f'src="./profile/{name}"', text)
readme.write_text(new_text)
print(f"wrote profile/{name}; README src updated (replacements={n})")
