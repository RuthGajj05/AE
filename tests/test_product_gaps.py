"""Product gaps from fast competitor research: category grouping, the minimum
competitor count, and verification of menu items against pages actually read."""

import unittest
from datetime import date

from agent import fast_competitors
from agent.evidence_store import SourceLedger
from agent.market_intelligence import analyze_market

TODAY = date(2026, 10, 25)


def menu(shop, product, category=None):
    return {"business_name": shop, "address": f"{len(shop)} Main St", "source_url": f"https://{shop.split()[0].lower()}.example/menu",
            "product": product, "category": category, "observed_at": TODAY.isoformat()}


class MinimumCompetitorTests(unittest.TestCase):
    EVIDENCE = {"menu_observations": [
        menu("Alpha Bakery", "Twice-Baked Almond Croissant", "almond croissant"),
        menu("Beta Cafe", "Almond Croissant", "almond croissant"),
        menu("Gamma Bakehouse", "Almond croissant (seasonal)", "almond croissant"),
        menu("Alpha Bakery", "Ube Mochi Donut", "ube mochi donut"),
    ]}

    def gaps(self, minimum, owned=()):
        result = analyze_market("Owner Bakery", "Seattle", owner_menu={"products": list(owned)},
                                evidence=self.EVIDENCE, as_of=TODAY, min_gap_competitors=minimum)
        return {g.product: g.competitor_count for g in result.product_gaps}

    def test_different_names_group_by_category(self):
        self.assertEqual(self.gaps(1)["almond croissant"], 3)

    def test_single_shop_specialty_is_not_a_gap_at_two(self):
        self.assertEqual(self.gaps(2), {"almond croissant": 3})

    def test_default_keeps_previous_behavior(self):
        self.assertIn("ube mochi donut", self.gaps(1))

    def test_owner_item_matching_the_category_is_not_a_gap(self):
        self.assertEqual(self.gaps(2, owned=["Almond Croissant"]), {})


class VerifiedMenuTests(unittest.TestCase):
    PICK = fast_competitors.Pick(name="Alpha Bakery", address="12 Main St", website=None)

    def ledger(self):
        ledger = SourceLedger()
        ledger.add("https://alpha.example/menu", "MENU\nAlmond Croissant $5.25\nCardamom Bun $5", "page_text")
        ledger.add("https://yelp.example/alpha", "Great Pistachio Croissant here", "search_snippet")
        return ledger

    def test_keeps_items_on_read_pages_and_drops_the_rest(self):
        result = {"name": "Alpha Bakery", "address": "12 Main St", "menu_items": [
            {"product": "Almond Croissant", "category": "almond croissant", "price": "$5.25", "source_url": "https://alpha.example/menu"},
            {"product": "Pistachio Croissant", "category": "pistachio croissant", "source_url": "https://yelp.example/alpha"},  # snippet only
            {"product": "Kouign-Amann", "category": "kouign-amann", "source_url": "https://alpha.example/menu"},  # not on the page
            {"product": "Croissant", "category": "croissant", "source_url": "https://never-read.example/menu"},
        ]}
        kept, dropped = fast_competitors._verified_menu(result, self.PICK, self.ledger())
        self.assertEqual([(k["product"], k["category"], k["price"]) for k in kept], [("Almond Croissant", "almond croissant", "$5.25")])
        self.assertEqual(dropped, 3)
        self.assertNotIn("menu_items", result)

    def test_no_address_means_no_menu_items(self):
        result = {"name": "Alpha Bakery", "address": None, "menu_items": [
            {"product": "Almond Croissant", "category": "almond croissant", "source_url": "https://alpha.example/menu"}]}
        pick = fast_competitors.Pick(name="Alpha Bakery", address=None, website=None)
        self.assertEqual(fast_competitors._verified_menu(result, pick, self.ledger()), ([], 1))


if __name__ == "__main__":
    unittest.main()
