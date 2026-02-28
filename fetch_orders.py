#!/usr/bin/env python3
"""
Fetch orders from gofigdisplays.com customer account.
Opens a visible browser for manual login (including 2FA), then
automatically waits for elements and extracts all orders.
"""

import json
import csv
import re
import time
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

OUTPUT_JSON = "orders.json"
OUTPUT_CSV = "orders.csv"
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

    # The login/2FA flow redirects away from /s/customer-accounts to a phone
    # entry page. After the user completes 2FA the site redirects back.
    # Step 1: wait for the redirect away (short timeout — skip if already logged in).
    try:
        page.wait_for_url(
            lambda url: "/s/customer-accounts" not in url,
            timeout=10000,
        )
    except PlaywrightTimeout:
        pass  # Already logged in, no redirect happened

    # Step 2: wait for the URL to return to /s/customer-accounts — this only
    # happens once 2FA is fully complete and the session is established.
    page.wait_for_url("**/s/customer-accounts**", timeout=LOGIN_TIMEOUT)
    print("Login detected.")


def click_order_history(page):
    """Click the Order History section button that appears inside the account page."""
    print("Looking for Order History button on the account page...")

    # After login, the account page has an "Order history" button in the account
    # section (not just the site nav). We wait for order data to appear after clicking.
    try:
        # Wait until an Order history button is visible
        page.wait_for_selector(
            "button:has-text('Order history'), a:has-text('Order history')",
            timeout=10000,
        )
        page.locator(
            "button:has-text('Order history'), a:has-text('Order history')"
        ).first.click()
        print("  Clicked Order history.")
    except PlaywrightTimeout:
        print("  Order history button not found — orders may already be visible.")

    # Optionally click "All orders" if it appears
    try:
        page.wait_for_selector(ALL_ORDERS_SELECTOR, timeout=5000)
        page.locator(ALL_ORDERS_SELECTOR).first.click()
        print("  Clicked 'All orders'.")
    except PlaywrightTimeout:
        pass

    # Wait until at least one order line is visible in the page text
    print("  Waiting for order data to appear...")
    page.wait_for_function(
        r"""() => /[A-Za-z]+ \d{1,2} - \$[\d,]+\.\d{2} - \d+ Items?/.test(document.body.innerText)""",
        timeout=15000,
    )
    print("  Order data visible.")


def collect_track_order_links(page):
    links = {}
    for i, el in enumerate(page.locator("a:has-text('Track order')").all()):
        try:
            href = el.get_attribute("href", timeout=2000) or ""
            links[i] = href if href.startswith("http") else BASE_URL + href
        except Exception:
            links[i] = ""
    return links


def extract_orders_from_text(page):
    body_text = page.inner_text("body", timeout=8000)
    track_links = collect_track_order_links(page)
    orders = []
    for i, line in enumerate(
        [l.strip() for l in body_text.splitlines() if ORDER_LINE_RE.match(l.strip())]
    ):
        m = ORDER_LINE_RE.match(line)
        orders.append({
            "date": m.group("date"),
            "amount": float(m.group("amount").replace(",", "")),
            "items": int(m.group("items")),
            "track_url": track_links.get(i, ""),
        })
    return orders


def extract_all_orders(page):
    seen_count = 0
    all_orders = []

    while True:
        orders = extract_orders_from_text(page)
        all_orders.extend(orders[seen_count:])
        seen_count = len(orders)

        try:
            see_more = page.locator(SEE_MORE_SELECTOR).first
            see_more.wait_for(state="visible", timeout=3000)
            print(f"  {seen_count} orders so far, clicking 'See more'...")
            see_more.click()
            page.wait_for_function(
                f"""() => document.body.innerText
                    .match(/[A-Za-z]+ \\d{{1,2}} - \\$/g)?.length > {seen_count}""",
                timeout=10000,
            )
        except (PlaywrightTimeout, Exception):
            break

    return all_orders


def save_results(orders):
    with open(OUTPUT_JSON, "w") as f:
        json.dump(orders, f, indent=2)
    print(f"Saved {len(orders)} orders to {OUTPUT_JSON}")

    keys = list(orders[0].keys())
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(orders)
    print(f"Saved {len(orders)} orders to {OUTPUT_CSV}")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        page = browser.new_context(viewport=None).new_page()

        try:
            wait_for_login(page)
            click_order_history(page)

            print("Extracting orders...")
            orders = extract_all_orders(page)

            if orders:
                save_results(orders)
                print(f"Done. Total orders: {len(orders)}")
            else:
                print("No orders found — saving page_debug.txt")
                with open("page_debug.txt", "w") as f:
                    f.write(page.url + "\n\n")
                    f.write(page.inner_text("body", timeout=5000))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
