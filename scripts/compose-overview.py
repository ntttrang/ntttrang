#!/usr/bin/env python3
"""Compose four stat cards into ONE composite SVG as a clean 2x2 grid.

Reads the four generated cards:
  profile/stats.svg        GitHub Stats
  profile/top-langs.svg    Most Used Languages
  profile/ai-powered.svg   AI-Powered Projects
  profile/streaks.svg      Streaks

The four source cards have very different native aspect ratios (the wide stats
card vs. the nearly-square top-langs card), so simply tiling them preserves
those ratios and yields four mismatched rectangles -- an ugly, ragged grid.

To get four IDENTICAL-sized cards, the composer does two things per card:
  1. strips the card's own background rect (every card marks it with
     data-testid="card-bg"), and
  2. scales the remaining CONTENT uniformly (contain) into one fixed-size cell.
The composer then draws a single uniform background frame for every cell, so all
four cards end up the exact same width and height -- a clean, aligned 2x2 grid.

Each card also carries its own <style> block, and nesting four styled SVGs in
one document would let their CSS classes / @keyframes / element ids collide (the
github-readme-stats cards share names like .stat, .header, fadeInAnimation,
titleId...). So each card is first **namespaced** (every class, keyframe and id
prefixed with c0-/c1-/...) before being embedded.

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

# Every cell is exactly this size -> all four cards are identical rectangles.
CELL_W, CELL_H, GAP = 460, 220, 16

# Visual style of the uniform card frame (matches github-readme-stats default).
BG = "#fffefe"
BORDER = "#e4e2e2"

# Matches the per-card background rect (self-closing or not, single- or
# multi-line). Every card marks its bg rect with data-testid="card-bg".
BG_RECT_RE = re.compile(r'<rect\b[^>]*\bdata-testid="card-bg"[^>]*/?>')


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
    """Return (nat_w, nat_h, css, content, prefix). `content` is the card body
    with its <style> split out and its background rect removed."""
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

    body = BG_RECT_RE.sub("", body)  # composer draws the uniform frame instead
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
        # Uniform "contain" scale: content stays proportional, no distortion.
        scale = min(CELL_W / nat_w, CELL_H / nat_h)
        disp_w = nat_w * scale
        disp_h = nat_h * scale
        ox = (CELL_W - disp_w) / 2
        oy = (CELL_H - disp_h) / 2

        out.append(
            f'<svg x="{cell_x}" y="{cell_y}" width="{CELL_W}" '
            f'height="{CELL_H}" viewBox="0 0 {CELL_W} {CELL_H}">'
        )
        if css.strip():
            out.append(f"<style>{css}</style>")
        # The single uniform card frame -- identical for every cell.
        out.append(
            f'<rect x="0.5" y="0.5" width="{CELL_W - 1}" height="{CELL_H - 1}" '
            f'rx="4.5" fill="{BG}" stroke="{BORDER}" stroke-opacity="1"/>'
        )
        # Card content, uniformly scaled + centered inside the frame.
        out.append(
            f'<g transform="translate({ox:.2f} {oy:.2f}) scale({scale:.4f})">'
        )
        out.append(body)
        out.append("</g>")
        out.append("</svg>")

    out.append("</svg>")
    os.makedirs("profile", exist_ok=True)
    with open("profile/overview.svg", "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"wrote profile/overview.svg ({pw}x{ph})")


if __name__ == "__main__":
    build()
