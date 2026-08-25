#!/usr/bin/env python3
"""Generate an "AI-enabled Projects" SVG card for a GitHub profile README.

Detects AI-enabled repositories via their **topic tags** (the labels in a repo's
"About" section) and renders a static SVG card matching the github-readme-stats
visual style -- including the same entrance animations (title fade-in, staggered
row reveal). The card is committed to the profile repo by the GitHub Actions
workflow, so profile views never hit the API at view time.

A repo counts as AI-enabled if any of its topics matches one of four categories,
split across two INDEPENDENT axes (a repo can appear under its build tool AND
under AI-Powered Features at the same time):

  Build tool -- how the repo was developed:
    - Claude Code / Cursor        shown as their own rows, OR
    - Other AI Assistants         another AI coding tool (Codex, GitHub Copilot,
                                  Droid, Kiro, Augment Code, Windsurf, Codeium)
                                  when no primary tool matched.

  Product features -- what the repo does:
    - AI-Powered Features         the product uses AI directly for end users or
                                  the system itself -- OCR, RAG, chatbot,
                                  classification, extraction, agent workflow,
                                  LLM/GPT/Gemini, NLP, embeddings, ...

The card's background rect is tagged data-testid="card-bg" so the composer can
swap in a uniform frame when merging all cards into one image.

Environment:
  GITHUB_TOKEN  GitHub token (PAT or the Actions GITHUB_TOKEN) for auth + rate
                limits. If unset, falls back to anonymous (heavily rate-limited).
                A PAT with repo scope belonging to OWNER also includes the
                owner's PRIVATE repositories; the Actions GITHUB_TOKEN is
                repo-scoped and sees public repos only.
  OWNER         GitHub username to scan (default: ntttrang).

Output:
  profile/AI-enabled.svg
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

# --- Visual style (text classes mirror the Streak Stats card) -----------------
BG = "#fffefe"
BORDER = "#e4e2e2"
TITLE_COLOR = "#2f80ed"
TEXT_COLOR = "#434d58"
MUTED = "#858585"
TRACK = "#e4e2e2"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
# github-readme-stats titles use this shorter stack (no "Helvetica Neue") plus a
# Firefox font-size override. Match it so the title matches the other cards.
TITLE_FONT = "'Segoe UI', Ubuntu, Sans-Serif"
# Title-prefix icon (primer/octicons "ai-model-16" -- a node graph, fitting for an
# AI card). github-readme-stats renders a 16px title icon at x=0, y=-13 inside the
# card-title group, with the title text then shifted +25 by its flexLayout gap so
# the icon sits before the title. See render() for the matching layout.
TITLE_ICON_PATH = (
    "M10.628 7.25a2.25 2.25 0 1 1 0 1.5H8.622a2.25 2.25 0 0 1-2.513 1.466"
    "L5.03 12.124a2.25 2.25 0 1 1-1.262-.814l1.035-1.832A2.245 2.245 0 0 1 "
    "4.25 8c0-.566.209-1.082.553-1.478L3.768 4.69a2.25 2.25 0 1 1 1.262-.814"
    "l1.079 1.908A2.25 2.25 0 0 1 8.622 7.25ZM2.5 2.5a.75.75 0 1 0 1.5 0 "
    ".75.75 0 0 0-1.5 0Zm4 4.75a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm6.25 0"
    "a.75.75 0 1 0 0 1.5.75.75 0 0 0 0-1.5Zm-9.5 5.5a.75.75 0 1 0 0 1.5"
    ".75.75 0 0 0 0-1.5Z"
)
# Native width matches the composer's cell (460). With four category rows the
# native height (~240) exceeds the 220-tall cell, so the composer scales the card
# down slightly via its uniform "contain" fit -- the same mechanism already used
# for the other cards, which sit at varying scales near 1.0.
CARD_W = 460

# --- Tracked primary AI coding tools (their own rows) -------------------------
# (key, label, color, matcher). matcher(lowercased_topic) -> bool.
TOOLS = [
    ("claude", "Claude Code", "#d97757", lambda t: "claude" in t),
    ("cursor", "Cursor", "#4c71f2", lambda t: "cursor" in t),
]

# --- Other AI coding assistants / agents (build-tool axis) --------------------
# Repos developed with another AI coding tool, i.e. not Claude Code / Cursor.
# Counted only when no primary tool matched, so a repo shows under its main tool
# rather than "other".
ASSISTANT_LABEL = "Other AI Assistants"
ASSISTANT_COLOR = "#858585"
# Compound topics signalling the dev process used an AI assistant. Matched as
# EXACT whole topics (see topic_categories) so "ai-assisted" is claimed here
# instead of leaking its "ai" prefix into the feature axis below.
ASSISTANT_EXACT = {"ai-assisted", "ai-assistance", "ai-assistant"}
ASSISTANT_TOKENS = {
    "codex", "copilot", "droid", "kiro", "augment", "windsurf", "codeium",
}
ASSISTANT_SUBSTR = ()  # coding tools have distinctive names; no substring rules

# --- AI-powered product features (independent of the build tool) --------------
# Repos whose PRODUCT uses AI directly for end users or the system itself. This
# is a separate axis from the build tool, so a Cursor-built RAG service counts
# under BOTH Cursor and AI-Powered Features.
FEATURE_LABEL = "AI-Powered Features"
FEATURE_COLOR = "#8957e5"
FEATURE_EXACT = {"ai-powered", "ai-enabled", "ai-features"}
FEATURE_TOKENS = {
    "ai", "ml", "llm", "gpt", "rag", "agent", "agents", "agentic", "genai",
    "ocr", "classification", "extraction",
}
FEATURE_SUBSTR = (
    "artificial-intelligence", "machine-learning", "deep-learning", "neural",
    "generative", "gemini", "openai", "chatgpt", "langchain", "llamaindex",
    "llama", "anthropic", "huggingface", "transformer", "diffusion", "embedding",
    "vector", "chat-bot", "chatbot", "nlp",
)


def topic_categories(topic):
    """Return the set of axes ("assistant" / "feature") a single topic signals.

    Compound topics (ai-assisted, ai-powered, ...) are matched as EXACT whole
    topics first and claimed by their specific axis, so "ai-assisted" routes to
    the build-tool axis instead of matching "ai" and leaking into features.

    Otherwise short/ambiguous keywords are matched as whole tokens (split on
    non-alphanumerics) to avoid false positives (e.g. "rag" inside "storage",
    "ai" inside "trail"); distinctive terms are matched as substrings.
    """
    if topic in ASSISTANT_EXACT:
        return {"assistant"}
    if topic in FEATURE_EXACT:
        return {"feature"}
    cats = set()
    toks = set(re.split(r"[^a-z0-9]+", topic))
    if toks & ASSISTANT_TOKENS:
        cats.add("assistant")
    if toks & FEATURE_TOKENS:
        cats.add("feature")
    if any(s in topic for s in FEATURE_SUBSTR):
        cats.add("feature")
    return cats


# --- GitHub API helpers --------------------------------------------------------
def api_get(path):
    url = f"{API}{path}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-enabled-stats",
    }
    # Only send Authorization when a token exists -- an empty "Bearer " header
    # makes GitHub return 401, breaking the anonymous fallback.
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, None, dict(e.headers)
    except urllib.error.URLError as e:
        print(f"request error for {path}: {e}", file=sys.stderr)
        return 0, None, {}


def paged(path):
    """GET a paginated list endpoint, following Link rel="next"."""
    repos, page = [], 1
    while True:
        status, data, headers = api_get(f"{path}&page={page}")
        if status != 200 or not isinstance(data, list):
            break
        repos.extend(data)
        if 'rel="next"' not in headers.get("Link", ""):
            break
        page += 1
    return repos


def list_repos(owner):
    """Return (repos, private_included) for the owner's repositories.

    /users/{owner}/repos lists PUBLIC repos only -- even when authenticated.
    When the token is a PAT belonging to the same owner (repo scope), use the
    authenticated /user/repos instead so private repos are scanned too. The
    Actions GITHUB_TOKEN cannot call /user (not a user token), so CI falls
    back to the public listing until the workflow is given a real PAT.
    """
    if TOKEN:
        status, me, _ = api_get("/user")
        if status == 200 and isinstance(me, dict) and str(me.get("login", "")).lower() == owner.lower():
            return paged(
                "/user/repos?visibility=all&affiliation=owner&sort=updated&per_page=100"
            ), True
    return paged(f"/users/{owner}/repos?per_page=100&type=owner&sort=updated"), False


def classify(topics):
    """Return (tool_keys, is_assistant, is_feature) for a repo's topic list.

    tool_keys    primary tool(s) matched (claude / cursor).
    is_assistant developed with another AI coding tool, and no primary tool
                 matched (so it shows under "Other AI Assistants", not its tool).
    is_feature   the product itself uses AI directly. INDEPENDENT of the build
                 tool -- a repo can be both a Cursor build and AI-powered.
    """
    lowered = [t.lower() for t in (topics or [])]
    tool_keys = {
        key for key, _label, _color, matcher in TOOLS
        if any(matcher(t) for t in lowered)
    }
    axes = set()
    for t in lowered:
        axes |= topic_categories(t)
    is_assistant = (not tool_keys) and ("assistant" in axes)
    is_feature = "feature" in axes
    return tool_keys, is_assistant, is_feature


# --- SVG rendering -------------------------------------------------------------
def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(total, scanned, rows, private_included):
    """rows: list of (label, color, count) in display order."""
    scope = "repos" if private_included else "public repos"
    row_h = 25
    # Extra space inserted before the product-feature axis (the final row) so the
    # divider below it has breathing room -- the feature axis is a different axis
    # (what the product does) from the build-tool rows above (how it was built).
    feature_gap = 16
    top_y = 130
    height = top_y + len(rows) * row_h + feature_gap + 10
    parts = [
        f'<svg width="{CARD_W}" viewBox="0 0 {CARD_W} {height}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="titleId descId">',
        f'<title id="titleId">AI-enabled Projects</title>',
        f'<desc id="descId">{total} of {scanned} {"repos" if private_included else "public repos"} use AI tooling.</desc>',
        (
            f'<style>'
            f'@keyframes fadeInAnimation{{from{{opacity:0}}to{{opacity:1}}}}'
            f'.h{{font:600 18px {TITLE_FONT};fill:{TITLE_COLOR};animation:fadeInAnimation .8s ease-in-out forwards}}'
            f'@supports(-moz-appearance:auto){{.h{{font-size:15.5px}}}}'
            f'.icon{{fill:{TITLE_COLOR};display:block;animation:fadeInAnimation .8s ease-in-out forwards}}'
            f'.num{{font:800 30px {FONT};fill:{TEXT_COLOR}}}'
            f'.unit{{font:600 12px {FONT};fill:{MUTED}}}'
            f'.cap{{font:400 10.5px {FONT};fill:{MUTED}}}'
            f'.lbl{{font:600 12px {FONT};fill:{MUTED}}}'
            f'.cnt{{font:600 12px {FONT};fill:{TEXT_COLOR}}}'
            f'.stagger{{opacity:0;animation:fadeInAnimation .3s ease-in-out forwards}}'
            f'</style>'
        ),
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{CARD_W - 1}" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1" data-testid="card-bg"/>',
        # Title: github-readme-stats renders the header inside a card-title group
        # at the card padding (translate(25, 35)) -- the SAME left margin and
        # baseline the top-langs card's "Most Used Languages" title uses. The 16px
        # prefix icon sits at x=0, y=-13 and the text shifts +25 (flexLayout gap),
        # so the icon appears before the title without changing the title's margin.
        (
            f'<g data-testid="card-title" transform="translate(25, 35)">'
            f'<svg class="icon" x="0" y="-13" viewBox="0 0 16 16" version="1.1" width="16" height="16">'
            f'<path d="{TITLE_ICON_PATH}"/></svg>'
            f'<text x="25" y="0" class="h">AI-enabled Projects</text>'
            f'</g>'
        ),
        f'<g class="stagger" style="animation-delay:150ms">'
        f'<text x="{CARD_W / 2}" y="74" text-anchor="middle">'
        f'<tspan class="num">{total}</tspan>'
        f'<tspan class="unit" dx="8">repos</tspan></text>'
        f'<text x="{CARD_W / 2}" y="94" text-anchor="middle" class="cap">'
        f'{total} of {scanned} {scope} tagged with AI topics</text>'
        f'</g>',
        f'<line x1="25" y1="112" x2="{CARD_W - 25}" y2="112" stroke="{BORDER}" stroke-width="1"/>',
    ]

    # Bar sits just past the label column. Labels mirror the Streak Stats card
    # (.lbl = 12px semibold), which is wider than the old 11px lang-name style,
    # so the longest ("Other AI Assistants") needs more room; bar_x clears it
    # with margin to spare. The track rect is drawn AFTER the label text, so
    # this clearance keeps it from clipping the label's tail. bar_w leaves room
    # for the right-aligned count (up to two digits) before the 25px padding.
    bar_x, bar_w = 180, 235
    max_count = max([1] + [c for _, _, c in rows])
    last = len(rows) - 1
    y = top_y
    for i, (label, color, count) in enumerate(rows):
        # Set the product-feature axis (final row) off from the build-tool rows
        # above with a divider -- they are different axes, so a line between them
        # mirrors the header divider and makes the split legible at a glance.
        if i == last and i > 0:
            sep_y = y + (feature_gap - row_h) // 2   # midpoint between the rows
            parts.append(
                f'<line x1="25" y1="{sep_y}" x2="{CARD_W - 25}" y2="{sep_y}" '
                f'stroke="{BORDER}" stroke-width="1"/>'
            )
            y += feature_gap
        parts.append(f'<g class="stagger" style="animation-delay:{450 + i * 150}ms">')
        parts.append(f'<circle cx="30" cy="{y - 4}" r="5" fill="{color}"/>')
        parts.append(f'<text x="40" y="{y}" class="lbl">{esc(label)}</text>')
        parts.append(f'<rect x="{bar_x}" y="{y - 11}" width="{bar_w}" height="8" rx="4" fill="{TRACK}"/>')
        fill_w = round(bar_w * count / max_count)
        if fill_w > 0:
            parts.append(f'<rect x="{bar_x}" y="{y - 11}" width="{fill_w}" height="8" rx="4" fill="{color}"/>')
        parts.append(f'<text x="{CARD_W - 25}" y="{y}" text-anchor="end" class="cnt">{count}</text>')
        parts.append("</g>")
        y += row_h

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not TOKEN:
        print("warning: GITHUB_TOKEN not set; using anonymous (rate-limited) requests", file=sys.stderr)

    repos, private_included = list_repos(OWNER)
    candidates = [r for r in repos if not r.get("fork")]
    print(f"scanning {len(candidates)} "
          f"{'repos (incl. private)' if private_included else 'public repos'}")

    counts = {key: 0 for key, *_ in TOOLS}
    assistant = 0
    feature = 0
    total = 0
    for r in candidates:
        name = r["name"]
        topics = r.get("topics") or []
        tool_keys, is_assistant, is_feature = classify(topics)
        if not tool_keys and not is_assistant and not is_feature:
            tag = "-"
        else:
            total += 1
            for k in tool_keys:
                counts[k] += 1
            if is_assistant:
                assistant += 1
            if is_feature:
                feature += 1
            tag = ",".join(
                [label for key, label, _c, _m in TOOLS if key in tool_keys]
                + ([ASSISTANT_LABEL] if is_assistant else [])
                + ([FEATURE_LABEL] if is_feature else [])
            )
        shown = ", ".join(topics) if topics else "(no topics)"
        print(f"  {name:42s} [{shown}]  -> {tag}")

    rows = [(label, color, counts[key]) for key, label, color, _m in TOOLS]
    rows.append((ASSISTANT_LABEL, ASSISTANT_COLOR, assistant))
    rows.append((FEATURE_LABEL, FEATURE_COLOR, feature))

    svg = render(total, len(candidates), rows, private_included)
    os.makedirs("profile", exist_ok=True)
    with open("profile/AI-enabled.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"\nAI-enabled: {total}/{len(candidates)} repos  "
          f"tools={counts} assistant={assistant} feature={feature}")
    print("wrote profile/AI-enabled.svg")


if __name__ == "__main__":
    main()
