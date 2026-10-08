#!/usr/bin/env python3
"""Show what the catalogue would remove from a cached snapshot, and why.

This runs the **real pipeline** — `catalogue.to_dto`, the same function every
renderer is fed from — and compares each raw normalized customer-facing value
with the sanitized one. It cannot drift from the renderer, because it is not
a second scanner with its own list of fields: it reads `DTO_TEXT_FIELDS` and
`DTO_LIST_FIELDS` and asks the pipeline itself what changed.

It is read-only and makes **no supplier API call**: it opens
`runtime/cache/giveaways-<market>.json`, which a sync already wrote. Nothing
is charged to the five-a-day budget.

It never prints a price. A supplier price is internal-only, so a line reads

    ITGL 1455   description   removed price-related supplier text (rrp)

— the product, the field, and which indicator matched. Not the figure.

    python scripts/audit_catalogue_text.py            # both markets
    python scripts/audit_catalogue_text.py ksa        # one market
    python scripts/audit_catalogue_text.py ksa --show-kept
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from server import catalogue as cat          # noqa: E402

CACHE = pathlib.Path(__file__).resolve().parents[1] / "runtime" / "cache"


def _matched(value: str) -> str:
    """Which indicator a value tripped — a label, not the value."""
    m = cat._INDICATOR.search(value or "")
    return (m.group(0) or "").strip().lower()[:24] if m else ""


def _raw(product: dict, key: str, limit: int) -> str:
    """The value as the DTO would have received it, before sanitization."""
    return cat.clean_text(product.get(key), limit)


def audit(market: str, show_kept: bool = False) -> int:
    path = CACHE / f"giveaways-{market}.json"
    if not path.exists():
        print(f"{market.upper()}: no cached snapshot at {path} — nothing to audit")
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    products = data.get("products") or []
    hits = products_hit = 0
    for product in products:
        code = str(product.get("code") or product.get("id") or "?")
        dto = cat.to_dto(product)             # the one boundary, used as-is
        rows: list[tuple[str, str, str]] = []
        for key in cat.DTO_TEXT_FIELDS:
            before = _raw(product, key, 1200 if key == "description" else 240)
            if before and before != dto.get(key):
                rows.append((key, _matched(before), dto.get(key) or ""))
        for key in cat.DTO_LIST_FIELDS:
            if key == "images":
                continue                      # URLs, not customer text
            before = [str(v) for v in (product.get(key) or []) if v][:20]
            for value in before:
                if value not in (dto.get(key) or []):
                    rows.append((f"{key}[]", _matched(value), ""))
        if rows:
            products_hit += 1
        for key, word, kept in rows:
            hits += 1
            print(f"  {code:<14} {key:<16} removed price-related supplier "
                  f"text ({word or 'no indicator — check clean_text'})")
            if show_kept:
                print(f"  {'':<14} {'':<16} kept: {(kept or '(field omitted)')[:140]}")
    print(f"{market.upper()}: {len(products):,} products, {products_hit} carrying "
          f"price text in {hits} field(s)")
    return hits


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    markets = args or ["ksa", "uae"]
    show = "--show-kept" in sys.argv[1:] or "--show-cleaned" in sys.argv[1:]
    total = sum(audit(m.lower(), show) for m in markets)
    print(f"\n{total} field(s) would be cleaned. The catalogue does this "
          f"automatically; nothing here needs fixing by hand.")
