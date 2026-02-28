# GofigureDisplays

## Fetch Orders

To download orders from gofigdisplays.com, run:

```
python3 fetch_orders.py
```

- Opens a visible Chromium browser window
- Navigate to the URL and log in manually (including 2FA), then press ENTER in the terminal
- Script clicks "Order History" → "All orders", then pages through "See more" automatically
- Outputs: `orders.json` and `orders.csv` in the project directory

## Get Order Details

To get details for a specific order by date, run:

```
python3 get_order_details.py "February 22"
```

- Same login flow as above (browser opens, complete 2FA, script continues automatically)
- Finds the order matching the given date, clicks its "Track order" link
- Saves structured data to `order_<date>.json` with fields: order_number, customer, order_date, shipping_address, items (name, quantity, variation, price, image_url), subtotal, shipping, taxes, order_total
- If the date is not found, lists all available order dates

## Create Purchase Order CSV

To create a PO for an order, first get the order details (above), then run:

```
python3 create_po.py order_February_22.json
```

- Matches each order item against `heartland_items.json` (Go Figure Displays catalog from Heartland)
- Outputs `po_<order_number>.csv` using the column layout from `PO_headers.csv`
- PO# format: `Gofig<order_number>`
- PO Description format: `GoFigure displays Order <Month Day, Year>`
- PO Start Ship: order date (no timestamp); PO End Ship: today's date
- Item Default Cost = unit price from order; Item Current Price = 2× default cost
- Item Department: `Custom & Accesories`; Item Sub Department: `Display`; Item BAM Category: `Minifig Stand`
- Unmatched items are included with Item # blank — Heartland will auto-create them on import
- After import, manually set Vendor Product URLs in Heartland for any auto-created items

### Refreshing the Heartland item catalog

`heartland_items.json` is a cached snapshot of Go Figure Displays items from Heartland (vendor ID: 100026).
Ask Claude to "refresh Heartland items" to re-query and update the file.
