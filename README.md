# Go Figure Displays — PO Automation

Automates pulling orders from [gofigdisplays.com](https://www.gofigdisplays.com) and generating Purchase Order CSVs for import into Heartland Retail.

Designed to be operated through **Claude Code** using plain English commands.

---

## Prerequisites

- Python 3
- Claude Code with access to this project directory
- The **`heartland-retail` MCP server** configured in Claude Code (required for Heartland item lookups and catalog refresh)

### Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Typical Workflow

### 1. List orders

Ask Claude:
> **"list orders"**

Claude will open a browser, wait for you to log in (including 2FA), then automatically pull the full order history and display it.

### 2. Get details for a specific order

Ask Claude:
> **"get order details for February 2026 order"**
> **"get order details for January 19"**

Claude opens a browser, logs you in, navigates to that order, and saves the details (line items, quantities, prices, image URLs) to `order_<date>.json`.

### 3. Generate a Purchase Order CSV

Ask Claude:
> **"create PO for February 2026 order"**
> **"regenerate PO for January 19 order"**

Claude matches each line item against the Heartland item catalog and writes `po_<order_number>.csv`, ready to import into Heartland.

---

## Login & 2FA

All browser scripts require a manual login. When you run any command that opens a browser:

1. A Chromium window opens and navigates to the Go Figure Displays account page
2. You log in and complete 2FA (phone code)
3. Once redirected back to your account, the script takes over automatically — no further input needed

---

## PO CSV Format

The generated CSV matches the Heartland PO import format (`PO_headers.csv`) with these field values:

| Field | Value |
|---|---|
| PO # | `Gofig<order_number>` |
| PO Description | `GoFigure displays Order <Month Day, Year>` |
| PO Start Ship | Order date |
| PO End Ship | Today's date |
| PO Vendor | Go Figure Displays |
| PO Received at location | Bricks & Minifigs Herndon |
| Item Department | Custom & Accesories |
| Item Sub Department | Display |
| Item BAM Category | Minifig Stand |
| Item Default Cost | Unit price from order |
| Item Current Price | 2× default cost |
| Item # | Heartland item ID (blank if not yet in Heartland) |
| PO Line Unit Cost | Unit price from order |
| PO Line Qty | Quantity from order |
| Item Primary Image / Item Images URL | Image URL from product page |

### Unmatched items

If an order contains an item not yet in Heartland, it is still included in the CSV with **Item # left blank**. Heartland will auto-create the item on import. After importing, manually set the **Vendor Product URL** for any auto-created items in Heartland.

---

## Heartland Item Catalog

`heartland_items.json` is a cached snapshot of Go Figure Displays items from Heartland (vendor ID: `100026`). To refresh it after new items are added in Heartland, ask Claude:

> **"refresh Heartland items"**

---

## Files

| File | Description |
|---|---|
| `fetch_orders.py` | Pulls full order list from gofigdisplays.com |
| `get_order_details.py` | Pulls line item details for a specific order |
| `create_po.py` | Generates a Heartland PO CSV from an order JSON |
| `heartland_items.json` | Cached Go Figure Displays item catalog from Heartland |
| `PO_headers.csv` | Reference file defining PO CSV column layout |
| `CLAUDE.md` | Instructions for Claude (not for end users) |
