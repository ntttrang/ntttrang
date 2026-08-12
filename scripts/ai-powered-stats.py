#!/usr/bin/env python3
"""Generate an "AI-Powered Projects" SVG card for a GitHub profile README.

Scans an owner's non-fork, non-empty public repositories for AI-tool config
markers (.claude / .cursor / .agent / .agentkit and common file variants such
as CLAUDE.md, .cursorrules, AGENTS.md) and renders a static SVG card that
matches the github-readme-stats visual style. The card is committed to the
profile repo by the GitHub Actions workflow, so profile views never hit the
API at view time.

Environment:
  GITHUB_TOKEN  GitHub token (PAT or the Actions GITHUB_TOKEN) for auth + rate
                limits. If unset, falls back to anonymous (heavily rate-limited).
  OWNER         GitHub username to scan (default: ntttrang).

Output:
  profile/ai-powered.svg
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
OWNER = os.environ.get("OWNER") or "ntttrang"
TOKEN = os.environ.get("GITHUB_TOKEN") or ""

# --- Visual style (matches github-readme-stats default theme) -----------------
BG = "#fffefe"
BORDER = "#e4e2e2"
TITLE_COLOR = "#2f80ed"
TEXT_COLOR = "#434d58"
MUTED = "#858585"
TRACK = "#e4e2e2"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
CARD_W = 480

# --- Markers -------------------------------------------------------------------
# Display order: (key, label, color, matcher). matcher(c, basename) -> bool,
# where c is a lowercased path component and basename is the lowercased file name.
# AgentKit is listed before Agent so .agentkit is never mis-counted as .agent.
def _claude(c, b):
    return c.startswith(".claude") or b == "claude.md"


def _cursor(c, b):
    return c.startswith(".cursor")


def _agentkit(c, b):
    return c.startswith(".agentkit")


def _agent(c, b):
    return (c.startswith(".agent") and not c.startswith(".agentkit")) or b == "agents.md"


TOOLS = [
    ("cursor", "Cursor", "#4c71f2", _cursor),
    ("claude", "Claude", "#d97757", _claude),
    ("agent", "Agent", "#2ea043", _agent),
    ("agentkit", "AgentKit", "#a371f7", _agentkit),
]


# --- GitHub API helpers --------------------------------------------------------
def api_get(path):
    url = f"{API}{path}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-powered-stats",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, None, dict(e.headers)
    except urllib.error.URLError as e:
        print(f"request error for {path}: {e}", file=sys.stderr)
        return 0, None, {}


def list_repos(owner):
    repos, page = [], 1
    while True:
        status, data, headers = api_get(
            f"/users/{owner}/repos?per_page=100&type=owner&sort=updated&page={page}"
        )
        if status != 200 or not isinstance(data, list):
            break
        repos.extend(data)
        if 'rel="next"' not in headers.get("Link", ""):
            break
        page += 1
    return repos


def tree_paths(owner, repo, branch):
    """Return all file paths in a repo branch, or None if empty/unreadable.

    Note: the repo-listing `size` field is unreliable (GitHub often reports 0 for
    non-empty repos), so we don't pre-filter on it — we just try the tree and skip
    repos that come back empty (HTTP 409) or unreadable.
    """
    status, tree, _ = api_get(f"/repos/{owner}/{repo}/git/trees/{branch}?recursive=1")
    if status != 200 or not tree:
        return None
    if tree.get("truncated"):
        print(f"  note: {repo} tree truncated; results may be incomplete", file=sys.stderr)
    return [t.get("path", "") for t in tree.get("tree", [])]


def classify(paths):
    """Return {tool_key: bool} for whether each marker is present."""
    found = {key: False for key, *_ in TOOLS}
    for p in paths:
        comps = p.split("/")
        basename = comps[-1].lower()
        for comp in comps:
            c = comp.lower()
            for key, _label, _color, matcher in TOOLS:
                if matcher(c, basename):
                    found[key] = True
    return found


# --- SVG rendering -------------------------------------------------------------
def esc(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def robot_icon():
    """A small bot drawn from primitives (no emoji -> renders everywhere)."""
    return (
        '<g transform="translate(28,16)">'
        '<line x1="11" y1="0" x2="11" y2="4" stroke="#2f80ed" stroke-width="2"/>'
        '<circle cx="11" cy="0" r="2.6" fill="#2f80ed"/>'
        '<rect x="0" y="4" width="22" height="16" rx="4" fill="none" stroke="#2f80ed" stroke-width="2"/>'
        '<circle cx="6.5" cy="12" r="2" fill="#2f80ed"/>'
        '<circle cx="15.5" cy="12" r="2" fill="#2f80ed"/>'
        "</g>"
    )


def render(total, counts):
    parts = []
    parts.append(
        f'<svg width="{CARD_W}" viewBox="0 0 {CARD_W} 290" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="titleId descId">'
    )
    parts.append(f'<title id="titleId">AI-Powered Projects</title>')
    parts.append(
        f'<desc id="descId">{total} repositories using AI tooling '
        f'(Cursor {counts["cursor"]}, Claude {counts["claude"]}, '
        f'Agent {counts["agent"]}, AgentKit {counts["agentkit"]}).</desc>'
    )
    parts.append(
        f'<style>.h{{font:600 18px {FONT};fill:{TITLE_COLOR}}}'
        f'.n{{font:800 40px {FONT};fill:{TEXT_COLOR}}}'
        f'.cap{{font:600 16px {FONT};fill:{MUTED}}}'
        f'.lbl{{font:600 14px {FONT};fill:{TEXT_COLOR}}}'
        f'.cnt{{font:700 14px {FONT};fill:{TEXT_COLOR}}}'
        f'</style>'
    )
    # Card background
    parts.append(
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{CARD_W - 1}" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1"/>'
    )
    # Title row
    parts.append(robot_icon())
    parts.append(f'<text x="60" y="32" class="h">AI-Powered Projects</text>')

    # Big centered number
    parts.append(
        f'<text x="{CARD_W / 2}" y="86" text-anchor="middle">'
        f'<tspan class="n">{total}</tspan>'
        f'<tspan class="cap" dx="8">repos</tspan>'
        f'</text>'
    )
    parts.append(
        f'<text x="{CARD_W / 2}" y="108" text-anchor="middle" class="cap" '
        f'style="font-size:12px">powered by AI tooling</text>'
    )

    # Divider
    parts.append(f'<line x1="25" y1="128" x2="{CARD_W - 25}" y2="128" stroke="{BORDER}" stroke-width="1"/>')

    # Tool rows
    bar_x, bar_w = 150, 210
    max_count = max([1] + list(counts.values()))
    for i, (key, label, color, _matcher) in enumerate(TOOLS):
        y = 160 + i * 34
        count = counts[key]
        # dot
        parts.append(f'<circle cx="32" cy="{y - 5}" r="5" fill="{color}"/>')
        # label
        parts.append(f'<text x="46" y="{y}" class="lbl">{esc(label)}</text>')
        # track
        parts.append(
            f'<rect x="{bar_x}" y="{y - 12}" width="{bar_w}" height="8" rx="4" fill="{TRACK}"/>'
        )
        # filled bar
        fill_w = round(bar_w * count / max_count)
        if fill_w > 0:
            parts.append(
                f'<rect x="{bar_x}" y="{y - 12}" width="{fill_w}" height="8" rx="4" fill="{color}"/>'
            )
        # count (right-aligned)
        parts.append(
            f'<text x="{CARD_W - 25}" y="{y}" text-anchor="end" class="cnt">{count}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not TOKEN:
        print("warning: GITHUB_TOKEN not set; using anonymous (rate-limited) requests", file=sys.stderr)

    repos = list_repos(OWNER)
    candidates = [r for r in repos if not r.get("fork") and r.get("default_branch")]

    counts = {key: 0 for key, *_ in TOOLS}
    total = 0
    scanned = 0
    for r in candidates:
        name = r["name"]
        paths = tree_paths(OWNER, name, r["default_branch"])
        if paths is None:
            print(f"  skip {name}: empty or unreadable", file=sys.stderr)
            continue
        scanned += 1
        found = classify(paths)
        hit = any(found.values())
        if hit:
            total += 1
        for key, *_ in TOOLS:
            if found[key]:
                counts[key] += 1
        print(f"  {name:42s} -> {', '.join(k for k, *_ in TOOLS if found[k]) or '-'}")

    svg = render(total, counts)
    os.makedirs("profile", exist_ok=True)
    with open("profile/ai-powered.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"\nAI-powered: {total}/{scanned} repos  counts={counts}")
    print("wrote profile/ai-powered.svg")


if __name__ == "__main__":
    main()
