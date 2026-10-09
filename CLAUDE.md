# Elite Marcom Website — working notes

Static multi-page site (`public/` webroot, vanilla JS namespaced under `window.EM`)
plus a FastAPI backend (`server/`). Tests: `python -m pytest tests/` (must stay green).
Local run: `START WEBSITE.bat` (Windows) / `uvicorn server.main:app --port 8847`.
Secrets live only in the git-ignored `.env` (see `.env.example`) — never commit them.

## Jasani supplier integration — read this first

**Before changing anything under `server/jasani.py` or the Corporate Gifts pages,
review `docs/jasani-api-reference.md`** (the complete Jasani API technical
documentation). Non-negotiable rules from it:

- **One supplier account per market**: `JASANI_API_TOKEN` is KSA,
  `JASANI_API_TOKEN_UAE` is UAE. Never fall back from one to the other — a
  single token carrying both markets means ten calls a day on one account and a
  403 that parks it.
- At most **5 primary GET calls per market per day** (products / price / stock),
  measured in that market's **own local time** (`JASANI_UTC_OFFSET`: KSA +3,
  UAE +4). Branding endpoints are outside the limit. Per-market counters live in
  `runtime/cache/supplier-budget.json`; never retry a 403.
  Automatic work stops at `EM_SUPPLIER_AUTO_BUDGET` (default 4) so the remaining
  call stays available for a manual sync by an owner or admin —
  `_budget_ok(market, manual=True)`, reached only through `force_refresh`. A call
  that never got an HTTP response is refunded; anything the supplier served counts.
  One in-flight sync per market (`_refresh_lock`), so a double-click or a burst
  of visitors cannot spend two calls on the same work.
- The four automatic calls are **scheduled, not demand-driven**
  (`JASANI_SCHEDULE`): products at 00:00, **price at 01:00**, stock at 08:00 and
  18:00 local. Each slot is exactly one call and runs once per local day, marked
  in the budget file whether it succeeded or failed — a failing hour must not
  retry all day. Four slots is exactly `SUPPLIER_AUTO_BUDGET`: adding one
  without raising that spends the reserved manual call.
  `get_catalog` never triggers a refresh; it serves the snapshot so a page load
  never waits on the supplier.
- **Price is its own primary call.** `list_price` is *not* in the Product API
  (reference §12 lists no price field); it comes from the **Price API**,
  `GET https://{host}/products/price/{token}` (§22), with `id`, `default_code`,
  `currency`, `list_price`, `retail_price`. Join on **`id` only** — the two
  markets share product codes but never share ids, so matching on
  `default_code` is how a KSA price lands on a UAE product; the code is kept
  for mismatch reporting and nothing else. Never try to read the price off the
  products feed again: that is how 1,778 KSA and 2,573 UAE products sat at zero
  prices through any number of syncs.
- **One price, called Price.** `list_price` — our own supplier price, excluding
  VAT — is the only price the panel keeps, stored as `internal[id]["price"]`.
  The supplier's `retail_price` is a *suggested selling* price, not ours, and is
  deliberately dropped at `normalize_price`: it is not stored, not exported, not
  shown, and `_lift_internal` strips it (`_DEAD_INTERNAL_KEYS`) from snapshots
  that still carry it. Do not reintroduce it as a second column — a figure that
  is not ours sitting beside one that is only invites the wrong number into a
  quote. `_price_of` reads a pre-rename snapshot's `wholesale` key so a live
  cache keeps working until its next write.
- Manual sync targets (`force_refresh`, `REFRESH_COST`): `products`, `prices`,
  `stock` — one call each — and `full` = all three. A multi-call target checks
  `_budget_left` **before the first request**, so a full sync never spends one
  call and then dies half-applied. A products refresh carries forward cached
  stock, and a failed price leg leaves the last-known-good prices in place —
  `_lift_internal` merges each write into the stored map rather than replacing
  it.
- `EM_SUPPLIER_TIMEOUT_S` (default 60) is the read timeout for supplier calls.
  The UAE products feed is ~4 MB and measured 24.2s from the production VPS, so
  a 20s timeout aborted valid replies. A timed-out call is refunded, not spent.
- `EM_SUPPLIER_MAX_BYTES` (default 8388608 = 8 MB) caps an upstream response.
  The UAE products feed is ~4.17 MB, so keep headroom above the live size — an
  over-limit response is rejected and reads as a supplier failure. Never remove
  the cap: it is what stops an endless upstream stream.
- Upstream refresh cadence: products ~daily, stock ~twice daily
  (`EM_PRODUCT_REFRESH_HOURS` / `EM_STOCK_REFRESH_HOURS`). The website reads the
  cached snapshot; serve last-known-good on any supplier failure.
- `id` = supplier variant id; `default_code` = SKU; `parent_id` = template id,
  meaningful for grouping **only when `configurable` is true**.
- Stock availability comes from **`net_available_qty` only** — never `total_qty`,
  never add `blocked_qty`. `blocked_qty` and all supplier prices are internal-only:
  keep them out of every public payload, page, and log.
- `color_options` and `alternative_products` carry **template** ids — resolve them
  against the catalog before linking; never build URLs from raw supplier ids.
- Token stays server-side (`JASANI_API_TOKEN`), never in browser code, URLs shown
  to users, or logs. Host allowlist: `www.giftsksa.com` (KSA), `www.jasani.ae` (UAE);
  never mix markets.
- No public prices, no online payment, no automatic supplier orders. The Order API
  needs separate written authorization — do not wire it to the public site.
- **Internal-only supplier fields.** `blocked_qty` and `list_price` are
  captured but never ride on a product: the stock and price merges park them
  under `_INT_KEY`, and `_write_cache` — the single choke point that
  persists a snapshot — lifts them into a sibling `internal` map keyed by
  product id. A caller that hands the product list to a public response
  therefore cannot leak what the list never holds. Read them with
  `internal_map(market)`; they reach the admin only behind `jasani.prices`
  (owner/admin), and never a customer document — the product-sheet PDF is
  asserted price-free in the tests.
- **What the website shows** is decided in `get_catalog`, the one function every
  public path already goes through, so the catalogue, stock feed, product page,
  request validation and the notify-me flow can never disagree. Two switches,
  both behind `jasani.visibility`: a per-market `jasani.hideZeroStock.<market>`
  setting, and the `jasani_hidden` table for items taken off by hand. The
  zero-stock rule ships **off** — turning it on removes items from the live site,
  so it is an explicit decision, and it also removes the page a customer would
  use to ask for a back-in-stock notification.
- Low stock is `EM_LOW_STOCK_THRESHOLD` (default 20) — the same figure
  `public/js/giveaways.js` uses. Two thresholds would disagree in public.
- Printing manuals: `parent_id` is only a CANDIDATE manual id for the supplier's
  `/preview_product?product_id=...` PDF. Candidates are validated server-side
  (signature, page count, 10 MB cap) and cached 24h — valid and failed verdicts
  alike — in `runtime/cache/manuals/`. Customers download only via the
  `/api/giveaways/manual` proxy; never link to a Jasani URL. Full guide:
  `docs/jasani-printing-manual-guide.md` (drawing tools, custom PDFs and
  branding-price enrichment are future phases from that guide).
- **Product videos come from the supplier's PUBLIC page, not the API**
  (`server/supplier_video.py`). The Product API returns `videos: []` for items
  that plainly have one — ITGL 1291 is id 24246 / `parentId` 29453, and
  `https://www.jasani.ae/shop/…-29453` embeds `youtube.com/embed/lFhAiGLjoMo`.
  `parentId` **is** that public page id. Reading a webpage is not an API call:
  no token, no primary endpoint, nothing charged to the five-a-day budget — do
  not route it through `_fetch`. It is lazy (only a product page a customer
  opened, only after that page has rendered — the catalogue never asks), paced
  (`VIDEO_CONCURRENCY`, `VIDEO_MIN_INTERVAL_S`) and cached per **template**,
  positive *and* negative: without the negative cache every video-less product
  would be re-fetched on every visit, which is the crawl this must never
  become. Only a validated 11-character YouTube id leaves the module; supplier
  HTML is parsed and discarded.
- **A video's poster is a gallery photograph too.** Odoo keeps it as a
  `product.image` record, so the feed sends it as an ordinary picture and the
  same frame appears twice — once playable, once not. The two URLs
  (`/web/image/product.image/8803/…` and `i.ytimg.com/vi/{id}/…`) share
  nothing, so they are matched by **supplier record id**, never by URL and
  never by gallery position. Three methods, first one to answer wins:
  **Odoo's own slide numbering** (the video is carousel slide N and
  `<li data-bs-slide-to="N">` carries `o_product_video_thumb` plus a
  `product.image` id — confirmed live on ITGL 1290, slide 9 → image 20045);
  then containment (one record in the smallest element that also holds the
  embed); then subtraction (one video, one of our records the page never shows
  as a photograph). The video marker is **required** for the first — slide
  numbers lining up prove nothing on their own. Anything less certain leaves
  every image in place: `supplierPoster` stays empty and the browser removes
  nothing. Showing one picture twice is a blemish; deleting the wrong one
  loses a product photo. `supplier_video.without_posters` is that removal on
  the server — the admin item page and the product-sheet PDF go through it, so
  the panel shows the video a customer sees and a customer document never
  carries a frame of one.
- **The Items screen and its catalogue read the snapshot, never the
  supplier.** Searching, filtering, paging, selecting and generating a PDF all
  go through `item_list`, which filters the cached products in memory — none
  of it is a reason to spend one of the five daily calls, and there is a test
  that fails if any of them reaches `_fetch` or charges the budget. The old
  "20 items" ceiling was two things and neither was the dataset: the panel
  offered 25/50/100 and the route clamped `perPage` to 200. The options are
  now 20/50/100/250/500 (`PER_PAGE_OPTIONS`, `PER_PAGE_MAX`) and search was
  always across the whole snapshot — only the slice handed to the browser
  changed. The listing also returns `ids`, every matching id, so **Select all
  filtered** needs no second request and no five hundred checkboxes in the
  document.
  `min_stock` filters on the **viewed market's** available quantity with
  `>=`, so a minimum of 100 keeps an item sitting on exactly 100; a negative
  minimum is refused rather than read as zero.
  **Known and zero are different answers, per product.** A stock
  synchronisation that succeeds for a market is not a promise that it covered
  every product: `_merge_stock` only writes to the products it found a row
  for. So `stock.known` is tracked per item, and the test is always
  `_present`, never `_i` returning its default — the products feed sets it
  when it really carried a quantity field, and the stock merge sets it only
  for a row that really carries one. **A matched row is not a quantity**: a
  stock row that finds a product by id but holds no recognised quantity key
  says nothing about it, so it leaves the figure and the verdict alone rather
  than becoming a confident nought. `_row` exposes the flag as
  `availableKnown`; a snapshot written before this carries none and falls
  back to `jasani.stock_known(market)`, the honest reading of an older file.
  An unknown quantity cannot clear a positive minimum, and the catalogue
  prints "Availability unavailable" for it while a product the supplier
  really reports as empty still prints "0 units".
  **Carry-forward asks "known", not "zero"** (`_carry_stock`, used by the
  scheduled products sync and by a manual `products` or `full` refresh). A
  products call replaces the catalogue, not the figures joined onto it, so
  yesterday's quantities are carried onto the new list — but only for a
  product whose new record has no quantity at all. A feed that really reports
  nought is the supplier speaking and stands; judging it on `available == 0`
  replaced a genuine sold-out with yesterday's fifty.
- **The product catalogue is price-free because the renderer never sees a
  price** (`server/catalogue.py`, permission `jasani.view`). `to_dto` builds
  the customer-facing record key by key from `DTO_FIELDS`; the supplier dict
  is never passed through with price keys deleted, because that would carry
  along whatever price field a future feed invents. An allowlist has to know
  each field's **real shape**: `cartonWeight` and `cartonVolume` are
  normalized *strings* from `jasani._weight` ("9.5", or "9.5 kg" when the
  supplier sent the unit with the figure), so reading them as numbers
  silently dropped every carton row — they live in `DTO_MEASURE_FIELDS` and
  go through `_measure`, which keeps a string as it stands, accepts a number,
  and drops anything that is not a positive figure rather than printing
  "0 kg". `with_unit` appends the label's unit only when the value did not
  bring one, because "9.5 kg kg" is what doing it unconditionally produces. `FORBIDDEN_FIELDS` is
  asserted against the allowlist at import time. `assert_price_free` is the
  second line and runs inside `Document.finish`, so a document carrying a
  price indicator is refused rather than handed over. It decodes the page
  text — reportlab writes ASCII85 over Flate, so a raw byte scan would pass
  on every document ever made — and looks for **currencies and price labels
  only**. **What counts as "text" is the whole of
  that guarantee.** `extract_text` used to walk every `stream ... endstream`
  in the file and treat any parenthesised run of bytes as a drawn string. A
  photograph is an image XObject: 1200 x 1200 RGB decompresses to 4.3 MB of
  pixels, and in that much photographic noise the three letters of `rrp`,
  `sar`, `aed` or `usd` turn up by chance, between brackets, sooner or
  later. That is how production refused a catalogue whose every
  customer-facing field was clean — the bytes were never text, and no amount
  of sanitizing text could have fixed it. It now skips a stream whose object
  dictionary says image or font, and reads only strings inside a `BT`/`ET`
  block. If you ever widen what the extractor reads, widen it towards
  *drawn* text only.
  It deliberately does *not* match price figures: an item priced 100
  with 100 units in stock prints "100 units", a 500 ml capacity sits beside a
  price of 500, a carton of 24 beside a price of 24. Rejecting those would
  break honest catalogues while still missing a leak at an unusual value.
  A cover, an optional contents page, then exactly one A4 page per product —
  everything on a page is clipped to fit, because the contract is one page
  each and a reader counting pages has to trust it. Quantities are captured
  when the rows are read, so page 1 and page 400 cannot disagree, and the
  page prints the **stock synchronisation** timestamp rather than the moment
  the PDF was made; the cover labels the two dates separately.
  **The document is streamed, not assembled.** `Document` draws a page at a
  time and `_render` fetches one product's photographs, draws them and drops
  them before looking at the next, so the working set is a page's worth
  rather than five hundred products' worth — the first version held every
  blob until the end, which at 500 x 3 x 4 MB was a multi-gigabyte ceiling on
  a small VPS. `prepare_image` refuses an over-large picture on its header
  before a pixel is decoded (`MAX_IMAGE_PIXELS`), downscales to
  `MAX_IMAGE_DIM` and re-encodes, so a 4 MB original becomes tens of
  kilobytes; `PHOTO_CACHE_MAX` bounds what is remembered between products. Two
  measured runs, and they measure different things: 500 products with **one**
  photograph each (which is what the 640-product fixture carries) is 500
  fetches, 89.6 MB of source imagery in, 3.61 MB PDF out, about 114 seconds,
  largest single page ~62 KB; and 8 products with **three** each — the main
  image plus the secondary strip, `IMAGES_PER_ITEM` — is 24 fetches, 4.3 MB
  in, largest page 181 KB, peak prepared 1.3 MB. The three-picture path is
  deliberately measured small: 1,500 image transformations would add minutes
  to every full test run and prove nothing the eight do not. Do not quote a
  500 x 3 figure; it has never been run.
  Photographs come from the supplier's public image host, a file read rather
  than a primary endpoint and charged to nothing; one unreachable picture
  costs that product its photograph and nothing else. The build runs on a
  worker thread (`spawn`) and the panel polls for progress, so a long
  catalogue never holds a request open. The PDF lives in memory under a token
  that expires, is handed over once and then dropped.
  The audit records **two** facts: `jasani.catalogue_requested` when the job
  is accepted, and `jasani.catalogue_generated` — or `catalogue_failed` —
  written by the worker once the outcome is known. Writing "generated" at the
  start would be a log of intentions rather than outcomes. The worker writes
  that entry *before* it publishes the terminal state, because the panel
  polls the job from another thread: the other order left a window in which
  the build was over and the log did not yet say so.
- **A supplier writes what a supplier writes, so customer text is cleaned on
  the way in.** Production refused a whole catalogue with *"a price indicator
  reached the catalogue: 'rrp'"* — a real Jasani description carrying
  "RRP: SAR 45" in the middle of otherwise useful prose. Refusing is the
  right **last** resort and it stays; it is the wrong first answer, because
  one careless sentence must not make a five-hundred page document
  impossible. `sanitize_catalogue_text(value, field)` runs inside `to_dto`,
  before a page is drawn, and is a different job from `clean_text`:
  `clean_text` makes a value *printable* (tags, control characters,
  "undefined"), this makes a printable value *ours to print*.
  Prose (`FREE_TEXT_FIELDS` — description and name) is cut **fragment by
  fragment**, so "Premium bottle. RRP: SAR 45. Capacity 500 ml." keeps both
  real sentences. A short structured value — a colour, a material, an option,
  a category — is kept whole or dropped whole, because cutting half of a
  two-word value leaves nonsense: `option = "RRP 20 SAR"` is left out and the
  Black and Blue beside it are untouched. Three rules worth keeping:
  - **Nothing is left dangling.** Whatever survives is re-checked, and a
    value still carrying an indicator is dropped rather than printed
    half-cleaned — a "45" orphaned by a deleted "SAR 45" is worse than no
    sentence. `_ONLY_FIGURE` catches the same thing one level down: "R.R.P.
    99" splits on the abbreviation's dots, and the amount goes with the
    label.
  - **A bare currency counts.** The guard rejects a bare `SAR`/`AED`/`USD`,
    so the sanitizer removes one too; otherwise "quoted in SAR" would still
    fail the document.
  - **"price" alone is not a price.** It is far too ordinary a word — a
    price-conscious design is a design, "low cost" is a description. Bare
    `price` counts only where it introduces a figure: a colon, a spaced dash,
    a currency or a number. Every label that *is* unambiguous (RRP, R.R.P.,
    recommended/retail/list/unit/selling/reseller/wholesale price, ex/incl
    VAT) counts on its own, because "RRP available on request" carries no
    figure and is still a price statement.
  The contents page reads the name separately, so it is sanitized separately.
  The cleanup is **counted and reported** — `sanitizedProducts` /
  `sanitizedFields` on the job, in the status payload, in the audit entry and
  as one unalarming sentence in the panel — because silently editing a
  customer document is worse than an ordinary note about normal supplier-data
  cleanup. Counts only: a figure that is not ours to show is not ours to log.
  `scripts/audit_catalogue_text.py` answers "which product caused it" from
  the cached snapshot alone — read-only, no supplier call, naming the product
  code, the field and which indicator matched, never the price. It runs
  `to_dto` itself and diffs raw against sanitized rather than keeping its own
  list of fields, so it cannot drift from the renderer.
  **One boundary, and only one.** Every customer-facing string the document
  draws comes out of `to_dto` — the product page, the cover, the contents
  list and the PDF's own title. The contents page used to clean its own two
  strings, which was a second implementation of the boundary and therefore
  one that could drift; it now reads the DTO like everything else. A
  parametrized test asserts the contract in the other direction too: for
  every entry in `PRICE_WORDS`, text the finished-document guard would
  refuse is text the sanitizer removes first — otherwise a product would
  exist that could never be put in a catalogue. `SRP` and `MSRP` are in
  neither list, deliberately: no supplier record audited carries them, and
  "SRP" has honest meanings. Adding one means adding it to **both**.
- **The catalogue is designed, not generated.** The first version was
  functional and looked it: a cover whose lower half was empty, a product
  page that read as a specification sheet, one large photograph and a strip
  of 52pt thumbnails. The layout is now a composition, and these are the
  rules it keeps.
  - **A description is never cut mid-sentence.** `trim_to_sentence` falls
    back to the last complete sentence that fits, because "…compatibility
    with …" reads as a fault in the document while a shorter whole sentence
    reads as an edit. An ellipsis appears only when not even one sentence
    fits. Before truncating at all the composer lets the gallery yield a
    further 44pt (`GALLERY_FLOOR` below `GALLERY_MIN`) on a text-heavy
    product: the order of preference is the whole description, then all the
    specifications, then readable type, then a moderately smaller gallery,
    and only then the knife.
  - **The availability band's label is the verdict, not a heading.** It used
    to be a fixed "AVAILABLE NOW" drawn above whatever `stock_sentence`
    returned, so a genuinely empty product printed "AVAILABLE NOW / 0 units"
    — two statements on one page contradicting each other, which production
    review found on ITWC 1302, Maglite 5K - Navy Blue. `stock_state` is now
    the one reading of the figures that the label (`STOCK_LABEL`), the mark
    (`_STOCK_ICON`) and the quantity all take: **in** → AVAILABLE NOW and the
    figure, **out** → OUT OF STOCK and the real nought, **unknown** →
    AVAILABILITY UNAVAILABLE and `STOCK_UNKNOWN_FIGURE` ("Not reported")
    where the number would be, because a quantity nobody reported is not a
    nought and printing one is the same lie read from the other side. The
    verdict is taken from the integer `_num` would **print**, not the raw
    value, so a quantity of 0.4 prints "0 units" under OUT OF STOCK rather
    than claiming to be available. The mark moves with the words — a tick
    beside OUT OF STOCK is the same contradiction as the label — so `_icon`
    gained `cross` and `dash`. Nothing else in the band moved: the panel, the
    orange rule, the 74pt height, the type sizes and the STOCK UPDATED
    timestamp are as they were, and a known-positive page is byte-identical
    to before the correction. `stock_state` is now the one reading on all
    three surfaces — the catalogue page, the shared web viewer and the admin
    product sheet, whose chips are In stock / Currently out of stock /
    **Availability not reported**. The sheet used to judge `available <= 0`,
    which told an admin a product was out of stock when the synchronisation
    had simply never answered for it.
  - **The feature row is the only part of the page that could lie, so it is
    the most tightly held.** `product_features` reads the sanitized DTO's
    name, description and the material/size/capacity specifications — and
    nothing else — against `FEATURE_RULES`, a table of explicit patterns.
    A badge appears only when the product's own words say so, its label is
    built from the matched text ("15W wireless", "5,000 mAh") rather than
    written in the table, and nothing is ever inferred from a category or a
    brand: being in Power Banks is not a claim about wireless charging.
    **A figure is a figure, however it is punctuated**, and every numeric
    rule is built from one pattern (`_figure_before`) and one normalization
    (`_fig`) so a comma cannot make one badge right and another wrong. The
    old `\b(\d{3,6})\s*mah\b` could not match across a separator: on a real
    description reading "The 5,000 mAh capacity …" the scan failed at the
    "5" and matched the "000" three characters later, so ITWC 1302 told a
    customer "0 mAh" — and `\b(\d{1,3})\s*w\b` turned "1,500 W" into
    "500W charging", a lower claim about a real product. `_figure(sep)` is
    three branches and the order is the fix: **grouped** first so the whole
    number wins at the leftmost position; **four digits or more**, which
    cannot be a group tail and so needs no guard ("USB 3.0 and a 5000 mAh
    cell" still matches); and a **short** one-to-three-digit run, refused
    directly after a digit or a digit and any separator (`_TAIL_SEP`, which
    always includes the ordinary space), so the tail of a malformed "5,00"
    — or of a prose "5 000" — is no badge rather than a wrong one. `_fig`
    then prints it one way: grouped in thousands, the fraction as written,
    no trailing ".0".
    **Where a figure was written decides how far it is trusted.** Accepting
    an ordinary space as a separator is what "5 000 mAh" needs and what "Set
    of 4 750 ml bottles" cannot survive — it read as 4,750 ml, a
    specification no reader would question and the product does not have.
    The first attempt was a list of count words, and it was the wrong shape:
    "a gift set containing 4 750 ml bottles" walked straight through it, and
    no enumeration of verbs ever closes that. The fields used to be joined
    into one string before anything was read, which threw away the fact that
    settles it. They are read separately now (`feature_sources`):
    `STRUCTURED_FIELDS` (**capacity, size**) are measurement fields, read
    one at a time and never joined — a capacity of "2" beside a size of
    "500 ml" would otherwise invent "2 500 ml" — and they accept
    `_GROUP_SEP`, ordinary space included, because the field itself is the
    context. `PROSE_FIELDS` (**name, description, material**) are read as
    one passage, so negation still reaches across a sentence, and they
    accept `_PROSE_SEP`, which is the same list **without** the ordinary
    space. `material` is prose deliberately: "Stainless steel" describes a
    material, it does not promise that a figure inside it is a measurement.
    Two rule tables are built from one literal definition (`_rules(figure)`)
    so the rules are written once; families still deduplicate across every
    source. **A missing badge is acceptable; a plausible false
    specification is not** — prose carrying "5 000 mAh" simply gets no
    badge, and the 750 is never pulled back out of a number we have just
    said we cannot read.
    `_is_counted` / `_COUNT_LEAD` survive, and guard **exactly one thing**:
    a quantity written into a field whose job is a measurement
    (`capacity = "set of 4 750 ml"`), the one source where a space still
    groups. It is passed `guard_counts=True` from there and nowhere else.
    Keep that list short — a vague word in it suppresses a real
    specification, which is the same mistake reversed — and do not grow it
    to cover prose, which no longer needs it.
    One wrinkle, asserted rather than glossed: `clean_text` folds U+00A0 to
    an ordinary space before any of this runs, so a plain no-break space
    still groups in a measurement field but is read as language in prose;
    only U+202F is unambiguous everywhere. Each
    rule belongs to a **family** that fires once, because "PD 22.5W" and
    "22.5W charging" are one fact twice and the second slot is better spent.
    A match is rejected when a negation stands near it **in the same
    sentence, on either side** — "dishwasher safe parts are not applicable"
    is a supplier saying the opposite. At most `MAX_FEATURES` (4), and with
    nothing certain the row is simply absent. The icons are drawn with
    reportlab primitives in `_icon`: no icon font, no third-party file,
    nothing to go missing from a deploy. One row per page, under the name,
    and it is dropped before a specification row or a sentence is — content
    first, badges second.
  - **The page is composed before anything is drawn.** `_identity_plan`,
    `_description_height` and `_specs_height` measure first, and the gallery
    takes what is left between `GALLERY_MIN` and `GALLERY_MAX`. That is why
    a product with two specifications fills the page with its photograph
    instead of leaving a hole, and one with thirteen still prints all
    thirteen — the picture yields, never the content. A measurement and its
    renderer must agree exactly: when `_specs_height` allowed 26 points for
    a heading the loop charged 24 for, the composer reserved room for twelve
    rows and the page printed eleven.
  - **The gallery adapts to how many pictures there really are**
    (`usable_photos`, `_gallery`): one spans the page; two sit side by side
    at 64/36; three are a main with two stacked beside it; four are a main
    with three. Four is a ceiling, not a target — a fifth view costs the
    others the room that makes them legible, and a full-width fourth strip
    was tried and rejected because a portrait product in a 500 x 75
    letterbox is a picture nobody can read. The main image is 50–72% of the
    composition, which a test asserts. Duplicates are dropped before
    layout: a supplier that lists one file twice should not spend half the
    gallery showing it twice.
  - **The cover is no longer composed here.** It was: a hero built from the
    catalogue's own first few products, a headline split out of the admin's
    title. It is now the approved master (`server/cover.py`, below), and
    `Document.cover()` ignores any photographs handed to it. `_cover_ground`,
    `_cover_hero`, `_cover_meta`, `cover_title`, `_cover_photos` and
    `COVER_IMAGES` went with it.
  - **Type carries the hierarchy.** `name_parts` reads the supplier's own
    " - " segments as range / product / variant, so "NAPIER - MagCase Phone
    Cardholder - Navy Blue" is set at three weights. It is presentation only
    — every word still prints, and there is a test that says so.
    `_tracked` draws the letterspaced labels and **must** reset `Tc` to 0
    before the text object ends: character spacing is page state, so one
    tracked label left every later string on the page letterspaced, drawing
    wider than it was wrapped for and running into its neighbour.
  - **Orange is an accent.** `PAPER`, `SOFT`, `FAINT` are the surfaces; the
    brand colour is a 2pt rule, a section label, the availability marker, a
    detail inside an icon and the dilute field behind the cover hero. No borders where a tint or a hairline will do:
    specification rows alternate rather than sitting in a table, and a
    photograph gets a soft three-pass shadow rather than an outline.
  - The redesign changed no behaviour: the price guarantee, the sanitizer,
    the final guard, stock figures and timestamps, one product per page,
    the bounded per-product image pipeline and the 500-product ceiling are
    all as they were. 500 products with one photograph each measured 4.01 MB
    and 111s after the change (3.61 MB before — the extra is per-page vector
    work, not imagery).
- **A photograph goes into the PDF as the JPEG it already is.** This was the
  whole of a catalogue's size, and it was not the layout, the fonts or the
  vector work: `exports._image_box` re-encoded every prepared JPEG to PNG
  before handing it to reportlab, and reportlab embeds a decoded picture as
  zlib-compressed raw RGB. Measured on real photography, a 140 KB product
  shot became **1.55 MB** in the file; 500 products with one picture each was
  **428 MB** and 100 with three was **270 MB**. reportlab will embed a JPEG
  verbatim (`/DCTDecode`) when the source answers `jpeg_fh()`, and
  `ImageReader` does answer it for a file PIL opened as a JPEG — so the fix
  is to stop re-encoding, not to subclass anything. `_image_box` now passes a
  **baseline** RGB/greyscale JPEG straight through and still flattens
  everything else (PNG, palette, alpha, CMYK, progressive) onto white,
  because the drawing code assumes RGB and `/DCTDecode` does not promise to
  read a progressive scan. `_JPEGReader` overrides `getRGBData` to hand back
  the compressed bytes: `Canvas.drawImage` reads it only for the digest it
  keys an image by, so the same picture still collapses to one object — the
  cover hero and the page that repeats it are one stream — and nothing is
  decoded twice.
- **Two picture sizes, two quality modes, and the slot is part of the cache
  key.** A page draws a leading photograph up to 503pt wide or 366pt tall and
  a supporting one never wider than 207pt, so `PHOTO_DIMS` prepares them at
  different sizes: Standard 1000/620 px at JPEG 72 with 4:2:0 chroma, High
  1400/920 at 86 with 4:2:2. Standard is the default and an unreadable mode
  reads as Standard, never as the heavier document. `prepare_image(raw,
  slot=, quality=)` with neither argument keeps the old behaviour, which is
  what the product sheet and the tests use. The URL cache in `_photos_for` is
  keyed on `(url, slot)`: one picture used as a leading shot by one product
  and a side view by another is prepared twice, which is honest — the
  alternative is a leading photograph that is soft because some other product
  got there first. The cover hero shares the `"main"` entry its own page
  uses, so it is never fetched twice. Nothing of the original survives: no
  EXIF, no colour profile, no thumbnail, and `progressive=False` so the
  picture can always go in untouched.
- **Streams are binary, not ASCII base-85** (`rl_config.useA85 = 0`, set once
  in `server/exports.py`). Base-85 writes four bytes as five printable
  characters — a flat 25% on every stream in the file — to make PDF bytes
  safe for a 7-bit transport nobody has used in thirty years. It is a
  library-wide setting read at the moment a stream is written, so it is set at
  the module every PDF in this application is drawn through rather than
  toggled around a build where two threads could disagree.
  **One thing depended on it.** `extract_text` found a stream by scanning for
  `stream ... endstream`, which is safe only while stream data is printable:
  in binary data those eight letters turn up by chance, and the letters
  *around* them would then be read as drawn text — the exact failure the
  image-stream fix exists to prevent. So a stream is now identified by the
  dictionary in front of it (the preceding bytes must end in `>>`), which
  every real stream has and a run of JPEG bytes does not. Measured on a small
  catalogue, that rejects 18 bogus matches out of 36. `_decode_stream` tries
  base-85 **and** falls through to zlib rather than giving up, so a document
  written before this still reads.
- **The logo was 49 KB in every document.** The shipped wordmark is 1660 x 560
  with an alpha channel, drawn 26pt tall — about 1,500 dots to the inch — and
  an alpha channel means raw RGB plus a soft mask. `exports.logo_reader(h)`
  resizes it once to `LOGO_PX_PER_PT` (6) pixels per point, caches it per
  drawn height and keeps the alpha, so the mark still sits on a tinted band.
  On a one-product catalogue that was a fifth of the file.
- **Measured, with real photography.** The source imagery for a size
  benchmark has to be real: a flat synthetic swatch compresses to a few
  kilobytes whatever the filter and film grain compresses to nothing, so
  either one makes the measurement say whatever it was built to say. The
  committed "500 products = 4.01 MB" figure came from flat test fixtures and
  was never a photographic catalogue. Against the site's own photograph
  library, one product per picture:

  | case | before | after (Standard) | |
  | --- | --- | --- | --- |
  | 1 x 1 | 1.60 MB | 0.11 MB | -93% |
  | 1 x 3 | 5.19 MB | 0.18 MB | -97% |
  | 25 x 1 | 20.9 MB | 1.16 MB | -94% |
  | 25 x 3 | 67.8 MB | 2.23 MB | -97% |
  | 100 x 1 | 86.8 MB | 4.72 MB | -95% |
  | 100 x 3 | 270 MB | 8.98 MB | -97% |
  | 500 x 1 | 429 MB | 23.4 MB | -95% |
  | 500 x 3 | 1329 MB | 44.5 MB | -97% |

  Generation time fell with it (100 x 3: 239s to 84s, and 83s of that 84 is
  the image pipeline rather than the renderer; 500 x 3: 1200s to 422s) and so
  did the working set (500 x 3: 4920 MB to 310 MB), because nothing decodes a
  photograph to raw pixels any more — the largest catalogue went from a
  document the implementation could not really produce to one it can.
  High is about twice Standard and still a tenth of what it was
  (100 x 1: 4.72 / 9.10 MB; 500 x 1: 23.4 / 45.3 MB against 429 MB).
  Do not quote a figure this table does not carry.
- **The cover is an approved design, translated — not composed**
  (`server/cover.py`, assets in `server/data/cover`, fonts in
  `server/data/fonts`, the authority in `docs/catalogue-cover-master.md`).
  Every number in that module is measured from the master's own PDF, so a
  coordinate that looks odd is a coordinate that was measured. It may not be
  improved, rounded off or re-judged; the implementation map wins for cover
  visuals, and the catalogue's own logic still wins for stock, selection,
  counts, dates, prices, images, sharing and size.
  - **Three things are raster, and they are the approved artwork.** The
    official wordmark (`logo.png`), the faint watermark symbol derived from it
    (`watermark.png`) and the branded hero photograph (`hero.jpg`) — the
    master supplies all three as images and the watermark is deliberately not
    traced. The background fall, the orange field and its shading, every
    letter, the metadata band, its three icons and its rules are vector or
    text, so the page stays searchable and scales without pixels. A test
    fails if a fourth raster appears. Those three drawn images are carried by
    **five** image XObjects: the hero is one opaque JPEG, and the wordmark and
    the watermark each have a greyscale soft mask for their transparency — so
    a test counting objects rather than drawn pictures must say five, and
    `page.get_images()` on the cover says three.
  - **The wordmark is a file, never a drawing.** `logo.png` is the approved
    source byte for byte — SHA-256 `38cb42d7…`, asserted in a test — placed
    at 16/12 mm, 57 mm wide and `57 × 518 / 1629` tall, which is its own
    aspect ratio and not a rounded figure. Never trace it, never re-typeset
    ELITE MARCOM, never substitute the older defective SVG.
  - **The hero's seven product applications were audited once, in the
    master**, and are not recreated. `scripts/build_cover_assets.py` lifts
    the composition out of the master HTML by hash. There is a test that
    fails if the words "homography", "perspective" or "quadrilateral" appear
    in the generator, because a future reader must not be tempted.
  - **What is behind the hero is baked into it.** The hero is 210 mm wide
    and three quarters transparent, so the gradient, the field and the
    watermark show through. ReportLab can embed a JPEG, or raw pixels with
    an alpha channel, but not a JPEG with one — and the alpha route costs
    7.75 MB of Flate against 1.75 MB of JPEG. So the build script composites
    the hero over exactly the three layers beneath it, computed from the
    same constants `cover.py` draws them with, and the result is drawn
    opaque. `lerp_stops` and `field_path_points` exist so that the bake and
    the renderer cannot interpret the gradient or the contour differently.
    The baked band is identical to what it covers: measured against the
    master's own 300 dpi render, every sampled point agrees within two
    levels of 255.
  - **The hero is embedded at the master's own 4096-px canvas**, so nothing
    is resampled. That canvas is 4x for a reason — it is what antialiases
    marks as small as the pen's 2.9 mm — and at 300 dpi the pen visibly
    softens under the 600 dpi loupe the logo audit uses. Measured
    alternatives are in the build script.
  - **Six strings change and nothing else does**: market, country, year,
    product count, prepared date, stock timestamp. The wording — CORPORATE
    GIFTS, PRODUCT, CATALOGUE, the promise line, the disclaimer, the address
    — is the approved wording, the same on a one-product catalogue and a
    five-hundred-product one, which is the point. A test asserts the proof's
    own fixture values ("08 Oct 2026", "1 product") appear nowhere in the
    code. **The admin's catalogue title no longer sets the cover**; it is
    still the PDF's document title, and the dialog says so.
  - **Tracking is `setCharSpace`, never literal spaces**, and CSS adds it
    after the last character too — which is why a right-aligned string is
    measured with its trailing space included and `Saudi Arabia · KSA` ends
    0.38 mm short of 194. `draw_tracked` always puts the char space back.
  - Poppins 400/500/600 are registered from `server/data/fonts`. They are
    the first embedded fonts this application ships; the standard 14 are
    still what every other page uses. If the files go missing the cover sets
    in Helvetica rather than failing, and `fonts_ready()` says so.
    The faces are under the **SIL Open Font License 1.1**, which the fonts'
    own name table declares, and the licence travels with them:
    `server/data/fonts/OFL.txt` is the authoritative text as distributed with
    the upstream family (`google/fonts/ofl/poppins`), copyright 2020 The
    Poppins Project Authors. It is verbatim and must stay beside the files —
    the OFL requires the notice to be bundled with the font software, so
    moving or trimming it is a licence matter, not tidying. Never write
    licence text by hand.

- **A shared web catalogue is a frozen copy, not a live view**
  (`server/catalogue_share.py`, `catalogue_shares` and `catalogue_assets` in
  admin.db, permission `jasani.view`). `/catalogue/<token>` serves
  `public/catalogue-view.html` — a standalone viewer, deliberately not built
  on `styles.css` and with no site nav, so a client on a phone downloads one
  small stylesheet and a code change needs no **Publish site**. The products,
  the quantities, the stock timestamp and the photographs are written once
  and never rebuilt, which is where every other property comes from:
  - **No supplier call on a page view, ever.** The snapshot comes from the
    same cached products the PDF is built from, and the pictures are copied
    into `runtime/catalogue-assets` while the share is being made. A visitor
    reads our own database and our own files. There is a test that fails if
    opening a share reaches `_fetch`, `_fetch_image_bytes` or the budget.
  - **The same price boundary.** Every customer-facing string comes out of
    `catalogue.to_dto`, and `assert_snapshot_price_free` is the second line,
    exactly as `assert_price_free` is for the PDF. It names the field and
    never the figure.
  - **Python decides what a quantity means; the browser prints it.** The
    viewer drew `stockText` and then the word "available" after it, so an
    empty product and one the supplier never answered for each read as a
    sentence contradicting itself. `catalogue_share.stock_presentation`
    returns `stockState` / `stockLabel` / `stockFigure` from
    `catalogue.stock_state` and `STOCK_LABEL` — the PDF page's own reading,
    not a second one written in JavaScript, because two sets of rounding and
    threshold rules are two that can disagree in front of a client. A new
    snapshot stores the three fields; an **older** share carries only `qty`
    and `known`, which is all the function needs, so a link already sent
    renders correctly without being regenerated and **without being
    rewritten** — the frozen record is read to render, never edited to
    render, and a test asserts the stored bytes are unchanged afterwards.
    An unknown item's frozen figure stays in the snapshot and is dropped
    from the *payload*: a stale number the browser never receives is one it
    can never print.
  - **The link is the credential, so the database cannot hand one out.** Only
    `sha256(token)` is stored; the token is 128 bits from `secrets`, shown to
    the admin once, and in no log, audit entry or error message — the audit
    records the share's **id**, which is what somebody revoking it needs.
  - **Two stages, because a catalogue is long.** `index.json` is one small
    record per product (name, code, first picture, availability, categories)
    and powers the grid, the search and the filters; `p/<i>.json` carries the
    specifications and the description for the one product a client opened.
    A page option switched off is left out of the **snapshot**, not hidden by
    the viewer — a viewer cannot show what it was never given.
  - **Pictures are addressed by the hash of their own bytes**, so two products
    carrying one photograph are one file and re-sharing the same products
    copies nothing; `catalogue_assets` remembers which URL produced which hash
    so a re-share does not re-read the image host either. A picture is served
    only under a live token that names it, and the name is 64 hex characters
    with no separator a traversal could use. Cleanup is mark-and-sweep over
    the live snapshots, never reference counting, because a count that drifts
    leaves either a broken picture or a file nobody can delete.
    **The temporary file is per writer, not per picture.** Two builds meeting
    one uncached photograph both see the destination missing and both write
    it; with a shared `<digest>.webp.part` they wrote the same path and then
    both renamed it, so whichever lost the race renamed a file that was no
    longer there. `store_asset` writes `<digest>.<pid>-<random>.part` in the
    same directory and `os.replace`s it, which is atomic within a directory:
    the loser simply overwrites the winner with identical bytes, a reader
    never sees a partial file because a partial file never has the final
    name, and a failed write cleans up after itself.
  - **Two timestamps on a mapping, because they answer two questions.**
    `last_used_at` moves whenever a build names a picture and is what keeps
    the sweep off it; `fetched_at` moves only when the image host was really
    read, and is what decides whether a **new** share may reuse the mapping.
    Overloading one column meant every reuse looked like a fresh read, so a
    mapping could never go stale and a photograph the supplier replaced
    behind the same address would have been ours for ever. Past
    `SOURCE_TTL_S` (7 days) a new share re-reads the public picture once,
    re-encodes and re-hashes it; unchanged bytes give the same hash and the
    same single file, changed bytes give a new hash that only the new share
    names. An existing share is frozen regardless — it stores hashes, not
    URLs — and if the image host is unreachable the last-known-good picture
    is used and `fetched_at` is left alone so the next share tries again.
    This is share **creation** only: no page view ever revalidates anything,
    and reading a public image host is not a Jasani API call.
  - **A cached picture must not outlive the link.** The image response was
    `private, max-age=86400`, which lets a browser reuse it for a day without
    asking: revoke a catalogue and the page, the data and the document stop
    while a picture already in that browser keeps resolving. It is now
    `private, no-cache` with the content hash as the `ETag` — the browser
    still keeps the file and still avoids re-downloading it, but it has to
    ask, and asking is what makes revocation complete. The share is resolved
    **before** a conditional is honoured, so a withdrawn link gets its 404
    and a lapsed one its 410 rather than a 304. Never `public`, never
    `immutable`, never a bare `max-age` on bearer-protected imagery; the page,
    the JSON and the PDF stay `no-store`.
  - **A client is holding the link, so a backup carries it.** The Operations
    backup now includes every `catalogue_shares` row — history is a few
    hundred bytes and worth keeping — plus, for the shares that are still
    live, the frozen snapshot, the photographs they name (content-addressed,
    so ten shares naming one picture store it once) and the optional PDF.
    The raw token is not in the backup and is not needed: the client has it
    and the database only ever stored its SHA-256, so a restore brings the
    *same* link back. A revoked or lapsed share is carried as its row alone.
    `BACKUP_ASSET_BUDGET` (30 MB) bounds the imagery so the zip still fits
    `MAX_RESTORE_BYTES`, newest share first; one that does not fit keeps its
    row and its snapshot so the link still opens with every word of the
    catalogue, and the manifest says how many were trimmed. **A backup with
    no `catalogueShares` key at all is one written before any of this, and
    leaves the table alone** — that is not the same as a backup saying there
    are none, and getting it wrong would have had an old backup quietly take
    down every live client link.
  - **Revoked means revoked**: the page, the data, the pictures and the
    document stop together, and the row stays so the history reads straight.
    An expired link says so (410) because that is something a client can ask
    about; an unknown and a withdrawn one read the same (404).
  - **The PDF is drawn in the same pass**, when the share allows one (off by
    default), so the document a client downloads is built from the pictures
    the page shows and downloading it is a file read. A share's settings are
    fixed — change one by making another share.
  - **A view is a counter and a timestamp.** No address, no user agent, no
    identifier of any kind, and reading the data does not count as another
    view. The viewer sets no cookie and loads no analytics.
  - `noindex,nofollow,noarchive` in the shipped markup **and** as
    `X-Robots-Tag` on every route; `content.SITEMAP_SKIP` keeps the shell out
    of the sitemap; nothing is added to robots.txt, because a page that is
    never fetched is a page whose noindex is never read. The viewer's JS is a
    file, not inline, because `script-src` is `'self'` with no
    `'unsafe-inline'` — and there is no `innerHTML` in it, so no supplier
    string can ever be read as markup.
- **`supplier_video.CACHE_SCHEMA` invalidates stale verdicts.** Bump it
  whenever a parser change means a stored answer could be improved on; an
  entry written under a lower number is treated as absent and rediscovered.
  Nobody should ever delete cache files by hand for a parser fix to land.

## Site conventions

- **Cache busting is mandatory, not optional.** Production serves CSS/JS by
  path (no hashed filenames), so a changed asset only reaches returning
  visitors when its `?v=` changes. Every time you edit a `.css` or `.js` file,
  before the task is done:
  1. Bump `?v=` for that asset — and only that asset; assets you did not
     change keep their version.
  2. Update **every** page that references it — `public/*.html` *and*
     `server/adminui/*.html` (`app.html`, `login.html`). Shared assets like
     `styles.css`, `site.js`, `theme-init.js` and `insights.js` appear on a
     dozen pages; missing one leaves that page on the stale copy.
  3. Grep the repo for the *old* value and confirm nothing still references it.
  4. Run `python -m pytest tests/test_asset_versions.py` — it fails if one
     asset carries two different versions, if a local CSS/JS reference has no
     `?v=` at all, or if a referenced file is missing from disk.
  `runtime/published/site/` needs no hand-editing: it is baked from
  `public/` by **Publish site**, so bumping the sources and publishing carries
  the new versions through. `/theme-custom.css` is server-rendered with
  `Cache-Control: no-cache` and is exempt.
- **What the visual editor can change, and where it is stored.** Three layers,
  in this order at bake time: `design.apply_to_page` (sections → text → attrs →
  `<style id="em-design">`), then the keyed content model, then nav/social
  injection. Which layer owns an edit:
  - Text on an element **with** a `data-em` key → the content model
    (`content` table, per language, shared site-wide for `_global` keys).
  - Text on any **other** element → `design` doc, `elements[path].text`,
    sanitized with `content.sanitize_rich` (bold/italic/link/list/`<br>` only).
    The bridge offers this only for elements whose children are all inline —
    editing a wrapper must never delete the cards inside it. If a container and
    something inside it both carry text, the container wins: applying both
    would splice the inner edit into offsets the outer one already moved.
  - New blocks → `sections.added = [{id: "aN", template}]`, rendered from
    `server/blocks.py`. Ids are `s…` for sections already in the page and `a…`
    for added ones; both are valid in `order` / `removed` / `duplicated`.
    **Templates are ours, never admin input** — an admin places a block and
    edits its text, and that text goes through the same whitelist.
  - A **blank** section carries `children: [{id: "eN", template}]` from
    `blocks.ELEMENTS` — heading, paragraph, image, video, button, icon,
    columns, cards, list, divider, spacer. Each is stamped `data-em-el`, and a
    path may anchor on it (`[data-em-sec=a1]>[data-em-el=e2]>a:nth-of-type(1)`)
    so a style stays on its element when the ones around it are reordered.
    Same rule as sections: the panel sends a template id, never markup.
  - A **copied** section is `{id: "aN", from: {page, sec}}` — we remember which
    of our pages it came from and `design.section_from_page` lifts the markup
    out of that page at bake time, after collections have been applied, with
    ids and `data-em`/`data-em-list` markers stripped. So copy/paste works
    across pages, the copy is edited independently, and no HTML ever travels
    through the panel. It is a frozen copy: it does not become a second live
    instance of a managed list.
- **The visual editor's section controls** are one implementation shared by
  two surfaces: an on-page toolbar the bridge draws over the selected section
  (grip, ↑ ↓, duplicate, copy, hide, delete) and the Sections list in the
  panel (the same, plus drag-and-drop rows and Paste). Both call the same
  `sec*` functions, so they cannot disagree. A hidden section stays on screen
  in the editor, dimmed and labelled — `display:none` would take its own Show
  button away with it; only the bake drops it. Dragging an element's orange
  edge handle writes `width`/`height` for the viewport being edited, like any
  other style.
- **Spacing is eight properties, never a shorthand.** The style engine used
  to know `margin` and `padding` only as the CSS shorthand, and every
  declaration `build_css` emits carries `!important` — so "padding: 20px"
  forced all four sides and wiped whatever horizontal padding a container was
  designed with. That is why spacing appeared to work on some elements and to
  break the layout on others, and why a single side could not be set at all.
  `STYLE_PROPS` now also holds `margin-top/right/bottom/left` and
  `padding-top/right/bottom/left`; the Spacing panel writes those, so an
  override touches the side that was changed and leaves the other three to
  the site's own CSS. The shorthands stay for documents saved before this and
  are still applied — the panel offers **Split into sides** rather than
  rewriting them behind the admin's back. Padding is validated separately
  (`_PAD_RE`): no negative values and no `auto`, because neither exists in
  CSS; margin keeps both. Everything else was already generic and needed no
  change — validation is a table lookup, `build_css` and the panel's mirror of
  it iterate whatever keys a breakpoint holds, and undo, dirty-tracking, save
  and publish all work on the document rather than on named properties.
  **An empty value deletes the property**, which is what Reset sends: writing
  `0px` instead would look identical on an element whose CSS said 0 and
  silently flatten one whose CSS said 32px. With nothing overridden the page
  gets no `<style id="em-design">` at all, so the public site is byte-identical
  until somebody changes something.
  One consequence worth knowing: the preview's live `<style id="em-live">`
  carries the **whole** merged document, not a delta, so the bridge switches
  off the baked `em-design` block on the first apply. Without that, removing
  an override could never be previewed — the live sheet would simply stop
  mentioning the property and the baked `!important` underneath would keep
  winning, so Reset would look like it had done nothing until the frame
  reloaded.
- **Repeatable content — the items inside a section** lives in
  `server/collections.py`, and is the other half of the design layer: sections
  are added, duplicated, reordered, hidden and deleted in the visual editor;
  the items inside one are managed on the **Sections & items** screen. That
  screen is **page-first** — every page of the site, then that page's lists,
  then one list's items (`#sections/<page>/<list>`) — so the whole website is
  managed page by page rather than a flat pile of lists. A managed list is a
  container in the shipped HTML carrying `data-em-list="<name>"` plus a schema
  here — fields, a `render` that writes the markup and a `parse` that reads the
  shipped page back. Two rules:
  - **The markup is ours.** `render` writes every tag; an admin supplies text,
    an image path (`/assets/…` or `/media/…` only) and a link, each escaped or
    validated on the way in. Nothing typed in the panel is parsed as HTML.
  - **An untouched list is the page.** With no rows in `collection_items`, the
    list is parsed out of the git HTML and follows it; the first edit copies it
    in and the panel owns it from then on, exactly as the rental inventory
    works. Reset drops the rows and the page comes back. So a shipped list must
    survive `render(parse(page))` field for field — there is a test for every
    one, and a new list is not finished until it passes.
  Collections bake **between** the section layer and the element overrides
  (`design.apply_to_page(..., between=…)`): a section duplicated in the editor
  brings its list, one removed takes its list away, and a text or style
  override on a card inside a list is applied after the list is built rather
  than being rebuilt away. Adding another managed list is a `data-em-list`
  attribute plus one entry in `SCHEMAS`.
  - **`_header` and `_footer` are pseudo-pages.** The menus and the footer
    columns are not on a page, they are on every page: they are read from
    `index.html` (`source`) and baked into all of them, so
    `apply_to_page` applies a list whose `page` is in `GLOBAL_PAGES`
    regardless of which page is being baked, and an edit to one marks every
    page as waiting to publish. `page_href` decides which link gets
    `aria-current="page"` from the page being baked — a stored "this is the
    current one" field would have marked Home as current on every page — and
    `NAV_PARENT` maps a product or rental-item page onto the menu entry it
    belongs under. Only the header marks it; a footer link repeating it is
    noise for a screen reader.
  - **The menu labels are the list, not content keys.** `nav.home` … 
    `nav.contact` used to be eight fixed `data-em` keys, which could rename a
    link but never add, remove or reorder one. They were removed from
    `GLOBAL_REGIONS` and from the markup so the menu has exactly one owner. The
    cost is that an Arabic edition carries the English menu — the same
    limitation every other managed list already has, since `collection_items`
    has no language dimension. Per-language items would fix all 31 at once.
  - **A renderer never invents a picture's dimensions.** `_dims` writes back
    the `width`/`height` the page had, carried through `_clean_values` as a
    `carry` key rather than a form field, because a fixed pair would put every
    image in the wrong aspect box.
- **Ten published versions, and every field shows its real text.**
  `content.KEEP_PUBLISHES` bounds the `publishes` table: each row carries a
  full copy of the content and design tables, so an unbounded history is an
  unbounded database. The prune runs inside `publish_all`, right after the
  insert, so the ceiling holds whether or not anybody opens the screen. A
  version beyond the last ten is gone, and `rollback` refuses it by name
  rather than silently doing nothing.
  In the Text & SEO editor a field is filled with the live sentence rather
  than showing it as a placeholder, because a placeholder cannot be selected
  or edited. The storage rule underneath is unchanged: `originalOf` is
  compared on submit and a field still holding the original saves as `""`, so
  the page keeps *following* the design instead of freezing a copy of it. The
  "Original: …" footnote and **Restore original** appear only once a field
  actually carries an override.
- **Pages created in the panel** live in the `custom_pages` table, not in git.
  Their HTML is generated by `blocks.page_shell()` from `public/about.html` at
  every bake, deliberately: a hand-kept shell would drift the first time a
  shared asset changed. They publish, localize, sitemap and back up like any
  built-in page; `published_file()` only hits the database for an `.html` miss,
  so asset requests stay allocation-cheap. Built-in pages cannot be deleted.
- **The default theme is the admin's, the current theme is the visitor's.**
  `brand.tokens.theme` (Website & Brand) is `auto` | `dark` | `light`, and
  `content._stamp_default_theme` bakes the two explicit choices onto `<html>`
  as `data-default-theme` — after the nav and social injection, so it lands on
  every page of both editions. `public/js/theme-init.js` reads, in order: the
  visitor's own `em-theme` in localStorage, then that attribute, then the
  device. **Never let the admin's choice win over a saved one** — it decides
  what a *first-time* visitor sees, not what a returning one already asked
  for. A page with no attribute (the shipped `public/` files before a publish,
  and the admin panel itself) takes the device, exactly as the site behaved
  before. Because it is baked rather than served, a theme change is an
  unpublished edit to every page: `media.theme_changed_at()` feeds
  `admin_pages` so the Pages screen says so, and `themeSetAt` moves only when
  the theme itself changes — saving a colour must not mark the whole site
  dirty.
- Footer social icons come from `social.*` settings (https:// only, validated
  twice — on save and again in `blocks.render_social`) and are baked in, so a
  new link reaches the site at the next **Publish site**.
- Corporate Gifts UI: catalog + product page share variant grouping via
  `EM.giftKey` (`public/js/site.js`); request lists live in localStorage
  (`em-giveaway-request`, per market, max 50 items).
  **A card is a family; the count is of products.** One product in six colours
  is one card, so counting cards said 1,127 KSA / 1,519 UAE where the admin
  panel said 1,778 / 2,573 — the same catalogue, two numbers, and the smaller
  one on the public page. `filtered()` therefore returns `{items, n}` per
  family and `countProducts` sums `n`: the number of variants that actually
  match, never `items.length`, because a family survives a filter when any one
  variant matches and filtering to Black must not count the other five. The
  headline and "Load more" both read it, so they cannot disagree. The website
  can still legitimately show fewer than the panel — `get_catalog` drops
  hidden items and, if the rule is on, zero-stock ones.
- **The catalogue detail route is `noindex,follow`, all of it.**
  `public/product.html` and `public/rental-item.html` each carry the tag, so
  the empty shell and a real `?id=…` page say the same thing, in both
  editions — `localize` never touches it. That is deliberate rather than an
  oversight: these are roughly 4,300 query-based, client-rendered addresses,
  and they become indexable only once they have permanent addresses of their
  own (`/giveaways/{slug}`, `/rental/{slug}`) with server-rendered content,
  unique metadata, a canonical and structured data. `follow`, not `none`, so
  a crawler still walks the links out of them; and never `Disallow:` them in
  robots.txt, because a page that is never fetched is a page whose noindex is
  never read. `content.SITEMAP_SKIP` keeps both out of the sitemap.
- **Public addresses carry no `.html`.** The files keep their names; the
  addresses do not. `clean_urls` in `server/main.py` is the whole mechanism:
  `/about` is rewritten in place onto `about.html`, and `/about.html`,
  `/about/` and `/index*` are answered with a **301** to the clean form. It
  fires only for a slug `content.is_public_page` recognises — a built-in page
  or a row in `custom_pages` — so `/admin`, `/api/…`, assets, downloads and
  unknown addresses pass through untouched, and because nothing unknown is
  ever rewritten a loop cannot form. It lives in the app, not in nginx, so
  development and production route identically and the production nginx
  config needs no change. Both editions work: `/ar/about`, `/ar/about.html`
  → 301, and `/ar/` stays the Arabic root. **A new public link is written
  `/services`, never `/services.html`** — in the pages, in page JS, in
  `blocks.py` templates, in `collections.page_href`, in the sitemap, in
  canonical/OG/JSON-LD and in email templates. `localize` rewrites a
  one-segment `href="/x"` into `/ar/x` with a lookahead so `#fragments`
  survive; two-segment paths (`/assets/…`, `/js/…`) are left alone.
- **The ten service detail pages are ordinary pages with a two-segment
  address.** `/services/branding` is served from `public/services-branding.html`
  — the slug stays flat because a slug with a slash in it would have to be
  handled again in `published_file`, `_SLUG_RESERVED`, the admin routes and
  every layer keyed on a page name. `content.PAGE_ADDRESS` is the single
  lookup that maps slug → address, `page_for_address` maps back, and
  `page_address` is what the sitemap, `collections.page_href` and
  `media._public_href` all read, so a menu link and a canonical tag cannot
  point at different forms of one page. Each page answers to four addresses
  and exactly one is canonical: `/services-branding`, `/services-branding.html`
  and `/services/branding.html` all 301 to `/services/branding`, so the file
  name is never separately indexable. `collections._nav_parent` maps a
  `services-*` slug onto the Services menu entry, so a service page marks
  Services as current rather than nothing. `/services` stays the overview and
  the hub; the ten pages are reached from its cards. `content.SITEMAP_SKIP`
  keeps `/product` and `/rental-item` out of the sitemap — without an id they
  are empty shells, not pages worth offering, and
  `content._sitemap_english_only` keeps the Arabic editions of the ten out of
  it as well. There is deliberately no hreflang for them either: the pages
  serve and stay reachable from the language switch, but their body is still
  English (`collection_items` has no language dimension), so listing them
  would be advertising a page in the wrong language to Google. Both come back
  the moment the service pages have real Arabic text.
- After a code change that touches `public/*.html`, the admin must press
  **Publish site** once: published snapshots in `runtime/published/site/` are
  served ahead of `public/`, so a stale bake would hide new markup/scripts.
  The Pages screen detects this and says so.
- **Site Insights is hybrid, and the split is deliberate.** First-party
  measurement (`server/analytics.py`, `public/js/insights.js`) stays cookieless:
  no raw IP or user-agent is stored and visitor keys use a salt that rotates
  daily. It owns everything that happens on our own pages — product views,
  catalogue searches, filters, add-to-request, enquiries, manual downloads,
  form errors and Web Vitals — and it is the **authoritative** record, because
  it does not depend on a Google tag being allowed to load.
  `server/ga4.py` owns the rest: audience, geography, acquisition, engagement,
  landing pages, devices and realtime, read from the GA4 Data API. Do not
  duplicate a metric across the two.
  - **Geography is GA4's, not Cloudflare's.** Nothing reads `CF-IPCountry` any
    more — the site is not going behind Cloudflare for a two-letter code. The
    `country` column and its history stay for compatibility; the dashboard does
    not read it, and a half-full local list beside a complete one from Google
    would be worse than neither.
  - **The tag is loaded once, by us.** `insights.js` injects gtag when an admin
    sets `analytics.ga4Id`, and `gtag("config", …)` sends the one automatic
    `page_view`. Never add a second snippet to a page and never push a manual
    `page_view` on top of it — there is a test that counts both.
  - **Two different Google ids.** `analytics.ga4Id` (`G-DY2NW9HPSJ`) is the
    *measurement* id and lives in the admin database. `GA4_PROPERTY_ID` is the
    numeric *property* id and is environment-only, as is
    `GOOGLE_APPLICATION_CREDENTIALS` — the path to a service-account JSON that
    lives outside the repository. The key is read by `server/ga4.py` alone and
    reaches no API response, no log and no browser; `status()` exposes the
    service-account address on purpose, because an admin has to grant it read
    access to the property.
  - **A Google failure is never a panel failure.** Every report returns
    `{"ok": False, "reason": <one safe sentence>}` rather than raising, so each
    widget shows its own state while the rest of the screen works. Technical
    detail is logged server-side at most once a minute, and Google's own
    wording never reaches an admin.
  - **Google is not called on every render.** Reports cache for
    `EM_GA4_CACHE_TTL_S` (12 min) and realtime for `EM_GA4_REALTIME_TTL_S`
    (45 s), keyed on property + report + window; concurrent callers wait on
    the first request instead of making a second. Failures are cached briefly
    too, or a broken credential means one round trip per widget per render.
    The dashboard polls realtime once a minute and stops when the tab is
    hidden or the screen is left.
  - **No invented numbers.** A percentage change against a zero previous
    period is `None` and renders as "no comparison", never +100%. Product
    views and add-to-request are both ours so the rate between them is real;
    per-product *enquiry* attribution is not shown at all, because a request
    carries a basket rather than one item.
- Transactional email goes through Resend (`server/mailer.py`). `RESEND_API_KEY`
  is environment-only — never in the admin DB, an API response or browser code.
  Sender addresses are restricted to domains in `EM_MAIL_SENDER_DOMAINS`
  (default `mail.elitemarcom.com`). Routing, on/off switches, subjects and the
  six customer templates are edited in the admin Email screen. Sending is a
  durable outbox: the request only enqueues (unique per reference+kind), and a
  startup worker drains it with backoff — never a post-response thread.
- **A picture in the Media library knows where it hangs.**
  `media.library_usage()` finds a file by looking for its own `/media/<name>`
  address inside the stores that can hold one — `collection_items`, `designs`,
  `content` and the rental inventory — rather than by a list of known fields,
  so a schema that gains an image field later is covered without anyone coming
  back. Each hit carries `href` (the live page, for "show me") and `adminHref`
  (the screen that owns it, for "let me change it"). `library_delete` refuses
  an image that is still placed: the file would go, the page would keep
  pointing at it, and a broken picture on the live site is how you would find
  out. `_usage_index` answers the same question for shipped `assets/` artwork
  by scanning the git sources; a stylesheet or script is named but carries no
  link, because there is nowhere for that link to go.
- **Every vacancy is its own record with its own address** (`server/jobs.py`,
  `job_posts` in admin.db, permission `careers.manage`). `/careers/<slug>` is
  server-rendered into `public/job.html` — the template's head between the
  `job:head` markers and its whole `<main>` are replaced per job, so a job
  page wears whatever chrome the published bake wears and a crawler reads the
  whole posting without scripts. `/job` on its own is the template and stays
  `noindex,follow`; `SITEMAP_SKIP` keeps it out of the sitemap, and
  `/sitemap.xml` is now a live route so a job published from the panel is
  offered without a site publish. Four states: draft (404), published (listed
  and served; a closing date in the past reads as closed on its own), closed
  (page answers, says "Applications closed", no form, `noindex`, no
  JobPosting), archived (404). **A slug is chosen once and kept**: renaming a
  published job does not move it, and a deliberate slug change writes the old
  one to `job_slugs` for a 301 — a shared link must not rot. `job.html`
  seeds from `server/data/jobs.json` the first time the table is empty, so the
  three shipped roles survived the migration. The long fields go through
  `jobs.sanitize_body` (p, h3/h4, lists, emphasis, safe hrefs; everything else
  reduced to text) and the JSON-LD is written with `_json_for_script`, because
  `json.dumps` leaves `</script>` alone and a title is admin input. An
  application carries its job in the clear (`records.job_id` — a key, not
  personal data) so the panel counts applications per vacancy without
  decrypting anything; `?job=` narrows the inbox to one post. `public_jobs`
  puts **featured posts first** (a stable sort, so the admin's order holds
  within each group): the badge is meant to be seen, and the same list feeds
  the careers cards and the application form's role menu, so the two cannot
  order differently. The admin's order is `sort_order`, set by
  `jobs.reorder` (`POST /api/admin/jobs/order`): drag a row by its grip or
  use Move up / Move down in its menu. A post the order omits keeps its
  place behind the named ones and an unknown id is ignored, so a stale
  screen can never lose a post. With a search or filter on, the arrows
  move past the neighbouring *visible* row but the order saved is the whole
  list's, and the admin list always shows the admin's order — the featured
  lift is public-only.
  **A job's featured image is a path, not a file.** `featuredImage` /
  `featuredImageAlt` live in the record's JSON (`poster` from before the
  rename is read as `featuredImage` and never written back); the file itself
  is a Media library upload — the editor posts to `/api/admin/media/upload`
  and the picker is the shared `mediaPicker`, so there is one image store,
  one validator (bytes sniffed, PIL-opened, re-encoded to WebP, no SVG) and
  one place a picture can be deleted from. Deleting or archiving a job never
  touches the library. The path is checked by `_safe_image_path` — `/media/`
  or `/assets/`, and no `..` segment, because the extension regex allows
  dots. **The picture is shown whole, in its own shape** — card, hero and
  admin preview alike: no aspect-ratio box, no `object-fit: cover`, only a
  height cap so a portrait scales down rather than turning a card into a
  poster, and the site's hover zoom is off on the job frame because a zoom
  is a crop. `jobs.image_dims` supplies the real `width`/`height` (the
  `media` table for an upload, the file header for shipped artwork) so the
  page reserves the right box before the file arrives; the careers feed
  carries them as `featuredImageWidth`/`featuredImageHeight` for the card.
  With no image there is no placeholder, and og:image / twitter:image /
  JobPosting.image fall back to
  `FALLBACK_IMAGE`. Changing the picture is an ordinary edit: the slug does
  not move and nothing needs a site publish.
- **Bulk import is a faster way to use the rental form, not a second one**
  (`server/rental_import.py`, permission `rentals.manage`). Every row is built
  into the dict the Add Rental Item form posts and handed to
  `content._clean_rental`, and every picture goes through
  `media.ingest_library_image` — the same choke point the panel's uploader
  uses, so a photograph is sniffed, PIL-opened, re-encoded to WebP and
  content-addressed, which also means the same file named by ten rows is
  stored once. The columns come from `COLUMNS`, which is what the template is
  generated from: add a rental field and the template gains it rather than
  going stale. Two phases, always: `/import/validate` parses, checks and
  resolves every image but **creates nothing**, staging the job in memory
  under a token that expires in 30 minutes and takes its copy of the upload
  with it; `/import/run` is the only thing that writes, and a second click on
  a staged token is refused rather than importing twice. Items are matched on
  `id` — the permanent identifier, never the name — and the default is
  **skip**, so a re-import cannot overwrite. An update applies only the cells
  that were filled in; a blank cell leaves the value alone and `[clear]` is
  the one way to empty a field. Images default to keep-existing-and-add.
  Writing happens in batches of 25 through the inventory's own atomic
  replace, so a failure late in a long import leaves the rows already written
  intact. An unknown category is an error, never invented, unless the admin
  ticks the box. Untrusted input is treated as such: a ZIP member is
  addressed by its **leaf name only** and nothing is ever extracted to disk
  (traversal is impossible rather than detected), non-image members are never
  offered to a row, expansion and entry count are capped; an image URL must
  resolve to a public address on every answer, redirects are refused rather
  than followed, and a cell's markup is stripped before the row is built —
  the public pages escape what they render, so this is about a rental card
  not reading `<b>Chair</b>`, and the preview reports every cell it changed.
  Files we write (template, error report) have formula-leading cells prefixed,
  so a downloaded report cannot execute in Excel. `/api/admin/rentals/import/
  validate` is the one admin path allowed past `MAX_BODY_BYTES`
  (`LARGE_UPLOAD_PATHS` in `server/main.py`) because it carries an archive of
  photographs; it enforces its own limits on the sheet, the archive and each
  picture. History lives in `rental_imports` (last 50) and every step is
  audited; the uploaded file itself is never kept. XLSX needs `openpyxl` —
  pinned in `requirements.txt`, so a deploy must reinstall requirements; CSV
  works without it and the template endpoint says so rather than failing
  opaquely.
- Backups (Operations) carry content, design, settings, rentals and media —
  never customer submissions, which stay encrypted with their own retention.
- Arabic publishes a full RTL edition under `/ar/` when `site.languages`
  includes `ar`; both editions are baked by the same publish action.
- Workflow: develop on `claude/markdown-file-instructions-y9jr50`, push, and
  fast-forward `main` (the user pulls from `main` to test locally).
- **Every finished task ends with a complete report in one copyable block.**
  A fenced block the user can copy whole — what changed and why, the exact
  code paths, files changed, full test results, verification actually
  performed, and the remaining limitations stated plainly. Not a summary in
  prose beside it: the block is the deliverable.
