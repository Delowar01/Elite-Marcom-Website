"""Elite Marcom admin — backups, restore and scheduled publishing (Phase 6).

A backup is a single zip holding everything the panel owns: page content
(all languages), pages created in the panel, design overrides, settings,
rental inventory, media
metadata and the uploaded media files themselves. Customer submissions are
deliberately NOT included — they are encrypted personal data with their own
retention rules and must not travel in an operational backup.
"""
from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone

BACKUP_VERSION = 1
MAX_RESTORE_BYTES = 80 * 1024 * 1024
_MEDIA_NAME = re.compile(r"^[0-9a-f]{16}\.webp$")


class BackupError(Exception):
    """User-facing backup/restore problem."""


def _rows(table: str, columns: str) -> list[dict]:
    from . import adminauth as aa

    return [dict(r) for r in aa._connect().execute(f"SELECT {columns} FROM {table}").fetchall()]


def create() -> tuple[bytes, dict]:
    from . import adminauth as aa
    from . import content, media

    manifest = {
        "version": BACKUP_VERSION,
        "createdAt": int(time.time()),
        "createdAtHuman": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "contains": ["content", "designs", "pages", "settings", "rentals", "media",
                     "jasaniHidden"],
    }
    payload = {
        "content": _rows("content", "page, key, lang, value, updated_at, updated_by"),
        "designs": _rows("designs", "page, doc, updated_at, updated_by"),
        # pages created in the panel: a restore that dropped these would take
        # the pages themselves away, not just their text
        "customPages": _rows("custom_pages",
                             "slug, label, title, description, nav, created_at, created_by"),
        # which supplier items an admin has taken off the website by hand
        "jasaniHidden": _rows("jasani_hidden",
                              "market, product_id, code, name, hidden_at, hidden_by"),
        "settings": _rows("settings", "key, value, updated_at"),
        "media": _rows("media", "file, name, mime, bytes, width, height, alt, created_at, created_by"),
        "rentals": content.rentals_load()[0],
        "publishes": [dict(r) for r in aa._connect().execute(
            "SELECT id, ts, by, pages FROM publishes ORDER BY id DESC LIMIT 20").fetchall()],
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1))
        z.writestr("data.json", json.dumps(payload, ensure_ascii=False, indent=1))
        if media.MEDIA_DIR.exists():
            for f in sorted(media.MEDIA_DIR.glob("*.webp")):
                z.write(f, f"media/{f.name}")
        overrides = media.OVERRIDES_DIR
        if overrides.exists():
            for f in sorted(overrides.rglob("*")):
                if f.is_file() and f.stat().st_size <= 45 * 1024 * 1024:
                    z.write(f, f"overrides/{f.relative_to(overrides).as_posix()}")
    manifest["bytes"] = buf.tell()
    manifest["mediaFiles"] = len(payload["media"])
    return buf.getvalue(), manifest


def inspect(blob: bytes) -> dict:
    if len(blob) > MAX_RESTORE_BYTES:
        raise BackupError("That backup file is too large.")
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            manifest = json.loads(z.read("manifest.json"))
            data = json.loads(z.read("data.json"))
    except (KeyError, ValueError, zipfile.BadZipFile):
        raise BackupError("This is not a valid Elite Marcom backup file.")
    if manifest.get("version") != BACKUP_VERSION:
        raise BackupError("This backup was made by a different version of the panel.")
    return {"manifest": manifest,
            "counts": {key: len(data.get(key) or []) for key in
                       ("content", "designs", "settings", "rentals", "media")}}


def restore(blob: bytes, by: str) -> dict:
    """Replace panel-owned data with the backup's contents (admin accounts,
    sessions and customer submissions are never touched)."""
    from . import adminauth as aa
    from . import content, media

    info = inspect(blob)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        data = json.loads(z.read("data.json"))
        media.MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        restored_files = 0
        for name in z.namelist():
            if name.startswith("media/") and _MEDIA_NAME.match(name[6:]):
                (media.MEDIA_DIR / name[6:]).write_bytes(z.read(name))
                restored_files += 1
            elif name.startswith("overrides/") and ".." not in name:
                target = media.OVERRIDES_DIR / name[len("overrides/"):]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
    now = int(time.time())
    with aa._lock:
        conn = aa._connect()
        conn.execute("DELETE FROM content")
        for r in data.get("content", []):
            conn.execute("INSERT INTO content (page, key, lang, value, updated_at, updated_by)"
                         " VALUES (?,?,?,?,?,?)",
                         (r["page"], r["key"], r["lang"], r["value"], now, by[:200]))
        conn.execute("DELETE FROM designs")
        for r in data.get("designs", []):
            conn.execute("INSERT INTO designs (page, doc, updated_at, updated_by) VALUES (?,?,?,?)",
                         (r["page"], r["doc"], now, by[:200]))
        conn.execute("DELETE FROM jasani_hidden")
        for r in data.get("jasaniHidden", []):
            conn.execute("INSERT INTO jasani_hidden (market, product_id, code, name,"
                         " hidden_at, hidden_by) VALUES (?,?,?,?,?,?)",
                         (r["market"], r["product_id"], r.get("code", ""), r.get("name", ""),
                          r.get("hidden_at", now), r.get("hidden_by", "")))
        conn.execute("DELETE FROM custom_pages")
        for r in data.get("customPages", []):
            conn.execute("INSERT INTO custom_pages (slug, label, title, description, nav,"
                         " created_at, created_by) VALUES (?,?,?,?,?,?,?)",
                         (r["slug"], r["label"], r["title"], r.get("description", ""),
                          int(r.get("nav", 1)), r.get("created_at", now), r.get("created_by", "")))
        for r in data.get("settings", []):
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
                         " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                         " updated_at=excluded.updated_at", (r["key"], r["value"], now))
        conn.execute("DELETE FROM media")
        for r in data.get("media", []):
            conn.execute("INSERT OR IGNORE INTO media (file, name, mime, bytes, width, height,"
                         " alt, created_at, created_by) VALUES (?,?,?,?,?,?,?,?,?)",
                         (r["file"], r["name"], r["mime"], r["bytes"], r.get("width"),
                          r.get("height"), r.get("alt", ""), r.get("created_at", now),
                          r.get("created_by", "")))
        conn.commit()
    rentals = data.get("rentals")
    if rentals:
        content._write_rentals(rentals)
    info["restoredFiles"] = restored_files
    return info


# ---------------- scheduled publishing ----------------

def get_schedule() -> dict:
    from . import adminauth as aa

    at = aa.setting_get("publish.scheduledAt", 0) or 0
    return {"at": int(at), "by": aa.setting_get("publish.scheduledBy", "") or ""}


def set_schedule(when_ts: int, by: str) -> dict:
    from . import adminauth as aa

    if when_ts and when_ts < time.time() - 60:
        raise BackupError("Choose a time in the future.")
    if when_ts and when_ts > time.time() + 365 * 86400:
        raise BackupError("Scheduled publishing is limited to one year ahead.")
    aa.setting_set("publish.scheduledAt", int(when_ts))
    aa.setting_set("publish.scheduledBy", by[:200] if when_ts else "")
    return get_schedule()


def run_due_publish() -> dict | None:
    """Called by the background tick; publishes once the moment arrives."""
    from . import adminauth as aa
    from . import content

    schedule = get_schedule()
    if not schedule["at"] or schedule["at"] > time.time():
        return None
    aa.setting_set("publish.scheduledAt", 0)
    result = content.publish_all(schedule["by"] or "scheduler", note="scheduled publish")
    aa.audit(None, "site.published_scheduled", "pages",
             {"by": schedule["by"], **result}, "")
    return result
