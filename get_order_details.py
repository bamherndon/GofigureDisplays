#!/usr/bin/env python3
"""
Get details for a specific order by date from gofigdisplays.com.

Usage:
    python3 get_order_details.py "February 22"
    python3 get_order_details.py "January 19"
"""

import sys
import json
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

BASE_URL = "https://www.gofigdisplays.com"
ACCOUNT_URL = f"{BASE_URL}/s/customer-accounts"
LOGIN_TIMEOUT = 5 * 60 * 1000  # 5 minutes

ORDER_LINE_RE = re.compile(
    r"^(?P<date>[A-Za-z]+ \d{1,2})\s*-\s*\$(?P<amount>[\d,]+\.\d{2})\s*-\s*(?P<items>\d+) Items?$"
)
SEE_MORE_SELECTOR = "button:has-text('See more'), a:has-text('See more')"
ALL_ORDERS_SELECTOR = "button:has-text('All orders'), a:has-text('All orders')"


def wait_for_login(page):
    print(f"Opening: {ACCOUNT_URL}")
    page.goto(ACCOUNT_URL, wait_until="domcontentloaded")
    print("Waiting for login... (you have 5 minutes to complete login + 2FA)")

    try:
        page.wait_for_url(
            lambda url: "/s/customer-accounts" not in url,
            timeout=10000,
        )
    except PlaywrightTimeout:
        pass  # Already logged in

    page.wait_for_url("**/s/customer-accounts**", timeout=LOGIN_TIMEOUT)
    print("Login detected.")


def click_order_history(page):
    try:
        page.wait_for_selector(
            "button:has-text('Order history'), a:has-text('Order history')",
            timeout=10000,
        )
        page.locator(
            "button:has-text('Order history'), a:has-text('Order history')"
        ).first.click()
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector(ALL_ORDERS_SELECTOR, timeout=5000)
        page.locator(ALL_ORDERS_SELECTOR).first.click()
    except PlaywrightTimeout:
        pass

    page.wait_for_function(
        r"""() => /[A-Za-z]+ \d{1,2} - \$[\d,]+\.\d{2} - \d+ Items?/.test(document.body.innerText)""",
        timeout=15000,
    )


def find_order_index(page, target_date):
    """
    Scan visible order lines and return the 0-based index of the one
    matching target_date. Clicks 'See more' as needed.
    """
    target = target_date.strip().lower()

    while True:
        body_text = page.inner_text("body", timeout=8000)
        lines = [l.strip() for l in body_text.splitlines()]
        for i, line in enumerate(lines):
            m = ORDER_LINE_RE.match(line)
            if m and m.group("date").lower() == target:
                # Count which order index this is (0-based among all order lines)
                order_lines_before = sum(
                    1 for l in lines[:lines.index(line)]
                    if ORDER_LINE_RE.match(l)
                )
                return order_lines_before

        # Not found yet — try loading more
        try:
            see_more = page.locator(SEE_MORE_SELECTOR).first
            see_more.wait_for(state="visible", timeout=3000)
            current_count = sum(1 for l in lines if ORDER_LINE_RE.match(l))
            see_more.click()
            page.wait_for_function(
                f"""() => document.body.innerText
                    .match(/[A-Za-z]+ \\d{{1,2}} - \\$/g)?.length > {current_count}""",
                timeout=10000,
            )
        except (PlaywrightTimeout, Exception):
            return None  # Exhausted all pages, order not found


def click_track_order(page, order_index):
    """Click the Track order link for the nth order (0-based)."""
    track_links = page.locator("a:has-text('Track order'), button:has-text('Track order')").all()
    if order_index >= len(track_links):
        raise RuntimeError(
            f"Found {len(track_links)} 'Track order' links but needed index {order_index}."
        )
    track_links[order_index].click()


def extract_order_details(page, baseline_text):
    """Wait for the order confirmation page to load and parse it."""
    page.wait_for_load_state("domcontentloaded", timeout=15000)

    # Wait until order number is visible
    page.wait_for_function(
        r"() => /Order number:/.test(document.body.innerText)",
        timeout=15000,
    )

    text = page.inner_text("body", timeout=8000)
    lines = [l.strip() for l in text.splitlines()]

    def find_after(label):
        """Return the first non-empty line after the line containing label."""
        for i, l in enumerate(lines):
            if label.lower() in l.lower():
                for j in range(i + 1, len(lines)):
                    if lines[j]:
                        return lines[j]
        return ""

    details = {"url": page.url}

    # Order number
    m = re.search(r"Order number:\s*#(\w+)", text)
    if m:
        details["order_number"] = m.group(1)

    # Customer name
    m = re.search(r"thank you for your order,\s*(.+)\.", text, re.IGNORECASE)
    if m:
        details["customer"] = m.group(1).strip()

    # Order date
    m = re.search(r"Order placed at\s+(.+)", text)
    if m:
        details["order_date"] = m.group(1).strip()

    # Shipping address
    details["shipping_address"] = find_after("Delivering to")

    # Email
    m = re.search(r"Sent to\s+(\S+)", text)
    if m:
        details["email"] = m.group(1).strip()

    # --- Parse line items ---
    # Items section spans from "Items (N)" to "Subtotal"
    items_start = next((i for i, l in enumerate(lines) if re.match(r"Items \(\d+\)", l)), None)
    items_end = next((i for i, l in enumerate(lines) if l == "Subtotal"), None)

    items = []
    if items_start is not None and items_end is not None:
        # Strip empty lines and the "Order placed at" metadata line
        item_lines = [
            l for l in lines[items_start + 1 : items_end]
            if l and not l.startswith("Order placed")
        ]
        i = 0
        while i < len(item_lines):
            line = item_lines[i]
            # Skip price lines and "Variation" keyword at the top level
            if re.match(r"^\$", line) or line == "Variation":
                i += 1
                continue
            # This line is an item name; extract trailing quantity like "x10" or "x 10"
            qty_match = re.search(r"\s+x\s*(\d+)$", line, re.IGNORECASE)
            item = {
                "name": re.sub(r"\s+x\s*\d+$", "", line, flags=re.IGNORECASE).strip(),
                "quantity": int(qty_match.group(1)) if qty_match else 1,
            }
            i += 1
            # Optional variation block
            if i < len(item_lines) and item_lines[i] == "Variation":
                i += 1
                if i < len(item_lines) and not re.match(r"^\$", item_lines[i]):
                    item["variation"] = item_lines[i]
                    i += 1
            # Price
            if i < len(item_lines) and re.match(r"^\$", item_lines[i]):
                item["price"] = item_lines[i]
                i += 1
            items.append(item)

    # --- Item images ---
    # Each item has an img.order-confirmation-item-image in the same order as items
    img_els = page.locator("img.order-confirmation-item-image").all()
    for i, item in enumerate(items):
        try:
            src = img_els[i].get_attribute("src", timeout=2000) or ""
            item["image_url"] = src
        except Exception:
            item["image_url"] = ""

    details["items"] = items

    # --- Totals ---
    # Walk lines looking for label then value (they may have blank/card lines between)
    for label, key in [
        ("Subtotal", "subtotal"),
        ("Shipping", "shipping"),
        ("Taxes", "taxes"),
        ("Order total", "order_total"),
    ]:
        for i, l in enumerate(lines):
            if l == label:
                # Find the next dollar amount after this label
                for j in range(i + 1, min(i + 5, len(lines))):
                    if re.match(r"^\$[\d,]+\.\d{2}$", lines[j]):
                        details[key] = lines[j]
                        break
                break

    return details


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 get_order_details.py \"<date>\"")
        print('Example: python3 get_order_details.py "February 22"')
        sys.exit(1)

    target_date = " ".join(sys.argv[1:])
    print(f"Looking for order: {target_date}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_context(viewport=None).new_page()

        try:
            wait_for_login(page)
            print("Loading order history...")
            click_order_history(page)

            print(f"Searching for order dated '{target_date}'...")
            order_index = find_order_index(page, target_date)

            if order_index is None:
                print(f"No order found with date '{target_date}'.")
                print("Available orders:")
                body_text = page.inner_text("body", timeout=5000)
                for line in body_text.splitlines():
                    if ORDER_LINE_RE.match(line.strip()):
                        print(f"  {line.strip()}")
                sys.exit(1)

            print(f"  Found at index {order_index}. Clicking 'Track order'...")

            # Track order opens a new tab
            with page.context.expect_page(timeout=10000) as new_page_info:
                click_track_order(page, order_index)
            new_page = new_page_info.value
            print(f"  Opened: {new_page.url}")

            print("  Extracting order details...")
            details = extract_order_details(new_page, "")

            output_file = f"order_{target_date.replace(' ', '_')}.json"
            with open(output_file, "w") as f:
                json.dump(details, f, indent=2)

            print(f"\nOrder details saved to {output_file}")
            print(json.dumps(details, indent=2))

        finally:
            browser.close()


if __name__ == "__main__":
    main()
