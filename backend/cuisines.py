"""The five crumbs food types. Ids, labels and pickLine copy the frontend's src/crumbs/data/cuisines.json.

`attributes` is what the compare screen shows. Rows with a `unit` are not Claude scores: "wait" comes
from minutes mentioned in reviews (lower is better). Ambiance is added to every food type on the
frontend and comes from review mentions too.
"""

CUISINES = [
    {"id": "sushi", "label": "Sushi", "pickLine": "good rice and fish, short waits", "attributes": [
        {"id": "rice", "label": "Rice"}, {"id": "fish", "label": "Fish"}, {"id": "seaweed", "label": "Seaweed"},
        {"id": "value", "label": "Value"}, {"id": "wait", "label": "Wait time", "unit": "min"}]},
    {"id": "ramen", "label": "Ramen", "pickLine": "rich broth, tender chashu", "attributes": [
        {"id": "broth", "label": "Broth"}, {"id": "noodles", "label": "Noodles"}, {"id": "egg", "label": "Egg"},
        {"id": "chashu", "label": "Chashu"}, {"id": "value", "label": "Value"}]},
    {"id": "steak", "label": "Steak", "pickLine": "spot-on cook, great service", "attributes": [
        {"id": "cook", "label": "Cook"}, {"id": "cut", "label": "Cut quality"}, {"id": "sides", "label": "Sides"},
        {"id": "value", "label": "Value"}, {"id": "service", "label": "Service"}]},
    {"id": "pizza", "label": "Pizza", "pickLine": "chewy crust, bright sauce", "attributes": [
        {"id": "crust", "label": "Crust"}, {"id": "sauce", "label": "Sauce"}, {"id": "toppings", "label": "Toppings"},
        {"id": "value", "label": "Value"}, {"id": "wait", "label": "Wait time", "unit": "min"}]},
    {"id": "tacos", "label": "Tacos", "pickLine": "fresh tortillas, juicy al pastor", "attributes": [
        {"id": "tortilla", "label": "Tortilla"}, {"id": "meat", "label": "Meat"}, {"id": "salsa", "label": "Salsa"},
        {"id": "value", "label": "Value"}, {"id": "wait", "label": "Wait time", "unit": "min"}]},
]

WAIT = {"id": "wait", "label": "Wait time", "unit": "min"}
AMBIANCE = {"id": "ambiance", "label": "Ambiance", "unit": "%"}

# What the scorer looks for in reviews, per attribute, so "rice" isn't read as "fried rice side dish".
HINTS = {
    "rice": "sushi rice: texture, temperature, seasoning",
    "fish": "freshness, quality and cut of the fish",
    "seaweed": "nori: crispness, freshness",
    "broth": "ramen broth: depth, richness, saltiness",
    "noodles": "ramen noodle texture and chew",
    "egg": "ajitama / soft-boiled egg",
    "chashu": "chashu pork: tenderness, flavor",
    "cook": "whether steaks are cooked to the requested doneness",
    "cut": "quality and marbling of the cuts of meat",
    "sides": "side dishes",
    "service": "staff attentiveness and friendliness",
    "crust": "pizza crust and dough",
    "sauce": "pizza sauce",
    "toppings": "quality and amount of toppings",
    "tortilla": "tortillas: fresh, handmade, texture",
    "meat": "taco fillings: al pastor, carne asada, carnitas",
    "salsa": "salsas and sauces",
    "value": "price relative to portion and quality",
}

_BY_ID = {c["id"]: c for c in CUISINES}


def get(cuisine_id: str) -> dict | None:
    return _BY_ID.get(cuisine_id)


# Words owners use for these food types ("a taqueria", "sushi bar") → the crumbs food type.
_SYNONYMS = {"pizzeria": "pizza", "taqueria": "tacos", "taco": "tacos", "steakhouse": "steak", "sushi": "sushi",
             "ramen": "ramen", "pizza": "pizza", "tacos": "tacos", "steak": "steak"}


def match(text: str | None) -> str | None:
    """The crumbs food type an owner's description names, e.g. "Sushi bar" → "sushi"; None for "bakery"."""
    words = "".join(ch if ch.isalnum() else " " for ch in (text or "").lower()).split()
    for word in words:
        if word in _BY_ID:
            return word
        if word in _SYNONYMS:
            return _SYNONYMS[word]
    return None


def research_type(business: dict) -> str:
    """How Ruth's research describes the business: the owner's words, else "<food type> restaurant"."""
    kind = (business.get("kind") or "").strip()
    if kind:
        return kind
    business_type = business["business_type"]
    return f"{business_type} restaurant" if business_type in _BY_ID else business_type


def scored_attributes(cuisine_id: str) -> list[dict]:
    """The attributes Claude scores 0-100 from review text (everything without a unit)."""
    return [a for a in _BY_ID[cuisine_id]["attributes"] if "unit" not in a]


def compare_attributes(cuisine_id: str) -> list[dict]:
    """Every row the compare and business screens show: scored attributes, wait, then ambiance."""
    scored = scored_attributes(cuisine_id)
    return [*scored, WAIT, AMBIANCE]


def public(cuisine: dict) -> dict:
    return {"id": cuisine["id"], "label": cuisine["label"], "pickLine": cuisine["pickLine"], "attributes": cuisine["attributes"]}
