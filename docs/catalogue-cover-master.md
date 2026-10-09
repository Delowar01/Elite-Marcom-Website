# Elite Marcom Corporate Gifts Catalogue - Refined cover master

Version 3.0 | 09 October 2026 | Clean PNG logo replacement; refined design retained

This specification is for a future Claude Code translation into the existing ReportLab catalogue generator. The self-contained HTML remains the authoritative editable master. No generator, website, server or deployment was changed. The existing A4 canvas, main logo element, fonts, title sizes, dynamic fields, semantic dates/links and footer have been retained. User design approval remains separate from this technical and visual audit.

## Deliverables and authority

1. `Elite_Marcom_Catalogue_Cover_MASTER.html`: refined editable master; exact main PNG, embedded Poppins, vector field and source-alpha PNG watermark, product hero and product-branding provenance are self-contained.
2. `Elite_Marcom_Catalogue_Cover_MASTER.pdf`: one A4 page printed from the HTML, with exact ISO A4 page boxes.
3. `Elite_Marcom_Catalogue_Cover_MASTER_AUDIT.png`: final PDF page at 300 dpi, 2481 x 3508 px.
4. `Elite_Marcom_Catalogue_Cover_IMPLEMENTATION.md`: this updated deterministic map.
5. `Elite_Marcom_Catalogue_Cover_LOGO_AUDIT.png`: 2400 x 3060 px QA sheet, containing enlarged crops of the main logo and all seven branded products from a 600 dpi PDF render. It is not part of the catalogue page.

Authority: the user's refinement instructions; the clean supplied PNG for every logo's source pixels, under the user's later explicit authorization to replace the defective SVG; the brand guidelines for colour, typography and merchandise treatment; the preferred screenshot for visual direction. Subtle tonal variation and rounded metadata treatment are expressly authorized cover refinements. No generative image tool was used, and no source Library attachment was modified.

## Exact official logo: replacement source

The user reported an issue in the SVG and explicitly authorized a PDF or PNG replacement. This instruction supersedes the earlier SVG-only requirement and its fixed SHA-256. The old SVG is no longer rendered anywhere in the cover. No logo was redrawn, traced, generated, or re-typeset.

Source used: `D:\Elite Marcom\Elite Marcom.4 (1)d.png`. This is the supplied clean, full horizontal two-colour lockup found in the user's brand folder. Its opaque brand colours are exactly `#E56C25` and `#02004C`. It has a transparent background.

- Original size: **1629 x 518 RGBA pixels**, **43,144 bytes**.
- Required replacement SHA-256: `38cb42d7034a0bec3082aa9dab27afc66d4eea8c2d8a78d3a13e0c57ecfeaeb7`.
- `.brand-logo` contains `data:image/png;base64,...` with the **original bytes**. Decode and compare both bytes and hash with the source. No re-encoding or recolouring is applied to the main logo.
- Placement: x **16 mm**, top **12 mm**, width **57 mm**, height **18.125230203 mm** (`57 * 518 / 1629`). The 0.049 mm height change follows the replacement source's native aspect ratio; it does not move any other component.
- Effective native resolution: **725.905 ppi**, comfortably above 300 ppi at this size. This replacement is intentionally raster in both HTML and PDF, as authorized. The page is not flattened; all catalogue text remains editable and extractable.
- Clear space remains **7 mm on each side**, exceeding the guideline 1X counter-gap rule. Exclusion rectangle: x **9 mm**, top **5 mm**, width **71 mm**, height **32.125230203 mm**. The 57 mm lockup width exceeds the 35 mm guideline minimum.

The source's clean filled letterforms remove the visible sharp spike previously preserved above the A in MARCOM. The original PNG's wordmark, internal spacing, colours and aspect ratio are retained. Never try to recover editable paths by tracing this PNG; use it directly in the future generator.

### Decorative watermark

Extract the symbol alpha from the same PNG with source crop **[0, 0, 503, 518]** (left, top, right-exclusive, bottom-exclusive). The empty gap before the wordmark occupies source columns 503 through 530. Copy the 503 x 518 alpha pixels unchanged to a transparent **518 x 518** canvas at **(7,0)**, leaving 7 transparent columns left and 8 right. Set RGB to white while preserving every alpha pixel. This is a deterministic crop and single-colour treatment, not tracing or redrawing.

Position remains x **126 mm**, top **39 mm**, width **96 mm**, height **96 mm**, opacity **0.075**, clipped to the same orange-field contour and page. The deliberate 12 mm right bleed is clipped. The mask is an independent embedded PNG, separate from the hero. Its lower native resolution is appropriate to its very faint decorative role; it must not substitute for the crisp main logo.

## Page, units and design grid

- A4 portrait: **210 x 297 mm**, no browser margins or headers/footers.
- MediaBox, CropBox and TrimBox: **595.275590551 x 841.889763780 pt**.
- `@page { size: A4 portrait; margin: 0; }` remains in the HTML.
- `1 mm = 72/25.4 pt`; `1 CSS px = 0.75 pt`.
- All map coordinates use a top-left origin in **mm**. Do not turn these into a responsive layout.
- Editorial margins remain 16 mm; facts/footer margins remain 12 mm. Hero and decorative field bleed.
- The spacing module remains 2 mm, with the documented optical adjustments.
- Main logo, title sizes and baselines, hero bounding region, disclaimer and website positions are unchanged.
- The upper title field is pure white through y=96 mm. A restrained transition to Ground occurs only below the heading.

## Brand tokens and heading contrast

| Token | Value | Use |
|---|---|---|
| `--elite-orange` | `#E56C25` | CATALOGUE, title rule, icons; central orange-field stop |
| `--elite-navy` | `#02004C` | PRODUCT, market/subtitle, metadata, footer, navy product ink |
| `--white` | `#FFFFFF` | Title background; source white merchandise marks; watermark |
| `--ground` | `#F4F2F0` | Lower page and floor transition |
| `--line` | `#D9D5D0` | Metadata dividers |
| `--muted` | `#6B6A75` | Promise and disclaimer |
| `--ink` | `#1A1A20` | Default body token |
| `--orange-text` | `#E56C25` | Same exact Elite Orange; large heading on pure white only |

The orange heading is **59.5 pt SemiBold**. `#E56C25` against `#FFFFFF` has a computed contrast ratio of **3.229:1**, exceeding the 3:1 large-text threshold. The entire word sits left of the orange contour, on pure white. Do not place this heading on Ground or orange: orange/Ground falls below 3:1. Smaller text retains navy/muted colours. This explicitly requested brighter heading replaces the earlier `#B85218` treatment.

Orange-field tonal colours are limited to `#F4C09A`, `#ED9458`, `#E56C25`, `#DE6423`. Ground-transition midpoint is `#FAF8F5`. The faint band shadow uses `#A7917E` at very low alpha. Product photograph colours remain photographic, not forced to swatches. CMYK/Pantone values are not newly approved by this RGB proof.

## REPORTLAB IMPLEMENTATION MAP

These responsibilities map the existing components to generator functions. They are a specification, not an implementation request. Preserve the page structure. For a rectangle, ReportLab lower-left y is `(297 - top - height) * mm`. For text, use `(297 - baseline_from_top) * mm`.

| HTML component | ReportLab responsibility | x | top | width | height | Treatment |
|---|---|---:|---:|---:|---:|---|
| `.catalogue-cover` | `Document.cover_page()` | 0 | 0 | 210 | 297 | Exact A4, page clip |
| `.cover-ground` | `Document.cover_background()` | 0 | 0 | 210 | 297 | Axial white-to-Ground shading below y=96 |
| `.cover-orange-field` | `Document.cover_background()` | 0 | 0 | 210 | 250.555 | Two cubic segments, straight lower segment; axial shading |
| `.cover-watermark` | `Document.cover_watermark()` | 126 | 39 | 96 | 96 | Source-alpha white PNG symbol, alpha .075; field/page clip |
| `.cover-header` | `Document.cover_header()` | 16 | 12 | 178 | 18.125230203 | Same anchor; source aspect ratio |
| `.brand-logo` | `Document.draw_official_logo()` | 16 | 12 | 57 | 18.125230203 | Exact original PNG bytes, no restyling |
| `.market-label` | `Document.cover_header()` | right 194 | 15.7 | content | 5 | Right-aligned |
| `.cover-title` | `Document.cover_title()` | 16 | 42 | 140 | 48 | Existing eyebrow/title hierarchy |
| `.cover-eyebrow` | `Document.cover_title()` | 16 | 42 | 140 | 5 | CORPORATE GIFTS |
| PRODUCT line | `Document.cover_title()` | 15.4 | 49 | 119.704 | 20.3 | Navy, 59.5 pt / 600 |
| CATALOGUE line | `Document.cover_title()` | 15.4 | 69.3 | 119.704 | 20.3 | Elite Orange, 59.5 pt / 600 |
| `.title-rule` | `Document.cover_title()` | 16 | 90.5 | 14 | .8 | Orange |
| `.cover-subtitle` | `Document.cover_subtitle()` | 16 | 94 | 150 | 6.5 | Market / country / year |
| `.cover-promise` | `Document.cover_promise()` | 16 | 104 | 99.091 | 4 | Single line |
| `.cover-hero` | `Document.cover_hero()` | 0 | 107 | 210 | 143.5546875 | Replaceable alpha PNG; bottom 250.5546875 |
| `.meta-band-shadow` | `Document.cover_meta_shadow()` | 10.8 | 252.4 | 188.4 | 22.6 | Three faint vector rounded rectangles |
| `.cover-meta` | `Document.cover_meta()` | 12 | 253.2 | 186 | 20.2 | Radius 4 mm; white alpha .90 |
| First `.meta-item` | `Document.cover_meta_item()` | 12 | 253.2 | 57 | 20.2 | Catalogue count |
| Second `.meta-item` | `Document.cover_meta_item()` | 69 | 253.2 | 57 | 20.2 | Prepared date |
| Third `.meta-item` | `Document.cover_meta_item()` | 126 | 253.2 | 72 | 20.2 | Stock timestamp |
| `.cover-disclaimer` | `Document.cover_disclaimer()` | 12 | 276 | 186 | 9.2 | Existing two 10 pt lines |
| `.cover-footer` | `Document.cover_footer()` | 12 | 288 | 186 | 5 | Website right at 198 |

Millimetres are normative. The unchanged hero is 100% page width, starts at 36.027% of page height and occupies 48.335% of it. The band starts at 5.714% of page width and 85.253% of page height; it is 88.571% wide and 6.801% high.

### Orange-field path and light falloff

The final path is expressed in page top-left mm:

```svg
M152 0 C146 28 146 53 140 80 C134 108 121 138 108 151 L55 250.555 H210 V0 Z
```

Start at (152,0). The first cubic uses control points (146,28), (146,53), ending (140,80). The second uses (134,108), (121,138), ending (108,151). Continue straight to (55,250.555), right to (210,250.555), up to (210,0), then close. The field's container clips its watermark using the same contour, normalized to objectBoundingBox units in HTML. Do not restore the old polygon or approximate the curve with unrelated geometry.

Within this clip, use a **linear/axial RGB shading** from **(112,0) to (210,65) mm**, with these stops:

| Position | Colour |
|---:|---|
| 0 | #F4C09A |
| .40 | #ED9458 |
| .76 | #E56C25 |
| 1 | #DE6423 |

Extend the first/last colours outside the shading endpoints. The artwork is a quiet light falloff, not gloss or a multi-colour effect. SVG gradients and clipping remain vector in the proof. In ReportLab use `canvas.linearGradient` with these stop positions inside a saved clipping path; translate top-origin endpoints to bottom-origin page coordinates. No CSS filter, blur shader or blend mode is needed.

### White / cream background

Use a full-page rectangle with an axial shading from **(0,96) to (0,136) mm**: stop 0 `#FFFFFF`, stop .55 `#FAF8F5`, stop 1 `#F4F2F0`. Extend endpoint colours. Therefore the entire heading, ending above y=90 mm, remains on pure white. This replaces the previous hard white/Ground join at y=106.

### Paint order

1. White page and the white-to-Ground background shading.
2. Curved orange field with its own axial shading.
3. Exact watermark clipped to the field and page.
4. Composited branded hero PNG, retaining real photographic contact shadows and an opaque floor fade to Ground at its bottom.
5. Main logo/header, eyebrow, two title lines, rule, subtitle and promise.
6. Three low-opacity band-shadow rectangles.
7. Rounded white band, white circular icon grounds, divider rules, vector icons and metadata text.
8. Fixed disclaimer and website.

There is no visible reference-render label, no oversized drop shadow, no glass effect and no browser-only filter.

## Typography and exact text placement


Poppins Regular 400, Medium 500 and SemiBold 600 are embedded as font data in the HTML. No separate font files accompany the deliverables and no web-font service is required. Browser fallbacks are Poppins, Arial, sans-serif. The audited proof loaded all three embedded Poppins faces; it used no fallback. The logo's wordmark is original PNG artwork and must never be typeset with these fonts.

Use the equivalent installed/licensed Poppins TTF faces in ReportLab. Register each weight separately. Do not substitute Bold, Black, stretched text or synthetic bold. If fonts are unavailable, resolve that dependency before declaring the ReportLab translation matched.

| Element | Weight | Size pt | Tracking | Line height mm |
|---|---:|---:|---|---:|
| Header market | 400 | 9 | +0.38 mm | 5 |
| CORPORATE GIFTS | 500 | 12 | +1.34 mm | 5 |
| PRODUCT / CATALOGUE | 600 | 59.5 | -0.035 em = -2.0825 pt | 20.3 |
| Market/country/year subtitle | 400 | 14 | +0.5 mm | 6.5 |
| Promise | 500 | 7.4 | +0.38 mm | 4 |
| Facts labels | 500 | 7.7 | +0.24 mm | 3.8 |
| Count/prepared values | 600 | 12.5 | -0.12 mm | 5.3 |
| Stock timestamp | 600 | 11.2 | -0.14 mm | 5.3 |
| Disclaimer | 400 | 10 | 0 | 4.6 |
| Website | 400 | 10 | 0 | 5 |

Smaller type is restricted to concise labels. Body disclaimer text meets the guideline 10 pt minimum. The explicitly requested uppercase cover headings are retained. SemiBold is the maximum weight.

### Baselines measured from the audited PDF

These measurements remove the ambiguity between a CSS line box and a ReportLab baseline. Coordinates below are top-of-page to baseline, not glyph top. Use the nominal font sizes above; PDF font sizes can differ by less than 0.005 pt due to Chromium's quantization. Target overlay agreement within **0.2 mm** for glyph placement.

| Text | x mm | Baseline from top mm | Alignment |
|---|---:|---:|---|
| Header market string | 158.514 | 19.039 | Right at 194 |
| CORPORATE GIFTS | 16 | 45.762 | Left |
| PRODUCT | 15.4 | 66.135 | Left |
| CATALOGUE | 15.4 | 86.508 | Left |
| Subtitle | 16 | 98.679 | Left |
| Promise | 16 | 106.881 | Left |
| KSA CATALOGUE / PREPARED / STOCK UPDATED | 30 / 87 / 144 | 259.810 | Left |
| All three facts values | 30 / 87 / 144 | 266.160 | Left |
| Disclaimer line 1 | 12 | 279.389 | Left |
| Disclaimer line 2 | 12 | 284.152 | Left |
| Website | 157.051 | 291.560 | Right at 198 |

The measured second disclaimer baseline includes the browser's line-layout rounding; use the listed baselines to match the proof. Do not derive the second line from glyph bounding boxes.

For subtitle fixtures, `Saudi Arabia` begins at x 16, `KSA` at x 60.809, and `2026` at x 78.643 mm. Separators are middle dots, with 2.8 mm left/right margins. On dynamic updates, calculate widths using Poppins plus tracking and these margins; do not retain fixture x coordinates when the preceding string changes. Promise separators are vertical bars with 1.6 mm margins. The header uses literal spaced middle dot text and right alignment.

ReportLab tracked text must use a text object and `setCharSpace`. Compute visual string width as font advances plus tracking between glyphs; account for the browser's trailing CSS letter-spacing when matching right-aligned strings. Use the fixture coordinates as an overlay check. Do not replace letter spacing with literal spaces.


## Metadata band and footer details

The metadata text retains its previous baselines and x coordinates. The surrounding band gains breathing room: x=12, top=253.2, w=186, h=20.2 mm, corner radius=4 mm, white fill at alpha .90.

- Column starts: 12, 69, 126 mm; widths: 57, 57, 72 mm.
- Text x: 30, 87, 144 mm; label baseline from top: **259.810 mm**; value baseline: **266.160 mm**.
- Label line box starts at 257.25 mm. Column top padding is 4.05 mm; value gap is 1.1 mm after a 3.8 mm label line box.
- Icons: x=17, 74, 131 mm; top=259.1 mm; size 8 x 8 mm. Extract the existing inline cube/calendar/clock SVGs. Their viewBox is 24 x 24, stroke 1.6, round caps/joins, Elite Orange. Never substitute emoji.
- Circular icon grounds: x=14.5, 71.5, 128.5 mm; top=256.6 mm; diameter 13 mm; white alpha .95.
- Dividers: x=69 and 126 mm; top=257.3 mm; w=.25 mm, h=12 mm; Line colour.
- Band shadow contains three rounded rectangles in a group at x=10.8, top=252.4 mm. Relative `(x,top,w,h,radius,alpha)` values: `(0,1.4,188.4,20.2,5.2,.022)`, `(.6,.8,187.2,20.2,4.6,.026)`, `(1.2,.2,186,20.2,4,.018)`. All use `#A7917E`. Draw these as vector fills with alpha, not a blur or raster shadow. Their deliberately low opacity avoids a dashboard-like elevated card.
- Footer positions and text are unchanged; disclaimer remains 10 pt. Line 1 is `Quantities reflect the stock update shown above and are not reserved.` Line 2 is `Confirm availability before committing to a quantity.`
- The website remains real linked text, right-aligned at x=198 mm, with no printed underline.

## Hero geometry and replacement contract

The existing `.cover-hero` box is unchanged: **(0,107,210,143.5546875) mm**. Only merchandise, plant and stone staging are inside its PNG. Page logo, title, market, promise, watermark, facts, disclaimer and website remain independent editable elements.

The source arrangement comes from the user's preferred 1024 x 1536 screenshot, using original photo coordinates x=0..1024, y=575..1275. The previous cleaned, unbranded hero is the base; it had already removed the screenshot's inaccurate product marks and watermark using deterministic masking/texture cloning. This refinement removes remaining pale fragments along the upper backpack cutout, preserves the real object/contact shadows, and applies seven accurate source-PNG marks. No person or unrelated text is taken from the company-profile Giveaways page.

The base-photo crop is **1024 x 700**. The composite is **4096 x 2800 RGBA** to antialias the replacement PNG branding at 4x. This increases brand-artwork precision; it does **not** invent extra photographic detail. Effective original photo detail is about **123.86 ppi** at 210 mm width. A genuinely higher-resolution approved source remains preferable for production print. The page audit is 300 dpi; the logo-sheet crops use a 600 dpi page render.

The bottom 20 original source rows (hero y=680..699, page y=246.453..250.555 mm) blend photograph RGB linearly into `#F4F2F0`, with alpha fixed at 255. This is baked into the replaceable hero, prevents the orange field showing through the floor, and joins the lower information band softly. It is not an extra shadow. The rest of the asset preserves transparency around product silhouettes.

For future replacement, retain the exact box and aspect ratio **1024:700**. Selected Jasani products, a static approved image or a deterministic collage may replace the hero without changing the grid. Keep large tote/backpack mass in the middle/back and journals/bottle/power bank in the foreground. Do not move the page title or footer. Maintain the clear area above the merchandise apex, roughly y=108 mm. No reference label should be reintroduced on the final cover.

## PRODUCT BRANDING / MOCKUP IMPLEMENTATION

There are **seven visible product applications: one full lockup and six symbols**. The only full lockup is the tote, where the final displayed width is about 43.48 mm and the wordmark remains legible. Smaller cover applications use the symbol. All items use a single colour; none uses the full-colour logo on textile, metal or an orange object. These are print mockups, not claims of a particular supplier's manufacturing process. No artificial chrome, embossed bevel or coloured engraving infill was added.

### Immutable artwork source and embedded manifest

Every visible product mark originates from the same source PNG as the main logo: `D:\Elite Marcom\Elite Marcom.4 (1)d.png`, SHA-256 `38cb42d7034a0bec3082aa9dab27afc66d4eea8c2d8a78d3a13e0c57ecfeaeb7`. There are no remaining SVG logo variants in this version.

The HTML includes an inert `<script type="application/json" id="product-branding-manifest">` with three monochrome **PNG variants** as base64, their PNG and alpha hashes, source dimensions, crop/padding, and the full source hash. For each product it records the quadrilateral, 3x3 homography, cover bounding box, base opacity, material treatment and projected-alpha digest. It also binds the displayed hero PNG to its SHA-256.

`full-navy` copies the complete **1629 x 518** source alpha without resampling and sets RGB to `#02004C`. `symbol-white` and `symbol-navy` use the exact 503 x 518 symbol-alpha crop and 518-square canvas described above, setting RGB to `#FFFFFF` or `#02004C`. Every alpha pixel is compared against the source before projection. No individual shape is edited, and there is no separate horizontal/vertical stretch before whole-artwork surface placement.

The mask's source pixels define the geometry. Lighting changes only the printed ink appearance. **Never generate, redraw, trace or re-typeset any logo.** Use the already-composited hero for a routine ReportLab translation.

### Applications and final cover bounding boxes

Boxes below are projected source-viewBox bounds `(x, top, width, height)` in cover millimetres. Actual painted pixels can be slightly inset within those boxes because of the source PNG's transparent pixels. No part of a logo is unintentionally cropped.

| Product | Artwork | Source ink | Cover box mm | Base opacity | Surface treatment |
|---|---|---|---|---:|---|
| Backpack | Symbol | #FFFFFF | 46.963, 151.707, 11.074, 11.074 | 0.90 | single-colour matte white textile print |
| Tote | Full | #02004C | 105.615, 162.166, 43.477, 13.825 | 0.91 | single-colour navy textile print |
| Bottle | Symbol | #02004C | 18.457, 199.080, 11.279, 11.484 | 0.91 | single-colour navy print on the narrow, front-facing cylindrical area |
| Navy notebook | Symbol | #FFFFFF | 61.523, 196.004, 14.561, 13.125 | 0.89 | single-colour white matte print on textured cover |
| Orange notebook | Symbol | #FFFFFF | 156.475, 204.207, 10.664, 10.664 | 0.91 | single-colour white matte print on textured cover |
| Power bank | Symbol | #FFFFFF | 127.148, 223.279, 9.639, 9.023 | 0.88 | single-colour white pad print |
| Pen | Symbol | #FFFFFF | 100.488, 198.875, 2.871, 2.871 | 0.88 | single-colour white micro print; small symbol only |

### Exact placement quadrilaterals

Coordinates below are in the original **1024 x 1536 screenshot**, top-left origin, ordered **TL, TR, BR, BL**. To obtain the 4096 x 2800 hero-composite coordinates, map `(x,y)` to `(4*x, 4*(y-575))`. To obtain page coordinates, map to `(x*210/1024, 107+(y-575)*210/1024)` mm.

| Product | Source-photo quadrilateral |
|---|---|
| Backpack | (229, 795); (279, 793); (283, 845); (232, 847) |
| Tote | (515, 844); (727, 844); (726, 911.413); (515, 911.413) |
| Bottle | (90, 1024); (145, 1024); (145, 1080); (90, 1080) |
| Navy notebook | (311, 1009); (371, 1011); (361, 1073); (300, 1071) |
| Orange notebook | (766, 1049); (815, 1049); (812, 1101); (763, 1101) |
| Power bank | (626, 1142); (667, 1144); (661, 1186); (620, 1184) |
| Pen | (492, 1023); (504, 1025); (502, 1037); (490, 1035) |

The backpack has a mild trapezoidal surface projection. The tote is almost frontal with subtle perspective taper. The bottle uses the narrow central face, avoiding an exaggerated cylindrical wrap; the source is applied as one plane. Both notebooks and the power bank follow the photographed cover/front lean. The pen uses a roughly 9.46-degree whole-symbol rotation with the barrel and a tiny practical footprint; the full wordmark is intentionally not used there. No part of the source mask is edited individually.

### Deterministic compositing recipe

1. Begin with the clean hero derived from the supplied reference. Do not overlay correct marks on top of the screenshot's inaccurate marks. For the existing master translation, simply decode the already-composited `.hero-artwork`; no retouching or recompositing is required.
2. Decode the embedded monochrome PNG variants. The full lockup is 1629 x 518 px; each padded symbol is 518 x 518 px. Their alpha is copied pixel-for-pixel from the source, then RGB is set to one approved ink. No intermediate tracing or SVG conversion is permitted.
3. Create a 4096 x 2800 compositing canvas from the 1024 x 700 clean hero with Lanczos resampling. This is antialiasing for newly applied source artwork, not a claim of higher-resolution photography.
4. Solve the whole-artwork homography from source viewBox corners `(0,0),(w,0),(w,h),(0,h)` to each listed quad. Inverse-map destination pixels to the source raster with bicubic sampling. Do not scale x/y independently first. Source coordinate canvases are 1629 x 518 for full and 518 x 518 for symbol; one unit is one original variant pixel.
5. Blend only through the projected source alpha. Let `L` be product-patch luminance in 0..255. Let `low=GaussianBlur(L, radius=10 composite pixels)`, and `detail=L-low`. For white artwork, the lit single-colour ink is `clip(242 + .45*detail + .065*(low-100),225,250)` in all RGB channels. For navy it is `clip([2,0,76] + .12*detail,0,255)`. This allows the photograph's texture and light to remain visible through print.
6. Set `a = projected_source_alpha * item_base_opacity`, with alpha normalized to 0..1. Composite normally: `result = surface*(1-a) + ink*a`. Keep the existing product/silhouette alpha. Do not add a shadow behind a logo or simulate chrome.
7. Store the entire branded hero as one independent PNG. Keep page data and the main official logo outside it. The per-product image treatment may be baked into this replaceable asset for ReportLab; no browser blend mode is needed.

Every recorded homography was checked for inverse reprojection error below 1e-8. The hash of each warped source alpha is recorded, and source geometry was validated independently from the composite. Enlarged final-PDF crops were reviewed for every item: correct symbol shape, full-lockup spacing, single-colour treatment, natural orientation, material integration and no remaining inaccurate source marks.

### Product audit decisions

- Main page logo: pass, byte-identical PNG source, original aspect ratio and clean wordmark in the proof.
- Backpack: pass, white source symbol follows the textile face; weave remains visible.
- Tote: pass, complete mono navy lockup; original source spacing and clean filled letterforms retained.
- Bottle: pass, navy symbol centred on the front; no two-tone metal treatment or excessive wrap.
- Navy notebook: pass, white symbol follows the sloped cover plane.
- Orange notebook: pass, white symbol; no full-colour application on orange.
- Power bank: pass, white symbol follows the front face; full lockup avoided at this size.
- Pen: pass, white symbol only. Its small scale limits detail at normal page size, but the enlarged QA crop and source-projection check preserve recognizable source geometry.

The logo audit sheet is for QA only and must not be imported as a catalogue page.

## Dynamic content contract


Fixture values are copied from the approved reference. They are **not live inventory, a new stock sync, or a reservation**. Dates have intentionally not been replaced by an inferred current stock time.

| `data-field` | Initial value | Occurrences | Update rule |
|---|---|---:|---|
| `market` | Saudi Arabia | 2 | Header and subtitle; update both |
| `country` | KSA | 3 | Header, subtitle and catalogue label; update all |
| `year` | 2026 | 1 | Four-digit catalogue year |
| `product-count` | 1 product | 1 | Include correct singular/plural text |
| `prepared-date` | 08 Oct 2026 | 1 | `DD MMM YYYY`; also update the `<time datetime>` ISO date |
| `stock-updated` | 08 Oct 2026 · 15:01 | 1 | `DD MMM YYYY · HH:mm`; ISO datetime uses the actual time-zone offset, fixture `+03:00` |
| `website` | www.elitemarcom.com | 1 | Update visible text and link `href` consistently |

Update real text nodes by field name; do not replace the main page with a raster. All seven distinct dynamic fields were verified as DOM text, and their fixture values were found in the generated PDF's extractable text.

Preflight every update with actual font measurements. Values must fit their existing cells and remain on one line; no silent ellipsis, clipping, new rows or automatic shrinkage. Available value widths are approximately 37, 37 and 52 mm (column width minus 18 mm left and 2 mm right padding). If a new value does not fit, normalize its approved display format or request a deliberate design revision; do not move the grid. This KSA master does not imply support for unlimited translated text lengths.



## Fixed versus permitted changes

After approval, lock page geometry; main PNG asset and clear space; margins; title copy, positions, fonts, sizes and tracking; palette and contrast conditions; curved orange path and shading; watermark source/position/opacity; hero bounding box; facts-band treatment, geometry and baselines; disclaimer and footer; paint order and spacing.

Permitted catalogue-data changes remain the seven `data-field` values, updating repeated instances and corresponding `datetime`/`href` attributes consistently. The hero may be replaced inside its unchanged box, using approved imagery and accurate source-derived product marks. Never regenerate product logos. A field that does not fit must trigger formatting validation rather than silently shrinking fonts, clipping, moving components or changing the page geometry.

## Translation procedure and reusable coordinate helpers

1. Read this map and the HTML; do not trace the audit PNG or flatten the page.
2. Set ReportLab canvas to `(210*mm,297*mm)` and register Poppins 400/500/600.
3. Draw background and orange contour using standard clipping paths and axial shadings with the exact endpoints/stops above.
4. Decode `.brand-logo`, assert replacement PNG SHA-256, and use `ImageReader(BytesIO(png_bytes))` with `canvas.drawImage(..., mask='auto')` at (16,12,57,18.125230203) mm in top-origin coordinates. Preserve its native aspect ratio. Do not vector-trace it.
5. Decode the source-alpha white watermark PNG and draw it at (126,39,96,96) mm with `setFillAlpha(.075)` inside the orange-field clip, using `mask='auto'`. Wrap clip and transparency changes in `saveState()` / `restoreState()`.
6. Decode the existing branded PNG and draw it with `ImageReader` and `mask='auto'` in the locked hero box. This reproduces all seven audited mockups without new compositing. The manifest provides a deterministic basis if a later authorized image edit is needed.
7. Draw vector band-shadow rectangles, rounded band and icon circles with their explicit alpha values; draw existing icons and live metadata text at the retained baselines.
8. Draw the unchanged 10 pt disclaimer and website. Output exactly one A4 page.
9. Render that ReportLab result at 300 dpi and compare against the PDF proof, including every brand application. Target glyph/geometry alignment within 0.2 mm. Do not restore a reference-render label.

```python
from reportlab.lib.units import mm
PAGE_W, PAGE_H = 210*mm, 297*mm

def rect_from_top(x, top, width, height):
    return x*mm, PAGE_H-(top+height)*mm, width*mm, height*mm

def y_from_top(value_mm):
    return PAGE_H-value_mm*mm

# Orange contour: beginPath/moveTo/curveTo/lineTo/close.
# Shading endpoints: (112*mm, y_from_top(0)) -> (210*mm, y_from_top(65)).
# Replacement PNG logo height: 57 * 518 / 1629 mm; never independently stretched.
```

The decorative field and metadata icons still use their original SVG coordinate systems: do not invert their y axes twice. Text tracking requires `setCharSpace`, not extra literal spaces. The exact hero can be reused as supplied, while the primary logo and watermark are separate transparent PNG assets. The field, icons and live text retain vector/text output.

## Audit and proof production

The final HTML was rendered in Chromium after all embedded fonts/images loaded, with print backgrounds enabled, scale 1, CSS page size, and no browser headers/footers. It issued **zero HTTP/HTTPS requests** and zero page errors. Existing font, semantic-date and link systems remain intact.

Chromium quantizes its raw PDF page box to 594.95996 x 841.91998 pt. As in the existing master, pypdf sets MediaBox/CropBox/TrimBox to exact ISO A4 without resampling artwork or re-typesetting it. The correction is at most 0.112 mm. ReportLab should use exact A4 directly and needs no such correction. Final measured dimensions are 210 x 297 mm within PDF serialization precision.

The final PDF was rendered at 300 dpi for the cover audit and 600 dpi for logo-detail review. The full page, thumbnail, main logo, seven product marks, merchandise cutouts and footer were inspected. A side-by-side comparison with the preferred screenshot and previous technical master was made, along with the brand palette/typography and merchandise rules.

| Mandatory check | Result |
|---|---|
| Final HTML -> PDF -> 300 dpi PNG | Pass |
| Exactly one A4 page, all three page boxes | Pass |
| Full page and thumbnail | Pass |
| Main logo at high zoom | Pass; clean PNG pixels and native aspect ratio |
| Every product at high zoom | Pass; seven inspected applications |
| Main logo replacement integrity | Pass; embedded bytes equal the new source PNG, and replacement SHA-256 matches |
| Merchandise source identity | Pass; one full variant and two symbol colour variants validated |
| No inaccurate/generated logos remain | Pass; prior marks removed before exact-source application |
| PRODUCT / CATALOGUE hierarchy | Pass; retained scale, bright orange on pure white |
| Orange field | Pass; restrained native SVG shading and smooth diagonal contour |
| Watermark geometry | Pass; original symbol alpha pixels, with transparent centring padding |
| Hero edges / layering | Pass; repaired backpack edge fragments and retained photographic staging |
| Metadata band | Pass; soft treatment with retained text baselines |
| Clipping / overlap / page overflow | Pass; intentional bleed crops only; text inside page |
| Seven named dynamic fields extractable | Pass; real DOM text and PDF text |
| No visible reference-render label | Pass; absent from HTML and PDF page text |
| ReportLab map matches refined source | Pass; explicit paths, gradients, alpha, coordinates and raster treatment |
| No external render requests | Pass; all fonts/images/source-artwork data embedded |

## Remaining differences and compromises

The preferred screenshot's approximate two-tone merchandise marks have been replaced with accurate one-colour applications. Only the tote uses the full lockup; the smaller items use the symbol. The user-authorized PNG replacement removes the defective SVG join above the A. The main logo now uses the clean original PNG at approximately 726 ppi, rather than vector logo paths.

The field is smoother and more restrained than the reference's dramatic lighting. The photo still derives from the supplied reference: no new camera angle, physical merchandise sample or higher-detail product photography has been fabricated. The 4x compositing canvas improves the applied branding edges only. The main title remains Poppins SemiBold rather than the screenshot's heavier lettering, and bright orange type remains wholly on white for readability. Footer body stays at 10 pt, making it more readable than the reference.

The pen mark is deliberately tiny; it is a visual mockup, not a manufacturing specification or confirmation of supplier print tolerances. There are no additional mug/pouch products because the approved arrangement already has seven appropriate branding surfaces. The cover remains a focused refinement of the existing arrangement.

## File integrity at delivery

`Elite_Marcom_Catalogue_Cover_MASTER.html` SHA-256: `9d1170878ff80ad305203c5986f37fbb5ca1bc495833c4b4bec7b25c8cf19208`

`Elite_Marcom_Catalogue_Cover_MASTER.pdf` SHA-256: `c0d4025731be572799015b3eb46d2a515c0bfe248ba5c92af935b55f4b19bcf6`

`Elite_Marcom_Catalogue_Cover_MASTER_AUDIT.png` SHA-256: `a7a7505f5ac971307c822f95616b6e62e181eaec1fd95f68dab6ed1096fbbacd`

`Elite_Marcom_Catalogue_Cover_LOGO_AUDIT.png` SHA-256: `6b44b63a352fa2c13148b7cf960fd41df8acbdd495c946e5c94b3cac1c844fa4`

Document hashes change when catalogue data change. The replacement source PNG hash and the source-alpha derivation must remain fixed. The HTML embeds every required image/font; the website link does not make a request during rendering.

## Exact product projection matrices

These matrices map the monochrome variant pixel coordinates to the original screenshot coordinates. Multiply column vector `(x,y,1)` by H and divide by its third component. Full artwork uses a 1629 x 518 canvas; symbols use a 518-square canvas. They are also embedded in the HTML manifest.

### Backpack: complete source-to-photo matrix

```json
[[0.09612012657125436, -0.002963973640665369, 229.0], [-0.0050120474932504305, 0.06842105263157895, 795.0], [-1.451505210903707e-06, -3.773913548349638e-05, 1.0]]
```

Warped alpha SHA-256: `8dcca4f6bbdd0e8d0f4e3cf191456f578f8e83964d5e06c87c6472db40515311`.

### Tote: complete source-to-photo matrix

```json
[[0.13014119091467158, 0.004711888598144632, 515.0], [0.0, 0.1384787907921462, 844.0], [0.0, 9.149298248824316e-06, 1.0]]
```

Warped alpha SHA-256: `aefe05d907bf397bebdd4b8a30024c1cb30637ff9fc724086784e7f3c982a206`.

### Bottle: complete source-to-photo matrix

```json
[[0.10617760617760617, 0.0, 90.0], [0.0, 0.10810810810810811, 1024.0], [0.0, 0.0, 1.0]]
```

Warped alpha SHA-256: `ff74d48842f473d4d49d042fed99e0f6302b14a89b9b7e6a3a736a73addb1e60`.

### Navy notebook: complete source-to-photo matrix

```json
[[0.1162068734399087, -0.03067984945943915, 311.0], [0.004887693735668547, 0.08597486793173273, 1009.0], [1.0155191638621415e-06, -3.148109407972638e-05, 1.0]]
```

Warped alpha SHA-256: `41293121f8ffa8a91290ba5d493a3b8261f09df877ae2d08dddaeb7c39aba2b5`.

### Orange notebook: complete source-to-photo matrix

```json
[[0.0945945945945946, -0.005791505791505791, 766.0], [0.0, 0.10038610038610038, 1049.0], [0.0, 0.0, 1.0]]
```

Warped alpha SHA-256: `d0f256ce89a063f7f1ca1ecb9c0aef347326413863688b88adf33fda752c33af`.

### Power bank: complete source-to-photo matrix

```json
[[0.07915057915057915, -0.011583011583011582, 626.0], [0.003861003861003861, 0.08108108108108109, 1142.0], [0.0, 0.0, 1.0]]
```

Warped alpha SHA-256: `3c03f9be5df5439e86fc1aa9916d4c6981af3f145f157b9ffde670bda246547e`.

### Pen: complete source-to-photo matrix

```json
[[0.023166023166023165, -0.003861003861003861, 492.0], [0.003861003861003861, 0.023166023166023165, 1023.0], [0.0, 0.0, 1.0]]
```

Warped alpha SHA-256: `734f2664b152a172df0c4c1fd0add4ad979f8226c5a503550b4725171b12f38e`.

## Replacement source variant hashes

- `full-navy` PNG: `b505e57c2a44cffafc8b9a364262cb3abfde6cea3248a5686e6c288cea739240`; alpha: `cd5a9fbaa240fc75bb6636685ef70e37144fedd5e46641797ba7d0980310ec5e`.
- `symbol-white` PNG: `5e0ce1aebce13876a81b88aa63059aa44fa97b15d1425a4f6bc908979c87c3ec`; alpha: `8a73aab1c1fbc1789dd960ec9aa3c8ae8dbaeb62e854ae6f62629db25e68d1fa`.
- `symbol-navy` PNG: `e6c7a24823df84ea2cec733f0faee6efc89a91f8b5ff2983437b8b8a0ac6b5ba`; alpha: `8a73aab1c1fbc1789dd960ec9aa3c8ae8dbaeb62e854ae6f62629db25e68d1fa`.
