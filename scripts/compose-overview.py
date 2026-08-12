#!/usr/bin/env python3
"""Compose four stat cards into ONE composite SVG (2-column x 2-row grid).

Reads the four generated cards:
  profile/stats.svg        GitHub Stats
  profile/top-langs.svg    Most Used Languages
  profile/ai-powered.svg   AI-Powered Projects
  profile/streaks.svg      Streaks

Each card is a standalone SVG with its own <style> block. Nesting four styled
SVGs in one document would let their CSS classes / @keyframes / element IDs
collide (the github-readme-stats cards share names like .stat, .header,
fadeInAnimation, titleId...). So each card is first **namespaced** (every class,
keyframe and id prefixed with c0-/c1-/...) and then embedded as a nested <svg>
positioned in a 2x2 grid. The result is a single static image the README can
reference, keeping the "works anytime" guarantee (no live API at view time).

Output:
  profile/overview.svg
"""
import os
import re
import sys

# (path, label) in grid order: row0 = Stats | Languages, row1 = AI | Streaks
CARDS = [
    ("profile/stats.svg", "GitHub Stats"),
    ("profile/top-langs.svg", "Most Used Languages"),
    ("profile/ai-powered.svg", "AI-Powered Projects"),
    ("profile/streaks.svg", "Streaks"),
]

CELL_W, CELL_H, GAP = 440, 232, 16


def namespace(prefix, css, body):
    """Prefix every class, @keyframes name and element id in one card so it
    cannot clash with another card once both live in the same SVG document."""
    # ids used in this card (collected before any rewriting)
    ids = set(re.findall(r'\bid="([^"]+)"', body)) | set(
        re.findall(r"\bid='([^']+)'", body)
    )

    # @keyframes names -> rename declaration + every reference (names are
    # distinctive, so a plain word-boundary replace is safe).
    for name in set(re.findall(r"@keyframes\s+([A-Za-z_]\w*)", css)):
        css = re.sub(r"\b" + re.escape(name) + r"\b", f"{prefix}-{name}", css)

    # class selectors: .name -> .prefix-name  (safe: a "." followed by a letter
    # is always a class selector here, never a number like 0.5 or a hex color).
    css = re.sub(
        r"\.([A-Za-z_][\w-]*)", lambda m: f".{prefix}-{m.group(1)}", css
    )

    # id selectors in CSS: #name -> #prefix-name, but only for ids that actually
    # exist in this card (avoids mangling hex colors like #fffefe).
    for name in ids:
        css = re.sub(
            r"(?<![\w-])#" + re.escape(name) + r"(?![\w-])",
            f"#{prefix}-{name}",
            css,
        )

    # body: class="a b" -> class="prefix-a prefix-b" (handles single quotes too)
    def repl_class(m):
        q, val = m.group(1), m.group(2)
        renamed = " ".join(f"{prefix}-{v}" for v in val.split())
        return f"class={q}{renamed}{q}"

    body = re.sub(r'class=(["\'])([^"\']*)\1', repl_class, body)

    # body: id="x" -> id="prefix-x"
    body = re.sub(
        r'\bid="([^"]+)"', lambda m: f'id="{prefix}-{m.group(1)}"', body
    )
    body = re.sub(
        r"\bid='([^']+)'", lambda m: f"id='{prefix}-{m.group(1)}'", body
    )

    # body: references to ids (url(#x), href="#x")
    for name in ids:
        body = re.sub(
            r"(?<![\w-])#" + re.escape(name) + r"(?![\w-])",
            f"#{prefix}-{name}",
            body,
        )

    # body: aria-labelledby="a b" tokens
    def repl_aria(m):
        q, val = m.group(1), m.group(2)
        renamed = " ".join(f"{prefix}-{v}" for v in val.split())
        return f"aria-labelledby={q}{renamed}{q}"

    body = re.sub(r'aria-labelledby=(["\'])([^"\']*)\1', repl_aria, body)

    return css, body


def parse_card(path, idx):
    prefix = f"c{idx}"
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    open_tag = re.search(r"<svg\b[^>]*>", text)
    if not open_tag:
        print(f"warning: {path} has no <svg> tag; skipping", file=sys.stderr)
        return None
    head = open_tag.group(0)
    inner = text[open_tag.end() : text.rfind("</svg>")]

    vb = re.search(r'viewBox=["\']0 0 ([\d.]+) ([\d.]+)["\']', head)
    if vb:
        nat_w, nat_h = float(vb.group(1)), float(vb.group(2))
    else:
        w = re.search(r'\bwidth=["\']([\d.]+)', head)
        h = re.search(r'\bheight=["\']([\d.]+)', head)
        nat_w = float(w.group(1)) if w else CELL_W
        nat_h = float(h.group(1)) if h else CELL_H

    sm = re.search(r"<style[^>]*>(.*?)</style>", inner, re.S)
    if sm:
        css, body = sm.group(1), inner[: sm.start()] + inner[sm.end() :]
    else:
        css, body = "", inner

    css, body = namespace(prefix, css, body)
    return nat_w, nat_h, css, body, prefix


def build():
    cells = [None] * 4
    for i, (path, _label) in enumerate(CARDS):
        if not os.path.exists(path):
            print(f"warning: {path} missing — leaving cell {i} empty", file=sys.stderr)
            continue
        parsed = parse_card(path, i)
        if parsed:
            cells[i] = parsed

    pw = 2 * CELL_W + GAP
    ph = 2 * CELL_H + GAP
    out = [
        f'<svg width="{pw}" height="{ph}" viewBox="0 0 {pw} {ph}" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="ovTitle">',
        '<title id="ovTitle">Trang Nguyen&#39;s GitHub overview</title>',
    ]

    for i, cell in enumerate(cells):
        if not cell:
            continue
        nat_w, nat_h, css, body, prefix = cell
        col, row = i % 2, i // 2
        cell_x = col * (CELL_W + GAP)
        cell_y = row * (CELL_H + GAP)
        scale = min(CELL_W / nat_w, CELL_H / nat_h)
        disp_w = nat_w * scale
        disp_h = nat_h * scale
        x = cell_x + (CELL_W - disp_w) / 2
        y = cell_y + (CELL_H - disp_h) / 2
        out.append(
            f'<svg x="{x:.2f}" y="{y:.2f}" width="{disp_w:.2f}" '
            f'height="{disp_h:.2f}" viewBox="0 0 {nat_w:g} {nat_h:g}" '
            f'preserveAspectRatio="xMidYMid meet">'
        )
        if css.strip():
            out.append(f"<style>{css}</style>")
        out.append(body)
        out.append("</svg>")

    out.append("</svg>")
    os.makedirs("profile", exist_ok=True)
    with open("profile/overview.svg", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"wrote profile/overview.svg ({pw}x{ph})")


if __name__ == "__main__":
    build()
