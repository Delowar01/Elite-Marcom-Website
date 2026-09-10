"""Elite Marcom admin — job posts.

Every vacancy is its own record, with its own permanent address:

    /careers/<slug>

The record lives in ``job_posts`` (admin.db). The three roles that shipped in
``server/data/jobs.json`` are imported the first time the table is empty, so
the live site keeps showing what it showed before anyone opens the screen.

Four states, and what each one means to a visitor:

    draft       nobody outside the panel can reach it
    published   listed on /careers and served at /careers/<slug>; a closing
                date in the past makes it behave as closed without anybody
                having to notice
    closed      the page still answers — a shared link must not rot — but it
                says "Applications closed" and the form is gone
    archived    hidden from the site altogether; the address is a 404

A slug is chosen once and then kept. Renaming a published job does not move
its address, and an admin who changes the slug on purpose leaves the old one
behind as a redirect (``job_slugs``), so a link already pasted into a
WhatsApp group keeps working.

Everything an admin types is either escaped or run through a whitelist
sanitizer on the way in; nothing is ever rendered from the panel as raw
HTML.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import secrets
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

from . import config

SEED_FILE = Path(__file__).parent / "data" / "jobs.json"

STATUSES = ("draft", "published", "closed", "archived")
EMPLOYMENT_TYPES = ("Full time", "Part time", "Contract", "Internship", "Temporary")
WORKPLACE_TYPES = ("Onsite", "Hybrid", "Remote")

# schema.org employmentType values for the JobPosting markup
_SCHEMA_EMPLOYMENT = {"Full time": "FULL_TIME", "Part time": "PART_TIME", "Contract": "CONTRACTOR",
                      "Internship": "INTERN", "Temporary": "TEMPORARY"}

# text fields that carry no markup at all
_TEXT_FIELDS = {"title": 140, "department": 80, "location": 120, "experience": 120,
                "salary": 120, "summary": 400, "applyEmail": 200, "seoTitle": 200,
                "seoDescription": 320, "featuredImage": 240, "featuredImageAlt": 200}
# what a job page and a share card show when the post has no picture of its own
FALLBACK_IMAGE = "/assets/portfolio/team-experience.webp"
# long fields that may carry the whitelisted markup below
RICH_FIELDS = ("description", "responsibilities", "requirements", "qualifications",
               "skills", "benefits")
RICH_MAX = 20000

_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$")
_RESERVED_SLUGS = {"new", "apply", "index", "general"}
_IMG_RE = re.compile(r"^/(assets|media)/[\w./-]{1,240}$")
_EMAIL_RE = re.compile(r"^[^@\s]{1,120}@[^@\s]{1,120}\.[a-z]{2,}$", re.I)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class JobError(Exception):
    """A sentence the admin can act on."""


def _safe_image_path(path: str) -> bool:
    """/media/… or /assets/… and nothing that walks out of them: the regex
    allows dots for file extensions, so a `..` segment has to be refused by
    name."""
    return bool(_IMG_RE.match(path)) and ".." not in path.split("/")


# ---------------- whitelist sanitizer for the long fields ----------------

_BLOCK_TAGS = {"p", "ul", "ol", "li", "h3", "h4", "br"}
_INLINE_TAGS = {"strong", "em", "b", "i", "u", "a"}
_ALLOWED = _BLOCK_TAGS | _INLINE_TAGS
_HREF_RE = re.compile(r"^(https://|mailto:|tel:|/)[^\s\"'<>]{1,300}$", re.I)


class _BodySanitizer(HTMLParser):
    """Keep paragraphs, headings, lists, emphasis and safe links; reduce every
    other tag to its text. No attribute survives except a safe href, so an
    event handler, a style or a data: URL has nowhere to sit."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in ("script", "style"):
            self._open.append("!skip")
            return
        if tag not in _ALLOWED:
            return
        if tag == "br":
            self.out.append("<br>")
            return
        if tag == "b":
            tag = "strong"
        elif tag == "i":
            tag = "em"
        if tag == "a":
            href = next((v for k, v in attrs if k == "href"), "") or ""
            if not _HREF_RE.match(href):
                return
            self.out.append(f'<a href="{html_mod.escape(href, quote=True)}" rel="noopener">')
            self._open.append("a")
            return
        self.out.append(f"<{tag}>")
        self._open.append(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("script", "style"):
            if "!skip" in self._open:
                while self._open and self._open.pop() != "!skip":
                    pass
            return
        if tag == "b":
            tag = "strong"
        elif tag == "i":
            tag = "em"
        if tag in _ALLOWED and tag in self._open:
            while self._open:
                open_tag = self._open.pop()
                self.out.append(f"</{open_tag}>")
                if open_tag == tag:
                    break

    def handle_data(self, data):
        if "!skip" in self._open:
            return
        self.out.append(html_mod.escape(data))

    def result(self) -> str:
        while self._open:
            tag = self._open.pop()
            if tag != "!skip":
                self.out.append(f"</{tag}>")
        text = "".join(self.out)
        # empty paragraphs are what a contenteditable leaves behind
        text = re.sub(r"<p>(\s|<br>|&nbsp;)*</p>", "", text)
        return text.strip()


def sanitize_body(text: str) -> str:
    s = _BodySanitizer()
    s.feed(str(text or ""))
    s.close()
    return s.result()


def plain_text(rich: str, limit: int = 0) -> str:
    """The words alone — for a meta description or the structured data."""
    text = re.sub(r"</(p|li|h3|h4)>", " ", rich or "")
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:limit].rstrip() if limit and len(text) > limit else text


# ---------------- slugs ----------------

def slugify(text: str) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[’'`]", "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    text = re.sub(r"-{2,}", "-", text)
    return text[:80].strip("-")


def suggest_slug(title: str, location: str = "") -> str:
    """"Sales Manager – Riyadh" → sales-manager-riyadh. The city is added when
    the title does not already carry it, because two identical titles in two
    cities are two different jobs and should read as such."""
    base = slugify(title)
    city = slugify((location or "").split(",")[0])
    if city and city not in base:
        base = f"{base}-{city}" if base else city
    return base[:80].strip("-")


# ---------------- storage ----------------

def _conn():
    from . import adminauth as aa

    return aa._connect()


def _ensure() -> None:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS job_posts (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'draft',
                data TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                published_at INTEGER,
                updated_by TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS job_slugs (
                slug TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                moved_at INTEGER NOT NULL
            );
        """)
        conn.commit()
        if conn.execute("SELECT COUNT(*) FROM job_posts").fetchone()[0] == 0:
            _seed(conn)


def _seed(conn) -> None:
    """The roles that shipped as a JSON file become the first records, so the
    site keeps showing them until somebody decides otherwise."""
    try:
        raw = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    now = int(time.time())
    for i, old in enumerate(raw.get("jobs", [])):
        if not old.get("title"):
            continue
        reqs = "".join(f"<li>{html_mod.escape(str(r))}</li>" for r in old.get("requirements") or [])
        data = _defaults()
        data.update({
            "title": str(old.get("title", ""))[:140],
            "department": str(old.get("department", ""))[:80],
            "location": str(old.get("location", ""))[:120],
            "employmentType": _employment_from(old.get("employmentType", "")),
            "workplaceType": "Onsite",
            "summary": str(old.get("summary", ""))[:400],
            "description": f"<p>{html_mod.escape(str(old.get('summary', '')))}</p>",
            "requirements": f"<ul>{reqs}</ul>" if reqs else "",
            "featuredImage": str(old.get("poster", ""))[:240],
            "featuredImageAlt": f"{old.get('title', '')} — Elite Marcom careers"[:200],
            "applyEmail": "hr@elitemarcom.com",
        })
        slug = slugify(old.get("id") or old["title"]) or f"role-{i + 1}"
        published = bool(old.get("published")) and bool(old.get("open", True))
        conn.execute(
            "INSERT OR IGNORE INTO job_posts (id, slug, status, data, sort_order, created_at, "
            "updated_at, published_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (slug, slug, "published" if published else "draft",
             json.dumps(data, ensure_ascii=False), int(old.get("sortOrder") or i + 1),
             now, now, now if published else None, "seed"))
    conn.commit()


def _employment_from(value: str) -> str:
    v = str(value or "").strip().lower().replace("-", " ")
    for opt in EMPLOYMENT_TYPES:
        if opt.lower() == v:
            return opt
    return "Full time"


def _defaults() -> dict:
    d = {k: "" for k in _TEXT_FIELDS}
    d.update({k: "" for k in RICH_FIELDS})
    d.update({"employmentType": "Full time", "workplaceType": "Onsite", "vacancies": 1,
              "closingDate": "", "featured": False})
    return d


def _row(r) -> dict:
    data = _defaults()
    try:
        stored = json.loads(r["data"] or "{}")
    except ValueError:
        stored = {}
    # a record written before the rename kept the picture under `poster`
    if stored.get("poster") and not stored.get("featuredImage"):
        stored["featuredImage"] = stored["poster"]
    stored.pop("poster", None)
    data.update(stored)
    data.update({"id": r["id"], "slug": r["slug"], "status": r["status"],
                 "sortOrder": r["sort_order"], "createdAt": r["created_at"],
                 "updatedAt": r["updated_at"], "publishedAt": r["published_at"],
                 "updatedBy": r["updated_by"]})
    data["expired"] = _expired(data)
    data["open"] = data["status"] == "published" and not data["expired"]
    data["url"] = public_url(data["slug"])
    return data


def _expired(job: dict) -> bool:
    d = job.get("closingDate") or ""
    return bool(d) and d < date.today().isoformat()


def public_url(slug: str) -> str:
    from .content import SITE_ORIGIN

    return f"{SITE_ORIGIN}/careers/{slug}"


# ---------------- reading ----------------

def all_jobs() -> list[dict]:
    _ensure()
    rows = _conn().execute(
        "SELECT * FROM job_posts ORDER BY sort_order, created_at DESC").fetchall()
    return [_row(r) for r in rows]


def get(job_id: str) -> dict | None:
    _ensure()
    r = _conn().execute("SELECT * FROM job_posts WHERE id=?", (job_id,)).fetchone()
    return _row(r) if r else None


def by_slug(slug: str) -> dict | None:
    _ensure()
    r = _conn().execute("SELECT * FROM job_posts WHERE slug=?", (slug,)).fetchone()
    return _row(r) if r else None


def resolve_slug(slug: str) -> tuple[dict | None, bool]:
    """(job, moved). `moved` means the slug is an old address that should
    301 to job["slug"] rather than be served."""
    job = by_slug(slug)
    if job is not None:
        return job, False
    r = _conn().execute("SELECT job_id FROM job_slugs WHERE slug=?", (slug,)).fetchone()
    if r is None:
        return None, False
    job = get(r["job_id"])
    return (job, True) if job else (None, False)


def public_jobs() -> list[dict]:
    """What /careers lists and what the application form offers: published,
    and not past the closing date. Featured posts come first — a badge at the
    bottom of the list is a badge nobody scrolls to — and within each group
    the admin's own order holds (the sort is stable)."""
    return sorted((j for j in all_jobs() if j["open"]),
                  key=lambda j: 0 if j.get("featured") else 1)


def public_view(job: dict) -> dict:
    """The fields a visitor may see. Nothing internal rides along."""
    keys = ("id", "slug", "url", "title", "department", "location", "employmentType",
            "workplaceType", "experience", "summary", "closingDate", "featured",
            "featuredImage", "featuredImageAlt", "open", "status")
    out = {k: job.get(k) for k in keys}
    out["applicationsClosed"] = not job["open"]
    return out


def visible_on_site(job: dict | None) -> bool:
    """May this job's page be served at all? Draft and archived: no. Published
    and closed: yes — a shared link must keep working, even if it can only say
    the applications have closed."""
    return job is not None and job["status"] in ("published", "closed")


# ---------------- writing ----------------

def _clean(values: dict, existing: dict | None) -> dict:
    """Validate one submission into a stored record. Raises JobError with a
    sentence the admin can act on."""
    data = dict(existing) if existing else _defaults()
    for key, limit in _TEXT_FIELDS.items():
        if key in values:
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", str(values[key] or ""))
            data[key] = re.sub(r"\s+", " ", text).strip()[:limit]
    for key in RICH_FIELDS:
        if key in values:
            raw = str(values[key] or "")
            if len(raw) > RICH_MAX:
                raise JobError("One of the long sections is too long — keep each under 20,000 characters.")
            data[key] = sanitize_body(raw)
    if "employmentType" in values:
        et = str(values["employmentType"] or "").strip()
        if et not in EMPLOYMENT_TYPES:
            raise JobError("Choose an employment type from the list.")
        data["employmentType"] = et
    if "workplaceType" in values:
        wt = str(values["workplaceType"] or "").strip()
        if wt not in WORKPLACE_TYPES:
            raise JobError("Choose a workplace type from the list.")
        data["workplaceType"] = wt
    if "vacancies" in values:
        raw_n = values["vacancies"]
        try:
            n = 1 if raw_n in ("", None) else int(raw_n)
        except (TypeError, ValueError):
            raise JobError("Number of vacancies must be a whole number.")
        if not 1 <= n <= 500:
            raise JobError("Number of vacancies must be between 1 and 500.")
        data["vacancies"] = n
    if "closingDate" in values:
        d = str(values["closingDate"] or "").strip()
        if d and not _DATE_RE.match(d):
            raise JobError("Application deadline must be a date (YYYY-MM-DD).")
        if d:
            try:
                date.fromisoformat(d)
            except ValueError:
                raise JobError("Application deadline is not a real date.")
        data["closingDate"] = d
    if "featured" in values:
        data["featured"] = bool(values["featured"])
    if data.get("applyEmail") and not _EMAIL_RE.match(data["applyEmail"]):
        raise JobError("Application email does not look like an email address.")
    if data.get("featuredImage") and not _safe_image_path(data["featuredImage"]):
        raise JobError("The featured image must come from the Media library or the site "
                       "assets (a path starting /media/ or /assets/).")
    if data.get("featuredImageAlt") and not data.get("featuredImage"):
        data["featuredImageAlt"] = ""
    if not data["title"]:
        raise JobError("Job title is required.")
    if not data["location"]:
        raise JobError("Location is required.")
    if not plain_text(data["description"]):
        raise JobError("Full job description is required.")
    return data


def _slug_free(slug: str, job_id: str | None) -> bool:
    conn = _conn()
    taken = conn.execute("SELECT id FROM job_posts WHERE slug=?", (slug,)).fetchone()
    if taken and taken["id"] != job_id:
        return False
    moved = conn.execute("SELECT job_id FROM job_slugs WHERE slug=?", (slug,)).fetchone()
    if moved and moved["job_id"] != job_id:
        return False
    return True


def check_slug(slug: str, job_id: str | None = None) -> str:
    slug = slugify(slug)
    if not slug or not _SLUG_RE.match(slug):
        raise JobError("The web address may use lowercase letters, numbers and hyphens only.")
    if slug in _RESERVED_SLUGS:
        raise JobError(f"“{slug}” is reserved — choose another web address.")
    if not _slug_free(slug, job_id):
        raise JobError(f"The address /careers/{slug} is already used by another job post.")
    return slug


def unique_slug(base: str, job_id: str | None = None) -> str:
    """The base if it is free, else base-2, base-3, …"""
    base = slugify(base) or "job"
    if base in _RESERVED_SLUGS:
        base = f"{base}-role"
    candidate = base
    n = 2
    while not _slug_free(candidate, job_id):
        candidate = f"{base[:76]}-{n}"
        n += 1
    return candidate


def create(values: dict, by: str, status: str = "draft") -> dict:
    _ensure()
    from . import adminauth as aa

    if status not in ("draft", "published"):
        raise JobError("A new job post can be saved as a draft or published.")
    data = _clean(values, None)
    wanted = str(values.get("slug") or "").strip()
    slug = check_slug(wanted) if wanted else unique_slug(suggest_slug(data["title"], data["location"]))
    job_id = "j" + secrets.token_hex(5)
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        order = (conn.execute("SELECT COALESCE(MAX(sort_order), 0) FROM job_posts").fetchone()[0] or 0) + 1
        conn.execute(
            "INSERT INTO job_posts (id, slug, status, data, sort_order, created_at, updated_at, "
            "published_at, updated_by) VALUES (?,?,?,?,?,?,?,?,?)",
            (job_id, slug, status, json.dumps(data, ensure_ascii=False), order, now, now,
             now if status == "published" else None, by[:200]))
        conn.commit()
    return get(job_id)


def update(job_id: str, values: dict, by: str, status: str | None = None) -> dict:
    """Edit the fields, and optionally move to a status in the same save
    ("Publish" on the edit screen). A slug change keeps the old address as a
    redirect — a link already shared must not break."""
    from . import adminauth as aa

    current = get(job_id)
    if current is None:
        raise JobError("Unknown job post.")
    stored = {k: current[k] for k in _defaults()}
    data = _clean(values, stored)
    new_slug = current["slug"]
    if "slug" in values and str(values["slug"] or "").strip():
        new_slug = check_slug(str(values["slug"]), job_id)
    if status is not None and status not in STATUSES:
        raise JobError("Unknown status.")
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        if new_slug != current["slug"]:
            conn.execute("INSERT OR REPLACE INTO job_slugs (slug, job_id, moved_at) VALUES (?,?,?)",
                         (current["slug"], job_id, now))
            # the new address must not remain listed as somebody's old one
            conn.execute("DELETE FROM job_slugs WHERE slug=?", (new_slug,))
        published_at = current["publishedAt"]
        next_status = status or current["status"]
        if next_status == "published" and current["status"] != "published":
            published_at = now
        conn.execute(
            "UPDATE job_posts SET slug=?, status=?, data=?, updated_at=?, published_at=?, "
            "updated_by=? WHERE id=?",
            (new_slug, next_status, json.dumps(data, ensure_ascii=False), now, published_at,
             by[:200], job_id))
        conn.commit()
    return get(job_id)


def set_status(job_id: str, status: str, by: str) -> dict:
    from . import adminauth as aa

    current = get(job_id)
    if current is None:
        raise JobError("Unknown job post.")
    if status not in STATUSES:
        raise JobError("Unknown status.")
    now = int(time.time())
    published_at = current["publishedAt"]
    if status == "published" and current["status"] != "published":
        published_at = now
    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE job_posts SET status=?, updated_at=?, published_at=?, updated_by=? "
                     "WHERE id=?", (status, now, published_at, by[:200], job_id))
        conn.commit()
    return get(job_id)


def duplicate(job_id: str, by: str) -> dict:
    """A draft copy with its own address, so a similar vacancy starts from the
    last one rather than from nothing."""
    current = get(job_id)
    if current is None:
        raise JobError("Unknown job post.")
    values = {k: current[k] for k in _defaults()}
    values["title"] = f"{current['title']} (copy)"[:140]
    values["slug"] = unique_slug(current["slug"] + "-copy")
    return create(values, by, "draft")


def delete(job_id: str) -> bool:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        cur = conn.execute("DELETE FROM job_posts WHERE id=?", (job_id,))
        conn.execute("DELETE FROM job_slugs WHERE job_id=?", (job_id,))
        conn.commit()
    return cur.rowcount > 0


# ---------------- the public page ----------------

def _esc(t) -> str:
    return html_mod.escape(str(t or ""), quote=True)


def seo_title(job: dict) -> str:
    return job.get("seoTitle") or f"{job['title']} — Careers at Elite Marcom"


def seo_description(job: dict) -> str:
    if job.get("seoDescription"):
        return job["seoDescription"]
    base = job.get("summary") or plain_text(job.get("description", ""), 200)
    return f"{base} {job['location']} · {job['employmentType']}.".strip()[:300]


def job_posting_ld(job: dict) -> dict | None:
    """schema.org JobPosting — only for a job that is genuinely open. A draft,
    an archived job or a closed one gets none: Google treats a posting it can
    no longer apply to as a violation, not as a courtesy."""
    if not job["open"]:
        return None
    from .content import SITE_ORIGIN

    loc = job["location"]
    locality = loc.split(",")[0].strip()
    region = loc.split(",", 1)[1].strip() if "," in loc else ""
    posting: dict = {
        "@context": "https://schema.org",
        "@type": "JobPosting",
        "title": job["title"],
        "description": job["description"] or f"<p>{_esc(job['summary'])}</p>",
        "datePosted": time.strftime("%Y-%m-%d", time.gmtime(job["publishedAt"] or job["createdAt"])),
        "employmentType": _SCHEMA_EMPLOYMENT.get(job["employmentType"], "FULL_TIME"),
        "identifier": {"@type": "PropertyValue", "name": "Elite Marcom", "value": job["id"]},
        "hiringOrganization": {"@type": "Organization", "name": "Elite Marcom",
                               "sameAs": SITE_ORIGIN + "/", "@id": SITE_ORIGIN + "/#organization"},
        "jobLocation": {"@type": "Place", "address": {
            "@type": "PostalAddress", "addressLocality": locality,
            **({"addressRegion": region} if region else {})}},
        "url": job["url"],
        "directApply": True,
    }
    if job.get("featuredImage"):
        posting["image"] = SITE_ORIGIN + job["featuredImage"]
    if job.get("closingDate"):
        posting["validThrough"] = job["closingDate"] + "T23:59:59"
    if job.get("workplaceType") == "Remote":
        posting["jobLocationType"] = "TELECOMMUTE"
    if job.get("department"):
        posting["occupationalCategory"] = job["department"]
    if job.get("vacancies", 1) > 1:
        posting["totalJobOpenings"] = job["vacancies"]
    return posting


_ROBOTS_RE = re.compile(r'<meta name="robots" content="[^"]*">')
_INDEXABLE = ('<meta name="robots" content="index, follow, max-image-preview:large, '
              'max-snippet:-1, max-video-preview:-1">')
_NOINDEX = '<meta name="robots" content="noindex,follow">'


def _head(job: dict, lang: str) -> str:
    """The head fragment that replaces the template's placeholders."""
    from .content import SITE_ORIGIN

    canonical = job["url"] if lang == "en" else f"{SITE_ORIGIN}/ar/careers/{job['slug']}"
    title, desc = _esc(seo_title(job)), _esc(seo_description(job))
    image = job.get("featuredImage") or FALLBACK_IMAGE
    parts = [
        f"<title>{title}</title>",
        _INDEXABLE if job["open"] else _NOINDEX,
        f'<meta name="description" content="{desc}">',
        f'<link rel="canonical" href="{canonical}">',
        '<meta property="og:type" content="website">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        f'<meta property="og:image" content="{SITE_ORIGIN}{_esc(image)}">',
        f'<meta property="og:url" content="{canonical}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{desc}">',
        f'<meta name="twitter:image" content="{SITE_ORIGIN}{_esc(image)}">',
    ]
    ld = job_posting_ld(job)
    if ld:
        parts.append('<script type="application/ld+json">\n' + _json_for_script(ld) + "\n</script>")
    return "\n".join(parts)


def _json_for_script(data: dict) -> str:
    """JSON that is safe inside a <script> block. json.dumps leaves < > and &
    alone, so a title containing </script> would end the block and start
    another; the JSON escapes below mean the same characters, read by any
    JSON parser, and nothing to the HTML parser."""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _section(anchor: str, marker: str, heading: str, body: str) -> str:
    if not plain_text(body):
        return ""
    return (f'  <section class="job-section reveal" data-reveal="fade-up" id="{anchor}" '
            f'aria-labelledby="{anchor}-h">\n'
            f'    <p class="section-marker">{marker}</p>\n'
            f'    <h2 id="{anchor}-h">{heading}</h2>\n'
            f'    <div class="job-body">{body}</div>\n'
            "  </section>\n")


def _facts(job: dict) -> str:
    rows = [("Department", job.get("department")), ("Location", job.get("location")),
            ("Employment type", job.get("employmentType")),
            ("Workplace", job.get("workplaceType")), ("Experience", job.get("experience")),
            ("Salary", job.get("salary"))]
    if job.get("vacancies", 1) > 1:
        rows.append(("Vacancies", str(job["vacancies"])))
    if job.get("closingDate"):
        rows.append(("Closing date", _fmt_date(job["closingDate"])))
    return "".join(f"<div><dt>{_esc(k)}</dt><dd>{_esc(v)}</dd></div>" for k, v in rows if v)


def _fmt_date(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d %b %Y")
    except ValueError:
        return iso


def _share(job: dict) -> str:
    url = job["url"]
    text = f"{job['title']} at Elite Marcom"
    q = html_mod.escape
    return (
        '<div class="job-share" aria-label="Share this job">'
        '<span class="job-share__label">Share</span>'
        f'<button type="button" class="job-share__btn" data-copy-link="{q(url)}" title="Copy link">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/></svg>'
        '<span class="sr-only">Copy link</span></button>'
        f'<a class="job-share__btn" href="https://www.linkedin.com/sharing/share-offsite/?url={q(url)}" '
        'target="_blank" rel="noopener" title="Share on LinkedIn"><span aria-hidden="true">in</span>'
        '<span class="sr-only">Share on LinkedIn</span></a>'
        f'<a class="job-share__btn" href="https://wa.me/?text={q(text)}%20{q(url)}" '
        'target="_blank" rel="noopener" title="Share on WhatsApp">'
        '<svg viewBox="0 0 32 32" fill="currentColor" aria-hidden="true"><path d="M16 3C9.4 3 4 8.3 4 14.9c0 2.3.7 4.5 1.9 6.4L4 29l7.9-1.8a12.1 12.1 0 004.1.7c6.6 0 12-5.3 12-11.9C28 8.3 22.6 3 16 3zm0 21.8c-1.3 0-2.6-.3-3.7-.8l-.6-.3-4.4 1 1.1-4.2-.4-.6a9.6 9.6 0 01-1.6-5c0-5.3 4.3-9.7 9.6-9.7s9.6 4.3 9.6 9.7c0 5.3-4.3 9.9-9.6 9.9z"/></svg>'
        '<span class="sr-only">Share on WhatsApp</span></a>'
        f'<a class="job-share__btn" href="mailto:?subject={q(text)}&amp;body={q(url)}" title="Share by email">'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">'
        '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>'
        '<span class="sr-only">Share by email</span></a>'
        "</div>")


def _apply_block(job: dict) -> str:
    if not job["open"]:
        reason = ("The closing date for this role has passed." if job["expired"]
                  else "This role is no longer accepting applications.")
        return (
            '<div class="job-closed" role="status">'
            '<span class="status-chip status-chip--closed">Applications closed</span>'
            f"<p>{_esc(reason)} Other roles may be open — see "
            '<a href="/careers#openings">all current openings</a>, or send a general '
            'application from the <a href="/careers#apply">Careers page</a>.</p></div>')
    email = _esc(job.get("applyEmail") or "hr@elitemarcom.com")
    return (
        '<div class="form-panel" id="apply-panel">'
        f'<form id="application-form" novalidate data-job-id="{_esc(job["id"])}" data-job-title="{_esc(job["title"])}">'
        '<div class="form-grid">'
        '<div class="form-field"><label for="app-name">Full name <span class="req" aria-hidden="true">*</span></label>'
        '<input id="app-name" name="fullName" type="text" autocomplete="name" required minlength="2" maxlength="120">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field"><label for="app-email">Email <span class="req" aria-hidden="true">*</span></label>'
        '<input id="app-email" name="email" type="email" autocomplete="email" required maxlength="200">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field"><label for="app-phone">Phone <span class="req" aria-hidden="true">*</span></label>'
        '<input id="app-phone" name="phone" type="tel" autocomplete="tel" required pattern="[0-9+\\(\\)., \\-]{7,32}" maxlength="32">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field"><label for="app-location">Current location <span class="req" aria-hidden="true">*</span></label>'
        '<input id="app-location" name="location" type="text" required maxlength="120">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field"><label for="app-role">Role</label>'
        f'<input id="app-role" type="text" value="{_esc(job["title"])}" readonly>'
        f'<input type="hidden" name="roleId" value="{_esc(job["id"])}"></div>'
        '<div class="form-field"><label for="app-portfolio">Portfolio or LinkedIn URL (https) <span class="req" aria-hidden="true">*</span></label>'
        '<input id="app-portfolio" name="portfolioUrl" type="url" required pattern="https://.*" maxlength="300" placeholder="https://…">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field form-field--full"><label for="app-cv">CV (PDF, max 5&nbsp;MB — optional)</label>'
        '<input id="app-cv" name="cv" type="file" accept="application/pdf,.pdf">'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field form-field--full"><label for="app-intro">Brief introduction <span class="req" aria-hidden="true">*</span></label>'
        '<textarea id="app-intro" name="introduction" required minlength="10" maxlength="3000" '
        'placeholder="A few lines about you, your craft and why this role."></textarea>'
        '<span class="field-error" aria-live="polite"></span></div>'
        '<div class="form-field form-field--full"><div class="consent-row">'
        '<input id="app-consent" name="consent" type="checkbox" required>'
        '<label for="app-consent">I consent to Elite Marcom storing this application and CV for recruitment, '
        'as described in the <a href="/privacy">Privacy Notice</a>. <span class="req" aria-hidden="true">*</span></label>'
        '</div><span class="field-error" aria-live="polite"></span></div>'
        '<p class="hp-field" aria-hidden="true"><label>Leave this field empty<input type="text" name="website" tabindex="-1" autocomplete="off"></label></p>'
        '</div>'
        '<div style="margin-top:26px;"><button class="btn btn--primary" type="submit" data-magnetic>Submit application</button></div>'
        '<p class="form-status" role="status" aria-live="polite"></p>'
        f'<p class="text-muted" style="margin-top:14px;font-size:0.9rem;">Prefer email? Write to <a href="mailto:{email}">{email}</a> with the role in the subject line.</p>'
        "</form></div>")


def render_main(job: dict) -> str:
    """The <main> of a job page — server-rendered, so a crawler and a visitor
    with scripts off both read the whole posting."""
    chips = [job.get("location"), job.get("employmentType"), job.get("workplaceType")]
    chips_html = "".join(
        f'<span class="chip{" chip--violet" if i else ""}">{_esc(c)}</span>'
        for i, c in enumerate(chips) if c)
    status_chip = ("" if job["open"]
                   else '<span class="status-chip status-chip--closed">Applications closed</span>')
    apply_btn = ('<a class="btn btn--primary" href="#apply" data-magnetic>Apply for this role</a>'
                 if job["open"] else
                 '<a class="btn btn--ghost" href="/careers#openings">See open roles</a>')
    poster = (f'<figure class="job-image reveal" data-reveal="zoom-up" data-reveal-delay="160">'
              f'<div class="media-frame media-frame--sheen"><img src="{_esc(job["featuredImage"])}" '
              f'alt="{_esc(job.get("featuredImageAlt") or "")}" width="774" height="484"></div></figure>'
              if job.get("featuredImage") else "")
    sections = (
        _section("about", "01 — About the role", "What this role is", job.get("description", ""))
        + _section("responsibilities", "02 — Responsibilities", "What you will do", job.get("responsibilities", ""))
        + _section("requirements", "03 — Requirements", "What we are looking for", job.get("requirements", ""))
        + _section("qualifications", "04 — Qualifications", "Qualifications", job.get("qualifications", ""))
        + _section("skills", "05 — Skills", "Skills that matter here", job.get("skills", ""))
        + _section("benefits", "06 — Benefits", "What you get", job.get("benefits", ""))
    )
    return (
        '<main id="main">\n'
        f'  <section class="page-hero job-hero" aria-labelledby="job-h1">\n'
        '    <div class="aurora" aria-hidden="true"><span></span><span></span></div>\n'
        '    <div class="container">\n'
        '      <nav class="crumbs reveal" data-reveal="fade-up" aria-label="Breadcrumb"><ol>'
        '<li><a href="/">Home</a></li><li><a href="/careers">Careers</a></li>'
        f'<li><span aria-current="page">{_esc(job["title"])}</span></li></ol></nav>\n'
        '      <div class="grid-2 grid-2--wide-left">\n        <div>\n'
        f'          <p class="eyebrow reveal" data-reveal="fade-up">{_esc(job.get("department") or "Careers")}</p>\n'
        f'          <h1 id="job-h1"><span class="mask-clip"><span class="reveal" data-reveal="mask-title">{_esc(job["title"])}</span></span></h1>\n'
        f'          <p class="lede reveal" data-reveal="fade-up" data-reveal-delay="160">{_esc(job.get("summary") or plain_text(job.get("description", ""), 220))}</p>\n'
        f'          <p class="role-card__meta reveal" data-reveal="fade-up" data-reveal-delay="220">{chips_html}{status_chip}</p>\n'
        f'          <p class="page-hero__actions reveal" data-reveal="fade-up" data-reveal-delay="300">{apply_btn} {_share(job)}</p>\n'
        '        </div>\n'
        f'        {poster}\n'
        '      </div>\n    </div>\n  </section>\n'
        '  <section class="section" aria-label="Job details">\n    <div class="container job-layout">\n'
        f'      <div class="job-sections">\n{sections}      </div>\n'
        '      <aside class="job-facts reveal" data-reveal="fade-up" aria-labelledby="facts-h">\n'
        '        <h2 id="facts-h" class="job-facts__title">At a glance</h2>\n'
        f'        <dl>{_facts(job)}</dl>\n'
        f'        {apply_btn}\n'
        '      </aside>\n    </div>\n  </section>\n'
        '  <section class="section" id="apply" aria-labelledby="apply-h">\n    <div class="container">\n'
        '      <p class="section-marker reveal" data-reveal="fade-in">Application</p>\n'
        f'      <h2 id="apply-h" class="reveal" data-reveal="fade-up">Apply for <span class="accent-i">{_esc(job["title"])}</span></h2>\n'
        f'      {_apply_block(job)}\n'
        '    </div>\n  </section>\n'
        "</main>"
    )


_HEAD_START = "<!-- job:head -->"
_HEAD_END = "<!-- /job:head -->"


def render_page(template: str, job: dict, lang: str = "en") -> str:
    """Fill the served job template — published bake or shipped file, so the
    header, footer, theme and injected nav are whatever the rest of the site
    has — with one job."""
    raw = template
    start, end = raw.find(_HEAD_START), raw.find(_HEAD_END)
    if start != -1 and end != -1:
        raw = raw[:start] + _head(job, lang) + raw[end + len(_HEAD_END):]
    else:
        raw = _ROBOTS_RE.sub(_INDEXABLE if job["open"] else _NOINDEX, raw, count=1)
    m_start = raw.find('<main id="main"')
    m_end = raw.find("</main>", m_start)
    if m_start != -1 and m_end != -1:
        raw = raw[:m_start] + render_main(job) + raw[m_end + len("</main>"):]
    if lang == "ar":
        raw = raw.replace('href="/careers', 'href="/ar/careers')
    return raw
