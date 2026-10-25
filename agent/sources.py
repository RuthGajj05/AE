"""Which sites the agent searches with Tavily.

Google Places (find_places, get_place_reviews) is the main source for
finding businesses, ratings and reviews; these lists only affect web search.

Placeholder lists until the source research is done; edit these to change
where the agent looks. Empty lists mean "search the whole web".
"""

# Sites for finding businesses near a location (listings, maps, directories).
DISCOVERY_DOMAINS: list[str] = [
    "yelp.com",
    "tripadvisor.com",
    "google.com",
]

# Sites that carry customer reviews.
REVIEW_DOMAINS: list[str] = [
    "yelp.com",
    "tripadvisor.com",
    "google.com",
]

# Sites to never use (e.g. sites whose terms forbid automated access).
BLOCKED_DOMAINS: list[str] = []
