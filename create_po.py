#!/usr/bin/env python3
"""
Generate a Purchase Order CSV from a Go Figure order JSON file.

Matches each order line item against the Heartland item catalog
(heartland_items.json) to populate Item #.

Usage:
    python3 create_po.py order_February_22.json
    python3 create_po.py order_February_22.json --out my_po.csv
"""

import sys
import json
import csv
import re
import argparse
from datetime import date
from pathlib import Path

HEARTLAND_ITEMS_FILE = Path(__file__).parent / "heartland_items.json"
PO_HEADERS = [
    "PO #",
    "PO Description",
    "PO Start Ship",
    "PO End Ship",
    "PO Vendor",
    "PO Received at location",
    "Item Description",
    "Item Default Cost",
    "Item Current Price",
    "Item Primary Image",
    "Item Primary Vendor",
    "Item Department",
    "Item Sub Department",
    "Item BAM Category",
    "Item #",
    "PO Line Unit Cost",
    "PO Line Qty",
    "Item Images URL",
]

VENDOR_NAME = "Go Figure Displays"
LOCATION = "Bricks & Minifigs Herndon"


def load_heartland_items():
    with open(HEARTLAND_ITEMS_FILE) as f:
        return json.load(f)


def normalize(s):
    """Lowercase and collapse whitespace for comparison."""
    return re.sub(r"\s+", " ", s.strip().lower())


def find_heartland_item(items, order_item):
    """
    Match an order item to a Heartland item by description.

    Strategy (in order):
      1. Exact match on "<name> - <variation>"
      2. Exact match on "<name>" alone (no variation)
      3. Heartland description contains both name and variation as substrings
      4. Heartland description contains name as substring
    """
    name = order_item["name"]
    variation = order_item.get("variation", "")

    candidates = [
        normalize(f"{name} - {variation}") if variation else None,
        normalize(name),
    ]

    # Build a lookup by normalized description
    by_desc = {normalize(i["item.description"]): i for i in items}

    # Strategy 1 & 2: exact match
    for candidate in candidates:
        if candidate and candidate in by_desc:
            return by_desc[candidate]

    # Strategy 3: both name and variation appear in description
    if variation:
        norm_name = normalize(name)
        norm_var = normalize(variation)
        for desc, item in by_desc.items():
            if norm_name in desc and norm_var in desc:
                return item

    # Strategy 4: name alone appears in description — only when no variation
    if not variation:
        norm_name = normalize(name)
        for desc, item in by_desc.items():
            if norm_name in desc:
                return item

    return None


def parse_price(price_str):
    """Convert '$5.00' → 5.00"""
    return float(re.sub(r"[^\d.]", "", price_str))


def _readable_date(order_date_str):
    """Convert '1/19/2026, 8:00 PM' → 'January 19, 2026'"""
    from datetime import datetime
    date_part = order_date_str.split(",")[0].strip()
    return datetime.strptime(date_part, "%m/%d/%Y").strftime("%B %-d, %Y")


def build_po_row(order, item, heartland_item):
    """Build one CSV row for a single line item."""
    if heartland_item:
        matched_desc = heartland_item["item.description"]
        item_num = heartland_item["item.public_id"]
    else:
        variation = item.get("variation", "")
        matched_desc = f"{item['name']} - {variation}" if variation else item["name"]
        item_num = ""

    unit_cost = parse_price(item["price"])

    return {
        "PO #": f"Gofig{order['order_number']}",
        "PO Description": f"GoFigure displays Order {_readable_date(order['order_date'])}",
        "PO Start Ship": order["order_date"].split(",")[0].strip(),
        "PO End Ship": date.today().strftime("%-m/%-d/%Y"),
        "PO Vendor": VENDOR_NAME,
        "PO Received at location": LOCATION,
        "Item Description": matched_desc,
        "Item Default Cost": unit_cost,
        "Item Current Price": round(unit_cost * 2, 2),
        "Item Primary Image": item.get("image_url", ""),
        "Item Primary Vendor": VENDOR_NAME,
        "Item Department": "Custom & Accesories",
        "Item Sub Department": "Display",
        "Item BAM Category": "Minifig Stand",
        "Item #": item_num,
        "PO Line Unit Cost": unit_cost,
        "PO Line Qty": item["quantity"],
        "Item Images URL": item.get("image_url", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("order_json", help="Path to the order JSON file")
    parser.add_argument("--out", help="Output CSV filename (default: po_<order#>.csv)")
    args = parser.parse_args()

    with open(args.order_json) as f:
        order = json.load(f)

    heartland_items = load_heartland_items()

    rows = []
    unmatched = []

    for item in order["items"]:
        heartland_item = find_heartland_item(heartland_items, item)
        if heartland_item:
            print(f"  Matched: '{item['name']} - {item.get('variation', '')}'"
                  f" → {heartland_item['item.public_id']} ({heartland_item['item.description']})")
        else:
            label = f"{item['name']}" + (f" - {item['variation']}" if item.get('variation') else "")
            print(f"  WARNING: No Heartland match for '{label}'")
            unmatched.append(label)

        rows.append(build_po_row(order, item, heartland_item))

    out_file = args.out or f"po_{order['order_number']}.csv"
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PO_HEADERS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} line(s) to {out_file}")
    if unmatched:
        print(f"\nWARNING: {len(unmatched)} item(s) had no Heartland match — Item # left blank:")
        for u in unmatched:
            print(f"  - {u}")
        print(
            "\nThese items will be created automatically by Heartland on PO import.\n"
            "Once created, you will need to manually update their Vendor Product URLs in Heartland."
        )


if __name__ == "__main__":
    main()
