#!/usr/bin/env python3
"""Generate an "AI-Powered Projects" SVG card for a GitHub profile README.

Detects AI-enabled repositories via their **topic tags** (the labels in a
repo's "About" section) and renders a static SVG card matching the
github-readme-stats visual style -- including the same entrance animations
(title fade-in, staggered row reveal). The card is committed to the profile
repo by the GitHub Actions workflow, so profile views never hit the API at
view time.

A repo counts as AI-enabled when its PRODUCT uses AI directly for end users
or for the system itself -- OCR, RAG, chatbot, classification, extraction,
agent workflow, LLM/GPT/Gemini, NLP, embeddings, ... The card counts such
repos and lists the TOP 5 most recently updated ones, each row showing the
repo's primary language and framework on the right.

Only PUBLIC repos are counted and listed: the card is committed to the public
profile README, so it must never name a private repository -- and keeping the
count public-only means the big number and the rows always agree.

Deliberately NOT counted: build-tool topics (claude, cursor, copilot,
ai-assisted, ...). A repo developed *with* an AI tool is not itself an
AI-enabled project, so those tags are ignored here.

The card's background rect is tagged data-testid="card-bg" so the composer can
swap in a uniform frame when merging all cards into one image.

Environment:
  GITHUB_TOKEN  GitHub token (PAT or the Actions GITHUB_TOKEN) for auth + rate
                limits. If unset, falls back to anonymous (heavily rate-limited).
                Any token yields the same card: this card reads public repos
                only, so the extra private-repo reach of a PAT is unused here.
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
ACCENT = "#8957e5"  # row markers -- the AI-product accent color
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
# github-readme-stats titles use this shorter stack (no "Helvetica Neue") plus a
# Firefox font-size override. Match it so the title matches the other cards.
TITLE_FONT = "'Segoe UI', Ubuntu, Sans-Serif"
# Native width matches the composer's cell (460). The composer scales the card
# uniformly into its 220-tall cell if it grows past that.
CARD_W = 460
MAX_ROWS = 5  # top public repos listed before "+N more" takes over

# --- Topics that mark a repo's PRODUCT as AI-powered ---------------------------
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
# Build-tool topics routed AWAY from the feature axis: "ai-assisted" and friends
# say the repo was developed with AI help, not that the product itself uses AI.
# Matched first so their "ai" token can't leak into a feature match.
BUILD_TOOL_TOPICS = {"ai-assisted", "ai-assistance", "ai-assistant"}

# Framework labels for the rows' right column ("Go, Gin"). GitHub has no
# "framework" field, so the label comes from topic tags the repo already
# carries. App frameworks outrank AI SDKs: "Gin" says more about how the repo
# is built than the AI API it calls; an AI SDK is the fallback so the column
# is filled whenever possible.
APP_FRAMEWORKS = {
    "gin": "Gin", "fiber": "Fiber", "echo": "Echo", "beego": "Beego",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django",
    "streamlit": "Streamlit", "gradio": "Gradio",
    "nextjs": "Next.js", "nuxtjs": "Nuxt", "react": "React", "vue": "Vue",
    "angular": "Angular", "svelte": "Svelte", "sveltekit": "SvelteKit",
    "express": "Express", "nestjs": "NestJS", "electron": "Electron",
    "spring-boot": "Spring Boot", "spring": "Spring Boot", "quarkus": "Quarkus",
    "laravel": "Laravel", "rails": "Rails",
    "dotnet": ".NET", "aspnet-core": "ASP.NET Core",
    "flutter": "Flutter", "tauri": "Tauri",
}
AI_SDKS = {
    "gemini-api": "Gemini API", "google-genai": "Gemini", "vertex-ai": "Vertex AI",
    "openai-api": "OpenAI API", "langchain": "LangChain", "llamaindex": "LlamaIndex",
    "pytorch": "PyTorch", "tensorflow": "TensorFlow", "huggingface": "Hugging Face",
}


def feature_topics(topics):
    """Return the repo's topics that mark its PRODUCT as AI-powered.

    Short/ambiguous keywords are matched as whole tokens (split on
    non-alphanumerics) to avoid false positives (e.g. "rag" inside "storage",
    "ai" inside "trail"); distinctive terms are matched as substrings.
    """
    matched = []
    for topic in topics or []:
        t = topic.lower()
        if t in BUILD_TOOL_TOPICS:
            continue
        toks = set(re.split(r"[^a-z0-9]+", t))
        if (
            t in FEATURE_EXACT
            or toks & FEATURE_TOKENS
            or any(s in t for s in FEATURE_SUBSTR)
        ):
            matched.append(topic)
    return matched


def framework_from(topics):
    """Best framework label from the repo's topics ("" when none match)."""
    hits = []
    for topic in topics or []:
        t = topic.lower()
        if t in APP_FRAMEWORKS:
            hits.append((0, APP_FRAMEWORKS[t]))
        elif t in AI_SDKS:
            hits.append((1, AI_SDKS[t]))
    hits.sort()  # app frameworks first; ties keep topic order (stable sort)
    return hits[0][1] if hits else ""


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
    """The owner's PUBLIC repos, most recently updated first.

    The card is public-facing (committed to the profile README), so it never
    names or counts private repos -- the public listing is exactly the right
    dataset whichever token generated the card.
    """
    return paged(f"/users/{owner}/repos?per_page=100&type=owner&sort=updated")


# --- SVG rendering -------------------------------------------------------------
def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render(matches, scanned):
    """matches: list of (repo_name, language, framework), most recently
    updated first."""
    total = len(matches)
    shown = matches[:MAX_ROWS]
    more = total - len(shown)
    rows_n = len(shown) + (1 if more else 0)
    row_h = 25
    top_y = 130
    height = top_y + rows_n * row_h + 10
    parts = [
        f'<svg width="{CARD_W}" viewBox="0 0 {CARD_W} {height}" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="titleId descId">',
        f'<title id="titleId">AI-Powered Projects</title>',
        f'<desc id="descId">{total} of {scanned} public repos are AI-powered products.</desc>',
        (
            f'<style>'
            f'@keyframes fadeInAnimation{{from{{opacity:0}}to{{opacity:1}}}}'
            f'.h{{font:600 18px {TITLE_FONT};fill:{TITLE_COLOR};animation:fadeInAnimation .8s ease-in-out forwards}}'
            f'@supports(-moz-appearance:auto){{.h{{font-size:15.5px}}}}'
            f'.num{{font:800 30px {FONT};fill:{TEXT_COLOR}}}'
            f'.unit{{font:600 12px {FONT};fill:{MUTED}}}'
            f'.lbl{{font:600 12px {FONT};fill:{TEXT_COLOR}}}'
            f'.tp{{font:400 11px {FONT};fill:{MUTED}}}'
            f'.stagger{{opacity:0;animation:fadeInAnimation .3s ease-in-out forwards}}'
            f'</style>'
        ),
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{CARD_W - 1}" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1" data-testid="card-bg"/>',
        # Title: github-readme-stats renders the header inside a card-title group
        # at the card padding (translate(25, 35)) -- the SAME left margin and
        # baseline the top-langs card's "Most Used Languages" title uses. No
        # prefix icon: the text starts at x=0 inside the group, so it sits
        # exactly on the card padding like the other cards' titles.
        f'<g data-testid="card-title" transform="translate(25, 35)">'
        f'<text x="0" y="0" class="h">AI-Powered Projects</text>'
        f'</g>',
        f'<g class="stagger" style="animation-delay:150ms">'
        f'<text x="{CARD_W / 2}" y="74" text-anchor="middle">'
        f'<tspan class="num">{total}</tspan>'
        f'<tspan class="unit" dx="8">repos</tspan></text>'
        f'</g>',
        f'<line x1="25" y1="112" x2="{CARD_W - 25}" y2="112" stroke="{BORDER}" stroke-width="1"/>',
    ]

    # Each row: an accent dot, the repo name, and its "language, framework"
    # label (right-aligned, muted).
    y = top_y
    for i, (name, lang, framework) in enumerate(shown):
        tags = ", ".join(p for p in (lang, framework) if p)
        if len(tags) > 30:  # keep the label clear of the repo name
            tags = tags[:29].rstrip() + "…"
        parts.append(f'<g class="stagger" style="animation-delay:{450 + i * 150}ms">')
        parts.append(f'<circle cx="30" cy="{y - 4}" r="5" fill="{ACCENT}"/>')
        parts.append(f'<text x="40" y="{y}" class="lbl">{esc(name)}</text>')
        parts.append(f'<text x="{CARD_W - 25}" y="{y}" text-anchor="end" class="tp">{esc(tags)}</text>')
        parts.append("</g>")
        y += row_h
    if more:
        parts.append(f'<g class="stagger" style="animation-delay:{450 + len(shown) * 150}ms">')
        parts.append(f'<text x="40" y="{y}" class="tp">+{more} more</text>')
        parts.append("</g>")

    parts.append("</svg>")
    return "\n".join(parts)


def main():
    if not TOKEN:
        print("warning: GITHUB_TOKEN not set; using anonymous (rate-limited) requests", file=sys.stderr)

    repos = list_repos(OWNER)
    candidates = [r for r in repos if not r.get("fork")]
    print(f"scanning {len(candidates)} public repos")

    matches = []
    for r in candidates:
        topics = r.get("topics") or []
        hit = feature_topics(topics)
        if hit:
            lang = r.get("language") or ""
            framework = framework_from(topics)
            matches.append((r["name"], lang, framework))
            label = ", ".join(p for p in (lang, framework) if p) or "-"
            print(f"  {r['name']:42s} -> {label}   (matched: {','.join(hit)})")
        else:
            shown = ", ".join(topics) if topics else "(no topics)"
            print(f"  {r['name']:42s} [{shown}]")

    svg = render(matches, len(candidates))
    os.makedirs("profile", exist_ok=True)
    with open("profile/AI-enabled.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"\nAI-powered: {len(matches)}/{len(candidates)} public repos are "
          f"AI-powered products (top {min(len(matches), MAX_ROWS)} shown)")
    print("wrote profile/AI-enabled.svg")


if __name__ == "__main__":
    main()
