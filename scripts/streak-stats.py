#!/usr/bin/env python3
"""Generate a "Streak Stats" SVG card for a GitHub profile README.

Reads the owner's contribution calendar via the GraphQL API and computes the
current streak, the longest streak, and the yearly contribution total — then
renders a static SVG card matching the github-readme-stats visual style. The
card is committed to the profile repo by the GitHub Actions workflow, so profile
views never hit the API at view time (same "works anytime" approach as the other
cards).

The contribution calendar is read with the workflow's GITHUB_TOKEN. If that
token cannot read contributionsCollection, the card degrades gracefully
(placeholder dashes) instead of breaking the composite image.

Environment:
  GITHUB_TOKEN  GitHub token (PAT or the Actions GITHUB_TOKEN).
  OWNER         GitHub username (default: ntttrang).

Output:
  profile/streaks.svg
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com/graphql"
OWNER = os.environ.get("OWNER") or "ntttrang"
TOKEN = os.environ.get("GITHUB_TOKEN") or ""

# --- Visual style (matches github-readme-stats default theme) -----------------
BG = "#fffefe"
BOX = "#f6f8fa"
BORDER = "#e4e2e2"
TITLE_COLOR = "#2f80ed"
TEXT_COLOR = "#434d58"
MUTED = "#858585"
FLAME = "#ff6b35"
FLAME_INNER = "#ffd166"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
CARD_W = 480

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


# --- GitHub API helpers --------------------------------------------------------
def fetch_calendar():
    """Return (days, total, year) where days is a chronological list of
    (date_str, count). Returns (None, None, None) on any failure."""
    if not TOKEN:
        print("warning: GITHUB_TOKEN not set", file=sys.stderr)
    body = json.dumps({"query": QUERY, "variables": {"login": OWNER}}).encode("utf-8")
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "streak-stats",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        print(f"GraphQL HTTP {e.code}: {detail}", file=sys.stderr)
        return None, None, None
    except (urllib.error.URLError, ValueError) as e:
        print(f"GraphQL error: {e}", file=sys.stderr)
        return None, None, None

    if payload.get("errors"):
        print(f"GraphQL errors: {payload['errors']}", file=sys.stderr)
        return None, None, None

    try:
        cal = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except (KeyError, TypeError):
        print("unexpected GraphQL response shape", file=sys.stderr)
        return None, None, None

    total = cal.get("totalContributions", 0)
    days = []
    for week in cal.get("weeks", []):
        for day in week.get("contributionDays", []):
            days.append((day["date"], day.get("contributionCount", 0)))
    year = int(days[-1][0][:4]) if days else dt.date.today().year
    return days, total, year


# --- Streak computation --------------------------------------------------------
def compute_streaks(days):
    """days: chronological list of (date_str, count)."""
    if not days:
        return None

    # Current streak: count backwards from the most recent day. If today has no
    # contributions yet, skip it (the day isn't over) without breaking the run.
    rev = list(reversed(days))
    skip = 1 if rev[0][1] == 0 else 0
    cur, j = 0, skip
    while j < len(rev) and rev[j][1] > 0:
        cur += 1
        j += 1
    if cur > 0:
        cur_end = rev[skip][0]
        cur_start = rev[skip + cur - 1][0]
    else:
        cur_start = cur_end = None

    # Longest streak: longest run of consecutive non-zero days.
    best = best_start = best_end = 0
    best_start_date = best_end_date = None
    run = 0
    run_start_idx = None
    for idx, (d, c) in enumerate(days):
        if c > 0:
            if run == 0:
                run_start_idx = idx
            run += 1
            if run > best:
                best = run
                best_start_date = days[run_start_idx][0]
                best_end_date = d
        else:
            run = 0

    return {
        "current": cur,
        "current_start": cur_start,
        "current_end": cur_end,
        "longest": best,
        "longest_start": best_start_date,
        "longest_end": best_end_date,
    }


# --- SVG rendering -------------------------------------------------------------
def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fmt_day(date_str):
    d = dt.date.fromisoformat(date_str)
    return d.strftime("%b %-d")


def range_str(start, end):
    if not start:
        return ""
    if start == end:
        return fmt_day(start)
    return f"{fmt_day(start)} – {fmt_day(end)}"


def flame_icon():
    # Heroicons "fire" (24x24), drawn from primitives so it always renders.
    outer = (
        "M15.362 5.214A8.252 8.252 0 0 1 12 21 8.25 8.25 0 0 1 6.038 7.048 "
        "8.287 8.287 0 0 0 9 9.6a8.983 8.983 0 0 1 3.361-6.867 8.21 8.21 0 0 0 3 2.48z"
    )
    inner = (
        "M12 18a3.75 3.75 0 0 0 .495-7.467 5.99 5.99 0 0 0-1.925 3.546 "
        "5.974 5.974 0 0 1-2.133-1A3.75 3.75 0 0 0 12 18z"
    )
    return (
        '<g transform="translate(24,11) scale(0.82)">'
        f'<path d="{outer}" fill="{FLAME}"/>'
        f'<path d="{inner}" fill="{FLAME_INNER}"/>'
        "</g>"
    )


def stat_box(x, w, label, value, value_color, caption):
    """A rounded box with label / big number / caption, centered horizontally."""
    cx = x + w / 2
    parts = [
        f'<rect x="{x}" y="66" width="{w}" height="98" rx="8" fill="{BOX}" stroke="{BORDER}"/>',
        f'<text x="{cx}" y="89" text-anchor="middle" class="lbl">{esc(label)}</text>',
        f'<text x="{cx}" y="130" text-anchor="middle">'
        f'<tspan class="num" fill="{value_color}">{value}</tspan>'
        f'<tspan class="unit" dx="6">days</tspan></text>',
    ]
    if caption:
        parts.append(
            f'<text x="{cx}" y="152" text-anchor="middle" class="cap">{esc(caption)}</text>'
        )
    return "".join(parts)


def render(s, total, year, available):
    height = 232
    cur = s["current"] if s else 0
    best = s["longest"] if s else 0
    cur_cap = range_str(s["current_start"], s["current_end"]) if s else ""
    best_cap = range_str(s["longest_start"], s["longest_end"]) if s else ""
    cur_txt = f"{cur:,}" if available else "—"
    best_txt = f"{best:,}" if available else "—"
    total_txt = f"{total:,}" if available else "—"
    cap_note = "" if available else "contribution data unavailable"

    box_w = 205
    left_x = 25
    right_x = CARD_W - 25 - box_w

    parts = [
        f'<svg width="{CARD_W}" height="{height}" viewBox="0 0 {CARD_W} {height}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="titleId descId">',
        f'<title id="titleId">Streak Stats</title>',
        f'<desc id="descId">Current streak {cur_txt} days, longest streak '
        f'{best_txt} days, {total_txt} contributions in {year}.</desc>',
        (
            f'<style>.h{{font:600 18px {FONT};fill:{TITLE_COLOR}}}'
            f'.lbl{{font:600 12px {FONT};fill:{MUTED}}}'
            f'.num{{font:800 30px {FONT};fill:{TEXT_COLOR}}}'
            f'.unit{{font:600 12px {FONT};fill:{MUTED}}}'
            f'.cap{{font:400 10.5px {FONT};fill:{MUTED}}}'
            f'.tlbl{{font:600 13px {FONT};fill:{MUTED}}}'
            f'.tnum{{font:700 16px {FONT};fill:{TEXT_COLOR}}}'
            f'</style>'
        ),
        f'<rect x="0.5" y="0.5" rx="4.5" height="99%" width="{CARD_W - 1}" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1"/>',
        flame_icon(),
        f'<text x="52" y="33" class="h">Streak Stats</text>',
        f'<line x1="25" y1="52" x2="{CARD_W - 25}" y2="52" stroke="{BORDER}" stroke-width="1"/>',
        stat_box(left_x, box_w, "Current Streak", cur_txt, FLAME, cur_cap),
        stat_box(right_x, box_w, "Longest Streak", best_txt, TITLE_COLOR, best_cap),
        f'<line x1="25" y1="180" x2="{CARD_W - 25}" y2="180" stroke="{BORDER}" stroke-width="1"/>',
        f'<text x="{CARD_W / 2}" y="208" text-anchor="middle">'
        f'<tspan class="tlbl">Total Contributions </tspan>'
        f'<tspan class="tnum">{total_txt}</tspan>'
        f'<tspan class="cap"> in {year}</tspan></text>',
    ]
    if not available:
        parts.append(
            f'<text x="{CARD_W / 2}" y="224" text-anchor="middle" class="cap">{esc(cap_note)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    days, total, year = fetch_calendar()
    available = days is not None
    s = compute_streaks(days) if available else None

    svg = render(s, total, year, available)
    os.makedirs("profile", exist_ok=True)
    with open("profile/streaks.svg", "w", encoding="utf-8") as f:
        f.write(svg)

    if available:
        print(
            f"streaks: current={s['current']} longest={s['longest']} "
            f"total={total} ({year})"
        )
    else:
        print("streaks: contribution data unavailable; wrote placeholder card")
    print("wrote profile/streaks.svg")


if __name__ == "__main__":
    main()
