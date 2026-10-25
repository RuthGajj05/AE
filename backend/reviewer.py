"""One Claude call per spot: score the food type's attributes 0-100 from the review text only.

Claude reads numbered review texts and returns, per attribute, a score (or null when no review talks
about it), how many reviews mention it and one short line paraphrasing them; plus one ambiance label
per review. The output is validated with Pydantic, then cleaned: unknown attributes are dropped,
scores without mentions become null, and missing ambiance labels count as "none". Wait minutes and
ambiance percentages are computed in code from the same texts (scoring.py), not by the model.
"""

from typing import Literal

import anthropic
from pydantic import BaseModel, Field

import config
import cuisines

MAX_REVIEWS = 40  # per spot per call; reviewCount reports how many were actually read
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AttributeScore(BaseModel):
    attribute: str = Field(description="Attribute id exactly as given")
    score: int | None = Field(description="0-100 from the review text only; null when no review mentions it")
    mentions: int = Field(description="How many of the numbered reviews talk about this attribute")
    highlight: str | None = Field(description="Up to 12 words paraphrasing what reviewers say about it; null when unmentioned")


class ReviewAmbiance(BaseModel):
    review: int = Field(description="Review number")
    ambiance: Literal["positive", "negative", "mixed", "neutral", "none"]


class SpotScoring(BaseModel):
    attributes: list[AttributeScore]
    ambiance: list[ReviewAmbiance]
    summary: str = Field(description="One short line on what reviewers say overall")


class ScoringError(RuntimeError):
    """Claude could not score this spot (refusal, empty output, API error)."""


SYSTEM = """You score restaurants for a food-comparison app from customer review text.

You get one restaurant, the food type, the attributes to score, and numbered review texts (often short search snippets).
Rules:
- Use only the review texts given. Ignore star ratings, the restaurant's reputation and anything you already know about it.
- Score each attribute 0-100 from what reviewers say about it: 80+ for consistent praise, about 50 for mixed or lukewarm,
  below 40 for consistent complaints. More reviews agreeing moves the score further from 50.
- If no review talks about an attribute, return score null and mentions 0. Never guess.
- highlight paraphrases what reviewers say in up to 12 words, with no names and no invented details.
- For every numbered review, label ambiance: positive, negative, mixed or neutral when it talks about atmosphere,
  decor, noise, seating comfort or vibe; otherwise none.
- summary is one short, plain sentence a diner would find useful."""


def _prompt(name: str, cuisine_id: str, reviews: list[dict]) -> str:
    attrs = cuisines.scored_attributes(cuisine_id)
    lines = [f"Restaurant: {name}", f"Food type: {cuisines.get(cuisine_id)['label']}", "Attributes:"]
    lines += [f"- {a['id']} ({a['label']}): {cuisines.HINTS.get(a['id'], a['label'])}" for a in attrs]
    lines.append(f"\nReviews ({len(reviews)}):")
    lines += [f"[{i}] {r['text'].strip()}" for i, r in enumerate(reviews, start=1)]
    return "\n".join(lines)


def _parse(client: anthropic.Anthropic, prompt: str) -> SpotScoring:
    request = dict(
        model=config.SCORING_MODEL, max_tokens=8000, system=SYSTEM, output_format=SpotScoring,
        output_config={"effort": "medium"}, messages=[{"role": "user", "content": prompt}],
    )
    try:
        # Server-side fallback reroutes a safety decline to another model inside the same call.
        resp = client.beta.messages.parse(**request, betas=[FALLBACK_BETA], fallbacks="default")
    except anthropic.BadRequestError:
        resp = client.messages.parse(**request)  # accounts or platforms without the fallback beta
    if resp.stop_reason == "refusal" or resp.parsed_output is None:
        raise ScoringError(f"Claude returned no scores (stop_reason={resp.stop_reason})")
    return resp.parsed_output


def clean(raw: SpotScoring, cuisine_id: str, review_count: int) -> dict:
    """Keep only valid attributes and labels; turn unsupported scores into null."""
    known = {a["id"] for a in cuisines.scored_attributes(cuisine_id)}
    scores = {a: None for a in known}
    highlights: dict[str, str] = {}
    for item in raw.attributes:
        if item.attribute not in known or item.mentions <= 0 or item.score is None:
            continue
        scores[item.attribute] = max(0, min(100, int(item.score)))
        if item.highlight:
            highlights[item.attribute] = item.highlight.strip()[:120]
    labels = ["none"] * review_count
    for item in raw.ambiance:
        if 1 <= item.review <= review_count:
            labels[item.review - 1] = item.ambiance
    return {"scores": scores, "highlights": highlights, "ambianceLabels": labels, "summary": raw.summary.strip()[:200]}


def score_spot(name: str, cuisine_id: str, reviews: list[dict], client: anthropic.Anthropic | None = None) -> dict:
    """{scores, highlights, ambianceLabels, summary, reviewsUsed} for one spot. Raises ScoringError."""
    reviews = [r for r in reviews if (r.get("text") or "").strip()][:MAX_REVIEWS]
    if not reviews:
        known = cuisines.scored_attributes(cuisine_id)
        return {"scores": {a["id"]: None for a in known}, "highlights": {}, "ambianceLabels": [], "summary": "", "reviewsUsed": []}
    try:
        raw = _parse(client or anthropic.Anthropic(), _prompt(name, cuisine_id, reviews))
    except anthropic.APIError as e:
        raise ScoringError(f"Claude API error: {e}") from e
    return {**clean(raw, cuisine_id, len(reviews)), "reviewsUsed": reviews}
