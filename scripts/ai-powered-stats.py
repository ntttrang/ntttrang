#!/usr/bin/env python3
"""Generate an "AI-Powered Projects" SVG card for a GitHub profile README.

Detects AI-powered repositories via their **topic tags** (the labels in a repo's
"About" section) and renders a static SVG card matching the github-readme-stats
visual style. Topics come straight from the repo-listing API, so there are no
per-repository calls. The card is committed to the profile repo by the GitHub
Actions workflow, so profile views never hit the API at view time.

A repo counts as AI-powered if any of its topics:
  - matches one of the tracked AI coding tools (Claude Code, Cursor, Droid, Kiro,
    Augment Code, Windsurf), OR
  - matches a general AI keyword (ai, genai, llm, gemini, gpt, openai, agent,
    machine-learning, rag, ...).

Environment:
  GITHUB_TOKEN  GitHub token (PAT or the Actions GITHUB_TOKEN) for auth + rate
                limits. If unset, falls back to anonymous (heavily rate-limited).
  OWNER         GitHub username to scan (default: ntttrang).

Output:
  profile/ai-powered.svg
"""
import json
import os
import re
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

# --- Tracked AI coding tools --------------------------------------------------
# (key, label, color, matcher). matcher(lowercased_topic) -> bool.
TOOLS = [
    ("claude", "Claude Code", "#d97757", lambda t: "claude" in t),
    ("cursor", "Cursor", "#4c71f2", lambda t: "cursor" in t),
    ("droid", "Droid", "#2ea043", lambda t: "droid" in t),
    ("kiro", "Kiro", "#a371f7", lambda t: "kiro" in t),
    ("augment", "Augment Code", "#f0883e", lambda t: "augment" in t),
    ("windsurf", "Windsurf", "#218bff", lambda t: "windsurf" in t or "codeium" in t),
]
OTHER_LABEL = "Other AI"
OTHER_COLOR = "#858585"

# General AI keywords. Short/ambiguous ones are matched as whole tokens (split on
# non-alphanumerics) to avoid false positives (e.g. "rag" inside "storage", "ai"
# inside "trail"); distinctive terms are matched as substrings.
AI_TOKENS = {
    "ai", "ml", "llm", "gpt", "rag", "agent", "agents", "genai", "copilot",
    "agentic", "ragchain",
}
AI_SUBSTR = (
    "artificial-intelligence", "machine-learning", "deep-learning", "neural",
    "generative", "gemini", "openai", "chatgpt", "langchain", "llamaindex",
    "llama", "anthropic", "huggingface", "transformer", "diffusion", "embedding",
    "vector", "chat-bot", "chatbot", "nlp",
)


def topic_is_general_ai(topic):
    t = topic.lower()
    tokens = set(re.split(r"[^a-z0-9]+", t))
    if tokens & AI_TOKENS:
        return True
    return any(s in t for s in AI_SUBSTR)


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


def classify(topics):
    """Return (tool_keys:set, is_other_ai:bool) for a repo's topic list."""
    topics = [t for t in (topics or [])]
    tool_keys = {
        key for key, _label, _color, matcher in TOOLS
        if any(matcher(t.lower()) for t in topics)
    }
    general = any(topic_is_general_ai(t) for t in topics)
    is_other = (not tool_keys) and general
    return tool_keys, is_other


# --- SVG rendering -------------------------------------------------------------
def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def robot_icon():
    return (
        '<g transform="translate(28,16)">'
        '<line x1="11" y1="0" x2="11" y2="4" stroke="#2f80ed" stroke-width="2"/>'
        '<circle cx="11" cy="0" r="2.6" fill="#2f80ed"/>'
        '<rect x="0" y="4" width="22" height="16" rx="4" fill="none" stroke="#2f80ed" stroke-width="2"/>'
        '<circle cx="6.5" cy="12" r="2" fill="#2f80ed"/>'
        '<circle cx="15.5" cy="12" r="2" fill="#2f80ed"/>'
        "</g>"
    )


def render(total, scanned, rows):
    """rows: list of (label, color, count) in display order."""
    row_h = 28
    top_y = 168
    height = top_y + len(rows) * row_h + 14
    parts = [
        f'<svg width="{CARD_W}" viewBox="0 0 {CARD_W} {height}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="titleId descId">',
        f'<title id="titleId">AI-Powered Projects</title>',
        f'<desc id="descId">{total} of {scanned} public repositories use AI tooling.</desc>',
        (
            f'<style>.h{{font:600 18px {FONT};fill:{TITLE_COLOR}}}'
            f'.n{{font:800 40px {FONT};fill:{TEXT_COLOR}}}'
            f'.cap{{font:600 13px {FONT};fill:{MUTED}}}'
            f'.lbl{{font:600 14px {FONT};fill:{TEXT_COLOR}}}'
            f'.cnt{{font:700 14px {FONT};fill:{TEXT_COLOR}}}'
            f'</style>'
        ),
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{CARD_W - 1}" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1"/>',
        robot_icon(),
        f'<text x="60" y="32" class="h">AI-Powered Projects</text>',
        f'<text x="{CARD_W / 2}" y="90" text-anchor="middle">'
        f'<tspan class="n">{total}</tspan>'
        f'<tspan class="cap" dx="8">repos</tspan></text>',
        f'<text x="{CARD_W / 2}" y="112" text-anchor="middle" class="cap">'
        f'{total} of {scanned} public repos tagged with AI topics</text>',
        f'<line x1="25" y1="138" x2="{CARD_W - 25}" y2="138" stroke="{BORDER}" stroke-width="1"/>',
    ]

    bar_x, bar_w = 168, 200
    max_count = max([1] + [c for _, _, c in rows])
    for i, (label, color, count) in enumerate(rows):
        y = top_y + i * row_h
        parts.append(f'<circle cx="32" cy="{y - 4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="46" y="{y}" class="lbl">{esc(label)}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 11}" width="{bar_w}" height="8" rx="4" fill="{TRACK}"/>')
        fill_w = round(bar_w * count / max_count)
        if fill_w > 0:
            parts.append(f'<rect x="{bar_x}" y="{y - 11}" width="{fill_w}" height="8" rx="4" fill="{color}"/>')
        parts.append(
            f'<text x="{CARD_W - 25}" y="{y}" text-anchor="end" class="cnt">{count}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not TOKEN:
        print("warning: GITHUB_TOKEN not set; using anonymous (rate-limited) requests", file=sys.stderr)

    repos = list_repos(OWNER)
    candidates = [r for r in repos if not r.get("fork")]

    counts = {key: 0 for key, *_ in TOOLS}
    other = 0
    total = 0
    for r in candidates:
        name = r["name"]
        topics = r.get("topics") or []
        tool_keys, is_other = classify(topics)
        if not tool_keys and not is_other:
            tag = "-"
        else:
            total += 1
            for k in tool_keys:
                counts[k] += 1
            if is_other:
                other += 1
            tag = ",".join(
                [label for key, label, _c, _m in TOOLS if key in tool_keys]
                + ([OTHER_LABEL] if is_other else [])
            )
        shown = ", ".join(topics) if topics else "(no topics)"
        print(f"  {name:42s} [{shown}]  -> {tag}")

    rows = [(label, color, counts[key]) for key, label, color, _m in TOOLS]
    if other > 0:
        rows.append((OTHER_LABEL, OTHER_COLOR, other))

    svg = render(total, len(candidates), rows)
    os.makedirs("profile", exist_ok=True)
    with open("profile/ai-powered.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"\nAI-powered: {total}/{len(candidates)} repos  tools={counts} other={other}")
    print("wrote profile/ai-powered.svg")


if __name__ == "__main__":
    main()
