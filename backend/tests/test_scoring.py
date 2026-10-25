"""Scoring math on fixture reviews. No network, no Claude calls."""
import pytest

import cuisines
import scoring

# Made-up review lines in the style of real snippets.
REVIEWS = [
    "We waited 20 minutes for a table but the rice was perfect.",
    "Line was about 15-20 minutes on a Friday night.",
    "Took 45 minutes to get our food, way too long.",
    "Great vibe, cozy and dim. No wait at all on Tuesday.",
    "It's a 10 minute walk from the light rail, worth it.",
    "Wait a minute, this toro is unreal.",
    "The fish was fresh and we were seated right away.",
    "Waited an hour and a half on Saturday.",
    "Took my mom here 2 hours before close and she loved it.",
]


class TestWaitMinutes:
    def test_reads_only_stated_waits(self):
        assert scoring.wait_mentions(REVIEWS[0]) == [20]
        assert scoring.wait_mentions(REVIEWS[1]) == [17.5]  # a range counts as its midpoint
        assert scoring.wait_mentions(REVIEWS[2]) == [45]
        assert scoring.wait_mentions(REVIEWS[3]) == [0]  # "no wait" is a stated wait of zero
        assert scoring.wait_mentions(REVIEWS[6]) == [0]
        assert scoring.wait_mentions(REVIEWS[7]) == [90]

    def test_ignores_things_that_are_not_waits(self):
        assert scoring.wait_mentions(REVIEWS[4]) == []  # a walk, not a wait
        assert scoring.wait_mentions(REVIEWS[5]) == []  # "wait a minute" is an expression
        assert scoring.wait_mentions(REVIEWS[8]) == []  # "took my mom here", not "took 2 hours"

    def test_hours_and_words(self):
        assert scoring.wait_mentions("There was a 2 hour wait.") == [120]
        assert scoring.wait_mentions("An hour wait, but worth it") == [60]
        assert scoring.wait_mentions("waited half an hour") == [30]
        assert scoring.wait_mentions("expect a twenty minute line") == [20]

    def test_median_of_all_mentions(self):
        # Mentions: 20, 17.5, 45, 0, 0, 90 → median 18.75
        assert scoring.wait_minutes(REVIEWS) == 19

    def test_none_when_nobody_mentions_a_wait(self):
        assert scoring.wait_minutes(["Loved the broth.", "Pricey but good."]) is None
        assert scoring.wait_minutes([]) is None


class TestAmbiance:
    def test_share_of_positive_mentions_and_mention_rate(self):
        labels = ["positive", "negative", "none", "positive", "mixed", "none", "none", "none"]
        assert scoring.ambiance_stats(labels) == (50, 0.5)

    def test_no_mentions(self):
        assert scoring.ambiance_stats(["none", "none"]) == (None, 0.0)
        assert scoring.ambiance_stats([]) == (None, None)


def spot(id, scores, wait=None, ambiance=None, reviews=10, name=None):
    return {"id": id, "name": name or id, "scores": scores, "waitMinutes": wait, "ambiancePct": ambiance, "reviewCount": reviews}


class TestPick:
    def test_wait_score_scale(self):
        assert scoring.wait_score(0) == 100
        assert scoring.wait_score(15) == 50
        assert scoring.wait_score(45) == 0
        assert scoring.wait_score(None) is None

    def test_highest_average_including_wait(self):
        a = spot("a", {"rice": 90, "fish": 80}, wait=10)  # (90 + 80 + 67) / 3 = 79
        b = spot("b", {"rice": 85, "fish": 95}, wait=30)  # (85 + 95 + 0) / 3 = 60
        c = spot("c", {"rice": 70, "fish": None})  # unscored attributes and wait are left out → 70
        assert scoring.pick([a, b, c])["id"] == "a"
        d = spot("d", {"rice": 80, "fish": 80}, wait=0)  # (80 + 80 + 100) / 3 = 86.7
        assert scoring.pick([a, b, c, d])["id"] == "d"

    def test_tie_goes_to_more_reviews(self):
        assert scoring.pick([spot("x", {"rice": 80}, reviews=5), spot("y", {"rice": 80}, reviews=50)])["id"] == "y"

    def test_nothing_scored(self):
        assert scoring.pick([spot("x", {"rice": None})]) is None


# The frontend's sample sushi data: "you" vs two rivals.
ATTRS = cuisines.compare_attributes("sushi")
YOU = spot("you", {"rice": 78, "fish": 80, "seaweed": 94, "value": 85}, wait=18, ambiance=62)
HIKARI = spot("hikari", {"rice": 93, "fish": 91, "seaweed": 84, "value": 72}, wait=9, ambiance=81, name="Hikari Sushi Bar")
UMI = spot("umi", {"rice": 86, "fish": 95, "seaweed": 80, "value": 58}, wait=16, ambiance=88, name="Umi Counter")


class TestRivals:
    def test_gap_labels(self):
        assert scoring.gap_label("wait", 18, 9) == "+9 min"
        assert scoring.gap_label("rice", 78, 93) == "−15 pts"

    def test_likely_because_is_the_biggest_gap_on_one_scale(self):
        # Hikari: rice +15, fish +11, wait (18 − 9) / 30 = 30 on the shared scale, ambiance +19 → wait.
        reason = scoring.likely_because(YOU, HIKARI, ATTRS)
        assert reason == {"attribute": "wait", "label": "Wait time", "you": 18, "them": 9, "unit": "min", "gapLabel": "+9 min"}
        # Umi: rice +8, fish +15, wait 6.7, ambiance +26 → ambiance.
        assert scoring.likely_because(YOU, UMI, ATTRS)["gapLabel"] == "−26 pts"

    def test_no_reason_when_you_beat_them_everywhere(self):
        assert scoring.likely_because(HIKARI, spot("weak", {"rice": 10}, wait=29, ambiance=10), ATTRS) is None

    def test_picks_won_and_lost_from_the_picks_table(self):
        both = ["you", "hikari", "umi"]
        picks = [
            {"chosen_spot_id": "hikari", "compared_spot_ids": both},
            {"chosen_spot_id": "hikari", "compared_spot_ids": both},
            {"chosen_spot_id": "hikari", "compared_spot_ids": ["you", "hikari"]},
            {"chosen_spot_id": "umi", "compared_spot_ids": both},
            {"chosen_spot_id": "you", "compared_spot_ids": both},
            {"chosen_spot_id": "you", "compared_spot_ids": ["you", "umi"]},
            {"chosen_spot_id": "umi", "compared_spot_ids": ["hikari", "umi"]},  # you weren't compared: ignored
        ]
        report = scoring.rivals_report(YOU, picks, {"you": YOU, "hikari": HIKARI, "umi": UMI}, ATTRS)
        assert (report["picksWon"], report["picksLost"]) == (2, 4)
        assert [(r["spotId"], r["picksWon"]) for r in report["rivals"]] == [("hikari", 3), ("umi", 1)]
        assert report["rivals"][0]["likelyBecause"]["gapLabel"] == "+9 min"
        assert [w["attribute"] for w in report["whereYouWin"]] == ["seaweed", "value"]


class TestAreaAndInsights:
    def test_best_at_each_spot_leads_by_the_most(self):
        # Hikari leads rice by 7 and wait; Umi leads fish by 4 and ambiance by 7.
        leads = scoring.best_at([YOU, HIKARI, UMI], ATTRS)
        assert leads["umi"] == "ambiance"
        assert leads["you"] in ("seaweed", "value")
        assert leads["hikari"] in ("rice", "wait")

    def test_area_averages_skip_missing(self):
        avg = scoring.area_averages([HIKARI, UMI, spot("z", {"rice": None})], ATTRS)
        assert avg["rice"] == 90 and avg["waitMinutes"] == 12 and avg["ambiancePct"] == 84

    def test_insights_follow_goals_and_find_the_drag(self):
        result = scoring.insights(YOU, [HIKARI, UMI], ATTRS, ["Shorter waits", "value"], won=2, lost=4)
        assert [row["attribute"] for row in result["breakdown"]][:2] == ["wait", "value"]
        assert result["reputation"] == 84  # (78 + 80 + 94 + 85) / 4
        assert result["momentum"] == 33  # 2 of 6 picks
        assert 0 <= result["edge"] <= 100
        assert result["biggestDrag"]["attribute"] == "ambiance"  # 62 vs 84.5 avg is the biggest gap
        assert result["wait"] == {"youMinutes": 18, "areaMinutes": 12}

    @pytest.mark.parametrize("goal,expected", [("shorter waits", ["wait"]), ("Better vibe and rice", ["rice", "ambiance"]), ("parking", [])])
    def test_goal_mapping(self, goal, expected):
        assert scoring.goal_attributes([goal], ATTRS) == expected
