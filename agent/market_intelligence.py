"""Deterministic, offline product-gap and review-trend analysis.

Inputs are observations, not claims about sales. Product names use case/whitespace
normalization plus a small explicit alias list; classifiers should use consistent
names for other synonyms.
Branch identity is the normalized business name AND address. Full, dated review
texts alone qualify for trend calculations; search snippets, editorial text and
the relevance-selected Google Places sample never qualify.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Iterable, Literal
from urllib.parse import urlparse
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OwnerMenu(EvidenceModel):
    products: list[str] = Field(default_factory=list)
    confirmed_complete: bool = False
    confirmed_at: date | None = None

    @field_validator("products")
    @classmethod
    def clean_products(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Owner products must not be blank")
        return [value.strip() for value in values]


class ProductMention(EvidenceModel):
    product: str = Field(min_length=1)
    sentiment: Literal["positive", "negative", "neutral", "request"]


class LocatedEvidence(EvidenceModel):
    business_name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    source_url: str

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("source_url must be an absolute HTTP(S) URL")
        return value


class MenuObservation(LocatedEvidence):
    product: str = Field(min_length=1)
    observed_at: date
    price: str | None = None
    # Plain generic name used to group the same product across shops
    # ("Twice-Baked Almond Croissant" -> "almond croissant"); `product` stays verbatim.
    category: str | None = None


class ReviewObservation(LocatedEvidence):
    text: str = Field(min_length=1)
    published_at: date | None = None
    source_kind: Literal[
        "review_text", "search_snippet", "editorial", "google_places_sample"
    ] = "search_snippet"
    mentions: list[ProductMention] = Field(default_factory=list)
    review_id: str | None = None
    observed_at: date | None = None


class EvidenceBundle(EvidenceModel):
    menu_observations: list[MenuObservation] = Field(default_factory=list)
    review_observations: list[ReviewObservation] = Field(default_factory=list)


class BusinessEvidence(EvidenceModel):
    business_name: str
    address: str
    source_urls: list[str]


class ProductExperiment(EvidenceModel):
    action: str
    duration_days: int = 14
    metrics: list[str] = Field(default_factory=lambda: [
        "units produced", "units sold", "unsold units", "ingredient cost",
        "preparation time", "customer feedback",
    ])
    decision_rule: str = (
        "Set a minimum sell-through rate, maximum waste and preparation-time budget "
        "with the owner before the trial; expand only if those targets are met."
    )


class ProductGap(EvidenceModel):
    product: str
    owner_menu_status: Literal["confirmed_absent", "needs_confirmation"]
    competitor_count: int
    competitors: list[BusinessEvidence]
    positive_reviews: int
    request_reviews: int
    negative_reviews: int
    undated_supporting_reviews: int
    google_places_sample_reviews: int
    confidence: Literal["low", "moderate"]
    source_urls: list[str]
    limitations: list[str]
    experiment: ProductExperiment


class PeriodMetrics(EvidenceModel):
    start: date
    end: date
    total_reviews: int
    positive_or_request_reviews: int
    negative_reviews: int
    positive_or_request_share: float | None
    standardized_positive_or_request_share: float | None


class ProductTrend(EvidenceModel):
    product: str
    status: Literal["rising", "falling", "stable", "insufficient_evidence"]
    previous: PeriodMetrics
    current: PeriodMetrics
    change_percentage_points: float | None
    matched_cohorts: int
    comparison_method: Literal["fixed_cohort_weights"] = "fixed_cohort_weights"
    source_urls: list[str]
    limitations: list[str]


class MarketIntelligence(EvidenceModel):
    business: str
    location: str
    as_of: date
    window_days: int
    min_reviews_per_period: int
    min_product_mentions_per_period: int
    menu_max_age_days: int
    min_gap_competitors: int = 1
    trend_change_threshold_percentage_points: float = 5.0
    product_gaps: list[ProductGap]
    product_trends: list[ProductTrend]
    evidence_counts: dict[str, int]
    limitations: list[str]


def _normal(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def canonical_product(value: str) -> str:
    """Normalize only supported exact product aliases, never branch identities."""
    normalized = _normal(value)
    return {"pain au chocolat": "chocolate croissant"}.get(normalized, normalized)


def _branch(item: LocatedEvidence) -> tuple[str, str]:
    return _normal(item.business_name), _normal(item.address)


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _cohort(review: ReviewObservation) -> tuple[str, str, str]:
    return (*_branch(review), _host(review.source_url))


def merge_evidence(bundles: Iterable[EvidenceBundle | dict]) -> EvidenceBundle:
    """Merge serialized evidence snapshots. Analysis performs deduplication."""
    merged = EvidenceBundle()
    for value in bundles:
        bundle = EvidenceBundle.model_validate(value)
        merged.menu_observations.extend(bundle.menu_observations)
        merged.review_observations.extend(bundle.review_observations)
    return merged


def _deduplicate_reviews(reviews: list[ReviewObservation]) -> tuple[list[ReviewObservation], dict[int, set[str]]]:
    """Union matching stable IDs or exact branch/text/date fingerprints.

    Repeated snapshots and syndicated copies cannot inflate counts. Without
    stable IDs, identical text/date pairs may also merge distinct reviewers;
    this conservative limitation is reported to the caller.
    """
    parents = list(range(len(reviews)))
    identities = [{_cohort(r): {r.review_id}} if r.review_id else {} for r in reviews]

    def root(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left, right = root(left), root(right)
        if left == right:
            return
        # Two explicitly different IDs from one review provider represent two
        # customers even when they used identical text on the same day.
        if any(identities[left][key] != identities[right][key]
               for key in identities[left].keys() & identities[right].keys()):
            return
        parents[left] = right
        identities[right].update(identities[left])

    seen = {}
    for index, review in enumerate(reviews):
        keys = [("text", *_branch(review), _normal(review.text), review.published_at)]
        if review.review_id:
            keys.append(("id", *_cohort(review), review.review_id))
        for key in keys:
            if key in seen:
                union(index, seen[key])
            else:
                seen[key] = index
    groups = defaultdict(list)
    for index, review in enumerate(reviews):
        groups[root(index)].append(review)

    kind_rank = {"editorial": 0, "search_snippet": 1, "google_places_sample": 2, "review_text": 3}
    selected, sources = [], {}
    for group in groups.values():
        chosen = max(group, key=lambda r: (
            kind_rank[r.source_kind], r.published_at is not None,
            r.observed_at or date.min, len(r.mentions), len(r.text), r.source_url,
            r.model_dump_json(),
        ))
        sources[id(chosen)] = {r.source_url for r in group}
        selected.append(chosen)
    return selected, sources


def _sentiments(review: ReviewObservation, product: str) -> set[str]:
    return {mention.sentiment for mention in review.mentions if canonical_product(mention.product) == product}


def _support(review: ReviewObservation, product: str) -> bool:
    return bool(_sentiments(review, product) & {"positive", "request"})


def analyze_market(
    business: str,
    location: str,
    *,
    owner_menu: OwnerMenu | dict | None = None,
    evidence: EvidenceBundle | dict | None = None,
    as_of: date | None = None,
    window_days: int = 30,
    min_reviews_per_period: int = 10,
    min_product_mentions_per_period: int = 3,
    menu_max_age_days: int = 90,
    min_gap_competitors: int = 1,
) -> MarketIntelligence:
    """Find observed menu gaps and descriptive changes in matched review samples.

    The current period includes ``as_of``. Comparison periods have equal length.
    A trend requires minimum denominators AND positive/request counts in both
    periods; it is not a significance test or a prediction of demand or profit.
    """
    if not business.strip() or not location.strip():
        raise ValueError("business and location must not be blank")
    if any(value < 1 for value in (
        window_days, min_reviews_per_period, min_product_mentions_per_period, menu_max_age_days,
        min_gap_competitors,
    )):
        raise ValueError("Window, sample thresholds and menu age must be positive")
    today = as_of or date.today()
    bundle = EvidenceBundle.model_validate(evidence or {})
    owner = OwnerMenu.model_validate(owner_menu or {})
    current_start = today - timedelta(days=window_days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = current_start - timedelta(days=window_days)
    oldest_menu = today - timedelta(days=menu_max_age_days)
    owner_is_current = bool(
        owner.confirmed_complete and owner.confirmed_at
        and oldest_menu <= owner.confirmed_at <= today
    )
    owned = {canonical_product(product) for product in owner.products}
    target_name = _normal(business)
    target_branch = (target_name, _normal(location))

    # A missing/ambiguous target address must not turn the business's own listing
    # into a competitor. Same-name branches are excluded conservatively.
    def competitor(item: LocatedEvidence) -> bool:
        return _branch(item) != target_branch and _normal(item.business_name) != target_name

    valid_reviews = [r for r in bundle.review_observations if (
        (r.published_at is None or r.published_at <= today)
        and (r.observed_at is None or r.observed_at <= today)
    )]
    reviews, review_sources = _deduplicate_reviews(valid_reviews)
    menus = [m for m in bundle.menu_observations if oldest_menu <= m.observed_at <= today and competitor(m)]
    # Deduplicate identical observations, retaining multiple independent URLs.
    menu_keys = {(_branch(m), canonical_product(m.category or m.product), m.source_url, m.observed_at) for m in menus}
    by_product = defaultdict(list)
    for menu in menus:
        by_product[canonical_product(menu.category or menu.product)].append(menu)

    gaps = []
    for product, observations in sorted(by_product.items()):
        if product in owned:
            continue
        branches = defaultdict(list)
        for observation in observations:
            branches[_branch(observation)].append(observation)
        if len(branches) < min_gap_competitors:
            continue  # e.g. one shop's specialty item is not a market gap
        relevant_reviews = [r for r in reviews if competitor(r)
            and r.source_kind in {"review_text", "google_places_sample"}
            and (r.published_at is None or previous_start <= r.published_at <= today)
            and _sentiments(r, product)]
        dated = [r for r in relevant_reviews if r.published_at is not None]
        positive = sum("positive" in _sentiments(r, product) for r in dated)
        requested = sum("request" in _sentiments(r, product) for r in dated)
        negative = sum("negative" in _sentiments(r, product) for r in dated)
        full_support = [r for r in dated if r.source_kind == "review_text" and _support(r, product)]
        moderate = (owner_is_current and len(branches) >= 2 and len(full_support) >= 3
            and len({_branch(r) for r in full_support}) >= 2 and negative <= len(full_support))
        limitations = [
            "An observed menu listing does not verify current availability, sales or profitability.",
            "Review counts reflect the collected sample; positive and request categories may overlap.",
        ]
        if not owner_is_current:
            limitations.append("A complete owner menu confirmed within the menu-age limit is required to establish absence.")
        if not full_support:
            limitations.append("No recent full customer review supports demand; validate interest before a production trial.")
        if any(r.source_kind == "google_places_sample" for r in relevant_reviews):
            limitations.append("Google Places supplies a selected sample, not representative demand evidence.")
        if any(r.published_at is None for r in relevant_reviews):
            limitations.append("Undated feedback is reported separately and cannot establish current demand.")
        source_urls = {m.source_url for m in observations}
        for review in relevant_reviews:
            source_urls.update(review_sources[id(review)])
        action = (
            f"Confirm whether {product} is already offered, ask customers about interest, "
            "and check ingredients, equipment and preparation capacity. "
            "If feasible, run a limited-batch trial and measure the results."
        )
        gaps.append(ProductGap(
            product=product,
            owner_menu_status="confirmed_absent" if owner_is_current else "needs_confirmation",
            competitor_count=len(branches),
            competitors=[BusinessEvidence(
                business_name=items[0].business_name, address=items[0].address,
                source_urls=sorted({m.source_url for m in items}),
            ) for _, items in sorted(branches.items())],
            positive_reviews=positive, request_reviews=requested, negative_reviews=negative,
            undated_supporting_reviews=sum(r.published_at is None and _support(r, product) for r in relevant_reviews),
            google_places_sample_reviews=sum(r.source_kind == "google_places_sample" for r in relevant_reviews),
            confidence="moderate" if moderate else "low", source_urls=sorted(source_urls),
            limitations=limitations, experiment=ProductExperiment(action=action),
        ))
    gaps.sort(key=lambda g: (-(g.positive_reviews + g.request_reviews), -g.competitor_count, g.product))

    eligible = [r for r in reviews if r.source_kind == "review_text" and r.published_at is not None
        and previous_start <= r.published_at <= today]
    previous_all = [r for r in eligible if r.published_at < current_start]
    current_all = [r for r in eligible if r.published_at >= current_start]
    matched = {_cohort(r) for r in previous_all} & {_cohort(r) for r in current_all}
    previous_reviews = [r for r in previous_all if _cohort(r) in matched]
    current_reviews = [r for r in current_all if _cohort(r) in matched]
    products = sorted({canonical_product(m.product) for r in reviews for m in r.mentions} | set(by_product))
    previous_by_cohort = {key: [r for r in previous_reviews if _cohort(r) == key] for key in matched}
    current_by_cohort = {key: [r for r in current_reviews if _cohort(r) == key] for key in matched}
    combined_count = len(previous_reviews) + len(current_reviews)
    # Hold business/source composition fixed. Pooled shares alone can rise when
    # collection shifts toward a shop with a higher baseline product mention rate.
    weights = {key: (len(previous_by_cohort[key]) + len(current_by_cohort[key])) / combined_count
               for key in matched} if combined_count else {}

    def standardized_share(items_by_cohort: dict, product: str) -> float | None:
        if not weights:
            return None
        return sum(weights[key] * sum(_support(r, product) for r in items_by_cohort[key])
                   / len(items_by_cohort[key]) for key in sorted(weights))

    def metrics(items: list[ReviewObservation], product: str, start: date, end: date,
                standardized: float | None) -> PeriodMetrics:
        support = sum(_support(r, product) for r in items)
        return PeriodMetrics(
            start=start, end=end, total_reviews=len(items), positive_or_request_reviews=support,
            negative_reviews=sum("negative" in _sentiments(r, product) for r in items),
            positive_or_request_share=round(support / len(items), 6) if items else None,
            standardized_positive_or_request_share=round(standardized, 6) if standardized is not None else None,
        )

    trends = []
    for product in products:
        previous_standardized = standardized_share(previous_by_cohort, product)
        current_standardized = standardized_share(current_by_cohort, product)
        previous = metrics(previous_reviews, product, previous_start, previous_end, previous_standardized)
        current = metrics(current_reviews, product, current_start, today, current_standardized)
        limitations = [
            "Changes describe collected review samples, not sales or market-wide demand; no statistical significance is claimed.",
            "The change uses fixed business/source weights based on combined review volume across both periods; pooled shares remain visible.",
            "Collection coverage and reviewer composition within a cohort may still change between periods.",
        ]
        sufficient = bool(matched) and all(
            period.total_reviews >= min_reviews_per_period
            and period.positive_or_request_reviews >= min_product_mentions_per_period
            for period in (previous, current)
        )
        change = None
        status = "insufficient_evidence"
        if sufficient:
            # Compare raw standardized rates, not rounded displayed shares.
            change = round(100 * (current_standardized - previous_standardized), 2)
            status = "rising" if change >= 5 else "falling" if change <= -5 else "stable"
        else:
            limitations.append(
                f"Need at least {min_reviews_per_period} full dated reviews and "
                f"{min_product_mentions_per_period} positive/request reviews per period "
                "from business/source cohorts present in both periods."
            )
        sources = set()
        for review in previous_reviews + current_reviews:
            sources.update(review_sources[id(review)])
        trends.append(ProductTrend(
            product=product, status=status, previous=previous, current=current,
            change_percentage_points=change, matched_cohorts=len(matched),
            source_urls=sorted(sources), limitations=limitations,
        ))

    limitations = [
        "Products use case/whitespace matching and the exact alias pain au chocolat = chocolate croissant; other synonyms require consistent classification before import.",
        "Branch identity uses name plus address; all target-name branches are conservatively excluded from competitor gaps.",
        "Menu observation dates record collection time, not proof the underlying menu is up to date.",
        "Exact branch/text/date duplicates and stable review IDs are merged; identical reviews without IDs may be undercounted.",
        "Search snippets, editorial summaries and Google Places samples never establish temporal trends.",
    ]
    return MarketIntelligence(
        business=business, location=location, as_of=today, window_days=window_days,
        min_reviews_per_period=min_reviews_per_period,
        min_product_mentions_per_period=min_product_mentions_per_period,
        menu_max_age_days=menu_max_age_days, min_gap_competitors=min_gap_competitors,
        product_gaps=gaps, product_trends=trends,
        evidence_counts={
            "menu_observations_received": len(bundle.menu_observations),
            "recent_competitor_menu_observations": len(menu_keys),
            "review_observations_received": len(bundle.review_observations),
            "future_review_observations_excluded": len(bundle.review_observations) - len(valid_reviews),
            "duplicate_review_observations_removed": len(valid_reviews) - len(reviews),
            "unique_review_observations": len(reviews),
            "full_dated_reviews_in_windows": len(eligible),
            "matched_cohorts": len(matched),
            "previous_matched_reviews": len(previous_reviews),
            "current_matched_reviews": len(current_reviews),
            "undated_review_observations": sum(r.published_at is None for r in reviews),
            "non_full_review_observations": sum(r.source_kind != "review_text" for r in reviews),
        },
        limitations=limitations,
    )
