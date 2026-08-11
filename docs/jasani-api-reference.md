# Elite Marcom - Jasani API Complete Technical Documentation

**Document type:** Internal API reference and future-development guide  
**Status:** Implementation reference  
**Version:** 1.0  
**Last updated:** 12 August 2026  
**Owner:** Elite Marcom  
**Current website scope:** Saudi Arabia and UAE giveaways catalogues  
**Public pricing policy:** Do not display supplier product or branding prices  
**Public ordering policy:** Do not place supplier orders directly from the public website  

---

## 1. Purpose

This document is the central technical reference for integrating Jasani data with Elite Marcom systems.

It explains:

- Which Jasani APIs are available.
- Which fields each API provides.
- What each field means.
- How Elite Marcom should use each field.
- Which data may be shown to customers.
- Which data must remain internal.
- How products, prices, stock and branding records connect.
- How printing manuals and branding estimates should be built.
- How future developers should sync, normalize, cache and validate the data.
- Which questions still require written confirmation from Jasani.

This document must be reviewed before changing any Jasani integration.

---

## 2. Current Elite Marcom Use Case

Elite Marcom plans to use Jasani data for the Giveaways section of the website.

Current markets:

| Elite Marcom market | Jasani source |
|---|---|
| Saudi Arabia | giftsksa.com |
| UAE | jasani.ae |

The intended customer experience is:

- Customers browse products on the Elite Marcom website.
- Customers see product details, images, color, availability and branding options.
- Customers add products and quantities to a quotation request.
- Customers may select or suggest branding preferences.
- Customers remain on the Elite Marcom domain.
- Supplier credentials, URLs and internal prices remain hidden.
- Elite Marcom prepares the final quotation and confirms stock, branding and delivery.

The public website is not currently intended to:

- Display Jasani supplier prices.
- Accept online payment for Jasani products.
- Place automatic supplier orders.
- Guarantee incoming stock or production lead times.

---

## 3. Source and Confidence Levels

This document combines three evidence levels.

### 3.1 Officially documented

Information explicitly contained in the logged-in Jasani API documentation PDF captured on 12 August 2026.

Source file:

    apis _ Jasani.pdf

### 3.2 Verified during Elite Marcom testing

Behavior tested during the Elite Marcom integration review, including:

- A Jasani printing-manual PDF for sample template ID 29453.
- The relationship between product variant ID, template candidate ID and product code.
- Product-specific branding images and coordinate requirements.

Verified sample:

| Item | Value |
|---|---|
| Product variant ID | 24246 |
| Tested template/manual ID | 29453 |
| Item code | ITGL 1291 |
| Product | NAPIER - MagCase Phone Cardholder - Grey |

### 3.3 Recommended implementation

Security, data-model, caching, validation and UI rules recommended for Elite Marcom. These are implementation decisions, not claims that Jasani provides those features.

Where the official document is incomplete or ambiguous, this guide marks the item as requiring supplier confirmation.

---

## 4. API Catalogue

| API | Method | Primary purpose | Normal production limit |
|---|---|---|---|
| Product API | GET | Complete product catalogue and descriptive data | Subject to the primary GET limit |
| Price API | GET | Discounted and retail product prices | Subject to the primary GET limit |
| Stock API | GET | Available, reserved and incoming quantities | Subject to the primary GET limit |
| Branding API | GET | Product-specific branding areas and methods | Excluded from the documented daily limit |
| Branding Prices API | GET | Branding methods, color choices, lead times and price tiers | Excluded from the documented daily limit |
| Order API | POST | Submit an authorized supplier order | No documented usage limit; additional authorization required |
| Test API | GET | Test connection and parsing code | No documented usage limit |

The Product, Price and Stock APIs should be treated as the limited primary APIs.

---

## 5. Market Hosts

### 5.1 Current Elite Marcom hosts

| Market | Base URL |
|---|---|
| Saudi Arabia | https://www.giftsksa.com |
| UAE | https://www.jasani.ae |

The same endpoint structure is used by replacing the host.

The host determines:

- Local catalogue.
- Local stock.
- Local currency.
- Local customer price list.
- Local delivery and order behavior.

Never mix KSA price or stock data with a UAE product record.

### 5.2 Other hosts documented by Jasani

These are recorded for reference but are outside the current Elite Marcom website scope.

| Market | Base URL |
|---|---|
| Qatar | https://qa.giftsnpromo.com |
| South Africa | https://www.jasaniafrica.com |

Do not activate another market until its host, currency, tax, order and delivery rules have been confirmed.

### 5.3 Test host

    https://api-test.jasani.ae

Jasani states that integration and test code works in the same way on this host.

Use the test host for:

- Connection testing.
- Parser development.
- Schema validation.
- Error-handling tests.

Do not assume test stock, prices or products equal live production data.

---

## 6. Authentication

### 6.1 Product, Price, Stock, Branding and Branding Prices

These APIs use the Jasani token inside the URL path.

Example pattern:

    https://www.jasani.ae/products/all/{token}

The token must be stored only in a server-side secret.

Recommended environment variable:

    JASANI_API_TOKEN=server-only-value

### 6.2 Username and password

The username and password used to sign in to Jasani are not part of the documented Product, Price, Stock, Branding or Branding Prices requests.

The API integration should authenticate with the supplied API token, not by automatically signing in with the website username and password.

Do not store the Jasani website password in application code unless Jasani later documents a separate workflow that requires it.

### 6.3 Order API authorization

The Order API requires additional authorization from Jasani.

It uses a separate Authorization request header:

    Authorization: {order-api-authorization-value}

Do not assume the normal catalogue token and Order API authorization are interchangeable.

### 6.4 Credential safety

- Never commit credentials to Git.
- Never include credentials in Markdown documentation.
- Never expose credentials to browser JavaScript.
- Never include token-bearing URLs in analytics or logs.
- Redact tokens from error monitoring.
- Rotate any credential that has been shared in chat, screenshots, source code or public logs.

---

## 7. Rate Limits

Jasani documents a maximum of five primary GET requests per day.

The day is measured using UAE time.

A 403 Forbidden response may be returned when the limit is exceeded.

### 7.1 Limited APIs

Treat these as sharing the limited request budget until Jasani confirms otherwise:

- Product API.
- Price API.
- Stock API.

### 7.2 APIs documented outside the limit

- Test API.
- Branding API.
- Branding Prices API.
- Order API.

### 7.3 Important unresolved point

Jasani should confirm whether the five-call limit is:

- Per token.
- Per host.
- Per market.
- Per endpoint.
- Or five calls combined across all primary APIs.

Until confirmed, use the most conservative interpretation.

### 7.4 Recommended temporary production budget

For each confirmed rate-limit scope:

| Job | Calls per day |
|---|---:|
| Product catalogue | 1 |
| Price catalogue | 1 |
| Stock catalogue | 2 |
| Reserved recovery/manual call | 1 |
| Total | 5 |

The earlier requirement for hourly supplier synchronization cannot be achieved under the current five-call limit.

The website may refresh from Elite Marcom's cache hourly, but the upstream Jasani data can only be refreshed according to the allowed supplier schedule until Jasani increases the limit.

---

## 8. Error Handling

Jasani documents a 403 Forbidden response for:

1. An incorrect token.
2. An incorrect URL structure.
3. Exceeding the daily request limit.

Because the same status can represent different causes:

- Validate the URL and market before the request.
- Track the number and time of primary API calls.
- Never repeatedly retry a 403.
- Alert staff when a previously working configuration starts returning 403.
- Resume rate-limited calls after the UAE-day reset.
- Test credentials against the Test API before changing production code.

Recommended handling for other failures:

| Condition | Response |
|---|---|
| Timeout | Use last-known-good cache and retry later |
| HTTP 429 | Stop retries and respect any retry information |
| HTTP 500-599 | Exponential backoff with a strict retry limit |
| Invalid XML/JSON | Reject the new snapshot and retain the previous good snapshot |
| Missing required identifier | Quarantine the record |
| Unexpected content type | Do not parse blindly; record a sanitized error |

---

## 9. Response Formats

Jasani explicitly documents the Product API as returning XML.

The documentation lists fields for the other APIs but does not fully define every response envelope or nested object shape.

Future parsers must:

- Inspect the HTTP Content-Type.
- Validate the actual payload before parsing.
- Support documented empty values such as False where applicable.
- Preserve raw supplier snapshots for diagnosis.
- Never assume every endpoint uses the same response format.
- Never infer a successful response from HTTP 200 alone.

Recommended parser flow:

    request
      -> validate status
      -> inspect content type
      -> parse XML or JSON
      -> validate schema
      -> normalize
      -> write one atomic snapshot
      -> activate snapshot only after validation

---

## 10. Identifier Dictionary

Correct identifier use is essential.

| Identifier | Meaning | Correct use |
|---|---|---|
| id | Jasani product variant ID | Product/price/stock matching, Branding API, Order API product line |
| default_code | Jasani product code/SKU | Display, search, reconciliation and secondary matching |
| parent_id | Product template ID for configurable grouping | Group garment variants; candidate manual ID only after validation |
| pricing_products.product_id | Jasani branding-method product ID | Identify a supported branding method for one area |
| pricing_products.default_code | Branding-method code | Join to Branding Prices internal_reference |
| internal_reference | Branding Prices method reference | Match branding method pricing |
| local_product_id | Elite Marcom internal identifier | All public routes and internal database relationships |

### 10.1 Non-negotiable rules

- Do not use default_code where the Order API requires id.
- Do not use a branding-method product_id as a physical Order API product line.
- Do not assume parent_id is valid for every non-configurable product.
- Do not expose supplier IDs as the only public identifier.
- Store market with every supplier identifier.

---

## 11. Product API

### 11.1 Endpoints

UAE:

    GET https://www.jasani.ae/products/all/{token}

KSA:

    GET https://www.giftsksa.com/products/all/{token}

Test:

    GET https://api-test.jasani.ae/products/all/{token}

### 11.2 Purpose

The Product API is the main source for:

- Product identity.
- Product name and description.
- Brand and categories.
- Primary and secondary images.
- Product color.
- Garment size/color attributes.
- Product grouping.
- Website sequence.
- Barcodes.
- Carton and customs information.
- Product tags.
- Alternative products.

It is not the source of:

- Guaranteed stock.
- Product pricing.
- Exact branding-area positions.
- Branding prices.
- A dedicated printing-manual URL.

---

## 12. Product API Field Reference

| Field | Type documented | Meaning | Elite Marcom use |
|---|---|---|---|
| id | integer | Unique product variant identifier | Primary supplier variant key |
| name | text | Full product name | Product title after content review |
| default_code | char | Jasani product code | SKU, search and reconciliation |
| description_sale | text | Long sales description | Product description after sanitization |
| brand_id | Many2One array | Product brand | Extract stable ID and display name |
| public_categ_ids | Many2Many array | Product category names | Category mapping and filters |
| product_template_attribute_value_ids | Many2Many array | Garment attributes such as Size and Color | Variant labels for configurable garments |
| image_url | char | Primary product image URL | Primary gallery image |
| images | Many2Many array | Additional secondary images | Additional gallery images when returned |
| barcode | string | GS1 barcode where available | Internal barcode/search |
| website_sequence | integer | Position on the Jasani website | Supplier default ordering |
| hs_code | string | HS or commodity code | Internal customs/logistics |
| units_per_carton | integer | Units per carton | Quantity and logistics planning |
| carton_weight | float | Gross carton weight in kilograms | Internal logistics estimate |
| carton_volume | float | Carton volume in cubic metres | Internal reference; validate before reliance |
| carton_dimensions | string | Carton dimensions in centimetres | Internal logistics display |
| color | char | Product color text | Customer-facing color |
| configurable | boolean | Whether size/color configuration applies | Variant-group behavior |
| parent_id | integer | Product template ID | Configurable grouping; candidate manual ID |
| color_options | array | Related color-option template IDs | Link non-configurable color options |
| alternative_products | array | Alternative product template IDs | Recommendations after mapping |
| product_template_tags | array | Supplier special tags | Filters and badges after approved mapping |

---

## 13. Product Name and Description

### 13.1 name

Use as the supplier product title.

Recommended normalization:

- Trim surrounding whitespace.
- Preserve model names and brand capitalization.
- Remove supplier-only wording only through an approved content rule.
- Store the original value separately.

### 13.2 description_sale

This is the closest general description field.

Use it for:

- Customer-facing product summary.
- Material or feature text when included.
- Search indexing.
- Internal content review.

Security rules:

- Sanitize HTML before rendering.
- Do not trust embedded links or markup.
- Store raw and sanitized versions separately if rich text is returned.

---

## 14. Specifications

The Product API does not document one universal Specifications field.

Specifications must be assembled only from real supplied data:

- description_sale.
- brand_id.
- color.
- product_template_attribute_value_ids for garments.
- barcode.
- hs_code.
- units_per_carton.
- carton_weight.
- carton_volume.
- carton_dimensions.

Do not present carton dimensions as product dimensions.

Do not invent:

- Product material.
- Product dimensions.
- Capacity.
- Weight per unit.
- Battery capacity.
- Printing compatibility.

If a specification appears only inside description_sale, it may be displayed as descriptive text but should not be converted into a structured attribute unless the parser can do so reliably and the result is reviewed.

Recommended UI behavior:

- Show a Specifications section only when there are meaningful values.
- Hide empty rows.
- Keep logistics-only fields out of the public product page unless required.
- Allow Elite Marcom admin content to supplement missing specifications later.

---

## 15. Brand, Categories and Tags

### 15.1 brand_id

This is documented as a Many2One array.

Expected conceptual structure:

    [supplier_brand_id, supplier_brand_name]

Store:

- Supplier brand ID.
- Supplier brand display name.
- Optional Elite Marcom brand mapping.

### 15.2 public_categ_ids

Jasani states that most products belong to approximately one to five categories, but the number is not fixed.

Use category names to map into Elite Marcom's taxonomy.

Do not create a new public category automatically for every unknown supplier category. Store unmapped values for staff review.

### 15.3 product_template_tags

Documented supplier tags include:

- Sustainable.
- New Arrivals.
- On Sale.
- Traditional / Ramadan.
- CHANGE Collection.
- CHANGE ZERO Collection.

Use tags for:

- New-arrival badges.
- Sustainability filters.
- Promotional collections.
- Seasonal collections.

The On Sale tag does not by itself define a price or discount percentage.

---

## 16. Color, Size and Configurable Products

### 16.1 Standard product color

Use:

    color

This is the documented text color for the product.

### 16.2 Garment color and size

For configurable garments, use:

    product_template_attribute_value_ids

Example documented shape:

    [
      {"id": 312, "display_name": "Size: M"},
      {"id": 313, "display_name": "Color: Grey"}
    ]

For non-garment products this field may be empty.

### 16.3 configurable

- true: apparel or garment variants may be grouped by size/color.
- false: normal non-configurable product behavior.

### 16.4 parent_id

Use parent_id to group variants only when configurable is true.

Jasani states that parent_id may be meaningless for non-configurable products and should normally be ignored.

Elite Marcom separately verified that parent_id 29453 produced a printing manual for one tested non-configurable product. Therefore, parent_id may be tested as a candidate manual template ID, but it must not be trusted without validation.

### 16.5 color_options

For non-configurable products, this array provides related product template IDs for other color options.

These are template-style identifiers, not guaranteed variant IDs.

Resolve them through the local product mapping before creating customer links.

---

## 17. Product Images

Jasani documents two Product API image sources:

| Field | Purpose |
|---|---|
| image_url | Primary product image |
| images | Additional secondary-image array |

### 17.1 Multiple-image finding

The API schema supports multiple additional images through images.

However:

- A particular product may return no secondary images.
- The array may contain only one image.
- The Jasani website may show more images than the API response.
- Website images may be assembled from template, variant or other internal assets not exposed in the API.

Therefore, implement images as zero-to-many and do not promise website-gallery parity.

### 17.2 Gallery rules

1. Use image_url as the primary image when valid.
2. Append valid entries from images.
3. Remove exact duplicates.
4. Preserve supplier order.
5. Store image type as primary or secondary.
6. Download/cache images through controlled server processing where permitted.
7. Validate content type, file signature, size and dimensions.
8. Use a placeholder only when no valid image exists.

### 17.3 Branding image is different

The Branding API web_image is not a normal gallery image.

It is the source image for a particular branding-area rectangle and must remain connected to that area.

Do not replace web_image with image_url when rendering print positions.

---

## 18. Default Sorting

The Product API field for Jasani's website position is:

    website_sequence

Use this field when Elite Marcom wants to approximate Jasani's default catalogue order.

Recommended sort:

1. Products with a valid website_sequence.
2. Lower sequence values first, subject to live verification.
3. Products without a sequence last.
4. Use name or default_code as a stable tie-breaker.

Elite Marcom may maintain a separate local featured order. Do not overwrite the supplier sequence when applying local merchandising.

Store both:

- supplier_website_sequence.
- elite_display_sequence.

---

## 19. Barcode and Logistics Data

### 19.1 barcode

Contains the GS1 barcode when available.

Not all products are guaranteed to have a barcode.

### 19.2 hs_code

Use for customs and logistics.

Do not expose publicly unless required.

### 19.3 units_per_carton

Use for:

- Carton calculations.
- Procurement planning.
- Warehouse quantities.

### 19.4 carton_weight

Documented as gross kilograms per carton.

Do not treat this as unit weight.

### 19.5 carton_volume

Documented as cubic metres per carton. Jasani notes that it may not be kept updated consistently.

Treat it as advisory until checked.

### 19.6 carton_dimensions

Documented format:

    Length x Width x Height

Units are centimetres and refer to the carton, not the individual product.

---

## 20. Alternatives and Product Relationships

### 20.1 alternative_products

This array contains product template values, not product variant IDs.

Required implementation:

1. Store the raw template identifiers.
2. Resolve them against locally known supplier mappings.
3. Link only products active in the same market.
4. Never construct a public URL directly from an unresolved supplier ID.

### 20.2 Market separation

An alternative relationship from the KSA catalogue must not automatically point to a UAE product record.

---

## 21. Product Synchronization

Recommended process:

1. Fetch one complete Product API snapshot.
2. Validate the response and record count.
3. Parse all records into staging tables.
4. Normalize identifiers, arrays and empty values.
5. Upsert products by market plus supplier variant ID.
6. Use default_code as a reconciliation key, not the sole database key.
7. Upsert related brands, categories, tags and images.
8. Mark missing products as supplier-missing, not immediately deleted.
9. Activate the new snapshot atomically.
10. Record sync statistics and errors.

Never partially replace the live catalogue when parsing fails halfway.

Recommended product states:

- active.
- supplier_missing.
- hidden_by_admin.
- invalid_supplier_record.
- discontinued after staff confirmation.

---

## 22. Price API

### 22.1 Endpoints

UAE:

    GET https://www.jasani.ae/products/price/{token}

KSA:

    GET https://www.giftsksa.com/products/price/{token}

### 22.2 Field reference

| Field | Type | Meaning | Elite Marcom use |
|---|---|---|---|
| id | integer | Supplier product variant ID | Join to Product API |
| default_code | text | Jasani product code | Reconciliation |
| currency | char | Price-list currency | Validate market/currency |
| list_price | float | Elite Marcom discounted price, excluding VAT | Internal supplier cost reference |
| retail_price | float | Jasani retail selling price, excluding VAT | Internal comparison/reference |

### 22.3 Answer: Are prices provided?

Yes.

The API provides:

- list_price: the discounted customer/reseller price.
- retail_price: the retail selling price.
- currency.

Both documented price fields exclude VAT.

### 22.4 Important price boundary

These are product prices only.

They do not automatically include:

- VAT.
- Branding.
- Branding setup.
- Freight or shipping.
- Customs or duty.
- Elite Marcom margin.
- Delivery to the final customer.

---

## 23. Product Price Usage

Current Elite Marcom public policy is zero prices displayed on the Giveaways website.

Use Product API prices internally for:

- Quotation preparation.
- Supplier-cost reference.
- Margin analysis.
- Price-change alerts.
- Comparing list_price with retail_price.

Do not expose these fields in:

- Public product responses.
- Page source.
- Browser network responses.
- Analytics.
- Customer PDFs.
- Public search indexes.

Recommended internal calculation:

    supplier product cost
      + confirmed branding cost
      + confirmed logistics
      + applicable tax handling
      + Elite Marcom margin
      = proposed quotation price

This is an internal calculation. Do not treat the API value as the final customer quote.

---

## 24. Stock API

### 24.1 Endpoints

UAE:

    GET https://www.jasani.ae/products/stock/{token}

KSA:

    GET https://www.giftsksa.com/products/stock/{token}

### 24.2 Field reference

| Field | Type | Meaning | Elite Marcom use |
|---|---|---|---|
| id | integer | Supplier product variant ID | Join to Product API |
| default_code | text | Jasani product code | Reconciliation |
| blocked_qty | float | Stock reserved by other clients | Internal context only; not guaranteed |
| net_available_qty | float | Guaranteed available stock | Primary sellable stock field |
| incoming_qty | float | Stock in production/incoming | Future availability indicator |
| total_qty | float | Net available plus blocked | Warehouse total, not sellable quantity |
| incoming_date | date or False | Expected arrival date | Estimated incoming date |

Documented relationship:

    total_qty = net_available_qty + blocked_qty

### 24.3 Primary stock field

Always use:

    net_available_qty

This is the documented guaranteed stock available.

Do not use total_qty as available stock.

Do not add blocked_qty to net_available_qty.

---

## 25. Stock Display and Business Rules

Recommended customer-facing availability:

| Condition | Public status |
|---|---|
| net_available_qty greater than configured low-stock threshold | In Stock |
| net_available_qty between 1 and threshold | Low Stock |
| net_available_qty equals 0 and incoming_qty greater than 0 | Incoming Stock |
| net_available_qty equals 0 and no incoming quantity | Currently Unavailable |
| stock snapshot stale or missing | Confirm Availability |

Recommended rules:

- Quantity remains mandatory in Add to Request.
- Validate requested quantity against the latest cached net_available_qty.
- Do not prevent a request merely because quantity exceeds stock; mark it for review.
- Never guarantee incoming_date.
- Label incoming_date as estimated.
- Do not show blocked_qty to customers.
- Show exact stock quantities only if Elite Marcom explicitly chooses that policy.

Example low-stock threshold:

    LOW_STOCK_THRESHOLD=25

The threshold is an Elite Marcom rule, not a Jasani field.

---

## 26. Branding API

### 26.1 Endpoints

UAE:

    GET https://www.jasani.ae/branding/{token}/{product_id}

KSA:

    GET https://www.giftsksa.com/branding/{token}/{product_id}

product_id must be the Product API variant id.

Branding API usage is documented as not counting toward the normal daily request limit.

### 26.2 Purpose

The Branding API provides:

- Available branding areas for one product.
- Product-specific source image for each area.
- Rectangle position in source-image pixels.
- Physical branding dimensions in millimetres.
- Printing methods supported for each area.

It is the primary source for generating Elite Marcom printing-area previews and custom printing manuals.

---

## 27. Branding API Field Reference

| Field | Type | Meaning | Elite Marcom use |
|---|---|---|---|
| name | text | Branding-area name | Customer area label |
| width | float | Rectangle pixel width | Overlay width |
| height | float | Rectangle pixel height | Overlay height |
| top | float | Rectangle starting Y coordinate | Overlay top |
| left | float | Rectangle starting X coordinate | Overlay left |
| area_width | float | Physical branding width in millimetres | Maximum physical width |
| area_height | float | Physical branding height in millimetres | Maximum physical height |
| web_image | base64 image | Product view used for the area | Required overlay source image |
| pricing_products | array | Branding methods supported for the area | Method selection and price matching |

Each returned area is a separate record.

One product can have:

- One or many areas.
- Different view images.
- Different rectangle positions.
- Different physical dimensions.
- Different supported printing methods.

---

## 28. Branding Coordinates

The complete relationship is:

    web_image + left + top + width + height = one positioned branding area

Coordinate origin:

- left is measured from the image's left edge.
- top is measured from the image's top edge.
- width and height are source-image pixel values.

Physical size:

- area_width is millimetres.
- area_height is millimetres.

Do not calculate millimetres from displayed browser pixels.

### 28.1 Responsive rendering

For safe responsive storage, normalize the rectangle:

    left_ratio = left / natural_image_width
    top_ratio = top / natural_image_height
    width_ratio = width / natural_image_width
    height_ratio = height / natural_image_height

Render percentages against the exact image bounds.

Do not calculate against a card containing padding or letterboxing.

### 28.2 Product-specific rule

Never reuse coordinates:

- Between different products.
- Between categories.
- Between a pen and a power bank.
- Between color variants unless Jasani returns matching data.
- Between Product API images and Branding API images.

When valid coordinates are unavailable, show Request Branding Advice.

---

## 29. Branding Images

web_image is returned as a base64-encoded image.

Recommended processing:

1. Decode server-side.
2. Detect the real image file signature.
3. Reject oversized or invalid images.
4. Determine natural width and height.
5. Generate a content hash.
6. Store or cache through a controlled Elite Marcom asset URL.
7. Keep the hash and dimensions with every rectangle.

If several areas use the same image bytes, the image file can be deduplicated, but every area must retain its own rectangle.

web_image may be used for:

- Printing-area preview.
- Customer preference selection.
- Custom Elite Marcom printing manual.
- Staff branding review.

It should not automatically replace the primary product-gallery image.

---

## 30. Branding Methods

The Branding API pricing_products array contains the printing methods available for a specific branding area.

Documented/observed method attributes include:

- product_id.
- default_code.
- name where returned.

Use:

- product_id as the supplier branding-method identifier.
- default_code as the stable method reference.
- name as the customer-readable method name.

The same product may support different methods in different areas.

Customer method choices must be restricted to the selected area's pricing_products list.

The Branding API does not provide the actual branding price.

---

## 31. Branding Prices API

### 31.1 Endpoints

UAE:

    GET https://www.jasani.ae/brandingprices/all/{token}

KSA:

    GET https://www.giftsksa.com/brandingprices/all/{token}

Branding Prices API usage is documented as not counting toward the normal daily request limit.

### 31.2 Purpose

This API provides:

- Branding-method reference.
- Supported color choices.
- Branding lead time.
- Currency.
- Quantity-based branding price tiers.

It is used to enrich methods returned by the Branding API.

---

## 32. Branding Prices Field Reference

| Field | Type | Meaning | Elite Marcom use |
|---|---|---|---|
| name | text | Branding-method name | Display and staff reference |
| internal_reference | text | Unique method reference | Join to Branding API default_code |
| color_choice | array | Supported color counts/options | Method configuration |
| lead_time | text | Branding-job timeline | Estimated lead-time display |
| currency | text | Currency of branding price table | Internal estimate currency |
| price_table | array | Fixed quantity-based price tiers | Internal branding estimate |

Do not assume the nested price_table shape until a live response has been inspected and validated.

---

## 33. Branding Method and Price Matching

Use this join:

    Branding API pricing_products[].default_code
      =
    Branding Prices API internal_reference

Matching rules:

1. Trim documented accidental whitespace.
2. Preserve case for the first exact match.
3. Do not match only by name.
4. Record unmatched method codes.
5. Keep an available branding method visible even when its price record is missing.
6. Never invent a zero price.

Recommended normalized method:

    {
      supplier_method_id,
      method_code,
      method_name,
      color_choices,
      estimated_lead_time,
      currency,
      price_tiers,
      pricing_available
    }

---

## 34. Branding Color Choices

color_choice defines the supported color-count choices for the method.

This is especially important for screen printing, where cost may depend on artwork color count.

Rules:

- Show only supplier-supported options.
- Require a choice when the selected method needs it.
- Treat Full Color as a supplier-defined option, not a number.
- Do not multiply every method price by the color count.
- Do not create a universal screen-print formula without Jasani confirmation.

The selected print color option must be stored with the customer branding preference.

---

## 35. Branding Lead Time

lead_time is the timeline for the branding job.

Display wording:

    Estimated branding lead time: {lead_time}

It is not a guaranteed delivery date.

Final timing can depend on:

- Artwork approval.
- Product stock.
- Quantity.
- Production capacity.
- Branding method.
- Number of colors.
- Delivery market.
- Final destination.

Store a lead-time snapshot with the request because supplier values may change later.

---

## 36. Branding Quantity Tiers

The documented fixed quantities are:

    1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 20, 25, 30, 35, 40,
    45, 50, 60, 70, 80, 90, 100, 125, 150, 175,
    200, 250, 300, 400, 500, 1000, 1500, 2000

For a requested quantity between tiers, use the immediately lower tier.

Example:

    Requested quantity: 36
    Selected price tier: 35

Pseudocode:

    validate quantity is a positive whole number
    eligible_tiers = all tiers less than or equal to quantity
    selected_tier = highest eligible tier

For quantities above 2,000:

- Do not extrapolate.
- Do not use an invented formula.
- Send the request for manual confirmation.

---

## 37. Branding Estimate Policy

Branding prices should initially be used only for internal quotation support.

Internal estimate inputs:

- Market.
- Product variant.
- Approved branding area.
- Supported method.
- Selected color option/count.
- Required quantity.
- Applicable price tier.
- Currency.

Before treating the result as a final price, obtain Jasani confirmation of:

- Whether price_table values are per unit or total.
- Whether setup charges are included.
- Whether plate, screen or digitizing charges are included.
- Whether branding prices exclude VAT.
- How multi-color screen printing is calculated.
- How fixed-tier prices should be multiplied or extended.
- Required rounding.
- Whether KSA and UAE structures are identical.

Until confirmed:

- Store values for internal inspection.
- Do not show a final customer price.
- Mark estimates as provisional.
- Require staff review.

---

## 38. Existing Jasani Printing Manual

The Product API does not provide a dedicated printing_manual_url field.

Elite Marcom verified this URL pattern for sample ID 29453:

    https://www.giftsksa.com/preview_product?product_id=29453

The tested response was a PDF containing:

- Product name and code.
- Branding areas.
- Product-area images.
- Branding rectangles.
- Printing methods.
- Maximum physical branding dimensions.

### 38.1 ID caution

For the tested sample:

    product variant id: 24246
    parent/template candidate: 29453
    product code: ITGL 1291

Jasani's Product API documentation says parent_id may be meaningless for non-configurable products.

Therefore:

1. Treat parent_id as a candidate manual ID.
2. Fetch the PDF server-side.
3. Require HTTP success.
4. Validate the PDF signature.
5. Confirm it has at least one page.
6. Confirm product context where practical.
7. Store a separate supplier_manual_template_id only after validation.
8. Fall back to a Branding API-generated manual when validation fails.

### 38.2 Customer-domain rule

Do not redirect customers to Jasani.

Proxy a validated manual through:

    GET /api/products/{localProductId}/printing-manual.pdf

The browser should see only an Elite Marcom URL.

---

## 39. Elite Marcom Custom Printing Manual

Use the Branding API to generate a fully Elite Marcom-branded PDF.

Include:

- Elite Marcom logo.
- Product name, code, color and primary image.
- One section for every branding area.
- Each area's own web_image.
- Correct approved rectangle.
- Maximum area dimensions in millimetres.
- Supported printing methods.
- Supported color choices.
- Estimated lead time.
- Technical-review disclaimer.

Customer-specific manuals may also include:

- Preferred branding area.
- Preferred printing method.
- Selected color option.
- Requested dimensions.
- Required quantity.
- Customer comments.
- Artwork reference.
- Customer-suggested area.
- Pending Technical Review status.

Do not include:

- Jasani token.
- Jasani supplier pricing.
- Raw internal IDs.
- Supplier cost or margin.
- A customer suggestion marked Approved before staff review.

---

## 40. Order API

### 40.1 Authorization

The Order API requires additional supplier authorization.

### 40.2 Endpoint

UAE:

    POST https://www.jasani.ae/orders/place_order

Jasani states that the host-replacement principle applies to the Order API, but every market endpoint and permitted shipping option must be confirmed before activation.

### 40.3 Headers

    Content-Type: application/json
    Authorization: {order-api-authorization-value}

### 40.4 Example sanitized request

    {
      "customer_reference": "PO12345",
      "contact_number": "+971551234567",
      "products": [
        {
          "product_id": 15059,
          "quantity": 2
        }
      ],
      "order_type": "delivery",
      "shipping_method": "Delivery in Dubai, Sharjah or Ajman",
      "delivery_address": {
        "name": "Recipient Name",
        "street": "Address line 1",
        "street2": "Address line 2",
        "city": "Dubai",
        "state": "Dubai",
        "country": "AE",
        "zip": "00000",
        "phone": "0000000000"
      },
      "delivery_instruction": "Special delivery instructions",
      "delivery_note": "{base64-pdf}"
    }

### 40.5 Example success response

    {
      "jsonrpc": "2.0",
      "id": null,
      "result": {
        "success": true,
        "order_id": 1753567
      }
    }

The example order ID is documentation sample data, not a reusable order.

---

## 41. Order API Field Reference

| Field | Type | Requirement/use |
|---|---|---|
| customer_reference | char | Elite Marcom PO/reference number |
| contact_number | text | Recipient phone number |
| products | array | Physical supplier product IDs and quantities |
| order_type | selection | delivery or dropship |
| shipping_method | selection | Exact supplier-supported option |
| delivery_address | array/object | Required for dropship orders |
| delivery_instruction | string | Optional special instructions |
| delivery_note | base64 | PDF delivery note where supported |

### 41.1 products

Each item uses:

    {
      "product_id": Product API id,
      "quantity": positive quantity
    }

Use id, not default_code.

Jasani states that product pricing and taxes are calculated according to the authorized account's price list.

### 41.2 order_type

Allowed documented values:

- delivery: delivery to the registered company address.
- dropship: delivery directly to the client/recipient address.

### 41.3 delivery_address

Documented fields:

| Field | Required |
|---|---|
| name | Yes |
| street | Yes |
| street2 | No |
| city | Yes |
| state | No |
| country | Yes; use AE for UAE in the documented example |
| zip | No |
| phone | No |

### 41.4 delivery_note

This is a base64-encoded PDF intended for signature purposes.

Jasani notes that it is not used for the Dubai, Sharjah or Ajman delivery option because delivery partners use their own delivery note.

---

## 42. Documented Shipping Options

The PDF documents the following UAE-account examples:

- Delivery in Dubai, Sharjah or Ajman.
- Door Delivery within UAE.
- Door Delivery to Oman via Ground (Excludes 5% Duty).
- Door Delivery to Qatar via Ground (Excludes 5% Duty).
- Door Delivery to Bahrain via Ground (Excludes 5% Duty).
- Door Delivery to Kuwait via Ground (Excludes 5% Duty).

Shipping costs are calculated automatically according to the selected supplier option.

Do not hard-code these options globally.

Before placing an order:

- Fetch or confirm the current allowed wording.
- Validate the option against the order market.
- Confirm destination-country code.
- Confirm duty and tax treatment.
- Reject unsupported values before sending.

---

## 43. Order API Safeguards

The current Elite Marcom public website must not call the Order API directly.

Future activation requires:

- Written Jasani authorization.
- Separate Order API secret.
- Staff-only permission.
- Final stock confirmation.
- Final cost review.
- Approved PO/reference.
- Confirmed delivery address.
- Duplicate-order protection.
- Explicit staff confirmation before submission.
- Audit logging.
- Secure storage of returned order_id.
- Reconciliation of supplier response.

Recommended state flow:

    draft
      -> internally approved
      -> ready to submit
      -> submitting
      -> submitted
      -> supplier order confirmed
      -> failed or requires review

Never automatically retry an uncertain POST after a timeout without checking whether Jasani created the order. An uncontrolled retry could create a duplicate order.

---

## 44. Branding and Order API Boundary

The documented Order API covers physical products and quantities.

It does not explain how to submit:

- Branding area.
- Branding method.
- Print-color choice.
- Artwork.
- Branding dimensions.
- Branding notes.
- Branding approval.

Therefore:

- Do not send pricing_products.product_id as a normal Order API product line.
- Keep branding selections attached to the Elite Marcom request.
- Do not automate branded supplier orders until Jasani provides the official payload or workflow.
- Ask whether branding is added as separate service lines, notes, attachments or a different order process.

---

## 45. Recommended Normalized Data Model

The exact database names may follow the existing website architecture.

### 45.1 Supplier product

    local_product_id
    source_market
    supplier_variant_id
    supplier_default_code
    supplier_parent_id_raw
    supplier_manual_template_id
    manual_template_validated_at
    name_raw
    description_raw
    description_sanitized
    color
    configurable
    barcode
    website_sequence
    hs_code
    units_per_carton
    carton_weight_kg
    carton_volume_m3
    carton_dimensions_cm
    source_updated_at
    last_seen_at

### 45.2 Product images

    local_product_id
    source_type
    source_url_or_asset_id
    sequence
    content_hash
    width
    height
    fetched_at

source_type:

- primary.
- secondary.
- branding_view.

### 45.3 Product prices

    local_product_id
    market
    currency
    supplier_list_price_ex_vat
    supplier_retail_price_ex_vat
    fetched_at

Keep this table server-side and access-controlled.

### 45.4 Stock snapshot

    local_product_id
    market
    net_available_qty
    blocked_qty
    total_qty
    incoming_qty
    incoming_date
    fetched_at

### 45.5 Branding area

    local_product_id
    supplier_variant_id
    area_key
    area_name
    branding_image_asset_id
    image_hash
    image_natural_width
    image_natural_height
    left_px
    top_px
    width_px
    height_px
    left_ratio
    top_ratio
    width_ratio
    height_ratio
    area_width_mm
    area_height_mm
    fetched_at

### 45.6 Branding area method

    branding_area_id
    supplier_method_id
    method_code
    method_name

### 45.7 Branding price method

    market
    internal_reference
    method_name
    color_choices_json
    estimated_lead_time
    currency
    price_tiers_json
    fetched_at

### 45.8 Sync run

    id
    market
    api_name
    started_at
    completed_at
    status
    http_status
    record_count
    created_count
    updated_count
    missing_count
    rejected_count
    sanitized_error
    snapshot_id

---

## 46. Public and Internal Data Boundary

### 46.1 Safe customer-facing fields

- Elite Marcom product ID.
- Product name.
- Product code when approved.
- Sanitized description.
- Brand.
- Categories.
- Color.
- Garment size attributes.
- Product images.
- Availability status.
- Incoming status and estimated date when appropriate.
- Branding-area name.
- Branding dimensions.
- Supported method name.
- Supported color choices.
- Estimated branding lead time.

### 46.2 Internal-only fields

- Jasani API token.
- Order authorization.
- Token-bearing supplier URLs.
- Supplier list_price.
- Supplier retail_price.
- Branding price_table.
- Internal branding estimates.
- Supplier cost and Elite Marcom margin.
- blocked_qty.
- Raw API response containing sensitive details.
- Internal sync diagnostics.

### 46.3 Conditional internal fields

Supplier IDs may be returned only through authenticated internal APIs when developers or staff need them. Public customers should work with local Elite Marcom IDs.

---

## 47. Recommended Elite Marcom Endpoints

Public/customer routes:

    GET  /api/giveaways
    GET  /api/giveaways/{localProductId}
    GET  /api/giveaways/{localProductId}/availability
    GET  /api/giveaways/{localProductId}/branding-options
    GET  /api/giveaways/{localProductId}/printing-manual.pdf
    POST /api/giveaways/{localProductId}/branding-preference
    POST /api/giveaway-requests
    POST /api/giveaways/{localProductId}/stock-notification

Authenticated internal routes:

    POST /api/internal/jasani/sync/products
    POST /api/internal/jasani/sync/prices
    POST /api/internal/jasani/sync/stock
    POST /api/internal/jasani/sync/branding-prices
    POST /api/internal/jasani/products/{localProductId}/sync-branding
    POST /api/internal/jasani/branding-estimates
    POST /api/internal/jasani/manuals/{localProductId}/validate
    POST /api/internal/jasani/orders

Public routes must read normalized cached data. They must not become unrestricted proxies to Jasani.

---

## 48. Caching and Synchronization Strategy

| Data | Recommended refresh under current limits |
|---|---|
| Product catalogue | Once daily or less often if unchanged |
| Product prices | Once daily |
| Product stock | Up to twice daily under conservative five-call budget |
| Branding areas | On demand, then cache approximately 24 hours |
| Branding Prices | Full market feed approximately once daily |
| Existing supplier PDFs | On demand, cache approximately 24 hours |
| Product images | Cache by content hash and source change |

Use last-known-good snapshots.

Public pages may read the database/cache frequently without creating supplier API calls.

Cache keys must include:

- Market.
- API type.
- Product variant ID where applicable.
- Snapshot/version.

Do not serve UAE stock from a KSA cache key.

---

## 49. Data Validation Rules

### 49.1 Product

- id must be a positive safe integer.
- default_code must be normalized and non-empty for publishable products.
- market must be known.
- image URLs must use approved hosts and HTTPS.
- category and tag arrays must be bounded.
- descriptions must be sanitized.

### 49.2 Price

- id must match a known product in the same market.
- currency must match the expected market configuration.
- prices must be finite and non-negative.
- missing price must remain null, not zero.

### 49.3 Stock

- Quantities must be finite and non-negative unless Jasani documents another rule.
- net_available_qty is the primary value.
- Verify total_qty approximately equals net_available_qty plus blocked_qty.
- Convert False incoming_date to null.
- Reject impossible date formats.

### 49.4 Branding

- Area image must decode successfully.
- Natural dimensions must be known.
- left, top, width and height must be finite.
- Rectangle must remain inside image bounds.
- area_width and area_height must be positive.
- Every method must belong to the current area.

### 49.5 Branding Prices

- internal_reference must be non-empty.
- color_choice must be a valid bounded array.
- price tiers must contain supported positive quantities.
- Missing tiers must not be interpolated.
- Missing price must not become zero.

### 49.6 Order

- Require staff authorization.
- Validate every product ID and quantity.
- Validate order_type against the allowed list.
- Validate shipping_method against current market options.
- Require dropship address fields.
- Validate delivery-note PDF signature and size.
- Require an idempotency/duplicate-control record internally.

---

## 50. Security Requirements

1. Keep every supplier credential server-side.
2. Never expose token-bearing URLs.
3. Use a fixed market-to-host allowlist.
4. Never proxy a browser-supplied full URL.
5. Resolve supplier IDs from the database.
6. Use HTTPS only.
7. Apply request timeouts.
8. Limit response size.
9. Validate file and image signatures.
10. Sanitize supplier and customer text.
11. Keep pricing tables server-side.
12. Require staff roles for price and order functions.
13. Rate-limit public Elite Marcom endpoints.
14. Store artwork and customer PDFs privately.
15. Use expiring links for private files.
16. Redact credentials and supplier prices from logs.
17. Validate XML safely with external entity processing disabled.
18. Protect sync routes from public access.
19. Record all Order API attempts in an immutable audit trail.
20. Rotate exposed or reused secrets.

Because the token appears in the URL path, confirm that:

- Reverse proxies do not log full paths for these requests.
- Error trackers redact URL segments.
- APM tools do not capture the token.

---

## 51. Logging and Monitoring

Record:

- API name.
- Market.
- Start/end time.
- HTTP status.
- Record count.
- Parse result.
- Validation failures.
- Snapshot activated or rejected.
- Cache age.
- Rate-budget count.

Never record:

- API token.
- Order authorization.
- Full token-bearing URL.
- Customer artwork content.
- Base64 delivery notes.
- Raw supplier prices in public logs.

Recommended alerts:

- Repeated 403.
- Product count changes beyond a configured threshold.
- Empty product or stock feed.
- Currency mismatch.
- Stock snapshot older than the allowed freshness.
- Large price changes.
- Branding method no longer matching a price reference.
- Invalid branding rectangles.
- Order response without a clear success result.

---

## 52. Failure and Fallback Behavior

| Failure | Customer behavior | Internal behavior |
|---|---|---|
| Product sync fails | Continue last-known-good catalogue | Alert and retain previous snapshot |
| Price sync fails | No public change because prices are hidden | Mark internal cost stale |
| Stock sync fails | Show Confirm Availability when cache expires | Alert staff |
| Branding API fails | Show cached options or Request Branding Advice | Retry later |
| Branding Prices fails | Keep methods visible; hide enrichment | Manual estimate |
| Printing manual fails | Offer custom manual or branding assistance | Revalidate manual ID |
| Image fails | Use controlled placeholder | Quarantine invalid image |
| Order submission uncertain | Show internal Pending Verification | Check supplier before retry |

Never delete valid customer-facing data only because one supplier request failed.

---

## 53. Testing Checklist

### 53.1 Authentication and limits

- Valid Test API token succeeds.
- Invalid token returns a safe error.
- Token is absent from browser traffic.
- Token is absent from logs.
- Primary request counter respects UAE time.
- 403 does not cause repeated retries.

### 53.2 Products

- Product XML parses.
- Empty optional fields are accepted.
- brand_id maps correctly.
- Multiple categories map correctly.
- Garment Size and Color attributes display correctly.
- Non-garment attribute array may be empty.
- Primary image works.
- Zero, one and many secondary images work.
- Duplicate images are removed.
- website_sequence ordering is stable.
- Unmapped categories are queued for review.
- parent_id is not treated as a universal variant ID.

### 53.3 Prices

- Price joins by market and id.
- default_code mismatch is reported.
- Currency mismatch is blocked.
- list_price and retail_price remain internal.
- VAT is not assumed to be included.
- Missing price remains null.

### 53.4 Stock

- net_available_qty drives availability.
- blocked_qty is never counted as available.
- total_qty relationship is checked.
- incoming_date False becomes null.
- Low-stock alert works.
- Stale stock shows Confirm Availability.

### 53.5 Branding

- Branding request uses product variant id.
- One and multiple branding areas render.
- Each area uses its own web_image.
- Rectangles stay aligned responsively.
- Rectangle outside image bounds is rejected.
- area dimensions display in millimetres.
- Methods are limited to the selected area.

### 53.6 Branding Prices

- default_code matches internal_reference.
- Missing match does not hide the method.
- Color choices display correctly.
- lead_time is labelled estimated.
- Quantity 36 selects tier 35.
- Quantity above 2,000 requires manual review.
- Public responses exclude price_table.

### 53.7 Printing manuals

- Validated manual downloads through Elite Marcom domain.
- Invalid candidate parent_id is rejected.
- PDF signature and size are validated.
- Custom manual uses correct product images and coordinates.
- Customer PDF excludes supplier prices and credentials.

### 53.8 Orders

- Public users cannot submit supplier orders.
- Product API id is used, not code.
- Invalid shipping method is rejected.
- Dropship address is validated.
- Duplicate submission is prevented.
- Timeout does not trigger an uncontrolled retry.
- Supplier order_id is stored on success.
- Branding method IDs are not sent as physical product lines.

---

## 54. Known Limitations

1. The five-call rate-limit scope is not fully defined.
2. The API may not provide every image displayed on Jasani's website.
3. There is no universal structured Specifications field.
4. Size attributes are documented mainly for garments.
5. Product dimensions are not a dedicated documented field.
6. Carton volume may not always be maintained.
7. parent_id is unreliable for non-configurable product logic.
8. A dedicated printing-manual URL is not returned in Product API.
9. The complete nested price_table structure requires live inspection.
10. Branding price calculation semantics require written confirmation.
11. The documented Order API does not define branded-order instructions.
12. Incoming stock dates are estimates.
13. The response format of every non-Product GET endpoint is not fully specified.

---

## 55. Questions to Send to Jasani

### Rate limits

1. Is the five-GET daily limit per token, per host, per market, per endpoint or combined?
2. Can Elite Marcom receive a higher limit for KSA and UAE production synchronization?
3. Is there a webhook or incremental-update endpoint?

### Products and images

4. Does images include every secondary image shown on the Jasani website?
5. If not, is there another endpoint for the complete product gallery?
6. Is website_sequence sorted ascending?
7. Is there a last-modified field or delta-feed option?
8. Is there a dedicated structured specification or product-dimension field?

### Printing manuals

9. Is preview_product an officially supported endpoint?
10. Which exact identifier must be used for every product?
11. May Elite Marcom proxy and rebrand the manual?
12. Is there an API field for the validated printing-manual ID?

### Branding prices

13. Is each price_table value per unit or total?
14. Are setup, screen, plate or digitizing charges included?
15. Do branding prices exclude VAT?
16. How must multi-color screen-print prices be calculated?
17. How should rounding be handled?
18. Are KSA and UAE branding-price structures identical?
19. What should be done above quantity 2,000?

### Orders

20. What is the official KSA Order API endpoint and shipping-method list?
21. How should branding area, method, colors, artwork and notes be submitted?
22. Does the Order API support an idempotency key?
23. How can Elite Marcom check an order after a timeout?
24. Is there an order-status endpoint?

---

## 56. Recommended Implementation Order

### Phase 1 - Secure connector

- Add server-only market configuration.
- Store token securely.
- Add strict host allowlist.
- Add rate-budget tracking.
- Implement safe XML/JSON parsing.
- Add raw snapshot storage and sync logs.

### Phase 2 - Products

- Import Product API.
- Normalize identifiers, descriptions, brand, categories and tags.
- Import primary and secondary images.
- Add configurable-product mapping.
- Use website_sequence for optional supplier ordering.

### Phase 3 - Stock and internal prices

- Import Stock API.
- Use net_available_qty.
- Add availability buckets and low-stock alert.
- Import Price API into internal-only tables.
- Keep public prices disabled.

### Phase 4 - Branding

- Add per-product Branding API fetching.
- Decode and cache web_image.
- Render product-specific rectangles.
- Store physical area dimensions.
- Restrict methods by branding area.

### Phase 5 - Branding estimates

- Import Branding Prices API.
- Match default_code to internal_reference.
- Add color choices and estimated lead time.
- Add lower-tier quantity selection.
- Keep estimates staff-only until price semantics are confirmed.

### Phase 6 - Printing manuals

- Validate candidate supplier manual IDs.
- Add secure Elite Marcom PDF proxy.
- Generate custom Elite Marcom printing manuals.
- Save customer branding preferences.

### Phase 7 - Order API, only after authorization

- Obtain Jasani's approved order and branding workflow.
- Add staff approval.
- Add duplicate protection.
- Add audit logging.
- Test in a controlled environment.
- Activate only after written sign-off.

---

## 57. Maintenance Runbook

### Daily

- Check sync status.
- Check rate-budget usage.
- Review stale stock warnings.
- Review repeated supplier errors.

### Weekly

- Review unmapped categories and brands.
- Review invalid images.
- Review missing price or stock matches.
- Review unmatched branding method references.

### Monthly

- Reconfirm active API credentials.
- Review supplier schema changes.
- Review price and stock freshness.
- Review public data for accidental price exposure.
- Test one KSA and one UAE product end to end.

### When Jasani changes the API

1. Save the new official documentation.
2. Compare fields and endpoint behavior.
3. Update parsers in staging.
4. Run contract tests.
5. Update this document and version number.
6. Deploy only after a complete successful snapshot.

---

## 58. Quick Answers for Future Developers

### Which field is the product SKU?

    default_code

### Which field is the supplier product variant ID?

    id

### Which field should drive stock availability?

    net_available_qty

### Should total_qty be used as available stock?

No. It includes blocked stock.

### Does the API provide product prices?

Yes. list_price and retail_price, both documented as excluding VAT.

### Should those prices be shown publicly?

No, not under the current Elite Marcom policy.

### Does the Product API provide multiple images?

The schema supports a primary image_url plus an additional images array, but every product is not guaranteed to return all images shown on the Jasani website.

### Is there a Specifications field?

No universal field is documented. Use description_sale and genuine structured fields only.

### Where does product color come from?

Use color. Garment color may also appear in product_template_attribute_value_ids.

### Where does size come from?

For garments, use product_template_attribute_value_ids.

### What is Jasani's default sorting field?

Use website_sequence, with live confirmation of direction.

### Does Product API return a printing-manual link?

No dedicated link is documented.

### Which API provides printing positions?

Branding API.

### Which image must be used for the position?

The same branding area's web_image.

### Which API provides branding prices?

Branding Prices API.

### How are methods matched to prices?

    pricing_products.default_code
      =
    internal_reference

### Are API calls authenticated with the Jasani website password?

No. The documented catalogue APIs use the API token. Order API uses separate authorization.

### Can the public website place Jasani orders now?

No. Keep the current workflow as quotation/request only.

---

## 59. Final Non-negotiable Rules

1. Keep all Jasani credentials server-side.
2. Keep KSA and UAE records separated by market.
3. Use id as the supplier variant identifier.
4. Use net_available_qty as available stock.
5. Keep supplier product and branding prices internal.
6. Do not assume the Product API returns every website image.
7. Do not invent missing specifications.
8. Use each branding area's own web_image and coordinates.
9. Never reuse printing positions across products.
10. Treat parent_id as a manual candidate only until validated.
11. Do not redirect customers to Jasani for printing manuals.
12. Do not submit branding-method IDs as physical Order API product lines.
13. Do not activate automatic supplier ordering without authorization and staff approval.
14. Preserve last-known-good snapshots when supplier calls fail.
15. Update this document whenever the supplier schema or Elite Marcom policy changes.

---

## 60. Related Elite Marcom Documentation

Use this document together with:

- Elite-Marcom-Jasani-Printing-Manual-Integration-Guide.md
- Elite-Marcom-Printing-Manual-Sample.pdf
- Elite-Marcom-Website-Only-Master-Prompt.md

The printing-manual guide contains more detailed UI, coordinate, PDF-generation and customer-preference implementation instructions.
