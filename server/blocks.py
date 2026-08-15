"""Elite Marcom admin — building blocks the editor can add to the site.

Three things live here, and they share one rule: the HTML is written by us,
never by an admin. The visual editor lets someone *place* a block and then
edit the text inside it (through the design layer's validated text
overrides), so nothing an admin types is ever parsed as markup here.

- SECTION_TEMPLATES — ready-made page sections, in the site's own classes.
- SOCIAL_NETWORKS   — footer profile links, rendered from settings URLs.
- page_shell()      — the starting HTML for a brand-new page, derived from a
                      live page so the header, footer and script chain can
                      never drift from the rest of the site.
"""
from __future__ import annotations

import html as html_mod
import re

from . import config

# ---------------- section templates ----------------

# Every template is one <section class="section">…</section> with the classes
# the site already styles. Text nodes carry no data-em key: the editor makes
# them editable by path, which is what lets a copy of a block be edited
# independently of the original.

_TEMPLATES: list[dict] = [
    {
        "id": "heading-text",
        "label": "Heading & paragraph",
        "hint": "A section marker, a headline and a lead paragraph.",
        "html": """
  <div class="container">
    <p class="section-marker reveal" data-reveal="fade-in">New section</p>
    <h2 class="reveal" data-reveal="fade-up">A headline that says what this section is about</h2>
    <p class="lede reveal" data-reveal="fade-up" data-reveal-delay="80">Replace this paragraph with the story you want to tell. Click any line to edit it, or use the panel on the right to restyle it.</p>
  </div>""",
    },
    {
        "id": "text-image",
        "label": "Text beside an image",
        "hint": "Two columns: copy on the left, a picture on the right.",
        "html": """
  <div class="container">
    <div class="grid-2 grid-2--wide-left">
      <div>
        <p class="section-marker reveal" data-reveal="fade-in">New section</p>
        <h2 class="reveal" data-reveal="fade-up">Put the point of this block here</h2>
        <p class="reveal" data-reveal="fade-up" data-reveal-delay="80">Two or three sentences of supporting copy sit well in this column. Keep it to the one idea the picture illustrates.</p>
        <p class="text-muted reveal" data-reveal="fade-up" data-reveal-delay="140">A quieter second paragraph for detail that matters but should not compete with the first.</p>
      </div>
      <figure class="media-frame media-frame--sheen reveal" data-reveal="zoom-up" data-parallax="0.06" style="aspect-ratio:4/3;">
        <img src="/assets/portfolio/aces-pavilion-live.webp" alt="Replace this image" width="502" height="335" loading="lazy">
      </figure>
    </div>
  </div>""",
    },
    {
        "id": "image-text",
        "label": "Image beside text",
        "hint": "The same two columns, with the picture on the left.",
        "html": """
  <div class="container">
    <div class="grid-2 grid-2--wide-right">
      <figure class="media-frame media-frame--sheen reveal" data-reveal="zoom-up" data-parallax="0.06" style="aspect-ratio:4/3;">
        <img src="/assets/portfolio/aces-pavilion-live.webp" alt="Replace this image" width="502" height="335" loading="lazy">
      </figure>
      <div>
        <p class="section-marker reveal" data-reveal="fade-in">New section</p>
        <h2 class="reveal" data-reveal="fade-up">Put the point of this block here</h2>
        <p class="reveal" data-reveal="fade-up" data-reveal-delay="80">Two or three sentences of supporting copy sit well in this column. Keep it to the one idea the picture illustrates.</p>
      </div>
    </div>
  </div>""",
    },
    {
        "id": "cards-3",
        "label": "Three cards",
        "hint": "A row of three titled cards — services, benefits, steps.",
        "html": """
  <div class="container">
    <p class="section-marker reveal" data-reveal="fade-in">New section</p>
    <h2 class="reveal" data-reveal="fade-up">Three things worth spelling out</h2>
    <dl class="values-grid">
      <div class="value reveal" data-reveal="fade-up">
        <dt>First card</dt>
        <dd>One or two sentences explaining what this card is for. Click the title or the text to change it.</dd>
      </div>
      <div class="value reveal" data-reveal="fade-up" data-reveal-delay="80">
        <dt>Second card</dt>
        <dd>Keep the three cards roughly the same length — the row reads better when they balance.</dd>
      </div>
      <div class="value reveal" data-reveal="fade-up" data-reveal-delay="160">
        <dt>Third card</dt>
        <dd>Duplicate this whole section from the Sections panel if you need six cards instead of three.</dd>
      </div>
    </dl>
  </div>""",
    },
    {
        "id": "steps",
        "label": "Numbered steps",
        "hint": "A four-step process strip, like the one on About.",
        "html": """
  <div class="container">
    <p class="section-marker reveal" data-reveal="fade-in">New section</p>
    <h2 class="reveal" data-reveal="fade-up">How it works</h2>
    <div class="process reveal" data-reveal="fade-in" data-reveal-delay="120">
      <div class="process__line" aria-hidden="true"></div>
      <ol class="process__grid" style="list-style:none;margin:0;padding:0;">
        <li class="process__step"><span class="process__dot" aria-hidden="true"></span>
          <span class="process__num">STEP 01</span><h3>First step</h3>
          <p>What happens first, in one short sentence.</p></li>
        <li class="process__step"><span class="process__dot" aria-hidden="true"></span>
          <span class="process__num">STEP 02</span><h3>Second step</h3>
          <p>What happens next, in one short sentence.</p></li>
        <li class="process__step"><span class="process__dot" aria-hidden="true"></span>
          <span class="process__num">STEP 03</span><h3>Third step</h3>
          <p>What happens after that, in one short sentence.</p></li>
        <li class="process__step"><span class="process__dot" aria-hidden="true"></span>
          <span class="process__num">STEP 04</span><h3>Fourth step</h3>
          <p>How the work is handed over, in one short sentence.</p></li>
      </ol>
    </div>
  </div>""",
    },
    {
        "id": "stats",
        "label": "Numbers row",
        "hint": "Three or four figures with labels underneath.",
        "html": """
  <div class="container">
    <p class="section-marker reveal" data-reveal="fade-in">New section</p>
    <h2 class="reveal" data-reveal="fade-up">The numbers behind it</h2>
    <div class="stat-row reveal" data-reveal="fade-up" data-reveal-delay="80">
      <div class="stat"><span class="stat__num">15+</span><span class="stat__label">Years delivering</span></div>
      <div class="stat"><span class="stat__num">400</span><span class="stat__label">Projects completed</span></div>
      <div class="stat"><span class="stat__num">2</span><span class="stat__label">Regional offices</span></div>
      <div class="stat"><span class="stat__num">24h</span><span class="stat__label">Response time</span></div>
    </div>
  </div>""",
    },
    {
        "id": "bullets",
        "label": "Checklist",
        "hint": "A heading with a bulleted list of points.",
        "html": """
  <div class="container">
    <div class="grid-2 grid-2--wide-left">
      <div>
        <p class="section-marker reveal" data-reveal="fade-in">New section</p>
        <h2 class="reveal" data-reveal="fade-up">What is included</h2>
        <p class="lede reveal" data-reveal="fade-up" data-reveal-delay="80">A short line introducing the list.</p>
      </div>
      <ul class="diff-list reveal" data-reveal="fade-up" data-reveal-delay="120">
        <li>The first thing this covers.</li>
        <li>The second thing this covers.</li>
        <li>The third thing this covers.</li>
        <li>The fourth thing this covers.</li>
      </ul>
    </div>
  </div>""",
    },
    {
        "id": "quote",
        "label": "Quote",
        "hint": "A pulled-out client quote with attribution.",
        "html": """
  <div class="container">
    <figure class="media-frame reveal" data-reveal="fade-up" style="padding:clamp(28px,4vw,54px);">
      <blockquote style="margin:0;">
        <p class="lede">“Replace this with something a client actually said about the work. A quote earns its space when it says what a paragraph of ours cannot.”</p>
      </blockquote>
      <figcaption class="text-muted" style="margin-top:18px;">Name, Job title — Company</figcaption>
    </figure>
  </div>""",
    },
    {
        "id": "cta",
        "label": "Call to action",
        "hint": "A closing block with a headline and two buttons.",
        "html": """
  <div class="container center">
    <h2 class="reveal" data-reveal="fade-up">Ready to talk about your project?</h2>
    <p class="lede reveal" data-reveal="fade-up" data-reveal-delay="80" style="margin-inline:auto;">Tell us what you are planning and we will come back with an approach, a timeline and a number.</p>
    <p class="page-hero__actions reveal" data-reveal="fade-up" data-reveal-delay="160">
      <a class="btn btn--primary" href="/contact.html">Start a project</a>
      <a class="btn btn--ghost" href="/projects.html">See our work</a>
    </p>
  </div>""",
    },
    {
        "id": "banner",
        "label": "Wide image banner",
        "hint": "One full-width picture with a caption.",
        "html": """
  <div class="container">
    <figure class="media-frame media-frame--sheen reveal" data-reveal="zoom-up" style="aspect-ratio:21/9;">
      <img src="/assets/portfolio/aces-pavilion-live.webp" alt="Replace this image" width="1380" height="591" loading="lazy">
    </figure>
    <p class="text-muted center reveal" data-reveal="fade-in" data-reveal-delay="80" style="margin-top:16px;">A caption for the picture above.</p>
  </div>""",
    },
    {
        "id": "spacer",
        "label": "Blank block",
        "hint": "An empty section — a heading and one line, to build from scratch.",
        "html": """
  <div class="container">
    <h2 class="reveal" data-reveal="fade-up">New block</h2>
    <p class="reveal" data-reveal="fade-up" data-reveal-delay="80">Write anything here.</p>
  </div>""",
    },
    {
        "id": "blank",
        "label": "Blank section",
        "hint": "Nothing at all — add the headings, pictures and buttons yourself.",
        # The only template whose body is empty: elements are added into it one
        # at a time from the editor's element library, and each one is our
        # markup exactly like a section template is.
        "html": """
  <div class="container">
    <div class="em-stack" data-em-slot="1"></div>
  </div>""",
    },
]

TEMPLATES = {t["id"]: t for t in _TEMPLATES}


def template_list() -> list[dict]:
    """What the editor shows in its "Add section" picker."""
    return [{"id": t["id"], "label": t["label"], "hint": t["hint"]} for t in _TEMPLATES]


# ---------------- elements: what goes INSIDE a blank section ----------------
# Same rule as the section templates: every tag is written here. The editor
# places one and then edits its text, picture, link and styling through the
# design layer, so nothing an admin types is ever parsed as markup.

_ELEMENTS: list[dict] = [
    {
        "id": "heading",
        "label": "Heading",
        "hint": "A section headline.",
        "html": '<h2 class="reveal" data-reveal="fade-up">A new headline</h2>',
    },
    {
        "id": "subheading",
        "label": "Small heading",
        "hint": "A smaller heading for a sub-part.",
        "html": '<h3 class="reveal" data-reveal="fade-up">A smaller heading</h3>',
    },
    {
        "id": "eyebrow",
        "label": "Section marker",
        "hint": "The small line that sits above a headline.",
        "html": '<p class="section-marker reveal" data-reveal="fade-in">New section</p>',
    },
    {
        "id": "text",
        "label": "Paragraph",
        "hint": "A block of copy.",
        "html": ('<p class="reveal" data-reveal="fade-up">Replace this paragraph with what you '
                 'want to say. Click it in the page to edit the words.</p>'),
    },
    {
        "id": "lede",
        "label": "Lead paragraph",
        "hint": "A larger opening paragraph.",
        "html": ('<p class="lede reveal" data-reveal="fade-up">A larger opening line that '
                 'introduces what follows.</p>'),
    },
    {
        "id": "image",
        "label": "Image",
        "hint": "One picture in the site's frame.",
        "html": ('<figure class="media-frame media-frame--sheen reveal" data-reveal="zoom-up" '
                 'style="aspect-ratio:16/9;">'
                 '<img src="/assets/portfolio/aces-pavilion-live.webp" alt="Replace this image" '
                 'width="1000" height="563" loading="lazy"></figure>'),
    },
    {
        "id": "video",
        "label": "Video",
        "hint": "A YouTube video, played without cookies.",
        # privacy-preserving host, and the id is replaced through the editor's
        # validated attribute path — never by pasting an embed
        "html": ('<div class="em-video reveal" data-reveal="fade-up">'
                 '<iframe src="https://www.youtube-nocookie.com/embed/lFhAiGLjoMo?rel=0" '
                 'title="Video" loading="lazy" allowfullscreen '
                 'referrerpolicy="strict-origin-when-cross-origin" '
                 'allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; '
                 'picture-in-picture; fullscreen"></iframe></div>'),
    },
    {
        "id": "button",
        "label": "Button",
        "hint": "A primary call to action.",
        "html": ('<p class="reveal" data-reveal="fade-up">'
                 '<a class="btn btn--primary" href="/contact.html" data-magnetic>'
                 'Start the conversation</a></p>'),
    },
    {
        "id": "button-ghost",
        "label": "Outline button",
        "hint": "A quieter secondary button.",
        "html": ('<p class="reveal" data-reveal="fade-up">'
                 '<a class="btn btn--ghost" href="/projects.html">See our work</a></p>'),
    },
    {
        "id": "icon",
        "label": "Icon & line",
        "hint": "A small icon with a line of text beside it.",
        "html": ('<p class="em-iconline reveal" data-reveal="fade-up">'
                 '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
                 'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
                 '<path d="M20 6L9 17l-5-5"/></svg>'
                 '<span>Something worth pointing out</span></p>'),
    },
    {
        "id": "columns-2",
        "label": "Two columns",
        "hint": "Two side-by-side containers to put anything in.",
        "html": ('<div class="grid-2 reveal" data-reveal="fade-up">'
                 '<div><h3>First column</h3><p>Write the left-hand side here.</p></div>'
                 '<div><h3>Second column</h3><p>And the right-hand side here.</p></div></div>'),
    },
    {
        "id": "columns-3",
        "label": "Three columns",
        "hint": "Three side-by-side containers.",
        "html": ('<div class="grid-3 reveal" data-reveal="fade-up">'
                 '<div><h3>One</h3><p>First column.</p></div>'
                 '<div><h3>Two</h3><p>Second column.</p></div>'
                 '<div><h3>Three</h3><p>Third column.</p></div></div>'),
    },
    {
        "id": "card",
        "label": "Card",
        "hint": "A titled card with a line of copy.",
        "html": ('<article class="em-card reveal" data-reveal="fade-up">'
                 '<h3>Card title</h3><p>One or two sentences about it.</p></article>'),
    },
    {
        "id": "cards-row",
        "label": "Row of cards",
        "hint": "Three cards side by side.",
        "html": ('<div class="grid-3 reveal" data-reveal="fade-up">'
                 '<article class="em-card"><h3>First</h3><p>What this one is about.</p></article>'
                 '<article class="em-card"><h3>Second</h3><p>What this one is about.</p></article>'
                 '<article class="em-card"><h3>Third</h3><p>What this one is about.</p></article></div>'),
    },
    {
        "id": "list",
        "label": "Bullet list",
        "hint": "A short list of points.",
        "html": ('<ul class="em-ticks reveal" data-reveal="fade-up">'
                 '<li>First point</li><li>Second point</li><li>Third point</li></ul>'),
    },
    {
        "id": "divider",
        "label": "Divider",
        "hint": "A thin rule between two things.",
        "html": '<hr class="em-divider">',
    },
    {
        "id": "spacer-el",
        "label": "Spacer",
        "hint": "Empty vertical space. Set its height in the panel.",
        "html": '<div class="em-spacer" style="height:48px;" aria-hidden="true"></div>',
    },
]

ELEMENTS = {e["id"]: e for e in _ELEMENTS}


def element_list() -> list[dict]:
    """What the editor shows in its "Add element" library."""
    return [{"id": e["id"], "label": e["label"], "hint": e["hint"]} for e in _ELEMENTS]


def render_element(template_id: str, el_id: str) -> str:
    """One element inside an added section, stamped with the id its editor
    paths hang off — so styling survives the element being reordered."""
    tpl = ELEMENTS.get(template_id)
    if tpl is None:
        return ""
    html = tpl["html"]
    close = html.index(">")
    self_closing = html[close - 1] == "/"
    stamp = f' data-em-el="{el_id}" data-em-elt="{template_id}"'
    return html[:close - (1 if self_closing else 0)] + stamp + html[close - (1 if self_closing else 0):]


_SLOT_RE = re.compile(r'(<div class="em-stack" data-em-slot="1")(></div>)')


def render_section(template_id: str, sec_id: str, children: list[dict] | None = None) -> str:
    """One added section, stamped with the id its editor paths hang off.

    A blank section carries whatever elements were placed in it, in order.
    """
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        return ""
    body = tpl["html"]
    if children:
        inner = "".join(render_element(c["template"], c["id"]) for c in children)
        body = _SLOT_RE.sub(lambda m: m.group(1) + ">" + inner + "</div>", body, count=1)
    return (f'<section class="section" data-em-sec="{sec_id}" data-em-block="{template_id}">'
            f'{body}\n  </section>')


# ---------------- footer social links ----------------

# viewBox 0 0 24 24 throughout so one CSS rule sizes them all.
_ICONS = {
    "instagram": '<rect x="3" y="3" width="18" height="18" rx="5.2" fill="none" stroke="currentColor" '
                 'stroke-width="1.9"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="currentColor" '
                 'stroke-width="1.9"/><circle cx="17.3" cy="6.7" r="1.25"/>',
    "linkedin": '<path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.8v1.7h.05c'
                '.53-.95 1.83-1.95 3.77-1.95C21.4 8.75 22 11.1 22 14.2V21h-4v-6c0-1.43-.03-3.27-2-3.27'
                '-2 0-2.3 1.56-2.3 3.17V21h-4V9Z"/>',
    "facebook": '<path d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.63c-.29-.04-1.28'
                '-.13-2.44-.13-2.42 0-4.06 1.47-4.06 4.18V9.9H7.5V13h2.7v8h3.3Z"/>',
    "x": '<path d="M17.2 3h3.3l-7.2 8.2L21.8 21h-6.5l-5-6.1L4.4 21H1.1l7.7-8.8L1.5 3H8l4.5 5.6L17.2 3Zm'
         '-1.15 16h1.83L7.05 4.9H5.1l10.95 14.1Z"/>',
    # the play triangle is its own filled path, not a subpath cut out of the
    # body — as one path it needed an even-odd fill rule to punch through, and
    # without it the icon rendered as a solid rounded rectangle
    "youtube": ('<rect x="2.5" y="5.5" width="19" height="13" rx="4" '
                'fill="none" stroke="currentColor" stroke-width="1.9"/>'
                '<path d="M10 9l6 3-6 3V9Z" fill="currentColor"/>'),
    "tiktok": '<path d="M16.6 5.82A4.28 4.28 0 0 1 15.54 3h-3.1v12.4a2.59 2.59 0 0 1-2.6 2.5 2.6 2.6 0 0 1 '
              '0-5.2c.27 0 .53.04.78.12v-3.2a5.9 5.9 0 0 0-.78-.05 5.72 5.72 0 1 0 5.72 5.72V9.4a7.35 '
              '7.35 0 0 0 4.28 1.37V7.68a4.29 4.29 0 0 1-3.24-1.86Z"/>',
    "whatsapp": '<path d="M12.04 2C6.6 2 2.2 6.4 2.2 11.84c0 1.74.46 3.44 1.32 4.93L2.05 22l5.36-1.4a9.8 '
                '9.8 0 0 0 4.63 1.18c5.43 0 9.84-4.4 9.84-9.84S17.47 2 12.04 2Zm0 17.98a8.2 8.2 0 0 1-4.17'
                '-1.14l-.3-.18-3.1.81.83-3.02-.2-.31a8.13 8.13 0 0 1-1.25-4.3c0-4.5 3.68-8.17 8.2-8.17a8.16 '
                '8.16 0 0 1 8.18 8.18c0 4.5-3.68 8.13-8.19 8.13Zm4.49-6.09c-.25-.12-1.46-.72-1.68-.8-.23'
                '-.09-.39-.13-.55.12-.17.25-.64.8-.78.97-.14.16-.29.18-.53.06-.25-.12-1.04-.38-1.98-1.22'
                '-.73-.65-1.23-1.46-1.37-1.7-.14-.25-.02-.39.11-.51.11-.11.25-.29.37-.43.12-.15.16-.25'
                '.25-.41.08-.17.04-.31-.02-.43-.06-.12-.55-1.33-.76-1.82-.2-.48-.4-.41-.55-.42h-.47c-.16 '
                '0-.43.06-.65.31-.22.25-.85.83-.85 2.03s.87 2.35.99 2.51c.12.17 1.71 2.61 4.14 3.66.58.25 '
                '1.03.4 1.38.51.58.19 1.11.16 1.53.1.47-.07 1.46-.6 1.66-1.17.21-.58.21-1.07.14-1.17-.06'
                '-.11-.22-.17-.47-.29Z"/>',
    "snapchat": '<path d="M12 2.4c2.66 0 4.55 1.97 4.65 4.72.02.5.02 1 .05 1.48.08.03.25.06.5.06.4 0 .89'
                '-.16 1.19-.3a.75.75 0 0 1 .3-.06c.36 0 .69.24.69.6 0 .4-.34.6-.79.77-.49.2-1.19.4-1.34'
                '.75-.1.24 0 .5.13.75.02.04 1.19 2.68 3.56 3.08.3.05.5.3.5.6 0 .1-.02.2-.06.29-.24.56'
                '-1.29.95-3.17 1.24-.06.1-.13.44-.17.64-.05.23-.1.47-.2.7-.1.26-.3.4-.55.4h-.05c-.15 0'
                '-.35-.03-.6-.08a5 5 0 0 0-.99-.12c-.24 0-.48.02-.72.06-.46.08-.87.37-1.34.7-.67.47-1.43 '
                '1.02-2.6 1.02-1.17 0-1.93-.55-2.6-1.02-.47-.33-.88-.62-1.34-.7a4.4 4.4 0 0 0-.72-.06c'
                '-.4 0-.72.06-.99.12-.25.05-.45.08-.6.08-.3 0-.5-.16-.6-.42-.1-.23-.15-.47-.2-.7-.04-.2'
                '-.1-.54-.17-.64-1.88-.29-2.93-.68-3.17-1.24a.79.79 0 0 1-.06-.3c0-.3.2-.54.5-.59 2.37-.4 '
                '3.54-3.04 3.56-3.08.13-.25.23-.51.13-.75-.15-.35-.85-.55-1.34-.75-.45-.18-.79-.38-.79'
                '-.77 0-.36.33-.6.69-.6.1 0 .2.02.3.06.3.14.79.3 1.19.3.25 0 .42-.03.5-.06.03-.48.03-.98'
                '.05-1.48C7.45 4.37 9.34 2.4 12 2.4Z"/>',
    "pinterest": '<path d="M12 2.2a9.8 9.8 0 0 0-3.57 18.93c-.08-.8-.16-2.03.03-2.9.18-.79 1.15-5.02 1.15'
                 '-5.02s-.29-.59-.29-1.46c0-1.37.79-2.39 1.78-2.39.84 0 1.25.63 1.25 1.39 0 .84-.54 2.11'
                 '-.82 3.28-.23.98.49 1.79 1.46 1.79 1.75 0 3.1-1.85 3.1-4.52 0-2.36-1.7-4.01-4.12-4.01'
                 '-2.81 0-4.46 2.1-4.46 4.28 0 .85.33 1.76.74 2.25.08.1.09.19.07.29l-.28 1.12c-.04.18'
                 '-.14.22-.33.13-1.23-.57-2-2.37-2-3.81 0-3.1 2.25-5.95 6.5-5.95 3.41 0 6.06 2.43 6.06 '
                 '5.68 0 3.39-2.14 6.12-5.1 6.12-1 0-1.93-.52-2.25-1.13l-.61 2.33c-.22.85-.82 1.92-1.22 '
                 '2.57A9.8 9.8 0 1 0 12 2.2Z"/>',
    "behance": '<path d="M8.3 5.6c.96 0 1.79.09 2.55.34.7.17 1.3.43 1.79.77.47.35.83.77 1.09 1.29.25.52'
               '.38 1.2.38 1.9 0 .78-.18 1.46-.55 1.98-.35.52-.9.96-1.6 1.29 1 .26 1.7.78 2.2 1.47.48.69'
               '.7 1.55.7 2.5 0 .78-.13 1.46-.44 2.06a3.9 3.9 0 0 1-1.25 1.4c-.53.35-1.17.61-1.87.78-.7'
               '.17-1.4.26-2.12.26H2V5.6h6.3Zm-.38 5.94c.79 0 1.44-.18 1.93-.53.5-.36.7-.95.7-1.72 0-.43'
               '-.07-.86-.24-1.12a1.65 1.65 0 0 0-.62-.67 2.7 2.7 0 0 0-.9-.34c-.35-.09-.7-.09-1.1-.09'
               'H5.03v4.47h2.89Zm.17 6.28c.44 0 .87-.04 1.26-.13.4-.09.74-.22 1.01-.43.27-.18.53-.44.7'
               '-.77.17-.34.26-.78.26-1.29 0-1-.26-1.72-.83-2.15-.57-.44-1.34-.65-2.27-.65H5.03v5.42h3.06Z'
               'M17.4 17.62c.4.4 1.02.6 1.83.6.57 0 1.09-.14 1.5-.44.4-.3.66-.6.75-.94h2.09c-.35 1.05'
               '-.87 1.8-1.57 2.28-.7.44-1.57.7-2.6.7-.7 0-1.35-.13-1.92-.34a3.6 3.6 0 0 1-1.44-1 4.5 '
               '4.5 0 0 1-.9-1.55 6.1 6.1 0 0 1-.31-1.98c0-.7.1-1.34.32-1.94a4.4 4.4 0 0 1 2.38-2.6 4.5 '
               '4.5 0 0 1 1.87-.38c.78 0 1.48.15 2.05.44.6.3 1.05.7 1.44 1.2.35.5.61 1.08.79 1.72.09.65'
               '.13 1.29.09 1.98h-6.5c0 .82.26 1.55.66 1.94-.02.03.02.03.02.03Zm-.35-8.9h5.05V7.5h-5.05v1.2Z'
               'm4.36 4.6c-.09-.65-.31-1.13-.66-1.47-.35-.35-.88-.52-1.55-.52a2.3 2.3 0 0 0-1.14.25c-.31'
               '.17-.53.39-.7.6-.18.22-.31.48-.36.74-.09.26-.13.48-.13.7h4.54v-.3Z"/>',
}

SOCIAL_NETWORKS: list[dict] = [
    {"key": "instagram", "label": "Instagram", "placeholder": "https://www.instagram.com/yourbrand"},
    {"key": "linkedin", "label": "LinkedIn", "placeholder": "https://www.linkedin.com/company/yourbrand"},
    {"key": "facebook", "label": "Facebook", "placeholder": "https://www.facebook.com/yourbrand"},
    {"key": "x", "label": "X (Twitter)", "placeholder": "https://x.com/yourbrand"},
    {"key": "youtube", "label": "YouTube", "placeholder": "https://www.youtube.com/@yourbrand"},
    {"key": "tiktok", "label": "TikTok", "placeholder": "https://www.tiktok.com/@yourbrand"},
    {"key": "snapchat", "label": "Snapchat", "placeholder": "https://www.snapchat.com/add/yourbrand"},
    {"key": "pinterest", "label": "Pinterest", "placeholder": "https://www.pinterest.com/yourbrand"},
    {"key": "behance", "label": "Behance", "placeholder": "https://www.behance.net/yourbrand"},
    {"key": "whatsapp", "label": "WhatsApp", "placeholder": "https://wa.me/966599255995"},
]

SOCIAL_KEYS = [n["key"] for n in SOCIAL_NETWORKS]

# Only an https:// address (or wa.me / mailto-free equivalents) may become an
# href here. The value is escaped as well — belt and braces, because this
# string is written straight into every published page.
SOCIAL_URL_RE = re.compile(r"^https://[\w.-]+\.[a-z]{2,24}(/[\w./?=&%@+~#:-]*)?$", re.IGNORECASE)


def social_links(values: dict[str, str]) -> list[dict]:
    """The configured profiles, in the order they are listed above."""
    out = []
    for net in SOCIAL_NETWORKS:
        url = str(values.get(net["key"]) or "").strip()
        if url and SOCIAL_URL_RE.match(url) and len(url) <= 300:
            out.append({**net, "url": url})
    return out


def render_social(values: dict[str, str], label: str = "Elite Marcom on social media") -> str:
    links = social_links(values)
    if not links:
        return ""
    items = "".join(
        f'<a href="{html_mod.escape(net["url"], quote=True)}" rel="me noopener" target="_blank" '
        f'aria-label="{html_mod.escape(net["label"], quote=True)}" '
        f'title="{html_mod.escape(net["label"], quote=True)}">'
        f'<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{_ICONS[net["key"]]}</svg></a>'
        for net in links)
    return (f'<nav class="site-social" aria-label="{html_mod.escape(label, quote=True)}">'
            f"{items}</nav>")


# ---------------- new page shell ----------------

_SHELL_SOURCE = "about.html"
_STARTER_SECTIONS = ("heading-text", "cta")


def _starter_main(heading: str, lead: str) -> str:
    """A new page's <main>: a hero the content model can address by its usual
    hero.* keys, plus two starter blocks to edit or delete."""
    hero = f"""
  <section class="page-hero" aria-labelledby="page-h1">
    <div class="aurora" aria-hidden="true"><span></span><span></span></div>
    <div class="container">
      <div class="grid-2 grid-2--wide-left">
        <div>
          <p class="eyebrow reveal" data-reveal="fade-up" data-em="hero.eyebrow">Elite Marcom</p>
          <h1 id="page-h1">
            <span class="mask-clip"><span class="reveal" data-reveal="mask-title" data-em="hero.title1">{html_mod.escape(heading)}</span></span>
          </h1>
          <p class="lede reveal" data-reveal="fade-up" data-reveal-delay="220" data-em="hero.lead">{html_mod.escape(lead)}</p>
        </div>
      </div>
    </div>
  </section>
"""
    blocks = "\n".join(f'  <section class="section" data-em-block="{tid}">{TEMPLATES[tid]["html"]}\n  </section>'
                       for tid in _STARTER_SECTIONS)
    return f'<main id="main">\n{hero}\n{blocks}\n</main>'


def page_shell(slug: str, title: str, description: str, heading: str, lead: str) -> str:
    """Build a new page from a live one so the header, footer, styles and
    script chain are identical to the rest of the site by construction —
    a hand-kept copy would drift the first time a shared asset changed."""
    raw = (config.PUBLIC_DIR / _SHELL_SOURCE).read_text(encoding="utf-8")
    url = f"https://www.elitemarcom.com/{slug}.html"
    safe_title = html_mod.escape(title, quote=True)
    safe_desc = html_mod.escape(re.sub(r"\s+", " ", description).strip(), quote=True)
    raw = re.sub(r"<title>.*?</title>", f"<title>{html_mod.escape(title)}</title>",
                 raw, count=1, flags=re.S)
    for pattern, value in (
        (r'(<meta name="description" content=")[^"]*(")', safe_desc),
        (r'(<meta property="og:title" content=")[^"]*(")', safe_title),
        (r'(<meta property="og:description" content=")[^"]*(")', safe_desc),
        (r'(<meta name="twitter:title" content=")[^"]*(")', safe_title),
        (r'(<meta name="twitter:description" content=")[^"]*(")', safe_desc),
        (r'(<meta property="og:url" content=")[^"]*(")', url),
        (r'(<link rel="canonical" href=")[^"]*(")', url),
    ):
        raw = re.sub(pattern, lambda m, v=value: m.group(1) + v + m.group(2), raw, count=1)
    # the shell page's structured data and its own page scripts describe that
    # page, not this one — a new page starts with neither
    raw = re.sub(r'<script type="application/ld\+json">.*?</script>\s*', "", raw, flags=re.S)
    raw = re.sub(r'\s*<script src="/js/(?!site\.js|theme-init\.js|insights\.js)[^"]*"[^>]*></script>',
                 "", raw)
    raw = re.sub(r"<main.*?</main>", lambda _: _starter_main(heading, lead), raw,
                 count=1, flags=re.S)
    # aria-current belongs to the page the shell was copied from
    raw = raw.replace(' aria-current="page"', "", 1)
    return raw
