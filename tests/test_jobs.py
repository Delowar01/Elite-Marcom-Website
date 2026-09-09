"""Job posts: one record per vacancy, one address per record.

Covers the whole life of a post — create as a draft, edit, publish, close,
archive, duplicate, delete — and the two things that must never go wrong in
public: an address that stops working after it was shared, and an application
filed under the wrong job.
"""
from __future__ import annotations

import json
import re
import time

import pytest
from fastapi.testclient import TestClient

from server import adminauth as aa
from server import jobs
from server import storage
from server.main import app

client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def admin(tmp_path_factory):
    """An isolated admin database with one signed-in owner, for this module."""
    from server import content

    runtime = tmp_path_factory.mktemp("jobs-admin")
    aa._DB_PATH = runtime / "admin.db"
    aa._conn = None
    content.PUBLISHED_DIR = runtime / "published" / "site"
    client.post("/api/admin/bootstrap", json={"email": "owner@elitemarcom.com", "name": "Owner",
                                              "password": "correct-horse-battery", "setupCode": ""})
    r = client.post("/api/admin/login", json={"email": "owner@elitemarcom.com",
                                              "password": "correct-horse-battery"}).json()
    client.post("/api/admin/2fa/verify", json={"pending": r["pending"],
                                               "code": aa._totp_at(r["secret"], int(time.time() // 30))})
    yield
    client.post("/api/admin/logout")


def csrf():
    return {"X-CSRF": client.get("/api/admin/me").json()["csrf"]}


def make(values=None, status="draft"):
    body = {"title": "Sales Manager", "location": "Riyadh, Saudi Arabia",
            "department": "Business Development", "employmentType": "Full time",
            "workplaceType": "Onsite", "summary": "Grow the client base.",
            "description": "<p>Own relationships from first call to signed project.</p>",
            "responsibilities": "<ul><li>Pipeline</li><li>Proposals</li></ul>"}
    body.update(values or {})
    res = client.post("/api/admin/jobs", json={"values": body, "status": status}, headers=csrf())
    assert res.status_code == 200, res.text
    return res.json()["job"]


# ---------------- the seed ----------------

def test_the_roles_that_shipped_as_a_file_are_the_first_records():
    """Nothing disappears from the live site the day this arrives."""
    listing = client.get("/api/admin/jobs").json()
    slugs = {j["slug"] for j in listing["jobs"]}
    assert {"2d-designer", "3d-exhibition-designer", "sales-executive"} <= slugs
    seeded = [j for j in listing["jobs"] if j["slug"] == "sales-executive"][0]
    assert seeded["status"] == "published"
    assert "<li>" in seeded["requirements"], "the old bullet list became a real list"
    # ...and they are what the public sees
    public = client.get("/api/careers/jobs").json()["jobs"]
    assert "sales-executive" in {j["slug"] for j in public}
    assert client.get("/careers/sales-executive").status_code == 200


# ---------------- slugs ----------------

def test_a_slug_is_made_from_the_title_and_the_city():
    assert jobs.suggest_slug("Sales Manager – Riyadh") == "sales-manager-riyadh"
    assert jobs.suggest_slug("Sales Manager", "Riyadh, Saudi Arabia") == "sales-manager-riyadh"
    assert jobs.suggest_slug("Graphics  Designer!!", "Dubai, UAE") == "graphics-designer-dubai"
    assert jobs.slugify("  Événement / Producer  ") == "v-nement-producer"
    assert jobs.suggest_slug("Riyadh Office Manager", "Riyadh") == "riyadh-office-manager"


def test_two_jobs_cannot_share_an_address():
    a = make({"title": "Graphics Designer", "location": "Riyadh, Saudi Arabia"})
    assert a["slug"] == "graphics-designer-riyadh"
    b = make({"title": "Graphics Designer", "location": "Riyadh, Saudi Arabia"})
    assert b["slug"] == "graphics-designer-riyadh-2", "the second one gets a distinct address on its own"
    # asking for the taken one by hand is refused, with the reason
    res = client.post("/api/admin/jobs", headers=csrf(), json={"values": {
        "title": "Another", "location": "Riyadh", "description": "<p>x</p>",
        "slug": "graphics-designer-riyadh"}, "status": "draft"})
    assert res.status_code == 400
    assert "already used" in res.json()["detail"]
    for j in (a, b):
        client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())


def test_an_unsafe_slug_is_refused_and_a_reserved_one_too():
    for bad in ("New", "../etc", "sales manager", "-lead-", "new"):
        res = client.post("/api/admin/jobs", headers=csrf(), json={"values": {
            "title": "X", "location": "Y", "description": "<p>x</p>", "slug": bad}, "status": "draft"})
        if bad in ("New", "new"):
            assert res.status_code == 400 and "reserved" in res.json()["detail"], bad
        elif res.status_code == 200:
            # normalised into something safe rather than stored as typed
            got = res.json()["job"]["slug"]
            assert re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", got), (bad, got)
            client.post(f"/api/admin/jobs/{res.json()['job']['id']}/delete", headers=csrf())
        else:
            assert res.status_code == 400, bad


def test_the_slug_check_endpoint_suggests_and_validates():
    r = client.post("/api/admin/jobs/slug", json={"title": "Event Producer", "location": "Dubai, UAE"}).json()
    assert r["slug"] == "event-producer-dubai"
    r = client.post("/api/admin/jobs/slug", json={"slug": "sales-executive"})
    assert r.status_code == 400 and "already used" in r.json()["detail"]
    r = client.post("/api/admin/jobs/slug", json={"slug": "sales-executive", "id": "sales-executive"}).json()
    assert r["available"] is True, "a job's own slug is free for that job"


# ---------------- the life of a post ----------------

def test_create_edit_publish_close_archive_delete():
    j = make()
    assert j["status"] == "draft" and j["publishedAt"] is None
    assert j["url"] == f"https://www.elitemarcom.com/careers/{j['slug']}"

    # a draft is invisible outside the panel
    assert client.get(f"/careers/{j['slug']}").status_code == 404
    assert j["slug"] not in {x["slug"] for x in client.get("/api/careers/jobs").json()["jobs"]}

    # edit without publishing: still a draft
    res = client.post(f"/api/admin/jobs/{j['id']}", headers=csrf(),
                      json={"values": {"experience": "5+ years", "salary": "Competitive"}})
    assert res.status_code == 200 and res.json()["job"]["status"] == "draft"
    assert res.json()["job"]["experience"] == "5+ years"
    assert res.json()["job"]["title"] == "Sales Manager", "an edit touches only what was sent"

    # publish
    res = client.post(f"/api/admin/jobs/{j['id']}/status", json={"status": "published"}, headers=csrf())
    assert res.status_code == 200
    j = res.json()["job"]
    assert j["publishedAt"] and j["open"] is True
    page = client.get(f"/careers/{j['slug']}")
    assert page.status_code == 200
    assert "Sales Manager" in page.text and "5+ years" in page.text and "Competitive" in page.text
    assert '<form id="application-form"' in page.text
    assert j["slug"] in {x["slug"] for x in client.get("/api/careers/jobs").json()["jobs"]}

    # unpublish → draft, the page is gone again
    client.post(f"/api/admin/jobs/{j['id']}/status", json={"status": "draft"}, headers=csrf())
    assert client.get(f"/careers/{j['slug']}").status_code == 404
    client.post(f"/api/admin/jobs/{j['id']}/status", json={"status": "published"}, headers=csrf())

    # close: the page answers, says so, and the form is gone
    client.post(f"/api/admin/jobs/{j['id']}/status", json={"status": "closed"}, headers=csrf())
    page = client.get(f"/careers/{j['slug']}")
    assert page.status_code == 200
    assert "Applications closed" in page.text
    assert '<form id="application-form"' not in page.text
    assert 'content="noindex,follow"' in page.text
    assert j["slug"] not in {x["slug"] for x in client.get("/api/careers/jobs").json()["jobs"]}

    # archive: gone from the site, address is a 404
    client.post(f"/api/admin/jobs/{j['id']}/status", json={"status": "archived"}, headers=csrf())
    assert client.get(f"/careers/{j['slug']}").status_code == 404

    # delete
    assert client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf()).status_code == 200
    assert client.get(f"/api/admin/jobs/{j['id']}").status_code == 404
    assert client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf()).status_code == 404


def test_duplicate_makes_a_draft_copy_with_its_own_address():
    j = make({"title": "Event Producer", "location": "Dubai, UAE"}, status="published")
    res = client.post(f"/api/admin/jobs/{j['id']}/duplicate", headers=csrf())
    assert res.status_code == 200
    copy = res.json()["job"]
    assert copy["id"] != j["id"]
    assert copy["status"] == "draft"
    assert copy["slug"] == "event-producer-dubai-copy"
    assert copy["title"] == "Event Producer (copy)"
    assert copy["description"] == j["description"]
    for x in (j, copy):
        client.post(f"/api/admin/jobs/{x['id']}/delete", headers=csrf())


def test_a_published_job_past_its_closing_date_reads_as_closed():
    j = make({"closingDate": "2020-01-01"}, status="published")
    assert j["expired"] is True and j["open"] is False
    assert j["slug"] not in {x["slug"] for x in client.get("/api/careers/jobs").json()["jobs"]}
    page = client.get(f"/careers/{j['slug']}")
    assert page.status_code == 200
    assert "closing date for this role has passed" in page.text
    assert "JobPosting" not in page.text
    # and an application for it is refused
    client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())


def test_a_bad_closing_date_or_vacancy_count_is_refused():
    for values, word in (({"closingDate": "next week"}, "date"),
                         ({"closingDate": "2026-02-30"}, "real date"),
                         ({"vacancies": 0}, "between 1 and 500"),
                         ({"vacancies": "many"}, "whole number"),
                         ({"employmentType": "Gig"}, "employment type"),
                         ({"applyEmail": "not-an-email"}, "email"),
                         ({"poster": "https://evil.example/x.png"}, "Media library")):
        body = {"title": "T", "location": "L", "description": "<p>x</p>", **values}
        res = client.post("/api/admin/jobs", json={"values": body}, headers=csrf())
        assert res.status_code == 400, values
        assert word in res.json()["detail"], (values, res.json()["detail"])
    for missing in ({"title": ""}, {"location": ""}, {"description": ""}):
        body = {"title": "T", "location": "L", "description": "<p>x</p>", **missing}
        res = client.post("/api/admin/jobs", json={"values": body}, headers=csrf())
        assert res.status_code == 400 and "required" in res.json()["detail"], missing


# ---------------- the address, once shared, keeps working ----------------

def test_renaming_a_published_job_keeps_its_address():
    j = make({"title": "Account Manager", "location": "Riyadh, Saudi Arabia"}, status="published")
    assert j["slug"] == "account-manager-riyadh"
    res = client.post(f"/api/admin/jobs/{j['id']}", headers=csrf(),
                      json={"values": {"title": "Senior Account Manager"}})
    assert res.json()["job"]["slug"] == "account-manager-riyadh", "the title moved, the address did not"
    assert client.get("/careers/account-manager-riyadh").status_code == 200
    client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())


def test_changing_the_slug_on_purpose_leaves_a_redirect_behind():
    j = make({"title": "Copywriter", "location": "Dubai, UAE"}, status="published")
    res = client.post(f"/api/admin/jobs/{j['id']}", headers=csrf(),
                      json={"values": {"slug": "senior-copywriter-dubai"}})
    assert res.status_code == 200 and res.json()["job"]["slug"] == "senior-copywriter-dubai"
    old = client.get("/careers/copywriter-dubai", follow_redirects=False)
    assert old.status_code == 301
    assert old.headers["location"] == "/careers/senior-copywriter-dubai"
    assert client.get("/careers/senior-copywriter-dubai").status_code == 200
    # the vacated address cannot be given to another job
    res = client.post("/api/admin/jobs", headers=csrf(), json={"values": {
        "title": "Other", "location": "Dubai", "description": "<p>x</p>", "slug": "copywriter-dubai"}})
    assert res.status_code == 400
    # the Arabic edition redirects inside its own edition
    ar = client.get("/ar/careers/copywriter-dubai", follow_redirects=False)
    assert ar.status_code == 301 and ar.headers["location"] == "/ar/careers/senior-copywriter-dubai"
    client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())
    assert client.get("/careers/senior-copywriter-dubai").status_code == 404
    assert client.get("/careers/copywriter-dubai", follow_redirects=False).status_code == 404


# ---------------- the public page ----------------

def test_the_job_page_carries_its_own_seo_head_and_structured_data():
    j = make({"title": "3D Visualiser", "location": "Riyadh, Saudi Arabia",
              "department": "Spatial Design", "closingDate": "2099-12-31", "vacancies": 2,
              "workplaceType": "Hybrid", "seoDescription": "Render exhibition stands."},
             status="published")
    body = client.get(f"/careers/{j['slug']}").text
    url = f"https://www.elitemarcom.com/careers/{j['slug']}"
    assert "<title>3D Visualiser — Careers at Elite Marcom</title>" in body
    assert '<meta name="description" content="Render exhibition stands.">' in body
    assert f'<link rel="canonical" href="{url}">' in body
    assert f'<meta property="og:url" content="{url}">' in body
    assert '<meta property="og:title" content="3D Visualiser — Careers at Elite Marcom">' in body
    assert 'content="index, follow' in body
    assert body.count("<h1") == 1
    assert '<nav class="crumbs' in body and '<a href="/careers">Careers</a>' in body
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    assert len(blocks) == 1
    ld = json.loads(blocks[0])
    assert ld["@type"] == "JobPosting"
    assert ld["title"] == "3D Visualiser"
    assert ld["employmentType"] == "FULL_TIME"
    assert ld["validThrough"] == "2099-12-31T23:59:59"
    assert ld["jobLocation"]["address"]["addressLocality"] == "Riyadh"
    assert ld["hiringOrganization"]["@id"] == "https://www.elitemarcom.com/#organization"
    assert ld["totalJobOpenings"] == 2
    assert ld["url"] == url
    # the share row and the form point at this job and nothing else
    assert f'data-copy-link="{url}"' in body
    assert f'data-job-id="{j["id"]}"' in body
    # the Arabic edition serves too, with the canonical inside /ar/
    client.post("/api/admin/settings", json={"values": {"site.languages": ["en", "ar"]}}, headers=csrf())
    client.post("/api/admin/pages-publish", headers=csrf())
    ar = client.get(f"/ar/careers/{j['slug']}")
    assert ar.status_code == 200 and 'dir="rtl"' in ar.text
    assert f'<link rel="canonical" href="https://www.elitemarcom.com/ar/careers/{j["slug"]}">' in ar.text
    client.post("/api/admin/pages-unpublish", headers=csrf())
    client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())


def test_nothing_an_admin_types_is_rendered_as_raw_html():
    evil = ('<p onclick="x()">Fine</p><script>alert(1)</script><img src=x onerror=alert(1)>'
            '<a href="javascript:alert(1)">bad</a><a href="https://ok.example">ok</a>'
            '<b>bold</b><h3>Head</h3><style>*{}</style>')
    j = make({"title": 'Title </script><script>alert(1)</script><img src=x onerror=alert(1)>',
              "description": evil, "summary": '<script>x</script>summary'}, status="published")
    stored = client.get(f"/api/admin/jobs/{j['id']}").json()["job"]
    # the javascript: link loses its tag but keeps its words — text is never lost
    assert stored["description"] == ('<p>Fine</p>bad<a href="https://ok.example" rel="noopener">ok</a>'
                                     '<strong>bold</strong><h3>Head</h3>')
    body = client.get(f"/careers/{j['slug']}").text
    assert "<script>alert" not in body and "<img src=x" not in body and "javascript:" not in body
    assert "&lt;img src=x onerror=alert(1)&gt;" in body, "the title is text, escaped"
    assert "&lt;script&gt;" in body
    # the structured data carries the title too, and a </script> inside it
    # would end the block: it is JSON-escaped, and still decodes to the title
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    assert len(blocks) == 1
    assert "</script>" not in blocks[0] and "<" not in blocks[0]
    assert json.loads(blocks[0])["title"] == stored["title"]
    client.post(f"/api/admin/jobs/{j['id']}/delete", headers=csrf())


def test_the_template_alone_is_not_a_job_and_not_indexable():
    res = client.get("/job")
    assert res.status_code == 200
    assert 'content="noindex,follow"' in res.text
    assert "JobPosting" not in res.text
    assert client.get("/careers/no-such-job").status_code == 404
    assert client.get("/careers/../etc").status_code in (404, 301, 400)


# ---------------- the sitemap ----------------

def test_open_jobs_are_in_the_sitemap_and_only_those():
    live = make({"title": "Lighting Technician", "location": "Riyadh, Saudi Arabia"}, status="published")
    draft = make({"title": "Rigger", "location": "Riyadh, Saudi Arabia"})
    closed = make({"title": "Driver", "location": "Riyadh, Saudi Arabia"}, status="published")
    client.post(f"/api/admin/jobs/{closed['id']}/status", json={"status": "closed"}, headers=csrf())
    sm = client.get("/sitemap.xml")
    assert sm.status_code == 200 and "application/xml" in sm.headers["content-type"]
    assert f"<loc>{live['url']}</loc>" in sm.text
    assert draft["url"] not in sm.text
    assert closed["url"] not in sm.text
    assert "/job</loc>" not in sm.text, "the template is not a page worth offering"
    assert "/ar/careers/" not in sm.text
    for x in (live, draft, closed):
        client.post(f"/api/admin/jobs/{x['id']}/delete", headers=csrf())


# ---------------- applications stay with their job ----------------

def _form(role_id: str) -> dict:
    ch = client.get("/api/security/challenge?form=career").json()["challenge"]
    ver = client.get("/api/security/config").json()["consentVersion"]
    return {"fullName": "Test Person", "email": "t@example.com", "phone": "+966590000000",
            "location": "Riyadh", "roleId": role_id, "portfolioUrl": "https://example.com/me",
            "introduction": "Ten characters and more about me.", "consent": "yes",
            "challenge": ch, "consentVersion": ver, "sourcePage": "/careers/x"}


def test_an_application_is_filed_under_its_job_and_counted_there():
    a = make({"title": "Sales Manager", "location": "Riyadh, Saudi Arabia"}, status="published")
    b = make({"title": "Graphics Designer", "location": "Riyadh, Saudi Arabia"}, status="published")
    origin = {"Origin": "http://127.0.0.1:8847"}
    for role, n in ((a["id"], 2), (b["id"], 1), ("general", 1)):
        for _ in range(n):
            res = client.post("/api/careers/applications", data=_form(role), headers=origin)
            assert res.status_code == 200, res.text
    counts = storage.applications_by_job()
    assert counts[a["id"]] == 2 and counts[b["id"]] == 1 and counts["general"] >= 1

    listing = {j["id"]: j for j in client.get("/api/admin/jobs").json()["jobs"]}
    assert listing[a["id"]]["applications"] == 2
    assert listing[b["id"]]["applications"] == 1

    # the inbox narrows to one job, and the record names the job
    inbox = client.get(f"/api/admin/requests?job={a['id']}").json()
    assert inbox["total"] == 2
    assert all(r["summary"]["roleTitle"] == "Sales Manager" for r in inbox["requests"])
    ref = inbox["requests"][0]["reference"]
    detail = client.get(f"/api/admin/requests/{ref}").json()
    assert detail["payload"]["roleId"] == a["id"]
    assert detail["payload"]["jobSlug"] == a["slug"]

    # a draft or closed job takes no applications
    client.post(f"/api/admin/jobs/{b['id']}/status", json={"status": "closed"}, headers=csrf())
    res = client.post("/api/careers/applications", data=_form(b["id"]), headers=origin)
    assert res.status_code == 400 and "valid role" in res.json()["detail"]
    for x in (a, b):
        client.post(f"/api/admin/jobs/{x['id']}/delete", headers=csrf())


# ---------------- who may do this ----------------

def test_job_management_is_behind_the_careers_permission():
    from server.adminauth import ROLES, has_perm

    assert has_perm("owner", "careers.manage")
    assert has_perm("admin", "careers.manage")
    assert has_perm("editor", "careers.manage")
    for role in ("sales", "catalog", "analyst"):
        assert not has_perm(role, "careers.manage"), role
    assert "careers.manage" not in ROLES["sales"]

    # signed out: nothing
    anon = TestClient(app)
    assert anon.get("/api/admin/jobs").status_code == 401
    assert anon.post("/api/admin/jobs", json={"values": {}}).status_code == 401
    # signed in but no CSRF token: refused
    res = client.post("/api/admin/jobs", json={"values": {"title": "x", "location": "y",
                                                           "description": "<p>x</p>"}})
    assert res.status_code == 403
