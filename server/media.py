"""Elite Marcom admin — media library, site-asset overrides, brand theme, GLB.

Uploaded library images are re-encoded to WebP (EXIF stripped) and served
from /media/. Site assets are never edited in place: replacements live in
runtime/overrides/ mirroring the public/ tree, checked by the static server
first — resetting an override restores the original file from git.
"""
from __future__ import annotations

import hashlib
import io
import re
import time
from pathlib import Path

from . import config

MEDIA_DIR = config.RUNTIME_DIR / "media"
GLB_DIR = config.RUNTIME_DIR / "media" / "glb"
OVERRIDES_DIR = config.RUNTIME_DIR / "overrides"

LIBRARY_MAX_BYTES = 15 * 1024 * 1024
LIBRARY_MAX_DIM = 2560
GLB_MAX_BYTES = 40 * 1024 * 1024
GLB_TARGET = "assets/aces-exhibition.glb"

# public paths that may be replaced through the panel, by extension
REPLACEABLE_EXTS = {".webp", ".png", ".jpg", ".jpeg", ".svg", ".glb"}


class MediaError(Exception):
    """User-facing validation error (message is safe to show)."""


# ---------------- signatures & conversion ----------------

def _sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _open_image(data: bytes):
    from PIL import Image

    if len(data) > LIBRARY_MAX_BYTES:
        raise MediaError("Images must be 15 MB or smaller.")
    if _sniff(data) is None:
        raise MediaError("Please upload a PNG, JPEG or WebP image.")
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        raise MediaError("That file is not a valid image.")
    if im.width < 8 or im.height < 8 or im.width * im.height > 60_000_000:
        raise MediaError("Image dimensions are out of range.")
    return im


def _encode(im, fmt: str, max_dim: int = LIBRARY_MAX_DIM) -> bytes:
    """Re-encode (strips EXIF/metadata) with an optional size cap."""
    if max(im.width, im.height) > max_dim:
        im = im.copy()
        im.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    if fmt == "webp":
        im.convert("RGBA" if "A" in im.getbands() else "RGB").save(
            buf, format="WEBP", quality=82, method=4)
    elif fmt == "png":
        im.convert("RGBA" if "A" in im.getbands() else "RGB").save(buf, format="PNG")
    else:  # jpeg
        im.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()


_SVG_BLOCK = re.compile(rb"<script|javascript:|on[a-z]+\s*=|<foreignObject|data:text/html",
                        re.IGNORECASE)


def check_svg(data: bytes) -> None:
    if len(data) > 2 * 1024 * 1024:
        raise MediaError("SVG files must be 2 MB or smaller.")
    head = data[:4096].lstrip()
    if not (head.startswith(b"<svg") or head.startswith(b"<?xml")):
        raise MediaError("That file is not a valid SVG.")
    if _SVG_BLOCK.search(data):
        raise MediaError("This SVG contains scripting and cannot be used.")
    try:
        from defusedxml import ElementTree

        ElementTree.fromstring(data.decode("utf-8", errors="strict"))
    except Exception:
        raise MediaError("That file is not a valid SVG.")


def _scan(data: bytes) -> None:
    from . import main as _main

    _main.scan_malware(data)


# ---------------- media library ----------------

def ingest_library_image(data: bytes, orig_name: str, alt: str, by: str) -> dict:
    from . import adminauth as aa

    _scan(data)
    im = _open_image(data)
    encoded = _encode(im, "webp")
    digest = hashlib.sha256(encoded).hexdigest()[:16]
    file_name = f"{digest}.webp"
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    (MEDIA_DIR / file_name).write_bytes(encoded)
    from PIL import Image

    saved = Image.open(io.BytesIO(encoded))
    with aa._lock:
        conn = aa._connect()
        existing = conn.execute("SELECT id FROM media WHERE file=?", (file_name,)).fetchone()
        if existing:
            return library_get(existing["id"])
        cur = conn.execute(
            "INSERT INTO media (file, name, mime, bytes, width, height, alt, created_at, created_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (file_name, re.sub(r"[^\w. -]", "", orig_name)[:120] or "image",
             "image/webp", len(encoded), saved.width, saved.height,
             alt[:300], int(time.time()), by[:200]))
        conn.commit()
        return library_get(int(cur.lastrowid))


def library_get(media_id: int) -> dict | None:
    from . import adminauth as aa

    row = aa._connect().execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
    return dict(row) if row else None


def library_list() -> list[dict]:
    from . import adminauth as aa

    rows = aa._connect().execute("SELECT * FROM media ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def library_set_alt(media_id: int, alt: str) -> None:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        conn.execute("UPDATE media SET alt=? WHERE id=?", (alt[:300], media_id))
        conn.commit()


def library_delete(media_id: int) -> bool:
    from . import adminauth as aa

    with aa._lock:
        conn = aa._connect()
        row = conn.execute("SELECT file FROM media WHERE id=?", (media_id,)).fetchone()
        if row is None:
            return False
        conn.execute("DELETE FROM media WHERE id=?", (media_id,))
        conn.commit()
    try:
        (MEDIA_DIR / Path(row["file"]).name).unlink(missing_ok=True)
    except OSError:
        pass
    return True


def media_file_path(name: str) -> Path | None:
    safe = Path(name).name
    if not re.fullmatch(r"[0-9a-f]{16}\.webp", safe):
        return None
    p = MEDIA_DIR / safe
    return p if p.is_file() else None


def storage_usage() -> dict:
    def _du(d: Path) -> int:
        if not d.exists():
            return 0
        return sum(f.stat().st_size for f in d.rglob("*") if f.is_file())

    return {"libraryBytes": _du(MEDIA_DIR) - _du(GLB_DIR), "glbBytes": _du(GLB_DIR),
            "overridesBytes": _du(OVERRIDES_DIR)}


# ---------------- site assets & overrides ----------------

def _safe_rel(rel_path: str) -> str:
    rel = rel_path.replace("\\", "/").lstrip("/")
    if ".." in rel.split("/") or not rel:
        raise MediaError("Invalid asset path.")
    return rel


def override_for(rel_path: str) -> Path | None:
    """Called by the static server for every request — must stay cheap."""
    try:
        rel = _safe_rel(rel_path)
    except MediaError:
        return None
    p = (OVERRIDES_DIR / rel)
    return p if p.is_file() else None


def site_assets() -> list[dict]:
    """Images (and the GLB) under public/assets with override + usage info."""
    base = config.PUBLIC_DIR / "assets"
    usage = _usage_index()
    out = []
    for f in sorted(base.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in REPLACEABLE_EXTS:
            continue
        rel = f.relative_to(config.PUBLIC_DIR).as_posix()
        override = OVERRIDES_DIR / rel
        out.append({"path": rel, "bytes": f.stat().st_size,
                    "ext": f.suffix.lower().lstrip("."),
                    "overridden": override.is_file(),
                    "overrideBytes": override.stat().st_size if override.is_file() else 0,
                    "usedOn": usage.get(f.name, [])})
    return out


def _usage_index() -> dict[str, list[str]]:
    """Map asset basename -> pages/styles referencing it (best-effort)."""
    index: dict[str, list[str]] = {}
    sources = list(config.PUBLIC_DIR.glob("*.html")) + list(config.PUBLIC_DIR.glob("*.css")) \
        + list((config.PUBLIC_DIR / "js").glob("*.js"))
    texts = []
    for src in sources:
        try:
            texts.append((src.name, src.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    for f in (config.PUBLIC_DIR / "assets").rglob("*"):
        if not f.is_file():
            continue
        hits = [name for name, text in texts if f.name in text]
        if hits:
            index[f.name] = hits[:12]
    return index


def replace_site_asset(rel_path: str, data: bytes, by: str) -> dict:
    rel = _safe_rel(rel_path)
    original = config.PUBLIC_DIR / rel
    if not original.is_file() or not rel.startswith("assets/"):
        raise MediaError("Unknown site asset.")
    ext = original.suffix.lower()
    if ext not in REPLACEABLE_EXTS:
        raise MediaError("This file type cannot be replaced from the panel.")
    _scan(data)
    if ext == ".svg":
        check_svg(data)
        out = data
    elif ext == ".glb":
        raise MediaError("Replace the 3D model from the Website & Brand → 3D hero section.")
    else:
        im = _open_image(data)
        fmt = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg"}.get(ext.lstrip("."), "webp")
        out = _encode(im, fmt, max_dim=4096)
    target = OVERRIDES_DIR / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(out)
    return {"path": rel, "bytes": len(out)}


def reset_site_asset(rel_path: str) -> bool:
    rel = _safe_rel(rel_path)
    target = OVERRIDES_DIR / rel
    if not target.is_file():
        return False
    target.unlink()
    return True


# ---------------- identity slots ----------------

IDENTITY_SLOTS = {
    "logoLight": {"path": "assets/logo.svg", "kind": "svg",
                  "label": "Logo — light theme"},
    "logoDark": {"path": "assets/logo-light.svg", "kind": "svg",
                 "label": "Logo — dark theme"},
    "favicon": {"path": "assets/favicon.png", "kind": "favicon",
                "label": "Favicon (site icon)"},
    "pdfLogo": {"path": "pdf-logo.png", "kind": "pdflogo",
                "label": "PDF logo (printing manuals & exports)"},
}

_FAVICON_SIZES = {"assets/favicon.png": 48, "assets/favicon-64.png": 64,
                  "assets/favicon-180.png": 180, "assets/favicon-512.png": 512}


def identity_status() -> list[dict]:
    out = []
    for slot, cfg in IDENTITY_SLOTS.items():
        out.append({"slot": slot, "label": cfg["label"], "kind": cfg["kind"],
                    "path": cfg["path"],
                    "overridden": (OVERRIDES_DIR / cfg["path"]).is_file()})
    return out


def set_identity(slot: str, data: bytes, by: str) -> None:
    cfg = IDENTITY_SLOTS.get(slot)
    if cfg is None:
        raise MediaError("Unknown identity slot.")
    _scan(data)
    OVERRIDES_DIR.mkdir(parents=True, exist_ok=True)
    if cfg["kind"] == "svg":
        check_svg(data)
        target = OVERRIDES_DIR / cfg["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return
    im = _open_image(data)
    if cfg["kind"] == "favicon":
        if im.width < 128 or im.height < 128:
            raise MediaError("Favicon source should be at least 128×128 px.")
        for rel, size in _FAVICON_SIZES.items():
            icon = im.copy().convert("RGBA")
            icon.thumbnail((size, size))
            buf = io.BytesIO()
            icon.save(buf, format="PNG")
            target = OVERRIDES_DIR / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(buf.getvalue())
        return
    # pdfLogo — transparent PNG used by reportlab documents
    out = _encode(im, "png", max_dim=1800)
    (OVERRIDES_DIR / cfg["path"]).write_bytes(out)


def reset_identity(slot: str) -> None:
    cfg = IDENTITY_SLOTS.get(slot)
    if cfg is None:
        raise MediaError("Unknown identity slot.")
    if cfg["kind"] == "favicon":
        for rel in _FAVICON_SIZES:
            (OVERRIDES_DIR / rel).unlink(missing_ok=True)
        return
    (OVERRIDES_DIR / cfg["path"]).unlink(missing_ok=True)


def pdf_logo_path() -> Path | None:
    p = OVERRIDES_DIR / IDENTITY_SLOTS["pdfLogo"]["path"]
    return p if p.is_file() else None


# ---------------- brand theme tokens ----------------

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

TOKEN_DEFS = {
    "orange": {"var": "--orange", "label": "Primary orange", "default": "#ed6c26"},
    "orange2": {"var": "--orange-2", "label": "Orange highlight", "default": "#f18042"},
    "violet": {"var": "--violet", "label": "Violet", "default": "#7467c7"},
    "violet2": {"var": "--violet-2", "label": "Violet highlight", "default": "#8f77d6"},
}


def get_brand_tokens() -> dict:
    from . import adminauth as aa

    stored = aa.setting_get("brand.tokens") or {}
    return {k: stored.get(k) or v["default"] for k, v in TOKEN_DEFS.items()} | {
        "radius": stored.get("radius"), "motion": stored.get("motion", True)}


def save_brand_tokens(values: dict) -> dict:
    from . import adminauth as aa

    clean: dict = {}
    for key in TOKEN_DEFS:
        v = str(values.get(key) or "").strip()
        if v:
            if not _HEX_RE.match(v):
                raise MediaError(f"{TOKEN_DEFS[key]['label']} must be a #RRGGBB colour.")
            clean[key] = v.lower()
    if values.get("radius") not in (None, ""):
        try:
            r = float(values["radius"])
        except (TypeError, ValueError):
            raise MediaError("Corner radius must be a number.")
        if not 0 <= r <= 2:
            raise MediaError("Corner radius scale must be between 0 and 2.")
        clean["radius"] = r
    clean["motion"] = bool(values.get("motion", True))
    aa.setting_set("brand.tokens", clean)
    return clean


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def contrast_warnings(tokens: dict) -> list[str]:
    warnings = []
    orange = tokens.get("orange") or TOKEN_DEFS["orange"]["default"]
    if _contrast(orange, "#ffffff") < 2.4:
        warnings.append("Primary orange is very light — white button text may be hard to read "
                        f"(contrast {_contrast(orange, '#ffffff'):.1f}:1).")
    if _contrast(orange, "#202532") < 2.0:
        warnings.append("Primary orange is close to the dark panel colour — accents may not stand out "
                        f"(contrast {_contrast(orange, '#202532'):.1f}:1).")
    violet = tokens.get("violet2") or TOKEN_DEFS["violet2"]["default"]
    if _contrast(violet, "#202532") < 1.7:
        warnings.append("Violet highlight blends into dark surfaces.")
    return warnings


def theme_css() -> str:
    """The public /theme-custom.css payload — empty when brand is unchanged."""
    from . import adminauth as aa

    stored = aa.setting_get("brand.tokens") or {}
    lines = []
    for key, cfg in TOKEN_DEFS.items():
        v = stored.get(key)
        if v and _HEX_RE.match(str(v)) and v.lower() != cfg["default"]:
            lines.append(f"  {cfg['var']}: {v};")
    css = ""
    if lines:
        css += ":root {\n" + "\n".join(lines) + "\n}\n"
    radius = stored.get("radius")
    if isinstance(radius, (int, float)) and radius != 1 and 0 <= radius <= 2:
        css += (f".card, .admin-panel, .btn, .stat-card {{ border-radius: "
                f"calc(var(--radius, 16px) * {radius}); }}\n")
    if stored.get("motion") is False:
        css += ("*, *::before, *::after { animation-duration: 0.01ms !important; "
                "transition-duration: 0.01ms !important; scroll-behavior: auto !important; }\n")
    return css


# ---------------- 3D hero (GLB) manager ----------------

def glb_versions() -> dict:
    GLB_DIR.mkdir(parents=True, exist_ok=True)
    active_override = OVERRIDES_DIR / GLB_TARGET
    active_hash = None
    if active_override.is_file():
        active_hash = hashlib.sha256(active_override.read_bytes()).hexdigest()[:16]
    versions = []
    for f in sorted(GLB_DIR.glob("*.glb"), reverse=True):
        digest = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        versions.append({"file": f.name, "bytes": f.stat().st_size,
                         "uploadedAt": int(f.stat().st_mtime),
                         "active": digest == active_hash})
    original = config.PUBLIC_DIR / GLB_TARGET
    return {"versions": versions,
            "originalBytes": original.stat().st_size if original.is_file() else 0,
            "overrideActive": active_override.is_file()}


def glb_upload(data: bytes, orig_name: str) -> dict:
    if len(data) > GLB_MAX_BYTES:
        raise MediaError("GLB files must be 40 MB or smaller.")
    if len(data) < 100 or data[:4] != b"glTF":
        raise MediaError("That file is not a valid binary glTF (.glb) model.")
    version = int.from_bytes(data[4:8], "little")
    if version != 2:
        raise MediaError("Only glTF 2.0 models are supported.")
    _scan(data)
    GLB_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w-]", "", Path(orig_name).stem)[:40] or "model"
    name = f"{int(time.time())}-{safe}.glb"
    (GLB_DIR / name).write_bytes(data)
    return {"file": name, "bytes": len(data)}


def glb_activate(file_name: str) -> None:
    src = GLB_DIR / Path(file_name).name
    if not src.is_file():
        raise MediaError("Unknown model version.")
    target = OVERRIDES_DIR / GLB_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(src.read_bytes())


def glb_reset() -> None:
    (OVERRIDES_DIR / GLB_TARGET).unlink(missing_ok=True)


def glb_delete_version(file_name: str) -> bool:
    src = GLB_DIR / Path(file_name).name
    if not src.is_file():
        return False
    src.unlink()
    return True


# size is a fraction of the largest framing that never clips at any rotation:
# 1.0 is that maximum, above it the model fills more and its corners can reach
# the canvas edge as it turns.
HERO_RANGES = {"camz": (2.0, 12.0), "camy": (0.0, 4.0), "fov": (20.0, 70.0),
               "size": (0.6, 1.6)}


def get_hero_config() -> dict:
    from . import adminauth as aa

    cfg = aa.setting_get("hero.config") or {}
    return {k: cfg[k] for k in HERO_RANGES if isinstance(cfg.get(k), (int, float))}


def save_hero_config(values: dict) -> dict:
    from . import adminauth as aa

    clean = {}
    for key, (lo, hi) in HERO_RANGES.items():
        v = values.get(key)
        if v in (None, ""):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            raise MediaError("Camera values must be numbers.")
        if not lo <= f <= hi:
            raise MediaError(f"{key} must be between {lo} and {hi}.")
        clean[key] = round(f, 2)
    aa.setting_set("hero.config", clean)
    return clean
