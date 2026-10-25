"""crumbs scoring math. Pure functions, no network, so tests can cover them with fixture reviews.

A "spot" here is a dict with `scores` ({attribute: 0-100 or None}), `waitMinutes`, `ambiancePct` and
`reviewCount`. Higher scores are better; for wait, lower minutes are better. Minutes and points are
compared on one scale the same way the frontend does (src/crumbs/metrics.js): wait spans 0-30 min,
everything else 0-100.
"""

import re
import statistics

WAIT_SCALE_MIN = 30
MAX_WAIT_MIN = 240  # longer "waits" are almost always something else (reservations, delivery)

# ---------- wait time from review text ----------

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty-five": 45,
    "fifty": 50, "sixty": 60, "ninety": 90,
}
_NUM = r"(\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True)) + r")"
_DURATION = re.compile(
    rf"\b{_NUM}(?:\s*(?:-|–|to|or)\s*{_NUM})?\+?\s*(?:more\s+)?(minutes?|mins?|min|hours?|hrs?|hr)\b", re.I)
_HALF_HOUR = re.compile(r"\bhalf(?:\s+an)?\s+hour\b", re.I)
_HOUR_AND_HALF = re.compile(r"\b(?:an|one|1)\s+hour\s+and\s+a\s+half\b", re.I)
_NO_WAIT = re.compile(r"\b(?:no|zero)\s+wait\b|\bwalked\s+right\s+in\b|\bseated\s+(?:right\s+away|immediately)\b", re.I)
# "took" only counts right before a duration ("took 45 minutes"), not "took my mom here 2 hours before close".
_WAIT_WORDS = re.compile(
    r"\bwait(?:ed|ing|s)?\b|\bline\b|\bqueue\b|\bseated\b|\bfor a table\b|\bto get (?:our|my) food\b"
    r"|\btook\s+(?:about\s+|around\s+|over\s+|almost\s+|nearly\s+|like\s+)?(?:\d|an?\s+hour|half)", re.I)
_NOT_WAIT = re.compile(r"\bwalk(?:ing)?\b|\bdriv(?:e|ing)\b|\baway\b|\bcommute\b|\bparking\b|\bdelivery\b|\bbus\b", re.I)
_CLAUSE = re.compile(r"[.!?;\n]+")


def _number(token: str) -> float:
    return float(token) if token[0].isdigit() else float(_NUMBER_WORDS[token.lower()])


def wait_mentions(text: str) -> list[float]:
    """Minutes of waiting stated in one review: "waited 20 minutes" → [20]. Never estimates."""
    found: list[float] = []
    for clause in _CLAUSE.split(text or ""):
        if not _WAIT_WORDS.search(clause) or _NOT_WAIT.search(clause):
            if _NO_WAIT.search(clause):
                found.append(0.0)
            continue
        if _NO_WAIT.search(clause):
            found.append(0.0)
            continue
        if _HOUR_AND_HALF.search(clause):
            found.append(90.0)
            continue
        if _HALF_HOUR.search(clause):
            found.append(30.0)
            clause = _HALF_HOUR.sub(" ", clause)  # so "an hour" inside it isn't counted again
        for m in _DURATION.finditer(clause):
            # "wait a minute" is an expression, not a wait time; "an hour wait" is.
            if m.group(1).lower() in ("a", "an") and m.group(3).lower().startswith("m"):
                continue
            low = _number(m.group(1))
            high = _number(m.group(2)) if m.group(2) else low
            minutes = (low + high) / 2
            if m.group(3).lower().startswith(("h", "hr")):
                minutes *= 60
            if 0 <= minutes <= MAX_WAIT_MIN:
                found.append(minutes)
    return found


def wait_minutes(texts: list[str]) -> int | None:
    """Median of every wait time reviewers actually mention; None when nobody mentions one."""
    mentions = [m for t in texts for m in wait_mentions(t)]
    return round(statistics.median(mentions)) if mentions else None


# ---------- ambiance ----------

AMBIANCE_LABELS = ("positive", "negative", "mixed", "neutral", "none")


def ambiance_stats(labels: list[str]) -> tuple[int | None, float | None]:
    """(ambiancePct, ambianceMentionRate) from one label per review read.

    ambiancePct = positive ambiance mentions ÷ all ambiance mentions (0-100), None with no mentions.
    ambianceMentionRate = reviews mentioning ambiance ÷ reviews read (0-1), None with no reviews.
    """
    if not labels:
        return None, None
    mentioned = [label for label in labels if label != "none"]
    rate = round(len(mentioned) / len(labels), 2)
    if not mentioned:
        return None, rate
    return round(100 * sum(label == "positive" for label in mentioned) / len(mentioned)), rate


# ---------- ranking ----------

def wait_score(minutes: float | None) -> int | None:
    """Wait as a 0-100 score for ranking only: 0 min → 100, 30+ min → 0."""
    if minutes is None:
        return None
    return max(0, min(100, round(100 - minutes / WAIT_SCALE_MIN * 100)))


def ranking_average(spot: dict) -> float | None:
    """Average of the 0-100 attribute scores plus the wait score. None when nothing could be scored."""
    values = [v for v in (spot.get("scores") or {}).values() if v is not None]
    ws = wait_score(spot.get("waitMinutes"))
    if ws is not None:
        values.append(ws)
    return sum(values) / len(values) if values else None


def pick(spots: list[dict]) -> dict | None:
    """The crumbs pick: highest ranking average; ties go to the spot with more reviews read."""
    ranked = [(ranking_average(s), s) for s in spots]
    ranked = [(avg, s) for avg, s in ranked if avg is not None]
    if not ranked:
        return None
    ranked.sort(key=lambda pair: (pair[0], pair[1].get("reviewCount") or 0, pair[1].get("name", "")), reverse=True)
    return ranked[0][1]


def best_at(spots: list[dict], attributes: list[dict]) -> dict[str, str]:
    """{spot id: attribute id} for spots that rank #1 in the area on something.

    A spot that leads several attributes gets the one it leads by the most. A tie for first is no lead.
    """
    leads: dict[str, tuple[str, float]] = {}
    for attr in attributes:
        valued = [(metric_value(s, attr["id"]), s) for s in spots]
        valued = [(v, s) for v, s in valued if v is not None]
        if len(valued) < 2:
            continue
        better_first = sorted(valued, key=lambda pair: pair[0], reverse=attr["id"] != "wait")
        (top_value, top), (second_value, _) = better_first[0], better_first[1]
        if top_value == second_value:
            continue
        margin = abs(gap_score(attr["id"], second_value, top_value))
        if top["id"] not in leads or margin > leads[top["id"]][1]:
            leads[top["id"]] = (attr["id"], margin)
    return {spot_id: attr_id for spot_id, (attr_id, _) in leads.items()}


def attribute_leaders(spots: list[dict], attributes: list[dict]) -> dict[str, str]:
    """{attribute id: spot id} for the strict #1 on each attribute (at least two spots with a value, no tie)."""
    leaders: dict[str, str] = {}
    for attr in attributes:
        valued = [(metric_value(s, attr["id"]), s["id"]) for s in spots]
        valued = sorted(((v, i) for v, i in valued if v is not None), reverse=attr["id"] != "wait")
        if len(valued) >= 2 and valued[0][0] != valued[1][0]:
            leaders[attr["id"]] = valued[0][1]
    return leaders


def new_leaders(previous: list[dict] | None, current: list[dict], attributes: list[dict]) -> dict[str, str]:
    """Attributes whose #1 spot changed since the previous scoring of the same area: {attribute id: new #1 spot id}.

    The first scoring of an area is a baseline and produces nothing, like Ruth's monitor.
    """
    if previous is None:
        return {}
    before = attribute_leaders(previous, attributes)
    return {attr: spot for attr, spot in attribute_leaders(current, attributes).items() if before.get(attr) != spot}


def best_at_label(attr: dict) -> str:
    if attr["id"] == "wait":
        return "Shortest wait"
    if attr["id"] == "ambiance":
        return "Best vibe"
    return f"Best {attr['label'].lower()}"


def area_averages(spots: list[dict], attributes: list[dict]) -> dict:
    """Average of each attribute across spots that have a value, plus waitMinutes and ambiancePct."""
    out: dict = {}
    for attr in attributes:
        values = [v for v in (metric_value(s, attr["id"]) for s in spots) if v is not None]
        key = {"wait": "waitMinutes", "ambiance": "ambiancePct"}.get(attr["id"], attr["id"])
        out[key] = round(sum(values) / len(values)) if values else None
    return out


# ---------- comparing one business with rivals ----------

def metric_value(spot: dict, attr_id: str):
    if attr_id == "wait":
        return spot.get("waitMinutes")
    if attr_id == "ambiance":
        return spot.get("ambiancePct")
    return (spot.get("scores") or {}).get(attr_id)


def gap_score(attr_id: str, you: float, other: float) -> float:
    """How far `other` beats `you`, as a share of the bar scale (0-100). Negative when you're better."""
    if attr_id == "wait":
        return (you - other) / WAIT_SCALE_MIN * 100
    return other - you


def gap_label(attr_id: str, you: float, other: float) -> str:
    """"+12 min" or "−36 pts": how far behind you are."""
    if attr_id == "wait":
        return f"+{round(you - other)} min"
    return f"−{round(other - you)} pts"


def likely_because(you: dict, rival: dict, attributes: list[dict]) -> dict | None:
    """The attribute where the rival beats you by the most, minutes and points on one scale."""
    best = None
    for attr in attributes:
        mine, theirs = metric_value(you, attr["id"]), metric_value(rival, attr["id"])
        if mine is None or theirs is None:
            continue
        gap = gap_score(attr["id"], mine, theirs)
        if gap > 0 and (best is None or gap > best[0]):
            best = (gap, {
                "attribute": attr["id"], "label": attr["label"], "you": mine, "them": theirs,
                "unit": "min" if attr["id"] == "wait" else "pts", "gapLabel": gap_label(attr["id"], mine, theirs),
            })
    return best[1] if best else None


def rivals_report(you: dict, picks: list[dict], spots_by_id: dict[str, dict], attributes: list[dict]) -> dict:
    """Picks won and lost by `you` (picks where you were one of the compared spots) and why rivals won."""
    relevant = [p for p in picks if you["id"] in p["compared_spot_ids"]]
    won = sum(p["chosen_spot_id"] == you["id"] for p in relevant)
    lost_to: dict[str, int] = {}
    for p in relevant:
        if p["chosen_spot_id"] != you["id"]:
            lost_to[p["chosen_spot_id"]] = lost_to.get(p["chosen_spot_id"], 0) + 1

    rivals = []
    for spot_id, count in sorted(lost_to.items(), key=lambda kv: (-kv[1], kv[0])):
        rival = spots_by_id.get(spot_id)
        rivals.append({
            "spotId": spot_id,
            "name": rival["name"] if rival else "A nearby spot",
            "picksWon": count,
            "likelyBecause": likely_because(you, rival, attributes) if rival else None,
        })

    others = [s for s in spots_by_id.values() if s["id"] != you["id"]]
    where_you_win = []
    for attr in attributes:
        mine = metric_value(you, attr["id"])
        theirs = [v for v in (metric_value(s, attr["id"]) for s in others) if v is not None]
        if mine is None or not theirs or not all(gap_score(attr["id"], mine, t) < 0 for t in theirs):
            continue
        best_rival = min(theirs) if attr["id"] == "wait" else max(theirs)
        lead = (best_rival - mine) if attr["id"] == "wait" else (mine - best_rival)
        where_you_win.append({
            "attribute": attr["id"], "label": attr["label"], "you": mine, "bestRival": best_rival,
            "unit": "min" if attr["id"] == "wait" else "pts",
            "leadLabel": f"−{round(lead)} min" if attr["id"] == "wait" else f"+{round(lead)} pts",
        })

    return {"picksWon": won, "picksLost": sum(lost_to.values()), "rivals": rivals, "whereYouWin": where_you_win}


# ---------- business insights ----------

_GOAL_SYNONYMS = {"wait": ("wait", "line", "fast", "speed", "quick"), "ambiance": ("ambiance", "ambience", "vibe", "atmosphere", "decor")}


def goal_attributes(goals: list[str], attributes: list[dict]) -> list[str]:
    """Map the owner's goals ("shorter waits", "rice", "Value") to attribute ids, in the owner's order."""
    ordered: list[str] = []
    for goal in goals:
        text = goal.lower()
        for attr in attributes:
            words = _GOAL_SYNONYMS.get(attr["id"], (attr["id"], attr["label"].lower()))
            if any(re.search(rf"\b{re.escape(w)}", text) for w in words) and attr["id"] not in ordered:
                ordered.append(attr["id"])
    return ordered


def insights(you: dict, area: list[dict], attributes: list[dict], goals: list[str], won: int, lost: int) -> dict:
    """Reputation, momentum and edge (0-100 each) plus the breakdown, wait, ambiance and biggest drag.

    reputation = average of your 0-100 review scores.
    momentum   = share of recent picks you won when you were compared (None with no picks).
    edge       = share of head-to-head attribute comparisons with each nearby spot that you win (ties = half).
    """
    first = goal_attributes(goals, attributes)
    ordered = [a for i in first for a in attributes if a["id"] == i] + [a for a in attributes if a["id"] not in first]

    breakdown = []
    for attr in ordered:
        values = [v for v in (metric_value(s, attr["id"]) for s in area) if v is not None]
        breakdown.append({
            "attribute": attr["id"], "label": attr["label"], "unit": attr.get("unit", "pts"),
            "you": metric_value(you, attr["id"]),
            "areaAvg": round(sum(values) / len(values)) if values else None,
            "isGoal": attr["id"] in first,
        })

    scored = [v for k, v in (you.get("scores") or {}).items() if v is not None]
    reputation = round(sum(scored) / len(scored)) if scored else None
    momentum = round(100 * won / (won + lost)) if won + lost else None

    points, total = 0.0, 0
    for spot in area:
        for attr in attributes:
            mine, theirs = metric_value(you, attr["id"]), metric_value(spot, attr["id"])
            if mine is None or theirs is None:
                continue
            gap = gap_score(attr["id"], mine, theirs)
            points += 1 if gap < 0 else 0.5 if gap == 0 else 0
            total += 1
    edge = round(100 * points / total) if total else None

    drag = None
    for row in breakdown:
        if row["you"] is None or row["areaAvg"] is None:
            continue
        gap = gap_score(row["attribute"], row["you"], row["areaAvg"])
        if gap > 0 and (drag is None or gap > drag[0]):
            drag = (gap, row)
    biggest_drag = None
    if drag:
        row = drag[1]
        if row["attribute"] == "wait":
            text = f"Your wait is about {round(row['you'] - row['areaAvg'])} min longer than the area average ({row['you']} vs {row['areaAvg']} min)."
        else:
            text = f"{row['label']} is {round(row['areaAvg'] - row['you'])} pts below the area average ({row['you']} vs {row['areaAvg']})."
        biggest_drag = {"attribute": row["attribute"], "text": text}

    wait_row = next((r for r in breakdown if r["attribute"] == "wait"), None)
    return {
        "reputation": reputation,
        "momentum": momentum,
        "edge": edge,
        "breakdown": breakdown,
        "wait": {"youMinutes": you.get("waitMinutes"), "areaMinutes": wait_row["areaAvg"] if wait_row else None},
        "ambiance": {"pct": you.get("ambiancePct"), "mentionRate": you.get("ambianceMentionRate")},
        "biggestDrag": biggest_drag,
    }
