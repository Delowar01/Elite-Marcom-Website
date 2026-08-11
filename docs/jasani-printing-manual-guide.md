# Elite Marcom - Jasani Printing Manual Integration Guide

**Document status:** Implementation-ready guide  
**Revision:** Dynamic positioning, Branding Prices API enrichment, customer suggestions and validated manual IDs included  
**Verified sample product:** Jasani KSA Product Template `29453`  
**Sample item:** `ITGL 1291` - NAPIER - MagCase Phone Cardholder - Grey  
**Related sample file:** `Elite-Marcom-Printing-Manual-Sample.pdf`

---

## 1. Objective

Implement printing manuals for Jasani-supplied products without sending customers to a Jasani website or exposing Jasani API credentials.

The finished feature must allow customers to:

- View the available branding areas.
- View the printing methods available for each area.
- Select or suggest a preferred branding area.
- Select or suggest a preferred printing method.
- Add comments and optionally upload artwork.
- Download an Elite Marcom-branded PDF.
- Submit the preference with a quotation or product enquiry.

Customer selections are requests only. Final branding placement and printing method remain subject to artwork review, material compatibility, technical feasibility and production approval.

---

## 2. Verified Jasani Behavior

The following URL format was tested with product template `29453`:

```text
https://www.giftsksa.com/preview_product?product_id=29453
```

It returns a one-page A4 PDF directly. It is not a normal HTML product page.

The returned PDF contains:

- Product name and item code.
- Available branding areas.
- Product images with branding-area rectangles.
- Printing methods for each area.
- Maximum branding width and height.

The Product API does not provide a dedicated `printing_manual_url` field. The manual URL can be constructed from the Product Template ID contained in `parent_id`.

The Product API fields `image_url` and `images` are normal product-gallery images. They are not the source of truth for printing-area positioning.

The Branding API field `web_image` is the image intended for a specific branding-area view. The associated `left`, `top`, `width` and `height` values belong to that image and that product. A power bank, pen, bottle, notebook or bag can therefore return completely different images, aspect ratios, positions, sizes and printing methods.

Never copy printing coordinates from one product to another, even when both products belong to the same category or look similar.

Jasani also provides a separate Branding API that exposes the underlying branding-area information. Refer to the [official Jasani API documentation](https://www.jasani.ae/apis).

---

## 3. Correct Product Identifier Mapping

The IDs must not be mixed.

| Purpose | Field to use |
|---|---|
| Product, price and stock matching | `id` and/or `default_code` |
| Jasani Branding API request | Product variant `id` |
| Existing Jasani printing-manual PDF | Validated manual template ID, often sourced from `parent_id` |
| Displayed item code | `default_code` |

Example:

```json
{
  "id": 24246,
  "parent_id": 29453,
  "default_code": "ITGL 1291"
}
```

For this example:

- Branding API uses `24246`.
- Existing PDF endpoint uses the validated template ID `29453` for this tested product.
- Customer-facing item code is `ITGL 1291`.

Store the variant ID and template ID separately in the Elite Marcom database.

Jasani's documentation says `parent_id` is primarily for grouping configurable products and may be meaningless for non-configurable products. Therefore, do not assume every `parent_id` produces a valid manual.

Use this rule:

1. Treat `parent_id` as a candidate manual template ID.
2. Request the PDF server-side.
3. Verify a successful response, valid PDF signature, non-empty PDF and expected product context where practical.
4. Save it separately as `supplier_manual_template_id` only after validation.
5. If validation fails, generate the manual from the Branding API instead.

The sample product `29453` was tested successfully, but that result must not be generalized to every product.

### Non-negotiable dynamic-positioning rule

There is no universal printing position for all products.

- Fetch branding data for the current product variant `id`.
- Keep every area tied to its own returned `web_image`.
- Render the rectangle using that area's own coordinates.
- Render every returned area separately when a product has multiple areas.
- Never hard-code coordinates by category, brand, product shape or SKU pattern.
- Never use another color variant's coordinates unless Jasani explicitly returns the same branding record for that variant.
- If valid area data is unavailable, show `Request Branding Advice`; do not guess a position.

---

## 4. Market Mapping

Use a strict server-controlled market mapping.

| Market | Jasani host |
|---|---|
| Saudi Arabia | `https://www.giftsksa.com` |
| UAE | `https://www.jasani.ae` |

Never accept an arbitrary upstream hostname or complete URL from the browser. The product's saved market must determine the approved host.

---

## 5. Recommended Solution

Use a combined two-level solution.

### Level 1 - Server-side PDF proxy

Use the existing Jasani-generated PDF but fetch it through the Elite Marcom backend. The customer downloads it from an Elite Marcom URL and is never redirected to Jasani.

Advantages:

- Fastest implementation.
- Uses Jasani's current branding areas and methods.
- Does not expose the supplier URL in the customer interface.
- Does not require PDF recreation for every product.

### Level 2 - Elite Marcom custom manual

Use the Jasani Branding API to generate an Elite Marcom-branded manual containing the approved areas plus the customer's preference.

Advantages:

- Complete Elite Marcom visual identity.
- Customer preference can be recorded in the PDF.
- Customer comments and artwork references can be included.
- PDF can be attached automatically to an enquiry or quotation request.

### Level 3 - Printing-method enrichment

Join each method from the Branding API with the Branding Prices API. This adds:

- Supported color choices.
- Estimated branding lead time.
- Currency.
- Quantity-based price tiers for internal costing.

Public product pricing remains disabled unless Elite Marcom explicitly approves it. Branding prices should initially be used for internal quotation support only.

### Recommended rollout

1. Implement the secure PDF proxy first.
2. Add the customer preference modal and data storage.
3. Enrich approved printing methods with Branding Prices API data.
4. Generate the Elite Marcom custom PDF from the selected preference.
5. Keep the proxied Jasani PDF as a fallback.

---

## 6. Customer Experience

On an eligible product page, show:

```text
View Printing Options
```

When clicked, open an Elite Marcom modal or internal page. Do not open Jasani in a new tab and do not use an iframe.

The modal should contain:

1. Product image, name, item code and color.
2. Available branding-area cards.
3. Maximum branding dimensions for each area.
4. Available printing methods for each area.
5. Available color choices for the selected method.
6. Estimated branding lead time, when supplied.
7. Customer preference controls.
8. Optional artwork upload.
9. Notes field.
10. Download Manual button.
11. Add Preference to Request button.

Recommended actions:

- **Download Standard Manual** - downloads the generic manual.
- **Save My Branding Preference** - saves the customer selection.
- **Download My Preference PDF** - generates a customer-specific PDF.
- **Add to Request** - attaches the preference to the product enquiry.

---

## 7. Customer Preference Fields

### Preferred branding area

- Front Top
- Front Bottom
- Other area - customer describes the requested position
- Let Elite Marcom recommend the best area

Only show area names actually available for the selected product. `Other area` must be treated as a suggestion requiring review.

### Suggested-area drawing tool

When the customer selects `Other area`, provide a controlled draw-on-image tool:

1. Show the current product's available Branding API view images.
2. Let the customer choose the view that best shows the requested position.
3. Let the customer drag to draw one rectangular suggested area.
4. Allow the rectangle to be moved, resized, cleared or redrawn.
5. Store the rectangle as normalized ratios from `0` to `1`, not displayed pixels.
6. Store the selected source-view key or image hash with the rectangle.
7. Ask for the desired physical width and height in millimetres separately.
8. Display the rectangle in violet and label it `Customer Suggested Area - Pending Technical Review`.

The rectangle drawn by the customer is indicative only. Its on-screen size must not be treated as a verified physical printing size.

### Preferred printing method

- Laser engraving
- Silk screen printing
- Digital UV printing
- Other method - customer describes the request
- Let Elite Marcom recommend the best method

Only show methods supported by the selected branding area. A customer must not be able to select a method unavailable for that area unless using `Other method`.

Standard method choices must come from the selected area's Branding API `pricing_products` array. Each method record includes the method `product_id`, `name` and `default_code`.

When available, enrich the method by matching:

```text
Branding API pricing_products[].default_code
        -> Branding Prices API internal_reference
```

The matched record can provide allowed color choices and estimated lead time. Keep pricing internal unless public pricing is explicitly enabled.

For a customer-suggested area, list the method as a preference only. Do not imply that a method is compatible with the suggested position until reviewed by Elite Marcom.

### Additional fields

- Branding width and height requested by the customer.
- Number of print colors, when relevant.
- Estimated lead time acknowledgement, when available.
- Customer comments.
- Artwork or logo upload.
- Required quantity.
- Required delivery date.
- Reference or campaign name.

Quantity and product material may affect the final method, price and feasibility.

---

## 8. Required Customer Disclaimer

Add the following text below the preference fields and inside customer-specific PDFs:

> **Customer Branding Preference**  
> Customers may select their preferred branding area and printing method from the available options shown. Alternative placement or printing requests may also be suggested. All selections are subject to artwork review, product compatibility, technical feasibility, branding dimensions, quantity and final production approval by Elite Marcom.

Add this confirmation checkbox before submission:

```text
[ ] I understand that my selection is a preference and requires final technical approval.
```

Do not describe a customer suggestion as approved until it has been reviewed.

---

## 9. Website Form vs Editable PDF

The recommended approach is to collect customer preferences on the website and then generate a PDF containing the saved selection.

This is better than relying on editable PDF fields because:

- PDF form support varies between browsers and mobile devices.
- A completed PDF does not automatically update the Elite Marcom website.
- Customers may download the PDF but forget to send it back.
- Website validation can prevent invalid area and method combinations.
- Artwork and the product request can remain connected in one workflow.

An editable AcroForm PDF can be offered as an additional offline option, but it should not be the primary submission method.

---

## 10. Internal Elite Marcom Endpoints

Recommended internal routes:

```text
GET  /api/products/{localProductId}/printing-manual.pdf
GET  /api/products/{localProductId}/branding-options
POST /api/products/{localProductId}/branding-preference
POST /api/internal/branding-estimates
GET  /api/branding-preferences/{preferenceId}/manual.pdf
```

### `printing-manual.pdf`

- Loads the product from the Elite Marcom database.
- Reads its market and supplier `parent_id`.
- Fetches the supplier PDF server-side.
- Validates that the response is a genuine PDF.
- Returns it from the Elite Marcom domain.

### `branding-options`

- Loads the supplier variant `id`.
- Calls the Jasani Branding API server-side.
- Matches applicable methods to cached Branding Prices API records.
- Normalizes the returned areas and methods.
- Returns area, method, color-choice and lead-time fields required by the Elite Marcom interface.
- Does not return internal price values to public customers unless explicitly enabled.

### `branding-preference`

- Validates the chosen area and method.
- Stores customer comments and artwork references.
- Connects the preference to the product and request.
- Marks alternative suggestions as requiring review.

### Internal `branding-estimates`

- Requires authorized staff access.
- Accepts product, approved area, method, color count and quantity.
- Validates the method against the selected area's `pricing_products`.
- Selects the correct documented quantity tier.
- Returns an internal estimate only after the price-table semantics are confirmed with Jasani.
- Must not expose supplier cost data through a public response.

### Customer-specific `manual.pdf`

- Loads the saved preference.
- Loads a snapshot of the product and branding data.
- Generates an Elite Marcom-branded PDF.
- Returns it as a download.

---

## 11. Server-side PDF Proxy

The browser must request only an Elite Marcom route:

```text
https://elitemarcom.com/api/products/{localProductId}/printing-manual.pdf
```

The server performs the supplier request internally:

```text
KSA: https://www.giftsksa.com/preview_product?product_id={validated_manual_template_id}
UAE: https://www.jasani.ae/preview_product?product_id={validated_manual_template_id}
```

The route must use a previously validated `supplier_manual_template_id`. A raw `parent_id` may be tested as a candidate, but it must not be trusted permanently until a genuine manual PDF has been confirmed for that product.

### Next.js reference skeleton

Adapt the database lookup to the website's existing repository layer.

```ts
import { NextRequest } from "next/server";

const MANUAL_HOSTS = {
  ksa: "https://www.giftsksa.com",
  uae: "https://www.jasani.ae",
} as const;

type Market = keyof typeof MANUAL_HOSTS;

function safeFilename(value: string) {
  return value.replace(/[^a-zA-Z0-9_-]+/g, "-").replace(/^-+|-+$/g, "");
}

function hasPdfSignature(bytes: Uint8Array) {
  return bytes.length >= 5 &&
    bytes[0] === 0x25 &&
    bytes[1] === 0x50 &&
    bytes[2] === 0x44 &&
    bytes[3] === 0x46 &&
    bytes[4] === 0x2d;
}

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ productId: string }> },
) {
  const { productId } = await context.params;

  // Replace this with the existing database/repository query.
  const product = await loadProductManualSource(productId);

  if (!product) {
    return Response.json({ error: "Product not found" }, { status: 404 });
  }

  const market = product.sourceMarket as Market;
  const host = MANUAL_HOSTS[market];
  const manualTemplateId = Number(product.supplierManualTemplateId);

  if (
    !host ||
    !Number.isSafeInteger(manualTemplateId) ||
    manualTemplateId <= 0
  ) {
    return Response.json({ error: "Printing manual is unavailable" }, { status: 404 });
  }

  const upstream = new URL("/preview_product", host);
  upstream.searchParams.set("product_id", String(manualTemplateId));

  const upstreamResponse = await fetch(upstream, {
    redirect: "error",
    signal: AbortSignal.timeout(10_000),
    next: { revalidate: 86_400 },
  });

  if (!upstreamResponse.ok) {
    return Response.json({ error: "Printing manual is temporarily unavailable" }, { status: 502 });
  }

  const buffer = await upstreamResponse.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const maximumBytes = 10 * 1024 * 1024;

  if (bytes.byteLength > maximumBytes || !hasPdfSignature(bytes)) {
    return Response.json({ error: "Invalid printing manual response" }, { status: 502 });
  }

  const filename = `${safeFilename(product.defaultCode || "product")}-printing-manual.pdf`;

  return new Response(buffer, {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
      "X-Content-Type-Options": "nosniff",
    },
  });
}
```

The customer never receives the upstream Jasani URL.

When validating a candidate `parent_id` for the first time, additionally confirm that the PDF opens successfully, contains at least one page and corresponds to the intended product where practical. Save the validation timestamp. If the candidate fails, leave `supplier_manual_template_id` empty and use the custom Branding API manual.

---

## 12. Branding API Integration

Use the Jasani Branding API only from the server:

```text
KSA: https://www.giftsksa.com/branding/{token}/{product.id}
UAE: https://www.jasani.ae/branding/{token}/{product.id}
```

The API token must be stored in a server-only environment variable:

```env
JASANI_API_TOKEN=server-only-value
```

Never include the token in:

- Client-side JavaScript.
- HTML.
- Browser network responses.
- Analytics events.
- Error messages.
- Application logs.

The official Jasani documentation lists these Branding API fields:

- `name`
- `width`
- `height`
- `top`
- `left`
- `area_width`
- `area_height`
- `web_image`
- `pricing_products`

Jasani states that Branding API calls do not count toward the normal daily GET-request limit.

`pricing_products` identifies the printing methods that can be applied to that exact branding area. Each method entry contains:

- `product_id`
- `name`
- `default_code`

It does not contain branding prices. Prices, allowed color choices and lead times come from the separate Branding Prices API.

Each returned branding-area record must remain connected to its own `web_image`. Do not replace it with the Product API `image_url` merely because the product image looks similar. The rectangle coordinates were measured against the branding record's image.

Different areas of the same product may use different images or views. For example, a power bank can have front, rear and side views, while a pen can have barrel and clip-side views. Render each record independently.

Normalize the supplier response before returning it to the browser. Decode the image server-side, determine its natural pixel dimensions and create a stable internal view key or content hash.

Recommended normalized structure:

```ts
type BrandingArea = {
  key: string;
  name: string;
  image: {
    url: string;
    viewKey: string;
    naturalWidth: number;
    naturalHeight: number;
  };
  rectangle: {
    left: number;
    top: number;
    width: number;
    height: number;
  };
  physicalSizeMm: {
    width: number;
    height: number;
  };
  methods: Array<{
    id: number | string;
    code: string;
    name: string;
  }>;
};
```

If `web_image` is returned as base64, decode and store/cache it server-side or return a controlled Elite Marcom asset URL. Detect the real image MIME type from its bytes rather than assuming PNG or JPEG. Avoid repeatedly sending very large base64 strings.

If several areas use byte-identical images, the stored image asset may be deduplicated by hash, but every area must still retain its own rectangle, dimensions and method list.

Jasani's written documentation and live Product API response differ in format, so inspect `Content-Type` and validate the actual Branding API payload before finalizing the parser. Do not assume XML or JSON without checking the response.

---

## 13. Branding Prices API Integration

Use the Branding Prices API only from the server:

```text
KSA: https://www.giftsksa.com/brandingprices/all/{token}
UAE: https://www.jasani.ae/brandingprices/all/{token}
```

Jasani states that Branding Prices API calls do not count toward the normal daily GET-request limit. Cache the complete feed anyway to reduce latency and unnecessary supplier traffic.

### Returned fields

- `name` - branding or printing method name.
- `internal_reference` - identifier used to match the method to the Branding API.
- `color_choice` - supported number of colors or full-color choices.
- `lead_time` - estimated branding production time.
- `currency` - currency used by the price table.
- `price_table` - quantity-based branding price tiers.

### Method matching

For each method returned inside a branding area's `pricing_products`, normally match:

```text
pricing_products[].default_code
        =
brandingPrices[].internal_reference
```

Example server-side join:

```ts
function enrichMethod(
  method: {
    product_id: number;
    name: string;
    default_code: string;
  },
  prices: BrandingMethodPrice[],
) {
  const pricing = prices.find(
    (item) => item.internalReference === method.default_code,
  );

  return {
    id: method.product_id,
    code: method.default_code,
    name: method.name,
    colorChoices: pricing?.colorChoices ?? [],
    leadTime: pricing?.leadTime ?? null,
    currency: pricing?.currency ?? null,
    priceTiers: pricing?.priceTiers ?? [],
    pricingAvailable: Boolean(pricing),
  };
}
```

Use exact, case-sensitive normalized references after trimming documented whitespace. Do not match solely by the human-readable method name.

If the method has no matching price record:

- Continue showing it as an available printing method.
- Do not invent a lead time or price.
- Mark internal pricing as unavailable.
- Allow Elite Marcom staff to review it manually.

### Color-choice handling

The `color_choice` field is especially important for screen printing because cost can increase with the number of artwork colors.

Rules:

- Show only the color choices returned for the matched method.
- Require a color selection when the method needs it.
- Treat `Full Color` as a supplier-defined option, not a numeric color count.
- For methods where color count does not affect pricing, do not multiply the cost.
- Do not implement a universal multiplication formula until Jasani confirms the exact `price_table` structure and screen-printing calculation.

### Lead-time handling

Display the returned `lead_time` as an estimate:

```text
Estimated branding lead time: {lead_time}
```

Do not present it as a guaranteed delivery date. Final timing can depend on artwork approval, product stock, quantity, production capacity and delivery location.

### Quantity tiers

The documented branding-price quantities are:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 125,
150, 175, 200, 250, 300, 400, 500, 1000, 1500, 2000
```

For a quantity between documented tiers, Jasani instructs using the immediately lower tier. For example, use the 35-unit tier to estimate 36 units.

```ts
function selectBrandingTier(quantity: number, tiers: number[]) {
  if (!Number.isSafeInteger(quantity) || quantity < 1) {
    throw new Error("Quantity must be a positive whole number");
  }

  const eligible = tiers
    .filter((tier) => tier <= quantity)
    .sort((a, b) => b - a);

  return eligible[0] ?? null;
}
```

Quantities above the largest documented tier require manual confirmation.

### Price semantics requiring Jasani confirmation

Before calculating or displaying money, obtain written confirmation of:

- Whether each `price_table` value is per unit or a total charge.
- Whether setup, plate, digitizing or minimum charges are included.
- Whether values exclude VAT.
- The exact formula for multiple screen-print colors.
- Whether KSA and UAE price-table structures are identical.
- How rounding should be handled.

Until confirmed, price values may be stored for inspection but must not be shown as a final customer quote.

### Recommended normalized structure

```ts
type BrandingMethodPrice = {
  name: string;
  internalReference: string;
  colorChoices: Array<number | "Full Color" | string>;
  leadTime: string | null;
  currency: string;
  priceTiers: Array<{
    quantity: number;
    value: number;
  }>;
  fetchedAt: string;
};
```

Normalize the actual live response shape only after inspecting it. The PDF documents the fields but not the complete nested `price_table` object structure.

### Price visibility

For the current Elite Marcom Giveaways experience:

- Keep supplier product and branding costs server-side.
- Use them for internal quotation preparation and margin analysis.
- Do not expose them through public API responses, page source or PDFs.
- Do not show public pricing unless Elite Marcom explicitly changes the current no-price policy.

### Order API boundary

The documented Order API accepts physical product IDs and quantities, but it does not document how branding methods, artwork, area selection or customer printing preferences should be submitted.

Therefore:

- Do not send Branding API `pricing_products.product_id` values as Order API product lines without Jasani confirmation.
- Keep the approved area, method, colors, artwork and notes attached to the Elite Marcom request.
- Request Jasani's official process for transferring approved branding instructions into an API order.
- Do not automate branded order submission until that process is documented and tested.

---

## 14. Dynamic Product-specific Printing-area Positioning

### Why one fixed position is impossible

Every product has a different shape, orientation and printable surface. Even two power banks or two pens can have different printing positions. Therefore:

- A power bank's rectangle must come from that power bank's Branding API response.
- A pen's rectangle must come from that pen's Branding API response.
- A notebook, bottle, bag or garment must use its own response.
- Multiple areas on one product must each use their own image and coordinates.
- Product category must never determine the rectangle.

The source of truth is the current product variant's Branding API data.

### Coordinate relationship

For each approved branding area:

```text
web_image + left + top + width + height = one complete positioned area
```

The fields cannot be separated or reused with a different image.

- `left` is the horizontal distance from the image's left edge.
- `top` is the vertical distance from the image's top edge.
- `width` is the rectangle width in source-image pixels.
- `height` is the rectangle height in source-image pixels.
- `area_width` and `area_height` are the physical branding dimensions in millimetres.

The pixel rectangle controls visual placement. The millimetre values control the documented physical printing size. Do not attempt to calculate physical millimetres from the displayed browser image.

### Recommended browser rendering: SVG overlay

Use the area's natural image dimensions as the SVG coordinate system. SVG uses a top-left origin like the supplier coordinates, so the API rectangle can be rendered directly.

```tsx
function ApprovedBrandingArea({ area }: { area: BrandingArea }) {
  const { naturalWidth, naturalHeight } = area.image;

  return (
    <div
      className="branding-canvas"
      style={{ aspectRatio: `${naturalWidth} / ${naturalHeight}` }}
    >
      <img
        src={area.image.url}
        alt={`${area.name} branding view`}
        draggable={false}
      />

      <svg
        viewBox={`0 0 ${naturalWidth} ${naturalHeight}`}
        aria-label={`${area.name} approved branding area`}
      >
        <rect
          x={area.rectangle.left}
          y={area.rectangle.top}
          width={area.rectangle.width}
          height={area.rectangle.height}
          className="approved-area"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </div>
  );
}
```

```css
.branding-canvas {
  position: relative;
  width: min(100%, 640px);
  overflow: hidden;
}

.branding-canvas img,
.branding-canvas svg {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
}

.branding-canvas img {
  object-fit: contain;
}

.branding-canvas svg {
  pointer-events: none;
}

.approved-area {
  fill: rgb(240 111 34 / 10%);
  stroke: #f06f22;
  stroke-width: 2;
  stroke-dasharray: 7 5;
}
```

The container aspect ratio must exactly match the natural image ratio. Do not stretch the image independently from the SVG.

### Percentage-based alternative

If the UI uses an HTML rectangle instead of SVG, convert the source pixels to percentages:

```ts
const approvedOverlay = {
  leftRatio: area.rectangle.left / area.image.naturalWidth,
  topRatio: area.rectangle.top / area.image.naturalHeight,
  widthRatio: area.rectangle.width / area.image.naturalWidth,
  heightRatio: area.rectangle.height / area.image.naturalHeight,
};
```

Render them as percentages:

```ts
const style = {
  left: `${approvedOverlay.leftRatio * 100}%`,
  top: `${approvedOverlay.topRatio * 100}%`,
  width: `${approvedOverlay.widthRatio * 100}%`,
  height: `${approvedOverlay.heightRatio * 100}%`,
};
```

Do not calculate against a card containing padding or letterboxing. The overlay container must match the rendered image bounds exactly.

### Customer drag-to-suggest positioning

Approved supplier areas and customer-suggested areas are different data types.

When a customer selects `Suggest Another Area`:

1. Let the customer select one of the current product's known view images.
2. Enable pointer drag on that image.
3. Convert the pointer start and end positions into normalized ratios.
4. Clamp the result within the image bounds.
5. Store the selected view key with the rectangle.
6. Require desired width and height in millimetres as separate fields.
7. Show the suggested rectangle in violet.
8. Mark it `Pending Technical Review`.

Example normalization:

```ts
function toImageRatios(
  startX: number,
  startY: number,
  endX: number,
  endY: number,
  bounds: DOMRect,
) {
  const clamp = (value: number) => Math.max(0, Math.min(1, value));

  const x1 = clamp((startX - bounds.left) / bounds.width);
  const y1 = clamp((startY - bounds.top) / bounds.height);
  const x2 = clamp((endX - bounds.left) / bounds.width);
  const y2 = clamp((endY - bounds.top) / bounds.height);

  return {
    xRatio: Math.min(x1, x2),
    yRatio: Math.min(y1, y2),
    widthRatio: Math.abs(x2 - x1),
    heightRatio: Math.abs(y2 - y1),
  };
}
```

Recommended customer-suggestion structure:

```ts
type CustomerAreaSuggestion = {
  sourceViewKey: string;
  xRatio: number;
  yRatio: number;
  widthRatio: number;
  heightRatio: number;
  requestedWidthMm: number | null;
  requestedHeightMm: number | null;
  preferredMethodId: string | null;
  preferredMethodName: string | null;
  comments: string | null;
  status: "pending_technical_review";
};
```

Suggested-area style:

```css
.customer-suggested-area {
  fill: rgb(118 86 214 / 12%);
  stroke: #7656d6;
  stroke-width: 2;
  stroke-dasharray: 10 6;
}
```

Never save customer suggestions as pixels from the current screen. A mobile and desktop image have different displayed dimensions. Normalized ratios keep the rectangle attached to the same position.

### PDF positioning for approved areas

Browser images use a top-left origin. Most PDF libraries use a bottom-left origin. The Y coordinate must therefore be converted.

First calculate the image size and centering offsets inside the PDF image box:

```ts
const scale = Math.min(
  pdfImageBoxWidth / naturalImageWidth,
  pdfImageBoxHeight / naturalImageHeight,
);

const renderedImageWidth = naturalImageWidth * scale;
const renderedImageHeight = naturalImageHeight * scale;

const imageX = pdfImageBoxX +
  (pdfImageBoxWidth - renderedImageWidth) / 2;

const imageY = pdfImageBoxY +
  (pdfImageBoxHeight - renderedImageHeight) / 2;
```

Then convert the supplier rectangle:

```ts
const rectangleX = imageX + area.rectangle.left * scale;

const rectangleY = imageY + renderedImageHeight -
  (area.rectangle.top + area.rectangle.height) * scale;

const rectangleWidth = area.rectangle.width * scale;
const rectangleHeight = area.rectangle.height * scale;
```

The `rectangleY` conversion is essential. Omitting it will place the rectangle vertically in the wrong location.

### PDF positioning for customer suggestions

Convert normalized ratios against the rendered image only:

```ts
const suggestionX = imageX +
  suggestion.xRatio * renderedImageWidth;

const suggestionY = imageY + renderedImageHeight -
  (suggestion.yRatio + suggestion.heightRatio) * renderedImageHeight;

const suggestionWidth =
  suggestion.widthRatio * renderedImageWidth;

const suggestionHeight =
  suggestion.heightRatio * renderedImageHeight;
```

Do not calculate against the entire PDF card when the image is centered inside it. Always include the image centering offsets.

### Visual distinction

Use a permanent legend in the UI and customer-specific PDF:

```text
Orange dashed rectangle  = Jasani-provided approved branding area
Violet dashed rectangle  = Customer-suggested area, pending review
```

Never render a customer suggestion with the same styling or status as an approved area.

### Positioning fallback

If the custom Branding API response is missing, malformed or does not match the decoded `web_image` bounds:

- Do not guess or reuse another product's position.
- Use the cached last-known-good record when available.
- Otherwise offer the proxied supplier PDF.
- If neither is available, show `Request Branding Advice`.

---

## 15. Data Storage

The exact table names should follow the existing website schema. The following fields are required conceptually.

### Product supplier mapping

```text
local_product_id
source_market
supplier_variant_id       -> Jasani id
supplier_template_id      -> raw Jasani parent_id candidate
supplier_manual_template_id
manual_template_validated_at
supplier_default_code
```

Keep `supplier_manual_template_id` nullable until the candidate PDF has passed validation.

### Approved branding-area cache or snapshot

```text
local_product_id
supplier_variant_id
area_key
area_name
source_view_key
source_image_url or private_asset_id
source_image_hash
source_image_natural_width
source_image_natural_height
rectangle_left_px
rectangle_top_px
rectangle_width_px
rectangle_height_px
physical_width_mm
physical_height_mm
available_methods_json
supplier_payload_version or fetched_at
```

Coordinates and image metadata must be stored together. A rectangle without its original source view is incomplete and must not be rendered.

### Branding-method price cache

```text
internal_reference
method_name
color_choices_json
lead_time
currency
price_tiers_json
fetched_at
source_market
```

Keep this cache server-side. Public product responses should contain only approved customer-facing fields such as method name, allowed color choices and estimated lead time.

### Branding preference

```text
id
request_id
local_product_id
customer_id or guest_session_id
preferred_area_key
preferred_area_name
preferred_method_id
preferred_method_name
preferred_method_code
selected_color_choice
estimated_lead_time_snapshot
custom_area_note
custom_method_note
suggested_source_view_key
suggested_x_ratio
suggested_y_ratio
suggested_width_ratio
suggested_height_ratio
requested_width_mm
requested_height_mm
requested_color_count
selected_price_tier_quantity
internal_branding_price_snapshot
internal_branding_currency
quantity
required_date
customer_comments
artwork_file_ids
status
created_at
updated_at
```

Recommended statuses:

```text
submitted
under_review
approved
needs_changes
rejected
```

Store a snapshot of the area name, method name, source view, coordinates, dimensions, selected colors and estimated lead time used when the customer submitted the request. Supplier data may change later.

Internal price snapshots must be access-controlled and must not be included in public customer responses unless public pricing is explicitly enabled.

For approved-area selections, store the approved area key and supplier snapshot. For alternative placements, store normalized customer-suggestion ratios and keep the status pending until reviewed.

---

## 16. Validation Rules

The server must validate all customer selections.

1. The product must exist and be active.
2. The selected branding area must belong to that product.
3. The selected standard method must belong to the selected area.
4. `Other area` and `Other method` require explanatory notes.
5. Requested dimensions must be positive numbers.
6. Requested dimensions larger than the documented area must be flagged for review.
7. Quantity must be a positive whole number.
8. Uploaded artwork must pass the website's file security rules.
9. The acknowledgement checkbox must be accepted.
10. Customer-supplied text must never be rendered into HTML or PDF without escaping.
11. The approved area's source view must belong to the current product variant.
12. Supplier pixel coordinates must fit within the natural `web_image` bounds.
13. Customer suggestion ratios must each be finite values between `0` and `1`.
14. `xRatio + widthRatio` and `yRatio + heightRatio` must not exceed `1`.
15. Customer rectangles smaller than the configured usable minimum must be rejected.
16. A customer suggestion must retain the selected source-view key.
17. Coordinates from another product, category, variant or source image must be rejected.
18. A suggested visual rectangle must never be converted into physical millimetres automatically.
19. A standard printing method must exist in the selected area's current `pricing_products` list.
20. A selected color choice must be allowed by the matched Branding Prices API record.
21. Quantity-tier selection must use a positive whole-number quantity and the documented lower-tier rule.
22. Quantities above 2,000 must be sent for manual review unless Jasani supplies additional tiers.
23. Missing price data must never be replaced with zero or an invented value.
24. Lead time must be labelled estimated and must not be treated as a guaranteed delivery date.
25. Internal supplier prices must not be returned to an unauthorized or public client.
26. A raw `parent_id` must not be persisted as a validated manual ID until the returned PDF passes validation.

Do not trust area names, method names, dimensions or product IDs submitted by the browser.

Revalidate the saved area and method server-side at submission time. Client-side validation is for user experience only.

---

## 17. Artwork Upload Rules

Recommended accepted formats:

- PDF
- AI or EPS, only if the existing upload-security pipeline supports them safely
- SVG, only if sanitized and already approved by the website security policy
- PNG
- JPG or JPEG

Recommended controls:

- Maximum file size per file.
- Maximum number of files.
- MIME and file-signature validation.
- Malware scanning where available.
- Private storage by default.
- Signed, expiring download links for staff review.
- No executable files.
- Do not serve user uploads from the main application origin without safe content headers.

Follow the website's existing secure-upload policy if it is stricter.

---

## 18. Elite Marcom PDF Specification

Use the approved sample as the visual baseline.

### Generic manual

Include:

- Elite Marcom logo.
- `Printing Manual` title.
- Product name, item code, image, color and dimensions.
- One card per available branding area.
- The area-specific Branding API `web_image`, not a generic gallery image.
- Area image with its correctly positioned approved rectangle.
- Maximum area size in millimetres.
- Available printing methods.
- Supported color choices for each matched method, when relevant.
- Estimated branding lead time, when supplied.
- Technical disclaimer.
- Elite Marcom contact/footer information.

### Customer-specific manual

Include everything in the generic manual plus:

- Request reference.
- Customer or company name, if appropriate.
- Selected branding area.
- Selected printing method.
- Selected print-color option.
- Estimated branding lead-time snapshot.
- Requested branding size.
- Requested print colors.
- Customer-suggested rectangle when an alternative position was drawn.
- The exact source view on which the customer made the suggestion.
- Customer comments.
- Artwork filename or reference.
- Preference status: `Pending Technical Review` until approved.
- Generated date and document version.

### Suggested preference section

```text
CUSTOMER BRANDING PREFERENCE

Preferred area: Front Top
Preferred method: Digital (UV) Print
Selected color option: Full Color
Requested size: 40 x 28 mm
Estimated branding lead time: {lead_time}
Comments: Center the logo horizontally and match the supplied brand orange.
Status: Pending Technical Review
```

### Rectangle legend

Use these styles consistently:

- Elite orange dashed rectangle: supplier-provided approved branding area.
- Elite violet dashed rectangle: customer-suggested area pending technical review.
- Approved status may be shown only after staff review.

For a customer suggestion, show both the relevant approved area, when available, and the suggested area without combining their coordinates.

### PDF rules

- Use A4 landscape or portrait consistently.
- Keep product images sharp.
- Keep branding rectangles visible when printed.
- Calculate every rectangle from its own product and source image.
- Apply the PDF Y-axis conversion and image-centering offsets.
- Never reuse the sample product's coordinates for another product.
- Do not include Jasani logos, links, tokens or internal IDs.
- Do not include price unless Elite Marcom explicitly enables it.
- Do not include supplier cost, margin or raw price-table data under the current no-price policy.
- Label `lead_time` as estimated rather than guaranteed.
- Use a safe filename such as `ITGL-1291-printing-manual.pdf`.
- Customer-specific PDFs must not be publicly cached.

---

## 19. PDF Generation

For a Node.js or Next.js website, suitable PDF-generation approaches include:

- `pdf-lib`
- `@react-pdf/renderer`
- A controlled server-side HTML-to-PDF renderer already approved for the deployment platform

Recommended flow:

1. Load the product record.
2. Load cached normalized branding data.
3. Load the saved preference when generating a customer-specific PDF.
4. Match the selected method to cached Branding Prices API data.
5. Load the selected color choice and estimated lead-time snapshot.
6. Load each area's own source image and natural dimensions.
7. Fit each image proportionally into its PDF image box.
8. Calculate image-centering offsets.
9. Convert approved supplier coordinates from top-left image coordinates to bottom-left PDF coordinates.
10. Convert any customer-suggested normalized rectangle against the same rendered source image.
11. Render approved areas in orange and customer suggestions in violet.
12. Render approved branding dimensions, methods, color choices and estimated lead time.
13. Render customer preference, status and disclaimer.
14. Exclude internal supplier prices unless public pricing is explicitly enabled.
15. Generate the PDF server-side.
16. Store the PDF privately if it must be attached to an enquiry.
17. Stream the PDF using `Content-Type: application/pdf`.
18. Use `Content-Disposition: attachment` for downloads.

Generic manuals can be cached. Customer-specific manuals must use private storage and `Cache-Control: private, no-store` unless the current security design provides an equivalent safe policy.

---

## 20. Caching Strategy

Do not download every printing manual during every product sync.

Recommended approach:

- Fetch manuals and branding data on demand.
- Cache generic supplier PDFs for approximately 24 hours.
- Cache normalized Branding API data for approximately 24 hours.
- Cache the complete Branding Prices API feed per market for approximately 24 hours.
- Keep a last-known-good copy for temporary supplier outages.
- Revalidate popular products in the background if needed.
- Invalidate the cache when a product's supplier IDs change.
- Revalidate a saved manual template ID if the supplier PDF starts returning an error or an invalid file.

The public `preview_product` PDF route is not documented as part of Jasani's five-calls-per-day Product/Price/Stock API limit. Still cache responsibly and do not assume unlimited use without supplier confirmation.

Jasani explicitly documents the Branding API and Branding Prices API as excluded from the normal daily request limit. Caching is still required for performance, resilience and responsible supplier usage.

---

## 21. Failure and Fallback Behavior

### Supplier PDF unavailable

- Serve a valid cached copy when available.
- Otherwise show: `Printing manual is temporarily unavailable. Please contact us for branding assistance.`
- Do not redirect to Jasani.
- Revalidate the saved manual template ID before deciding it is permanently invalid.
- Fall back to a custom Branding API manual when the template ID is not valid for that product.

### Branding API unavailable

- Display cached branding options.
- Allow the customer to choose `Let Elite Marcom recommend`.
- Permit a general comment and artwork upload.

### Branding Prices API unavailable

- Continue showing areas and printing methods returned by the Branding API.
- Hide price estimates and unavailable lead-time or color-choice enrichment.
- Do not replace missing prices with zero.
- Use the last-known-good internal price cache when still within the approved fallback policy.
- Send the estimate for manual staff review when reliable price data is unavailable.

### Product has no branding areas

- Hide `Download Printing Manual`.
- Show `Request Branding Advice` instead.

### Image and coordinate mismatch

- Reject an area when its rectangle falls outside the associated `web_image` bounds.
- Do not substitute the Product API gallery image.
- Try a cached last-known-good record for the same product and area.
- Otherwise fall back to the supplier-generated PDF or manual review.

### Invalid or unexpected response

- Do not send it to the browser as a PDF.
- Record a sanitized internal error.
- Do not log the API token or token-bearing URL.

---

## 22. Security Requirements

1. Keep the Jasani token server-side only.
2. Never expose supplier credentials in browser code or responses.
3. Use a fixed market-to-host allowlist to prevent server-side request forgery.
4. Resolve the supplier ID from the database, not from a full client-supplied URL.
5. Accept only positive safe integers for supplier IDs.
6. Apply an upstream timeout.
7. Limit the maximum downloaded PDF size.
8. Validate the PDF signature, not only the response header.
9. Sanitize download filenames.
10. Rate-limit public manual and preference endpoints.
11. Escape customer text before rendering it.
12. Apply tenant and request ownership controls where customer accounts exist.
13. Store artwork privately.
14. Use expiring links for private files.
15. Do not log complete upstream Branding API URLs because they contain the token.
16. Do not proxy arbitrary URLs supplied by customers.
17. Resolve branding-area records from the server database or cache; do not trust client-submitted coordinates for approved areas.
18. Rate-limit drag-suggestion saves and PDF generation to prevent abuse.
19. Enforce maximum image dimensions and decoded image size before processing base64 `web_image` content.
20. Keep customer-suggested coordinates separate from supplier-approved coordinates in storage and rendering.
21. Keep Branding Prices API records, selected tiers, supplier costs and margin calculations on the server only.
22. Do not include `price_table`, internal price snapshots or supplier pricing in public product, branding-options or PDF responses.
23. Require staff authorization for internal branding estimates and price-cache diagnostics.
24. Redact tokens and supplier prices from application, analytics and error logs.
25. Validate the live Branding and Branding Prices response types before reading nested fields; do not assume every successful response has the documented shape.
26. Persist a manual template ID only after the fetched file has a valid PDF signature, sensible page count and matching product context.
27. Do not send Branding API `pricing_products.product_id` values to the Order API unless Jasani confirms the supported branded-order payload in writing.

---

## 23. Admin and Staff Review

The centralized Elite Marcom admin panel should eventually provide:

- Branding preference list.
- Filters by status, market, product and request.
- Product and customer details.
- Submitted artwork preview/download.
- Selected area and method.
- Selected print-color option and requested number of print colors.
- Estimated branding lead time and the supplier-data timestamp.
- Matched branding method code (`internal_reference`).
- Selected quantity tier, internal branding estimate and currency, visible only to authorized staff.
- Warning when a method has no matching Branding Prices record or when the requested quantity exceeds the documented tiers.
- Raw manual-template candidate, validated manual-template ID and last validation status.
- Customer's alternative suggestions.
- Side-by-side or overlaid comparison of approved and suggested areas.
- Source view used for the customer's drawing.
- Requested physical width and height in millimetres.
- Approve, request changes or reject actions.
- Staff comments.
- Approved branding size and method.
- Regenerate approved PDF.
- Activity log.

Do not create a separate admin login or separate admin panel only for printing manuals.

---

## 24. Testing Checklist

### Functional tests

- KSA product with manual downloads successfully.
- UAE product with manual downloads successfully.
- Product `29453` returns a valid PDF through the Elite Marcom route.
- Browser address remains on the Elite Marcom domain.
- Downloaded filename uses the Elite Marcom naming rule.
- Product with multiple areas displays every area.
- Each area displays only its supported methods.
- Each area uses its own Branding API `web_image` and coordinates.
- Approved rectangles remain aligned after responsive resizing.
- Customer can select an area and method.
- Customer can choose `Other` and enter a suggestion.
- Customer can draw, move, resize, clear and redraw a suggested rectangle.
- Customer suggestion remains correctly positioned after switching between desktop and mobile sizes.
- Customer suggestion is stored as ratios with its source-view key.
- Customer can choose `Let Elite Marcom recommend`.
- Customer preference is saved with the request.
- Customer-specific PDF contains the saved selection.
- Staff can review the saved preference.
- Branding method `default_code` matches the Branding Prices `internal_reference` exactly.
- Supported color choices and estimated lead time display for a matched method.
- Quantity `36` selects the documented `35` tier.
- A quantity above `2,000` is sent for manual review.
- A method remains selectable when its price record is unavailable; no zero price is invented.
- Public product and branding responses do not contain `price_table`, supplier cost or internal estimate fields.
- Only a validated manual-template ID is used for the supplier PDF route.
- An invalid `parent_id` candidate falls back to the custom Branding API manual.
- Branding selections stay in the Elite Marcom request and are not incorrectly submitted as Order API product lines.

### Validation tests

- Invalid product ID is rejected.
- Missing supplier template ID produces a safe unavailable message.
- Method not supported by the selected area is rejected.
- Oversized dimensions are flagged for review.
- Empty `Other` notes are rejected.
- Invalid artwork file is rejected.
- Approved coordinates outside the source image are rejected.
- Customer ratios below `0`, above `1` or outside the image are rejected.
- Suggested rectangle without a source-view key is rejected.
- Coordinates copied from another product are rejected.
- Color choice not allowed for the selected method is rejected.
- Quantity-tier lookup never rounds up to the next tier.
- Missing or malformed `price_table` data triggers manual review rather than a calculated price.
- Unauthorized users cannot read internal branding-price estimates.

### Supplier failure tests

- Supplier timeout.
- Supplier `404`.
- Supplier `403`.
- Supplier returns HTML instead of PDF.
- Supplier returns a file larger than the configured limit.
- Branding API returns an empty area list.
- Branding Prices API returns no matching `internal_reference`.
- Branding Prices API omits a tier or returns malformed pricing data.
- A raw manual-template candidate returns a valid PDF that does not match the current product context.

### Security tests

- Customer cannot change the upstream host.
- Customer cannot inject a complete URL.
- Customer cannot access another customer's preference PDF.
- Token is absent from client bundles, source maps, browser requests and logs.
- Customer text cannot inject HTML or scripts.
- Uploaded artwork cannot execute in the application origin.

### Visual tests

- Desktop, tablet and mobile modal layouts.
- Dark and light themes.
- Long product names.
- One, two and many branding areas.
- Power bank with front and rear branding positions.
- Pen with a narrow barrel or clip-side branding position.
- Bottle with curved or vertically oriented branding views.
- Notebook or flat product with a large rectangular branding area.
- Square, portrait and landscape source images.
- Multiple areas using different view images for the same product.
- Long method names.
- A4 PDF rendering.
- Printed PDF legibility.
- No clipped text, images or branding rectangles.
- Approved orange and suggested violet rectangles remain visually distinct.
- PDF rectangles align with the browser preview for the same source image.
- PDF Y-axis conversion is correct for areas near both the top and bottom of an image.

---

## 25. Acceptance Criteria

The feature is complete only when all of the following are true:

1. Customers are never redirected to Jasani.
2. No Jasani token appears in the browser.
3. Eligible products show an internal printing-options experience.
4. The standard manual downloads from an Elite Marcom URL.
5. Every approved area uses the current product's own Branding API record.
6. Every rectangle remains linked to its own `web_image` and natural dimensions.
7. No coordinates are hard-coded or reused by category.
8. Approved rectangles remain aligned across responsive screen sizes.
9. Power banks, pens and other product shapes display their independently supplied positions correctly.
10. Customers can select an approved area and printing method.
11. Customers can draw and submit an alternative area on a selected product view.
12. Customer drawings are stored as normalized ratios with the source-view key.
13. Approved areas and customer suggestions remain visually and logically separate.
14. Alternative requests are clearly marked as pending technical review.
15. Preferences are attached to the relevant product request.
16. Customer-specific PDFs use Elite Marcom branding.
17. PDF rectangles match the browser preview and use the correct Y-axis conversion.
18. Invalid coordinates, PDFs and unsafe upstream responses are blocked.
19. Cached fallback behavior works during supplier downtime.
20. Raw `parent_id` values are treated as candidates; only validated product-specific manual-template IDs are used.
21. Branding methods are matched from `pricing_products[].default_code` to Branding Prices `internal_reference`.
22. Supported color choices and estimated lead time are shown when supplied, with lead time labelled as estimated.
23. Quantity-tier selection follows the documented immediate-lower-tier rule and sends unsupported quantities for review.
24. Supplier branding prices remain internal and never appear in public responses or customer PDFs under the current policy.
25. Missing pricing enrichment never hides a valid method and never produces an invented zero price.
26. Branding preferences are not submitted to the Order API as ordinary product lines without a confirmed supplier workflow.
27. All functional, security, responsive and PDF-rendering tests pass.

---

## 26. Deployment Checklist

- Add the server-only Jasani token environment variable.
- Confirm KSA and UAE host mappings.
- Store the supplier variant ID and raw template candidate separately from the validated manual-template ID.
- Validate existing manual-template candidates against the returned PDF before enabling downloads.
- Add database migration for branding preferences.
- Implement secure artwork storage.
- Implement the PDF proxy route.
- Implement the Branding API normalization route.
- Implement the per-market Branding Prices sync, normalization and server-side cache.
- Match Branding API `pricing_products[].default_code` to Branding Prices `internal_reference`.
- Add the documented lower-tier quantity lookup, color choices and estimated lead-time handling.
- Keep supplier branding prices and estimate calculations out of all public responses and customer PDFs.
- Build the responsive preference modal.
- Build the SVG approved-area overlay using each area's `web_image`.
- Build the normalized drag-to-suggest tool with product-view selection.
- Build the PDF generator.
- Add caching and fallback storage.
- Add rate limits and safe error logging.
- Test product `29453` end to end.
- Test at least one power bank, pen, bottle and notebook with different positions and image ratios.
- Test at least one UAE product.
- Confirm no supplier URL or token is visible to customers.
- Confirm pricing semantics with Jasani: whether values are per-unit or totals, setup charges, VAT, rounding, market parity and screen-print color calculations.
- Obtain Jasani's official branded-order payload or workflow before connecting branding selections to the Order API.
- Obtain Jasani confirmation that proxying or rebranding printing manuals is permitted under the reseller arrangement.
- Deploy to staging and complete live testing before production.

---

## 27. Final Recommended Implementation Order

### Task 1 - Supplier ID mapping and manual validation

Store `id`, raw `parent_id`, `default_code` and market correctly during product sync. Validate the candidate manual PDF and persist a separate nullable `supplier_manual_template_id`.

### Task 2 - Internal PDF download

Implement the secure server-side PDF proxy with content and product-context validation. Verify product `29453` as a test case, not as a universal ID rule.

### Task 3 - Branding data normalization

Fetch and normalize product-specific areas, `web_image` data, coordinates and `pricing_products` methods from the Branding API.

### Task 4 - Branding Prices enrichment

Cache the Branding Prices feed per market. Match methods by `default_code` to `internal_reference`, then enrich them with color choices and estimated lead time. Implement the documented lower-tier lookup for internal estimates while keeping prices server-side.

### Task 5 - Printing-options interface and customer preferences

Add the internal modal/page. Display each approved area on its own Branding API `web_image` using product-specific SVG coordinates. Add area, method, color, comments, quantity and artwork fields plus the view selector and normalized drag-to-suggest rectangle.

### Task 6 - Preference storage

Attach the preference and its method, color and lead-time snapshots to the appropriate Elite Marcom product request or enquiry. Do not map branding method IDs into Order API product lines.

### Task 7 - Elite Marcom PDF

Generate the branded customer-specific manual. Convert supplier coordinates and customer ratios into PDF coordinates using the source image scale, centering offsets and Y-axis conversion.

### Task 8 - Staff review

Add review status, manual-ID diagnostics, unmatched-price warnings and authorized internal estimate details to the future centralized admin panel.

### Task 9 - Final verification

Complete security, API, price-mapping, tier-selection, PDF, mobile, caching and failure-mode testing. Obtain supplier confirmation for unresolved price semantics and the branded-order workflow.

---

## 28. Final Customer-facing Wording

Use this wording in the product interface and PDF:

> **Choose or Suggest Your Branding Preference**  
> Select one of the available branding areas, printing methods and print-color options, or draw a suggested alternative area on the product view. Any displayed branding lead time is an estimate. Elite Marcom will review your requested position, artwork, product material, quantity and branding dimensions before confirming the final production method and schedule.

Use this status until staff approval:

```text
Pending Technical Review
```

Do not use `Approved`, `Confirmed` or `Production Ready` until an authorized Elite Marcom team member has completed the technical review.
