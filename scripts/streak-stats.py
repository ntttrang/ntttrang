#!/usr/bin/env python3
"""Generate a "Streak Stats" SVG card for a GitHub profile README.

Reads the owner's contribution calendar via the GraphQL API and computes the
current streak, the longest streak, and the yearly contribution total -- then
renders a static SVG card in the classic github-readme-streak-stats layout:
three columns (Total Contributions | Current Streak in a flame-topped ring |
Longest Streak) with the same staggered entrance animations. The card is
committed to the profile repo by the GitHub Actions workflow, so profile
views never hit the API at view time (same "works anytime" approach as the
other cards).

The contribution calendar is read with the workflow's GITHUB_TOKEN. If that
token cannot read contributionsCollection, the card degrades gracefully
(placeholder dashes) instead of breaking the composite image.

The card's background rect is tagged data-testid="card-bg" so the composer can
swap in a uniform frame when merging all cards into one image.

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

# --- Visual style (github-readme-streak-stats "default" theme) ------------------
BG = "#fffefe"
BORDER = "#e4e2e2"
STROKE = "#e4e2e2"  # dividers between the three columns
RING = "#fb8c00"  # circle around the current streak
FIRE = "#fb8c00"  # flame at the top of the ring
NUM = "#151515"  # big numbers (side columns + current streak)
SIDE_LABEL = "#151515"  # "Total Contributions" / "Longest Streak"
CURR_LABEL = "#fb8c00"  # "Current Streak"
DATES = "#464646"  # date-range captions
FONT = "'Segoe UI', Ubuntu, Sans-Serif"

# Native size: 460 wide matches the composer's cell so the card is embedded at
# scale 1.0 -- its 28px/14px/12px text then renders at the same displayed size
# as the other cards. Height 195 is the reference card's default; the composer
# centers the content vertically in its 460x220 frame.
CARD_W = 460
CARD_H = 195

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
    (date_str, count) and total counts only days from Jan 1 of the current
    year. Returns (None, None, None) on any failure."""
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

    days = []
    for week in cal.get("weeks", []):
        for day in week.get("contributionDays", []):
            days.append((day["date"], day.get("contributionCount", 0)))
    year = int(days[-1][0][:4]) if days else dt.date.today().year
    # The default contributionsCollection spans a rolling year, so its
    # totalContributions would mix last year into a card labeled "in <year>".
    # Sum only the current year's days (Jan 1 --> latest day) instead.
    total = sum(c for d, c in days if d[:4] == str(year))
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
    best = best_start_date = best_end_date = 0
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


def fmt_day(date_str, force_year=False):
    """'2026-03-08' -> 'Mar 8' for the current year, 'Mar 8, 2025' otherwise
    (same rule as the reference card; the total range always shows the year
    because it scopes the total to that calendar year)."""
    d = dt.date.fromisoformat(date_str)
    if force_year or d.year != dt.date.today().year:
        return d.strftime("%b %-d, %Y")
    return d.strftime("%b %-d")


def range_str(start, end):
    if not start:
        return ""
    if start == end:
        return fmt_day(start)
    return f"{fmt_day(start)} - {fmt_day(end)}"


def range_text(cx, rng):
    """A centered date range, wrapped onto a second centered line at the
    ' - ' when it is too long for one column (same wrap as the reference)."""
    if len(rng) > 25 and " - " in rng:
        line1, line2 = rng.split(" - ", 1)
        return (
            f'<tspan x="{cx:.2f}" dy="0">{esc(line1)}</tspan>'
            f'<tspan x="{cx:.2f}" dy="16">- {esc(line2)}</tspan>'
        )
    return esc(rng)


def flame_icon(cx):
    # The reference card's flame (single tone), seated on top of the ring.
    fire = (
        "M 1.5 0.67 C 1.5 0.67 2.24 3.32 2.24 5.47 C 2.24 7.53 0.89 9.2 -1.17 9.2 "
        "C -3.23 9.2 -4.79 7.53 -4.79 5.47 L -4.76 5.11 C -6.78 7.51 -8 10.62 -8 13.99 "
        "C -8 18.41 -4.42 22 0 22 C 4.42 22 8 18.41 8 13.99 C 8 8.6 5.41 3.79 1.5 0.67 Z "
        "M -0.29 19 C -2.07 19 -3.51 17.6 -3.51 15.86 C -3.51 14.24 -2.46 13.1 -0.7 12.74 "
        "C 1.07 12.38 2.9 11.53 3.92 10.16 C 4.31 11.45 4.51 12.81 4.51 14.2 "
        "C 4.51 16.85 2.36 19 -0.29 19 Z"
    )
    return (
        f'<g transform="translate({cx:.2f} 19.5)" class="fi" style="animation-delay:.6s">'
        f'<path d="{fire}" fill="{FIRE}"/></g>'
    )


def render(s, total, year, available, total_start):
    col = CARD_W / 3
    xs = [col / 2, col * 1.5, col * 2.5]  # column centers: total | current | longest
    bars_x = [col, col * 2]

    cur = s["current"] if s else 0
    best = s["longest"] if s else 0
    cur_txt = f"{cur:,}" if available else "—"
    best_txt = f"{best:,}" if available else "—"
    total_txt = f"{total:,}" if available else "—"
    cur_rng = range_str(s["current_start"], s["current_end"]) if s else ""
    best_rng = range_str(s["longest_start"], s["longest_end"]) if s else ""
    total_rng = (
        f"{fmt_day(total_start, force_year=True)} - Present"
        if available and total_start
        else ""
    )

    parts = [
        f'<svg width="{CARD_W}" height="{CARD_H}" viewBox="0 0 {CARD_W} {CARD_H}" '
        f'fill="none" xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-labelledby="titleId descId">',
        f'<title id="titleId">Streak Stats</title>',
        f'<desc id="descId">Total contributions {total_txt} in {year}, current '
        f'streak {cur_txt} days, longest streak {best_txt} days.</desc>',
        (
            "<style>"
            "@keyframes fadein{from{opacity:0}to{opacity:1}}"
            "@keyframes currstreak{0%{font-size:3px;opacity:.2}80%{font-size:34px;opacity:1}"
            "100%{font-size:28px;opacity:1}}"
            ".fi{opacity:0;animation:fadein .5s linear forwards}"
            f".num{{font:700 28px {FONT};fill:{NUM}}}"
            f".lbl{{font:400 14px {FONT};fill:{SIDE_LABEL}}}"
            f".cur{{font:700 14px {FONT};fill:{CURR_LABEL}}}"
            f".dts{{font:400 12px {FONT};fill:{DATES}}}"
            f".note{{font:400 10px {FONT};fill:{DATES}}}"
            f".cs{{animation:currstreak .6s linear forwards}}"
            "</style>"
        ),
        f'<rect x="0.5" y="0.5" width="{CARD_W - 1}" height="{CARD_H - 1}" rx="4.5" '
        f'stroke="{BORDER}" fill="{BG}" stroke-opacity="1" data-testid="card-bg"/>',
        # Dividers between the three columns.
        *[
            f'<line x1="{x:.2f}" y1="28" x2="{x:.2f}" y2="170" '
            f'stroke="{STROKE}" stroke-width="1"/>'
            for x in bars_x
        ],
        # Total Contributions column.
        f'<text x="{xs[0]:.2f}" y="80" text-anchor="middle" class="num fi" '
        f'style="animation-delay:.6s">{total_txt}</text>',
        f'<text x="{xs[0]:.2f}" y="116" text-anchor="middle" class="lbl fi" '
        f'style="animation-delay:.7s">Total Contributions</text>',
        f'<text x="{xs[0]:.2f}" y="146" text-anchor="middle" class="dts fi" '
        f'style="animation-delay:.8s">{range_text(xs[0], total_rng)}</text>',
        # Current Streak column: flame-topped ring around the number.
        f'<defs><mask id="ringMask"><rect width="{CARD_W}" height="{CARD_H}" fill="#fff"/>'
        f'<ellipse cx="{xs[1]:.2f}" cy="32" rx="13" ry="18" fill="#000"/></mask></defs>',
        f'<g mask="url(#ringMask)"><circle cx="{xs[1]:.2f}" cy="71" r="40" fill="none" '
        f'stroke="{RING}" stroke-width="5" class="fi" style="animation-delay:.4s"/></g>',
        flame_icon(xs[1]),
        f'<text x="{xs[1]:.2f}" y="80" text-anchor="middle" class="num cs">{cur_txt}</text>',
        f'<text x="{xs[1]:.2f}" y="140" text-anchor="middle" class="cur fi" '
        f'style="animation-delay:.9s">Current Streak</text>',
        f'<text x="{xs[1]:.2f}" y="166" text-anchor="middle" class="dts fi" '
        f'style="animation-delay:.9s">{range_text(xs[1], cur_rng)}</text>',
        # Longest Streak column.
        f'<text x="{xs[2]:.2f}" y="80" text-anchor="middle" class="num fi" '
        f'style="animation-delay:1.2s">{best_txt}</text>',
        f'<text x="{xs[2]:.2f}" y="116" text-anchor="middle" class="lbl fi" '
        f'style="animation-delay:1.3s">Longest Streak</text>',
        f'<text x="{xs[2]:.2f}" y="146" text-anchor="middle" class="dts fi" '
        f'style="animation-delay:1.4s">{range_text(xs[2], best_rng)}</text>',
    ]
    if not available:
        parts.append(
            f'<text x="5" y="187" class="note fi" style="animation-delay:.9s">'
            f"contribution data unavailable</text>"
        )
    parts.append("</svg>")
    return "\n".join(parts)


def main():
    days, total, year = fetch_calendar()
    available = days is not None
    s = compute_streaks(days) if available else None
    total_start = (
        next((d for d, c in days if d[:4] == str(year)), None) if available else None
    )

    svg = render(s, total, year, available, total_start)
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
