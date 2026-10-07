#!/usr/bin/env python3
"""Find supplier price text in the customer-facing fields of a cached snapshot.

Why this exists: the catalogue's finished-document guard refuses a PDF that
carries a price indicator, and the first report of that was a production
failure — "a price indicator reached the catalogue: 'rrp'" — with no way to
say which product had caused it. This answers that question from the cache
alone.

It is read-only and makes **no supplier API call**: it opens
`runtime/cache/giveaways-<market>.json`, which a sync already wrote. Nothing
is charged to the five-a-day budget.

It never prints a price. A supplier price is internal-only, so a line reads

    ITGL 1234  description  removed price-related supplier text (rrp)

— the product, the field, and which indicator matched. Not the figure.

    python scripts/audit_catalogue_text.py            # both markets
    python scripts/audit_catalogue_text.py ksa        # one market
    python scripts/audit_catalogue_text.py ksa --show-cleaned
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from server import catalogue as cat          # noqa: E402

CACHE = pathlib.Path(__file__).resolve().parents[1] / "runtime" / "cache"

#: the fields a customer sees, which is exactly what the guard reads back
TEXT = ("name", "description", "brand", "color", "material", "size",
        "capacity", "cartonDimensions", "hsCode", "barcode")
LISTS = ("categories", "options")


def _matched(value: str) -> str:
    """Which indicator a value tripped — a label, not the value."""
    m = cat._INDICATOR.search(value or "")
    return (m.group(0) or "").strip().lower()[:24] if m else ""


def audit(market: str, show_cleaned: bool = False) -> int:
    path = CACHE / f"giveaways-{market}.json"
    if not path.exists():
        print(f"{market.upper()}: no cached snapshot at {path} — nothing to audit")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data.get("products") or []
    hits = 0
    products_hit = 0
    for p in products:
        code = str(p.get("code") or p.get("id") or "?")
        rows: list[tuple[str, str, str]] = []
        for field in TEXT:
            value = cat.clean_text(p.get(field), 1200)
            if not cat.has_price_text(value):
                continue
            rows.append((field, _matched(value),
                         cat.sanitize_catalogue_text(value, field)))
        for field in LISTS:
            for value in (p.get(field) or []):
                if cat.has_price_text(str(value)):
                    rows.append((f"{field}[]", _matched(str(value)), ""))
        if rows:
            products_hit += 1
        for field, word, cleaned in rows:
            hits += 1
            print(f"  {code:<14} {field:<16} removed price-related supplier "
                  f"text ({word})")
            if show_cleaned:
                print(f"  {'':<14} {'':<16} kept: "
                      f"{(cleaned or '(field omitted)')[:140]}")
    print(f"{market.upper()}: {len(products):,} products, {products_hit} carrying "
          f"price text in {hits} field(s)")
    return hits


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    markets = args or ["ksa", "uae"]
    show = "--show-cleaned" in sys.argv[1:]
    total = 0
    for m in markets:
        total += audit(m.lower(), show)
    print(f"\n{total} field(s) would be cleaned. The catalogue does this "
          f"automatically; nothing here needs fixing by hand.")
