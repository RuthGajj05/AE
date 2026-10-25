"""Generate FAKE sales data for testing the advisor (data/sample_sales.csv).

Mimics the columns of Square's "Items" sales export. The bakery is fictional
and the numbers are made up, with a few patterns built in for the advisor to
find: closed Mon/Tue, an almond croissant priced below the local market, a
cardamom bun that sells out around 10am, and a slow-selling scone.
"""

import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

random.seed(7)
OUT = Path(__file__).resolve().parent.parent / "data" / "sample_sales.csv"

# item: (category, price, avg sold per day, daily batch cap or None, peak hour)
MENU = {
    "Butter Croissant": ("Pastry", 4.00, 40, None, 8),
    "Almond Croissant": ("Pastry", 5.50, 28, None, 9),
    "Pain au Chocolat": ("Pastry", 5.00, 30, None, 8),
    "Cardamom Bun": ("Pastry", 5.00, 60, 36, 8),  # demand > batch: sells out
    "Blueberry Scone": ("Pastry", 4.00, 5, None, 10),
    "Gluten-Free Muffin": ("Pastry", 4.50, 7, None, 10),
    "Chocolate Chip Cookie": ("Cookies", 3.25, 22, None, 13),
    "Sourdough Loaf": ("Bread", 9.00, 14, None, 11),
    "Baguette": ("Bread", 4.50, 18, None, 12),
    "Quiche Slice": ("Savory", 8.50, 12, None, 12),
    "Drip Coffee": ("Drinks", 3.50, 55, None, 8),
    "Latte": ("Drinks", 5.50, 45, None, 9),
}
OPEN, CLOSE = 7, 15  # 7am-3pm
CLOSED_WEEKDAYS = {0, 1}  # Monday, Tuesday


def sale_time(day: date, peak: int) -> datetime:
    hour = random.gauss(peak, 1.6)
    while not OPEN <= hour < CLOSE:
        hour = random.gauss(peak, 1.6)
    return datetime.combine(day, time(0)) + timedelta(hours=hour)


rows = []
start = date(2026, 8, 31)
for d in range(56):  # 8 weeks
    day = start + timedelta(days=d)
    if day.weekday() in CLOSED_WEEKDAYS:
        continue
    weekend = 1.35 if day.weekday() >= 5 else 1.0
    for item, (category, price, avg, cap, peak) in MENU.items():
        demand = max(0, round(random.gauss(avg * weekend, avg * 0.15)))
        times = sorted(sale_time(day, peak) for _ in range(demand))
        if cap is not None:
            times = times[:cap]  # the batch runs out; later customers go without
        for t in times:
            qty = 2 if random.random() < 0.1 else 1
            rows.append([t.date().isoformat(), t.strftime("%H:%M:%S"), category, item, qty, f"${price * qty:.2f}"])

rows.sort(key=lambda r: (r[0], r[1]))
OUT.parent.mkdir(exist_ok=True)
with OUT.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Date", "Time", "Category", "Item", "Qty", "Gross Sales"])
    w.writerows(rows)
print(f"Wrote {len(rows)} rows to {OUT}")
