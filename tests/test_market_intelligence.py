"""Offline checks for evidence quality, product gaps and temporal denominators."""

from datetime import date, timedelta
import unittest

from pydantic import ValidationError

from agent.market_intelligence import (
    EvidenceBundle, MenuObservation, OwnerMenu, ProductMention, ReviewObservation,
    analyze_market, merge_evidence,
)


TODAY = date(2026, 10, 25)


def menu(product="matcha", business="Nearby Bakery", address="2 Main St", **kwargs):
    return MenuObservation(
        business_name=business, address=address, product=product,
        source_url="https://bakery.example/menu", observed_at=TODAY, **kwargs,
    )


def review(index, *, days_ago=1, product="matcha", sentiment="positive",
           business="Nearby Bakery", address="2 Main St", kind="review_text", **kwargs):
    values = dict(
        business_name=business, address=address,
        source_url="https://reviews.example/bakery", text=f"Customer feedback number {index}.",
        published_at=TODAY - timedelta(days=days_ago), source_kind=kind,
        mentions=[ProductMention(product=product, sentiment=sentiment)] if product else [],
        review_id=str(index), observed_at=TODAY,
    )
    values.update(kwargs)
    return ReviewObservation(**values)


def analyze(*, menus=(), reviews=(), owner=None, **kwargs):
    return analyze_market(
        "Moonrise Bakery", "1805 Queen Anne Ave N", owner_menu=owner,
        evidence=EvidenceBundle(menu_observations=list(menus), review_observations=list(reviews)),
        as_of=TODAY, **kwargs,
    )


class ProductGapTests(unittest.TestCase):
    def test_missing_incomplete_stale_or_future_owner_menu_needs_confirmation(self):
        owners = [None, OwnerMenu(products=[]), OwnerMenu(confirmed_complete=True),
            OwnerMenu(confirmed_complete=True, confirmed_at=TODAY - timedelta(days=91)),
            OwnerMenu(confirmed_complete=True, confirmed_at=TODAY + timedelta(days=1))]
        for owner in owners:
            with self.subTest(owner=owner):
                result = analyze(menus=[menu()], owner=owner)
                self.assertEqual(result.product_gaps[0].owner_menu_status, "needs_confirmation")
                self.assertEqual(result.product_gaps[0].confidence, "low")

    def test_fresh_complete_owner_menu_can_confirm_absence(self):
        owner = OwnerMenu(products=["Croissant"], confirmed_complete=True, confirmed_at=TODAY)
        gap = analyze(menus=[menu()], owner=owner).product_gaps[0]
        self.assertEqual(gap.owner_menu_status, "confirmed_absent")
        self.assertEqual(gap.positive_reviews, 0)
        self.assertTrue(any("validate interest" in limitation for limitation in gap.limitations))

    def test_owned_product_never_becomes_gap_with_case_and_whitespace_variation(self):
        result = analyze(menus=[menu("  MATCHA  latte ")], owner={"products": ["matcha latte"]})
        self.assertEqual(result.product_gaps, [])

    def test_exact_product_alias_does_not_create_false_owner_menu_gap(self):
        for owned, observed in (("Pain au chocolat", "Chocolate croissant"),
                                ("Chocolate croissant", " PAIN AU CHOCOLAT ")):
            with self.subTest(owned=owned):
                result = analyze(menus=[menu(observed)], owner={
                    "products": [owned], "confirmed_complete": True, "confirmed_at": TODAY,
                })
                self.assertEqual(result.product_gaps, [])

    def test_target_excluded_and_chain_branches_count_separately(self):
        menus = [menu(business="Moonrise Bakery", address="1805 Queen Anne Ave N"),
                 menu(business="MOONRISE Bakery", address="other branch"),
                 menu(address="2 Main St"), menu(address="3 Main St"), menu(address="2 Main St")]
        gap = analyze(menus=menus).product_gaps[0]
        self.assertEqual(gap.competitor_count, 2)
        self.assertEqual({x.address for x in gap.competitors}, {"2 Main St", "3 Main St"})

    def test_negative_mentions_and_snippets_are_not_positive_demand(self):
        reviews = [review("bad", sentiment="negative"), review("snippet", kind="search_snippet"),
                   review("editor", kind="editorial"), review("request", sentiment="request")]
        gap = analyze(menus=[menu()], reviews=reviews).product_gaps[0]
        self.assertEqual((gap.positive_reviews, gap.request_reviews, gap.negative_reviews), (0, 1, 1))

    def test_undated_google_and_future_reviews_are_explicit(self):
        reviews = [review("undated", published_at=None),
                   review("google", kind="google_places_sample"), review("future", days_ago=-1)]
        result = analyze(menus=[menu()], reviews=reviews)
        gap = result.product_gaps[0]
        self.assertEqual(gap.positive_reviews, 1)
        self.assertEqual(gap.undated_supporting_reviews, 1)
        self.assertEqual(gap.google_places_sample_reviews, 1)
        self.assertEqual(result.evidence_counts["future_review_observations_excluded"], 1)
        self.assertEqual(result.product_trends[0].status, "insufficient_evidence")

    def test_old_and_future_menu_observations_do_not_generate_gap(self):
        old = menu().model_copy(update={"observed_at": TODAY - timedelta(days=91)})
        future = menu().model_copy(update={"observed_at": TODAY + timedelta(days=1)})
        self.assertEqual(analyze(menus=[old, future]).product_gaps, [])


class ReviewDeduplicationTests(unittest.TestCase):
    def test_id_dedup_and_fingerprint_dedup_across_snapshots(self):
        original = review("first")
        edited = original.model_copy(update={"text": "Edited customer review.", "observed_at": TODAY})
        copy = review("copy", review_id=None, text=original.text)
        result = analyze(reviews=[original, original, edited, copy])
        self.assertEqual(result.evidence_counts["unique_review_observations"], 1)
        self.assertEqual(result.evidence_counts["duplicate_review_observations_removed"], 3)

    def test_identical_text_with_distinct_known_review_ids_remains_distinct(self):
        result = analyze(reviews=[review("one", text="Great food"), review("two", text="Great food")])
        self.assertEqual(result.evidence_counts["unique_review_observations"], 2)

    def test_different_branches_and_different_dates_not_merged_by_text(self):
        reviews = [review("one", review_id=None, text="Great food"),
                   review("two", review_id=None, text="Great food", address="other branch"),
                   review("three", review_id=None, text="Great food", days_ago=2)]
        self.assertEqual(analyze(reviews=reviews).evidence_counts["unique_review_observations"], 3)

    def test_full_review_preferred_over_snippet_without_double_counting(self):
        reviews = [review("one", kind="search_snippet"), review("one")]
        result = analyze(menus=[menu()], reviews=reviews)
        self.assertEqual(result.product_gaps[0].positive_reviews, 1)
        self.assertEqual(result.evidence_counts["non_full_review_observations"], 0)


class ProductTrendTests(unittest.TestCase):
    def paired_reviews(self, previous_support=3, current_support=6):
        return [review(f"old-{i}", days_ago=40, product="matcha" if i < previous_support else None)
                for i in range(10)] + [
                    review(f"new-{i}", days_ago=10, product="matcha" if i < current_support else None)
                    for i in range(10)]

    def test_equal_windows_all_reviews_denominator_and_actual_share_change(self):
        result = analyze(reviews=self.paired_reviews())
        trend = result.product_trends[0]
        self.assertEqual(trend.status, "rising")
        self.assertEqual((trend.previous.total_reviews, trend.current.total_reviews), (10, 10))
        self.assertEqual((trend.previous.positive_or_request_share, trend.current.positive_or_request_share), (0.3, 0.6))
        self.assertEqual(trend.change_percentage_points, 30)
        self.assertEqual((trend.current.end - trend.current.start).days, 29)
        self.assertEqual((trend.previous.end - trend.previous.start).days, 29)
        self.assertEqual(trend.previous.end + timedelta(days=1), trend.current.start)

    def test_product_aliases_coalesce_across_review_periods(self):
        reviews = []
        for period, days, product in (("old", 40, "pain au chocolat"),
                                      ("new", 10, "Chocolate croissant")):
            reviews.extend(review(f"{period}-{i}", days_ago=days,
                                  product=product if i < 3 else None) for i in range(10))
        trends = analyze(reviews=reviews).product_trends
        self.assertEqual(len(trends), 1)
        self.assertEqual(trends[0].product, "chocolate croissant")
        self.assertEqual(trends[0].status, "stable")
        self.assertEqual((trends[0].previous.positive_or_request_reviews,
                          trends[0].current.positive_or_request_reviews), (3, 3))

    def test_new_business_or_new_source_cannot_create_trend(self):
        reviews = self.paired_reviews(current_support=3)
        reviews += [review(f"new-business-{i}", business="New business", address="9 Main St") for i in range(30)]
        reviews += [review(f"new-source-{i}", source_url="https://other-reviews.example/bakery") for i in range(30)]
        trend = analyze(reviews=reviews).product_trends[0]
        self.assertEqual(trend.status, "stable")
        self.assertEqual(trend.current.total_reviews, 10)
        self.assertEqual(trend.matched_cohorts, 1)

    def test_changing_cohort_composition_does_not_create_simpsons_paradox_trend(self):
        reviews = []
        # Both shops have unchanged rates (20% and 80%), but collection shifts
        # toward the high-rate shop. Raw pooled shares rise from 32% to 68%.
        for period, days, low_count, high_count in (("old", 40, 40, 10), ("new", 10, 10, 40)):
            for branch, count, fraction in (("low", low_count, 0.2), ("high", high_count, 0.8)):
                reviews.extend(review(f"{period}-{branch}-{i}", days_ago=days,
                                      address=f"{branch} branch", product="matcha" if i < count * fraction else None)
                               for i in range(count))
        trend = analyze(reviews=reviews).product_trends[0]
        self.assertEqual((trend.previous.positive_or_request_share, trend.current.positive_or_request_share), (0.32, 0.68))
        self.assertEqual((trend.previous.standardized_positive_or_request_share,
                          trend.current.standardized_positive_or_request_share), (0.5, 0.5))
        self.assertEqual(trend.change_percentage_points, 0)
        self.assertEqual(trend.status, "stable")
        self.assertEqual(trend.comparison_method, "fixed_cohort_weights")

    def test_same_chain_different_addresses_are_not_matched(self):
        reviews = [review(f"old-{i}", days_ago=40, address="1 Main St") for i in range(12)]
        reviews += [review(f"new-{i}", days_ago=10, address="2 Main St") for i in range(12)]
        trend = analyze(reviews=reviews).product_trends[0]
        self.assertEqual(trend.matched_cohorts, 0)
        self.assertEqual(trend.status, "insufficient_evidence")

    def test_google_snippets_editorial_and_undated_never_establish_trend(self):
        for kind in ("google_places_sample", "search_snippet", "editorial"):
            with self.subTest(kind=kind):
                reviews = [r.model_copy(update={"source_kind": kind}) for r in self.paired_reviews()]
                result = analyze(reviews=reviews)
                self.assertEqual(result.product_trends[0].status, "insufficient_evidence")
                self.assertEqual(result.evidence_counts["full_dated_reviews_in_windows"], 0)
        reviews = [r.model_copy(update={"published_at": None}) for r in self.paired_reviews()]
        self.assertEqual(analyze(reviews=reviews).product_trends[0].status, "insufficient_evidence")

    def test_sparse_sample_or_sparse_product_mentions_is_insufficient(self):
        for reviews in (self.paired_reviews()[1:], self.paired_reviews(previous_support=1)):
            with self.subTest(count=len(reviews)):
                trend = analyze(reviews=reviews).product_trends[0]
                self.assertEqual(trend.status, "insufficient_evidence")
                self.assertIsNone(trend.change_percentage_points)

    def test_negative_mentions_do_not_count_toward_rising_demand(self):
        reviews = [r.model_copy(update={"mentions": [ProductMention(product="matcha", sentiment="negative")]})
                   for r in self.paired_reviews()]
        trend = analyze(reviews=reviews).product_trends[0]
        self.assertEqual(trend.status, "insufficient_evidence")
        self.assertEqual(trend.current.positive_or_request_reviews, 0)
        self.assertEqual(trend.current.negative_reviews, 10)

    def test_boundaries_future_dates_and_old_reviews(self):
        reviews = [review("today", days_ago=0), review("start-current", days_ago=29),
                   review("end-previous", days_ago=30), review("start-previous", days_ago=59),
                   review("old", days_ago=60), review("future", days_ago=-1)]
        trend = analyze(reviews=reviews, min_reviews_per_period=1,
                        min_product_mentions_per_period=1).product_trends[0]
        self.assertEqual((trend.previous.total_reviews, trend.current.total_reviews), (2, 2))
        self.assertEqual(trend.status, "stable")

    def test_serialized_history_merges_without_inflating_trends(self):
        snapshot = EvidenceBundle(review_observations=self.paired_reviews())
        merged = merge_evidence([snapshot.model_dump(mode="json"), snapshot])
        result = analyze_market("Moonrise Bakery", "1805 Queen Anne Ave N", evidence=merged, as_of=TODAY)
        self.assertEqual(result.product_trends[0].current.total_reviews, 10)
        self.assertEqual(result.evidence_counts["duplicate_review_observations_removed"], 20)
        self.assertIn('"product_trends"', result.model_dump_json())


class ValidationTests(unittest.TestCase):
    def test_invalid_urls_blank_text_and_blank_products_rejected(self):
        with self.assertRaises(ValidationError):
            review("bad", source_url="javascript:alert(1)")
        with self.assertRaises(ValidationError):
            review("bad", text="   ")
        with self.assertRaises(ValidationError):
            OwnerMenu(products=[""])

    def test_invalid_analysis_options_rejected(self):
        with self.assertRaises(ValueError):
            analyze(window_days=0)
        with self.assertRaises(ValueError):
            analyze_market("", "Seattle")


if __name__ == "__main__":
    unittest.main()
