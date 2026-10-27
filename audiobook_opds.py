# -*- coding: utf-8 -*-
"""BookOasis 3.0.2: authenticated OPDS 1.2 for category-first single and multi-track MP3/M4A/M4B audiobooks.

All database access goes through the official plugin gateway. No core patches,
schema changes, credentials in URLs, or subprocesses are required.
"""
import atexit
import io
import json
import math
import uuid
import logging
import os
import threading
import time
import warnings
import xml.etree.ElementTree as ET
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from socketserver import ThreadingMixIn
from urllib.parse import urlencode, urlsplit
from wsgiref.simple_server import ServerHandler, WSGIServer, WSGIRequestHandler

from flask import Flask, Response, abort, g, has_request_context, redirect, request, send_file, session
from PIL import Image, ImageDraw
from werkzeug.exceptions import HTTPException, RequestedRangeNotSatisfiable
from werkzeug.security import check_password_hash
from plugins.metadata.base import BaseMetadataProvider

LOG = logging.getLogger("audiobook_opds")
ATOM = "http://www.w3.org/2005/Atom"
OPDS = "http://opds-spec.org/2010/catalog"
DC = "http://purl.org/dc/terms/"
OPENSEARCH = "http://a9.com/-/spec/opensearch/1.1/"
ACQUISITION = "http://opds-spec.org/acquisition"
FEED_TYPE = "application/atom+xml;profile=opds-catalog;kind=acquisition"
NAV_TYPE = "application/atom+xml;profile=opds-catalog;kind=navigation"
ENTRY_TYPE = "application/atom+xml;type=entry;profile=opds-catalog"
AUDIO_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".m4b": "audio/mp4"}
SUPPORTED_TRACK_SQL = "(" + " OR ".join("LOWER(t.file_path) LIKE '%" + ext + "'" for ext in AUDIO_TYPES) + ")"
ET.register_namespace("", ATOM)
ET.register_namespace("opds", OPDS)
ET.register_namespace("dcterms", DC)

DEFAULTS = {"service_enabled": False, "bind_host": "0.0.0.0", "port": 5941,
            "public_base_url": "", "page_size": 30, "title": "BookOasis Audiobooks"}
# Only these fixed SQL fragments can reach ORDER BY; query input is never SQL.
SORT_OPTIONS = OrderedDict([
    ("title_asc", ("제목 가나다순", "LOWER(a.title) ASC, a.id ASC")),
    ("title_desc", ("제목 역순", "LOWER(a.title) DESC, a.id DESC")),
    ("added_desc", ("최신 추가순", "COALESCE(a.created_at, '') DESC, a.id DESC")),
    ("added_asc", ("오래된 추가순", "COALESCE(a.created_at, '') ASC, a.id ASC")),
    ("updated_desc", ("최근 수정순", "COALESCE(a.updated_at, a.created_at, '') DESC, a.id DESC")),
])
DEFAULT_SORT = "title_asc"
_START_LOCK = threading.Lock()
_SUPERVISOR = None


def _bool(value):
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def normalize_config(raw):
    config = dict(DEFAULTS)
    config.update(raw or {})
    config["service_enabled"] = _bool(config["service_enabled"])
    for key, low, high in (("port", 1024, 65535), ("page_size", 1, 100)):
        value = int(config[key])
        if not low <= value <= high:
            raise ValueError("Invalid " + key)
        config[key] = value
    host = str(config["bind_host"]).strip()
    if host not in ("0.0.0.0", "127.0.0.1"):
        raise ValueError("bind_host must be 0.0.0.0 or 127.0.0.1")
    config["bind_host"] = host
    base = str(config["public_base_url"]).strip().rstrip("/")
    if base:
        parts = urlsplit(base)
        if (parts.scheme not in ("http", "https") or not parts.hostname
                or parts.username or parts.password or parts.query or parts.fragment
                or any(ord(c) < 33 for c in base)):
            raise ValueError("Invalid public_base_url")
        # A path prefix is supported when a proxy strips it before forwarding.
        parts.port  # Validate malformed ports now, before opening a listener.
    config["public_base_url"] = base
    config["title"] = str(config["title"] or DEFAULTS["title"])[:200]
    return config


def _text(value):
    # XML 1.0 permits only these character ranges, even in escaped text.
    return "".join(c for c in str(value or "") if c in "\t\n\r" or
                   0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or
                   0x10000 <= ord(c) <= 0x10FFFF)


def _el(parent, name, text=None, **attrs):
    node = ET.SubElement(parent, "{" + ATOM + "}" + name, attrs)
    if text is not None:
        node.text = _text(text)
    return node


def _date(value=None):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        result = datetime.now(timezone.utc)
    return result.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _inside(path, root):
    if not path or not root or not os.path.isabs(path) or not os.path.isabs(root):
        return None
    resolved, boundary = os.path.realpath(path), os.path.realpath(root)
    try:
        return resolved if os.path.commonpath((resolved, boundary)) == boundary else None
    except (ValueError, OSError):
        return None


def _media_path(book, track):
    folder = _inside(book["folder_path"], book["physical_path"])
    path = _inside(track["file_path"], folder) if folder else None
    if not path or os.path.splitext(path)[1].lower() not in AUDIO_TYPES:
        abort(404)
    if not os.path.isfile(path):
        abort(404)
    return path


def _can_download(user):
    return user["role"] == "admin" or user["has_download_access"] == 1


class _AuthThrottle:
    """Bounded per-process failed-login throttle; never retains credentials."""
    def __init__(self):
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def blocked(self, address):
        with self.lock:
            now = time.monotonic()
            count, started = self.items.get(address, (0, now))
            if now - started >= 60:
                self.items.pop(address, None)
                return False
            return count >= 20

    def failed(self, address):
        with self.lock:
            now = time.monotonic()
            count, started = self.items.pop(address, (0, now))
            if now - started >= 60:
                count, started = 0, now
            self.items[address] = (count + 1, started)
            if len(self.items) > 4096:
                self.items.popitem(last=False)


_BOOK_SELECT = """
SELECT a.id, a.library_id, a.title, a.author, a.publisher, a.description,
       a.poster, a.folder_path, a.created_at, a.updated_at,
       l.physical_path, l.hide_cover,
       (SELECT COUNT(*) FROM audiobook_tracks n WHERE n.audiobook_id=a.id) AS track_count
FROM audiobooks a
JOIN libraries l ON l.id = a.library_id
WHERE COALESCE(a.is_deleted, 0) = 0 AND COALESCE(l.pending_delete, 0) = 0
AND EXISTS (SELECT 1 FROM audiobook_tracks t WHERE t.audiobook_id=a.id AND
""" + SUPPORTED_TRACK_SQL + ")"

_TRACK_BASE_SELECT = """
SELECT t.id, t.audiobook_id, t.track_number, t.title, t.artist,
       t.file_path, t.filename, t.duration, t.file_size
FROM audiobook_tracks t WHERE """
_TRACK_SELECT = _TRACK_BASE_SELECT + "t.audiobook_id = ? AND " + SUPPORTED_TRACK_SQL


def _permission(user):
    if user["role"] == "admin":
        return "", []
    return (" AND EXISTS (SELECT 1 FROM user_category_permissions p WHERE "
            "p.library_id = l.id AND p.user_id = ? AND p.has_access = 1)", [user["id"]])


@lru_cache(maxsize=1)
def _placeholder():
    image = Image.new("RGB", (360, 480), "#172b3a")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((78, 128, 282, 352), radius=18, outline="#9db9c7", width=8)
    draw.line((180, 145, 180, 334), fill="#9db9c7", width=6)
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85)
    return out.getvalue()


def _cover_bytes(book):
    if book.get("hide_cover") == 1:
        return _placeholder()
    poster = str(book.get("poster") or "")
    data = None
    try:
        if poster.startswith(("http://", "https://")):
            # Unlike the general poster helper, this core helper validates SSRF
            # targets and every redirect and imposes a response size limit.
            from utils.cover_helper import get_or_cache_external_image_webp
            path = get_or_cache_external_image_webp(poster, "audiobook_opds")
            if path and os.path.getsize(path) <= 20 * 1024 * 1024:
                with open(path, "rb") as source:
                    data = source.read(20 * 1024 * 1024 + 1)
        else:
            path = _inside(poster, book["physical_path"])
            if path and os.path.isfile(path):
                ext = os.path.splitext(path)[1].lower()
                if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    if os.path.getsize(path) <= 20 * 1024 * 1024:
                        with open(path, "rb") as source:
                            data = source.read(20 * 1024 * 1024 + 1)
                elif ext in (".json", ".mp3", ".m4a", ".m4b"):
                    from services.audiobook_scanner import read_embedded_cover, read_metadata_json_cover
                    data = (read_metadata_json_cover(path) if ext == ".json"
                            else read_embedded_cover(path))
        if data and len(data) <= 20 * 1024 * 1024:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(data)) as image:
                    image.thumbnail((600, 800))
                    out = io.BytesIO()
                    image.convert("RGB").save(out, "JPEG", quality=85)
                    return out.getvalue()
    except Exception:
        # A missing/invalid cover must not prevent catalog or audio access.
        LOG.debug("Cover unavailable for audiobook id=%s", book["id"])
    return _placeholder()


def _public_record(record):
    """Keep bridge bookkeeping private; the existing APK protocol is unchanged."""
    return {k: v for k, v in record.items() if not k.startswith("_")}


def _invalidate_native_history(user_id):
    # Same cache invalidation used by the installed native progress route.
    try:
        from utils.redis_helper import redis_delete_pattern
        redis_delete_pattern(f"cache:history*:audiobook:{user_id}:*")
        redis_delete_pattern(f"user:audiobook_progress:{user_id}:*")
    except Exception:
        # Redis is optional in BookOasis; a cache outage must not lose a save.
        LOG.debug("Native history cache invalidation unavailable")


class _NativeProgressBridge:
    """Gateway-only, recoverable bridge to the native web player's tables.

    Native saves have no revision and second-resolution timestamps. Compare all
    native fields, not only the clock, before mirroring. A pending target in the
    existing user record survives crashes between the two database commits.
    """
    columns = ("current_track_id", "current_time", "total_progress_pct",
               "playback_rate", "is_completed", "last_listened_at")

    def __init__(self, general, audio, user_id):
        self.general, self.audio, self.uid = general, audio, user_id
        self.prefix = "AUDIOBOOK_OPDS_SYNC_V1_U" + str(user_id) + "_"
        self.clock = None

    def key(self, bid):
        return self.prefix + "B" + str(bid)

    def read(self, bid):
        row = self.general.fetch_one(
            "SELECT `value` FROM user_settings WHERE user_id=? AND `key`=?", [self.uid, self.key(bid)])
        raw = row["value"] if row else None
        return raw, json.loads(raw) if raw else {"revision": 0}

    def save(self, bid, raw, record):
        encoded = json.dumps(record, separators=(",", ":"), allow_nan=False)
        if raw is None:
            try:
                self.general.execute("INSERT INTO user_settings (user_id,`key`,`value`) VALUES (?,?,?)",
                                     [self.uid, self.key(bid), encoded])
                return True
            except Exception:
                if self.read(bid)[0] is None:
                    raise
                return False
        return self.general.execute(
            "UPDATE user_settings SET `value`=? WHERE user_id=? AND `key`=? AND `value`=?",
            [encoded, self.uid, self.key(bid), raw]) == 1

    def native(self, bid):
        row = self.audio.fetch_one("SELECT " + ",".join("`" + c + "`" for c in self.columns) +
                                  " FROM audiobook_progress WHERE audiobook_id=? AND user_id=?", [bid, self.uid])
        if row is None:
            return None
        result = dict(row)
        if result["last_listened_at"] is not None:
            result["last_listened_at"] = str(result["last_listened_at"])
        return result

    def db_clock(self):
        if self.clock is None:
            row = self.audio.fetch_one("SELECT CURRENT_TIMESTAMP AS stamp")
            self.clock = (datetime.fromisoformat(str(row["stamp"])), int(time.time()) * 1000)
        return self.clock

    def milliseconds(self, stamp):
        if stamp is None:
            return 0
        try:
            now, epoch = self.db_clock()
            return int(epoch + (datetime.fromisoformat(str(stamp)) - now).total_seconds() * 1000)
        except (ValueError, TypeError):
            return 0

    def stamp(self, milliseconds):
        now, epoch = self.db_clock()
        return (now + timedelta(milliseconds=milliseconds - epoch)).isoformat(sep=" ", timespec="seconds")

    def tracks(self, bid):
        return self.audio.fetch_all("SELECT id, duration FROM audiobook_tracks WHERE audiobook_id=? "
                                    "ORDER BY track_number ASC, id ASC", [bid])

    def from_native(self, bid, native, record):
        if native is None:
            return None
        tid = native["current_track_id"]
        track = self.audio.fetch_one(_TRACK_BASE_SELECT + "t.audiobook_id=? AND t.id=? AND " + SUPPORTED_TRACK_SQL,
                                     [bid, tid])
        if not track:
            return None
        duration = record.get("_durations", {}).get(str(tid)) or track["duration"]
        if not duration and record.get("progress", {}).get("trackId") == tid:
            duration = record["progress"]["duration"]
        try:
            duration = float(duration or 0)
            position = float(native["current_time"] or 0)
            speed = float(native["playback_rate"] or 1)
            if not (math.isfinite(duration) and .001 <= duration <= 31536000 and math.isfinite(position)):
                return None
            # Native 'mark completed' can store whole-book seconds in this field.
            if not native["is_completed"] and position > duration + 1:
                return None
            if not math.isfinite(speed):
                return None
            return {"trackId": int(tid), "position": min(duration, max(0, position)),
                    "duration": duration, "speed": min(4, max(.25, speed)),
                    "completed": bool(native["is_completed"])}
        except (TypeError, ValueError):
            return None

    def target(self, bid, record):
        p = record["progress"]
        tracks = self.tracks(bid)
        index = next((i for i, t in enumerate(tracks) if t["id"] == p["trackId"]), None)
        if index is None:
            return None
        durations = dict(record.get("_durations", {}))
        durations[str(p["trackId"])] = p["duration"]
        record["_durations"] = durations
        lengths = [float(durations.get(str(t["id"])) or t["duration"] or 0) for t in tracks]
        if all(math.isfinite(n) and n > 0 for n in lengths):
            pct = (sum(lengths[:index]) + min(p["duration"], p["position"])) / sum(lengths) * 100
        else:
            pct = (index + min(1, p["position"] / p["duration"])) / len(tracks) * 100
        return dict(zip(self.columns, [p["trackId"], p["position"], 100 if p["completed"] else pct,
                                      p["speed"], int(p["completed"]), self.stamp(record["updatedAt"])]))

    def predicate(self, snapshot):
        sql, params = [], []
        for col in self.columns:
            value = snapshot[col]
            sql.append("`" + col + "` IS NULL" if value is None else "`" + col + "`=?")
            if value is not None:
                params.append(value)
        return " AND ".join(sql), params

    def mirror(self, bid, before, target):
        fields = ",".join("`" + col + "`" for col in self.columns)
        values = [target[col] for col in self.columns]
        if before is None:
            try:
                return self.audio.execute("INSERT INTO audiobook_progress (audiobook_id,user_id," + fields +
                    ") SELECT ?,?,?,?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM audiobook_progress "
                    "WHERE audiobook_id=? AND user_id=?)", [bid, self.uid] + values + [bid, self.uid]) == 1
            except Exception:
                if self.native(bid) is None:
                    raise
                return False
        where, params = self.predicate(before)
        return self.audio.execute("UPDATE audiobook_progress SET " +
            ",".join("`" + col + "`=?" for col in self.columns) +
            " WHERE audiobook_id=? AND user_id=? AND " + where, values + [bid, self.uid] + params) == 1

    def mirror_track(self, bid, record, target):
        p = record["progress"]
        percent = min(100, p["position"] / p["duration"] * 100)
        setting = self.general.fetch_one("SELECT `value` FROM user_settings WHERE user_id=? AND `key`='BOOK_COMPLETE_PERCENT'", [self.uid])
        if not setting:
            setting = self.general.fetch_one("SELECT `value` FROM settings WHERE `key`='BOOK_COMPLETE_PERCENT'")
        try:
            threshold = float(setting["value"]) if setting else 95
            if not 50 <= threshold <= 100:
                threshold = 95
        except (TypeError, ValueError):
            threshold = 95
        where, params = self.predicate(target)
        guard = "EXISTS (SELECT 1 FROM audiobook_progress WHERE audiobook_id=? AND user_id=? AND " + where + ")"
        guarded = [bid, self.uid] + params
        values = [p["position"], percent, int(percent >= threshold), target["last_listened_at"]]
        # Never mark skipped tracks as listened. Both writes remain conditional
        # on the native whole-book row still matching this app update.
        self.audio.execute("INSERT INTO audiobook_track_progress "
            "(audiobook_id,track_id,user_id,`current_time`,progress_pct,is_completed,updated_at) "
            "SELECT ?,?,?,?,?,?,? WHERE " + guard + " AND NOT EXISTS (SELECT 1 FROM audiobook_track_progress "
            "WHERE audiobook_id=? AND track_id=? AND user_id=?)",
            [bid, p["trackId"], self.uid] + values + guarded + [bid, p["trackId"], self.uid])
        self.audio.execute("UPDATE audiobook_track_progress SET `current_time`=?,progress_pct=?,is_completed=?,updated_at=? "
            "WHERE audiobook_id=? AND track_id=? AND user_id=? AND " + guard,
            values + [bid, p["trackId"], self.uid] + guarded)

    def reconcile(self, bid):
        for _ in range(5):
            raw, record = self.read(bid)
            native = self.native(bid)
            if "_pending" in record:
                target = record["_pending"]
                if native == target or (native == record.get("_native") and self.mirror(bid, native, target)):
                    self.mirror_track(bid, record, target)
                    # Do not hide a web save arriving during this mirror.
                    if self.native(bid) != target:
                        continue
                    _invalidate_native_history(self.uid)
                    updated = {**record, "_native": target}
                    updated.pop("_pending", None)
                    if self.save(bid, raw, updated):
                        return updated
                    continue
                # Web won the conditional write. Import it as a new revision.
                native = self.native(bid)
            elif "_native" in record and record["_native"] == native:
                # A scanner may fill in a missing track duration without changing
                # the listening row. Retry deferred imports when metadata arrives.
                if record.get("progress") is not None or self.from_native(bid, native, record) is None:
                    return record
            elif "_native" not in record and record.get("progress"):
                # First connection of pre-bridge records: preserve the newer
                # server timestamp. Once linked, snapshots handle same-second edits.
                if native is None or record.get("updatedAt", 0) > self.milliseconds(native["last_listened_at"]) + 1000:
                    updated = {**record, "_native": native}
                    updated.setdefault("updatedAt", int(time.time() * 1000))
                    target = self.target(bid, updated)
                    if target is not None:
                        updated["_pending"] = target
                        if self.save(bid, raw, updated):
                            continue
                        continue
            if raw is None and native is None:
                return record
            progress = self.from_native(bid, native, record)
            same = progress is not None and progress == record.get("progress")
            updated = {k: v for k, v in record.items() if k not in ("progress", "mutationId", "_pending")}
            updated.update(_native=native, revision=record["revision"] + (0 if same else 1),
                           updatedAt=self.milliseconds(native["last_listened_at"]) if native else int(time.time() * 1000))
            if same and "mutationId" in record:
                updated["mutationId"] = record["mutationId"]
            if progress is not None:
                updated["progress"] = progress
                updated["_durations"] = {**record.get("_durations", {}), str(progress["trackId"]): progress["duration"]}
            if raw is None and native is not None:
                updated["_webNew"] = True
            if self.save(bid, raw, updated):
                return updated
        abort(503)


def create_app(provider, config=None):
    config = normalize_config(config)
    app = Flask("audiobook_opds", static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=16384, PROPAGATE_EXCEPTIONS=False)
    throttle = _AuthThrottle()
    sync_lock = threading.RLock()

    def address(path, **params):
        base = config["public_base_url"] or request.url_root.rstrip("/")
        query = urlencode({k: v for k, v in params.items() if v is not None and v != ""})
        return base + path + (("?" + query) if query else "")

    def unavailable(error):
        # Deliberately omit SQL parameters, hashes, file paths and request URLs.
        LOG.error("Request failed: %s", type(error).__name__)
        return Response("Service unavailable\n", status=503, mimetype="text/plain")

    @app.before_request
    def authenticate():
        try:
            gateway = provider.get_db_gateway("general")
            enabled = gateway.get_setting("PLUGIN_ENABLED_audiobook_opds", None)
            if enabled is not None and not _bool(enabled["value"]):
                abort(503)
            if throttle.blocked(request.remote_addr):
                return Response("Too many failed logins\n", status=429,
                                headers={"Retry-After": "60"})
            credentials = request.authorization
            user = None
            if (credentials and credentials.type.lower() == "basic"
                    and credentials.username and credentials.password
                    and len(credentials.username) <= 128 and len(credentials.password) <= 256):
                user = gateway.fetch_one("SELECT id, username, password_hash, role, "
                                         "is_default_password, has_audiobook_access, has_download_access "
                                         "FROM users WHERE username = ?", (credentials.username,))
                if user:
                    try:
                        valid = check_password_hash(user["password_hash"], credentials.password)
                    except (ValueError, TypeError):
                        valid = False
                    if not valid:
                        user = None
            if not user:
                # The first unauthenticated request is the normal Basic-auth
                # challenge, including parallel cover requests from OPDS apps.
                # Count supplied bad credentials, not those initial challenges.
                if credentials is not None:
                    throttle.failed(request.remote_addr)
                return Response("Unauthorized\n", status=401,
                                headers={"WWW-Authenticate": 'Basic realm="BookOasis Audiobooks", charset="UTF-8"'})
            if user["is_default_password"] == 1:
                abort(403)
            if user["role"] != "admin" and user["has_audiobook_access"] != 1:
                abort(403)
            g.user = user
            g.audio = provider.get_db_gateway("audiobook")
        except HTTPException:
            raise
        except Exception as error:
            return unavailable(error)

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Vary"] = "Authorization"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.errorhandler(Exception)
    def on_error(error):
        if isinstance(error, HTTPException):
            return error
        return unavailable(error)

    def xml_response(root, media_type=FEED_TYPE):
        return Response(ET.tostring(root, encoding="utf-8", xml_declaration=True),
                        content_type=media_type + ";charset=utf-8")

    def feed(title, self_url, kind=FEED_TYPE, library_id=None, sort=None):
        root = ET.Element("{" + ATOM + "}feed")
        _el(root, "id", self_url)
        _el(root, "title", title)
        _el(root, "updated", _date())
        _el(root, "link", rel="self", href=self_url, type=kind)
        _el(root, "link", rel="start", href=address("/opds"), type=NAV_TYPE)
        _el(root, "link", rel="https://bookoasis.org/rel/sync", href=address("/opds/sync/v1"), type="application/json")
        _el(root, "link", rel="search", href=address("/opds/search.xml", library_id=library_id, sort=sort),
            type="application/opensearchdescription+xml")
        _el(_el(root, "author"), "name", "BookOasis")
        return root

    def entry(parent, book, complete=False, tracks=None):
        element = (_el(parent, "entry") if parent is not None
                   else ET.Element("{" + ATOM + "}entry"))
        _el(element, "id", "urn:bookoasis:audiobook:" + str(book["id"]))
        _el(element, "title", book["title"])
        _el(element, "updated", _date(book["updated_at"] or book["created_at"]))
        _el(_el(element, "author"), "name", book["author"] or "Unknown")
        _el(element, "summary", book["description"] or "", type="text")
        if book["publisher"]:
            ET.SubElement(element, "{" + DC + "}publisher").text = _text(book["publisher"])
        prefix = "/opds/books/" + str(book["id"])
        _el(element, "link", rel="self" if complete else "alternate", href=address(prefix), type=ENTRY_TYPE)
        for rel in ("http://opds-spec.org/image", "http://opds-spec.org/image/thumbnail"):
            _el(element, "link", rel=rel, href=address(prefix + "/cover"), type="image/jpeg")
        _el(element, "link", rel="subsection", href=address(prefix + "/tracks"),
            type=FEED_TYPE, title="Tracks")
        if complete and tracks is None:
            tracks = g.audio.fetch_all(_TRACK_SELECT + " ORDER BY t.track_number ASC, t.id ASC", [book["id"]])
        for track in tracks or ():
            acquisition_links(element, book, dict(track), single=book["track_count"] == 1)
        return element

    def acquisition_links(element, book, track, single=False):
        prefix = "/opds/books/" + str(book["id"])
        if not single:
            prefix += "/tracks/" + str(track["id"])
        ext = os.path.splitext(track["file_path"])[1].lower()
        _el(element, "link", rel=ACQUISITION, href=address(prefix + "/stream"),
            type=AUDIO_TYPES[ext], title=_text(track["title"] or track["filename"] or "Track " + str(track["track_number"])))
        if _can_download(g.user):
            # One acquisition per file: Readest plays every audio acquisition
            # in document order. A second acquisition for the download URL
            # would play each track twice. The explicit download stays related.
            _el(element, "link", rel="related", href=address(prefix + "/download"),
                type=AUDIO_TYPES[ext], title="Download " + ext[1:].upper())

    def track_entry(parent, book, track):
        element = _el(parent, "entry")
        book_urn = "urn:bookoasis:audiobook:" + str(book["id"])
        _el(element, "id", book_urn + ":track:" + str(track["id"]))
        title = track["title"] or track["filename"] or ("Track " + str(track["track_number"]))
        _el(element, "title", title)
        _el(element, "updated", _date(book["updated_at"] or book["created_at"]))
        _el(_el(element, "author"), "name", book["author"] or track["artist"] or "Unknown")
        _el(element, "summary", book["title"], type="text")
        ET.SubElement(element, "{" + DC + "}isPartOf").text = book_urn
        _el(element, "link", rel="http://opds-spec.org/image", type="image/jpeg",
            href=address("/opds/books/" + str(book["id"]) + "/cover"))
        acquisition_links(element, book, track)
        return element

    def sync_read(gateway, key):
        row = (gateway.fetch_one("SELECT `value` FROM settings WHERE `key` = ?", [key])
               if key == "AUDIOBOOK_OPDS_SYNC_SERVER_V1" else
               gateway.fetch_one("SELECT `value` FROM user_settings WHERE user_id=? AND `key`=?", [g.user["id"], key]))
        return row["value"] if row else None

    def sync_insert(gateway, key, value):
        try:
            if key == "AUDIOBOOK_OPDS_SYNC_SERVER_V1":
                gateway.execute("INSERT INTO settings (`key`,`value`) VALUES (?,?)", [key, value])
            else:
                gateway.execute("INSERT INTO user_settings (user_id,`key`,`value`) VALUES (?,?,?)", [g.user["id"], key, value])
            return True
        except Exception:
            # A different worker may have initialized this same record.
            if sync_read(gateway, key) is None:
                raise
            return False

    def sync_identity(gateway):
        key = "AUDIOBOOK_OPDS_SYNC_SERVER_V1"
        value = sync_read(gateway, key)
        if value is None:
            sync_insert(gateway, key, str(uuid.uuid4()))
            value = sync_read(gateway, key)
        return {"protocol": "bookoasis-audiobook-sync/1", "serverId": value,
                "accountId": str(g.user["id"])}

    def sync_prefix():
        return "AUDIOBOOK_OPDS_SYNC_V1_U" + str(g.user["id"]) + "_"

    def sync_empty(kind):
        return {"revision": 0, **({"bookIds": []} if kind == "queue" else {})}

    @app.route("/opds/sync/v1", methods=["GET", "POST"])
    def sync_state():
        with sync_lock:
            return sync_state_locked()

    def sync_state_locked():
        # Use the authenticated general identity, never a caller-supplied user id.
        gateway = provider.get_db_gateway("general")
        identity = sync_identity(gateway)
        prefix = sync_prefix()
        bridge = _NativeProgressBridge(gateway, g.audio, g.user["id"])
        if request.method == "GET":
            clause, params = _permission(g.user)
            allowed = {int(row["id"]): dict(row) for row in g.audio.fetch_all(_BOOK_SELECT + clause, params)}
            rows = gateway.fetch_all("SELECT `key`,`value` FROM user_settings WHERE user_id=? AND `key` LIKE ? ESCAPE '=' LIMIT 1002", [g.user["id"], prefix.replace("_", "=_") + "%"])
            queue = sync_empty("queue")
            progress = {}
            for row in rows:
                suffix = row["key"][len(prefix):]
                record = json.loads(row["value"])
                if suffix == "QUEUE":
                    queue = {**record, "bookIds": [bid for bid in record["bookIds"] if bid in allowed]}
                elif suffix.startswith("B") and suffix[1:].isdigit() and int(suffix[1:]) in allowed:
                    progress[suffix[1:]] = record
            native_ids = g.audio.fetch_all("SELECT audiobook_id FROM audiobook_progress WHERE user_id=? "
                                          "ORDER BY last_listened_at DESC LIMIT 1000", [g.user["id"]])
            ids = list(dict.fromkeys([int(bid) for bid in progress] +
                                    [int(r["audiobook_id"]) for r in native_ids if int(r["audiobook_id"]) in allowed]))[:1000]
            records = {bid: bridge.reconcile(bid) for bid in ids}
            new_web = [bid for bid, record in records.items() if record.get("_webNew")]
            if new_web:
                for _ in range(5):
                    queue_raw = sync_read(gateway, prefix + "QUEUE")
                    stored_queue = json.loads(queue_raw) if queue_raw else sync_empty("queue")
                    merged = list(dict.fromkeys(stored_queue["bookIds"] + new_web))[:100]
                    if merged == stored_queue["bookIds"]:
                        break
                    new_queue = {"revision": stored_queue["revision"] + 1, "bookIds": merged,
                                 "updatedAt": int(time.time() * 1000), "mutationId": str(uuid.uuid4())}
                    encoded = json.dumps(new_queue, separators=(",", ":"))
                    if (sync_insert(gateway, prefix + "QUEUE", encoded) if queue_raw is None else
                        gateway.execute("UPDATE user_settings SET `value`=? WHERE user_id=? AND `key`=? AND `value`=?",
                                        [encoded, g.user["id"], prefix + "QUEUE", queue_raw]) == 1):
                        stored_queue = new_queue
                        break
                else:
                    abort(503)
                queue = {**stored_queue, "bookIds": [bid for bid in stored_queue["bookIds"] if bid in allowed]}
                for bid in new_web:
                    raw, record = bridge.read(bid)
                    bridge.save(bid, raw, {**record, "_webNew": False})
            progress = {str(bid): _public_record(record) for bid, record in records.items()}
            books = []
            for bid in queue["bookIds"]:
                book = allowed[bid]
                tracks = g.audio.fetch_all(_TRACK_SELECT + " ORDER BY t.track_number ASC, t.id ASC", [bid])
                books.append({"id": bid, "title": book["title"], "author": book["author"] or "",
                              "cover": address("/opds/books/" + str(bid) + "/cover"),
                              "tracks": [{"id": int(t["id"]), "title": t["title"] or t["filename"] or "Track",
                                          "href": address("/opds/books/" + str(bid) + "/tracks/" + str(t["id"]) + "/stream"),
                                          "mimeType": AUDIO_TYPES[os.path.splitext(t["file_path"])[1].lower()]}
                                         for t in tracks]})
            return {**identity, "queue": queue, "progress": progress, "books": books}

        body = request.get_json()
        if not isinstance(body, dict):
            abort(400)
        kind = body.get("kind")
        fields = {"kind", "baseRevision", "mutationId"} | ({"bookIds"} if kind == "queue" else {"bookId", "progress"})
        if kind not in ("queue", "progress") or set(body) != fields:
            abort(400)
        revision = body["baseRevision"]
        if type(revision) is not int or revision < 0 or revision > 9007199254740000:
            abort(400)
        try:
            if not isinstance(body["mutationId"], str) or str(uuid.UUID(body["mutationId"])) != body["mutationId"]:
                abort(400)
        except (ValueError, TypeError, AttributeError):
            abort(400)
        if kind == "queue":
            ids = body["bookIds"]
            if (not isinstance(ids, list) or len(ids) > 100 or
                    any(type(bid) is not int or bid <= 0 for bid in ids) or len(set(ids)) != len(ids)):
                abort(400)
            for bid in ids:
                get_book(bid)
            key = prefix + "QUEUE"
            payload = {"bookIds": ids}
        else:
            bid, progress = body["bookId"], body["progress"]
            if type(bid) is not int or bid <= 0:
                abort(400)
            get_book(bid)
            if (not isinstance(progress, dict) or
                    set(progress) != {"trackId", "position", "duration", "speed", "completed"} or
                    type(progress["trackId"]) is not int or type(progress["completed"]) is not bool):
                abort(400)
            for name, low, high in (("position", 0, 31536000), ("duration", 0.001, 31536000), ("speed", 0.25, 4)):
                value = progress[name]
                if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
                    abort(400)
            if progress["position"] > progress["duration"] + 1:
                abort(400)
            if not g.audio.fetch_one(_TRACK_BASE_SELECT + "t.audiobook_id=? AND t.id=? AND " + SUPPORTED_TRACK_SQL,
                                     [bid, progress["trackId"]]):
                abort(404)
            key = prefix + "B" + str(bid)
            payload = {"progress": progress}
        if kind == "progress":
            bridge.reconcile(bid)
        raw = sync_read(gateway, key)
        current = json.loads(raw) if raw is not None else sync_empty(kind)
        if current.get("mutationId") == body["mutationId"]:
            return {**identity, "record": _public_record(current)}
        if current["revision"] != revision:
            return {**identity, "record": _public_record(current)}, 409
        if raw is None and kind == "progress":
            count = gateway.fetch_one("SELECT COUNT(*) AS n FROM user_settings WHERE user_id=? AND `key` LIKE ? ESCAPE '='", [g.user["id"], prefix.replace("_", "=_") + "B%"])
            if count["n"] >= 1000:
                abort(413)
        record = {**payload, "revision": revision + 1, "mutationId": body["mutationId"],
                  "updatedAt": int(time.time() * 1000)}
        if kind == "progress":
            record.update(_native=current.get("_native"), _durations=current.get("_durations", {}))
            record["_pending"] = bridge.target(bid, record)
        encoded = json.dumps(record, separators=(",", ":"), allow_nan=False)
        if raw is None:
            success = sync_insert(gateway, key, encoded)
        else:
            success = gateway.execute("UPDATE user_settings SET `value`=? WHERE user_id=? AND `key`=? AND `value`=?", [encoded, g.user["id"], key, raw]) == 1
        if not success:
            current = json.loads(sync_read(gateway, key))
            return {**identity, "record": _public_record(current)}, (200 if current.get("mutationId") == body["mutationId"] else 409)
        if kind == "progress":
            record = bridge.reconcile(bid)
        return {**identity, "record": _public_record(record)}, (200 if record.get("mutationId") == body["mutationId"] else 409)

    def get_book(book_id):
        clause, params = _permission(g.user)
        row = g.audio.fetch_one(_BOOK_SELECT + clause + " AND a.id = ?", params + [book_id])
        if not row:
            abort(404)
        return dict(row)

    def get_library(library_id):
        clause, params = _permission(g.user)
        row = g.audio.fetch_one("SELECT l.id, l.name FROM libraries l WHERE "
                                "COALESCE(l.pending_delete, 0) = 0" + clause + " AND l.id = ?",
                                params + [library_id])
        if not row:
            abort(404)
        return dict(row)

    def category_feed(path):
        page = page_number()
        size = config["page_size"]
        clause, params = _permission(g.user)
        query = ("SELECT l.id, l.name, (SELECT COUNT(*) FROM audiobooks a "
                 "WHERE a.library_id = l.id AND COALESCE(a.is_deleted, 0) = 0 "
                 "AND EXISTS (SELECT 1 FROM audiobook_tracks t WHERE t.audiobook_id = a.id AND "
                 + SUPPORTED_TRACK_SQL + ")) AS book_count FROM libraries l WHERE "
                 "COALESCE(l.pending_delete, 0) = 0" + clause +
                 " ORDER BY COALESCE(l.sort_order, 0), l.name, l.id LIMIT ? OFFSET ?")
        rows = g.audio.fetch_all(query, params + [size + 1, (page - 1) * size])
        root = feed(config["title"], address(path, page=page), NAV_TYPE)
        for row in rows[:size]:
            child = _el(root, "entry")
            _el(child, "id", "urn:bookoasis:audiobook:library:" + str(row["id"]))
            _el(child, "title", row["name"])
            _el(child, "updated", _date())
            _el(child, "summary", str(row["book_count"]) + "권", type="text")
            _el(child, "link", rel="subsection", href=address("/opds", library_id=row["id"]),
                type=FEED_TYPE)
        if len(rows) > size:
            _el(root, "link", rel="next", href=address(path, page=page + 1), type=NAV_TYPE)
        if page > 1:
            _el(root, "link", rel="previous", href=address(path, page=page - 1), type=NAV_TYPE)
        return xml_response(root, NAV_TYPE)

    def get_track(book, track_id=None):
        if track_id is None:
            if book["track_count"] != 1:
                abort(404)
            row = g.audio.fetch_one(_TRACK_SELECT, [book["id"]])
        else:
            row = g.audio.fetch_one(_TRACK_SELECT + " AND t.id = ?", [book["id"], track_id])
        if not row:
            abort(404)
        return dict(row)

    def page_number():
        try:
            page = int(request.args.get("page", "1"))
            if not 1 <= page <= 10000:
                abort(400)
            return page
        except ValueError:
            abort(400)

    def sort_order():
        key = request.args.get("sort", DEFAULT_SORT)
        if key not in SORT_OPTIONS:
            abort(400)
        return key

    def sort_links(root, path, selected, query, library_id):
        for key, (label, _) in SORT_OPTIONS.items():
            link = _el(root, "link", rel="http://opds-spec.org/facet", title=label,
                       href=address(path, q=query, library_id=library_id, sort=key), type=FEED_TYPE)
            link.set("{" + OPDS + "}facetGroup", "정렬")
            if key == selected:
                link.set("{" + OPDS + "}activeFacet", "true")

    @app.route("/")
    def index():
        return redirect(address("/opds"), code=302)

    @app.route("/opds")
    @app.route("/opds/")
    def catalog():
        if "library_id" in request.args or request.args.get("q", "").strip():
            return book_catalog()
        return category_feed("/opds")

    @app.route("/opds/books")
    def book_catalog():
        try:
            page = int(request.args.get("page", "1"))
            library_id = request.args.get("library_id")
            library_id = int(library_id) if library_id is not None else None
            if not 1 <= page <= 10000 or (library_id is not None and library_id < 1):
                abort(400)
        except ValueError:
            abort(400)
        query = request.args.get("q", "").strip()
        if len(query) > 200:
            abort(400)
        library = get_library(library_id) if library_id is not None else None
        clause, params = _permission(g.user)
        if library_id is not None:
            clause += " AND l.id = ?"
            params.append(library_id)
        if query:
            escaped = query.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            clause += " AND (a.title LIKE ? ESCAPE '!' OR a.author LIKE ? ESCAPE '!')"
            params.extend(["%" + escaped + "%"] * 2)
        selected_sort = sort_order()
        size = config["page_size"]
        rows = g.audio.fetch_all(_BOOK_SELECT + clause +
                                 " ORDER BY " + SORT_OPTIONS[selected_sort][1] + " LIMIT ? OFFSET ?",
                                 params + [size + 1, (page - 1) * size])
        path = request.path.rstrip("/")
        title = library["name"] if library else config["title"]
        root = feed(title, address(path, page=page, q=query, library_id=library_id, sort=selected_sort),
                    FEED_TYPE, library_id=library_id, sort=selected_sort)
        sort_links(root, path, selected_sort, query, library_id)
        _el(root, "link", rel="up", href=address("/opds"), type=NAV_TYPE)
        # Acquisition links make clients render books with covers, rather than
        # text-only navigation cards. Fetch only this page's track metadata in
        # one query; catalog browsing never opens or probes the media files.
        visible = rows[:size]
        track_groups = {row["id"]: [] for row in visible}
        if track_groups:
            placeholders = ",".join("?" for _ in track_groups)
            tracks = g.audio.fetch_all(
                _TRACK_BASE_SELECT + "t.audiobook_id IN (" + placeholders + ") AND "
                + SUPPORTED_TRACK_SQL + " ORDER BY t.audiobook_id, t.track_number ASC, t.id ASC",
                list(track_groups))
            for track in tracks:
                track_groups[track["audiobook_id"]].append(track)
        for row in visible:
            entry(root, dict(row), tracks=track_groups[row["id"]])
        if len(rows) > size:
            _el(root, "link", rel="next", href=address(path, page=page + 1, q=query,
                                                       library_id=library_id, sort=selected_sort), type=FEED_TYPE)
        if page > 1:
            _el(root, "link", rel="previous", href=address(path, page=page - 1, q=query,
                                                           library_id=library_id, sort=selected_sort), type=FEED_TYPE)
        return xml_response(root, FEED_TYPE)

    @app.route("/opds/libraries")
    def libraries():
        return category_feed("/opds/libraries")

    @app.route("/opds/search.xml")
    def search_description():
        library_id = request.args.get("library_id")
        if library_id is not None:
            try:
                library_id = int(library_id)
                if library_id < 1:
                    abort(400)
            except ValueError:
                abort(400)
            get_library(library_id)
        selected_sort = sort_order() if "sort" in request.args else None
        target = address("/opds", library_id=library_id, sort=selected_sort)
        template = target + ("&" if "?" in target else "?") + "q={searchTerms}"
        root = ET.Element("{" + OPENSEARCH + "}OpenSearchDescription")
        for key, value in (("ShortName", "Audiobooks"), ("Description", "Search BookOasis audiobooks"),
                           ("InputEncoding", "UTF-8")):
            ET.SubElement(root, "{" + OPENSEARCH + "}" + key).text = value
        ET.SubElement(root, "{" + OPENSEARCH + "}Url", {"type": FEED_TYPE,
                      "template": template})
        return xml_response(root, "application/opensearchdescription+xml")

    @app.route("/opds/books/<int:book_id>")
    def detail(book_id):
        book = get_book(book_id)
        return xml_response(entry(None, book, complete=True), ENTRY_TYPE)

    @app.route("/opds/books/<int:book_id>/cover")
    def cover(book_id):
        return Response(_cover_bytes(get_book(book_id)), mimetype="image/jpeg")

    @app.route("/opds/books/<int:book_id>/tracks")
    def tracks(book_id):
        book = get_book(book_id)
        page = page_number()
        size = config["page_size"]
        rows = g.audio.fetch_all(_TRACK_SELECT + " ORDER BY t.track_number ASC, t.id ASC LIMIT ? OFFSET ?",
                                 [book_id, size + 1, (page - 1) * size])
        prefix = "/opds/books/" + str(book_id) + "/tracks"
        root = feed(book["title"], address(prefix, page=page), library_id=book["library_id"])
        _el(root, "link", rel="up", href=address("/opds", library_id=book["library_id"]), type=FEED_TYPE)
        for row in rows[:size]:
            track_entry(root, book, dict(row))
        if len(rows) > size:
            _el(root, "link", rel="next", href=address(prefix, page=page + 1), type=FEED_TYPE)
        if page > 1:
            _el(root, "link", rel="previous", href=address(prefix, page=page - 1), type=FEED_TYPE)
        return xml_response(root)

    def audio(book_id, attachment, track_id=None):
        book = get_book(book_id)
        track = get_track(book, track_id)
        if attachment and not _can_download(g.user):
            abort(403)
        path = _media_path(book, track)
        size = os.path.getsize(path)
        try:
            response = send_file(path, mimetype=AUDIO_TYPES[os.path.splitext(path)[1].lower()], as_attachment=attachment,
                                 download_name=os.path.basename(path), conditional=True, etag=True)
        except RequestedRangeNotSatisfiable:
            return Response(status=416, headers={"Content-Range": "bytes */" + str(size),
                                                "Accept-Ranges": "bytes"})
        response.headers["Accept-Ranges"] = "bytes"
        return response

    @app.route("/opds/books/<int:book_id>/stream")
    def stream(book_id):
        return audio(book_id, False)

    @app.route("/opds/books/<int:book_id>/download")
    def download(book_id):
        return audio(book_id, True)

    @app.route("/opds/books/<int:book_id>/tracks/<int:track_id>/stream")
    def track_stream(book_id, track_id):
        return audio(book_id, False, track_id)

    @app.route("/opds/books/<int:book_id>/tracks/<int:track_id>/download")
    def track_download(book_id, track_id):
        return audio(book_id, True, track_id)

    return app


class _QuietHandler(WSGIRequestHandler):
    # The core logger is enough. Request URLs may contain private searches.
    def log_request(self, code="-", size="-"):
        pass

    def handle(self):
        self.connection.settimeout(30)
        self.raw_requestline = self.rfile.readline(65537)
        if len(self.raw_requestline) > 65536:
            self.requestline = self.request_version = self.command = ""
            self.send_error(414)
            return
        if not self.parse_request():
            return
        handler = ServerHandler(self.rfile, self.wfile, self.get_stderr(),
                                self.get_environ(), multithread=True)
        handler.request_handler = self
        handler.run(self.server.get_app())


class _LimitedServer(ThreadingMixIn, WSGIServer):
    """Embedded WSGI listener with a bounded number of concurrent connections."""
    daemon_threads = True
    block_on_close = False

    def __init__(self, host, port, app):
        self.slots = threading.BoundedSemaphore(16)
        super().__init__((host, port), _QuietHandler)
        self.set_app(app)

    def process_request(self, connection, client_address):
        if not self.slots.acquire(blocking=False):
            connection.close()
            return
        try:
            super().process_request(connection, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, connection, client_address):
        try:
            super().process_request_thread(connection, client_address)
        finally:
            self.slots.release()


class _Supervisor:
    def __init__(self, provider):
        self.provider = provider
        self.pid = os.getpid()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="audiobook_opds", daemon=True)
        self.server = None
        self.worker = None
        self.current_config = None
        self.last_problem = None

    def close_listener(self):
        if self.server is not None:
            if self.worker is not None and self.worker.is_alive():
                self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.worker is not None:
            if self.worker.ident is not None:
                self.worker.join(timeout=2)
            self.worker = None
        self.current_config = None

    def stop(self):
        self.stop_event.set()
        if self.thread is not threading.current_thread():
            self.thread.join(timeout=4)

    def problem(self, error):
        # Repeated bind conflicts can occur while another gunicorn worker owns
        # the port. Do not announce a successful service merely because hook ran.
        code = type(error).__name__
        if code != self.last_problem:
            LOG.warning("Listener unavailable (%s); will retry", code)
            self.last_problem = code

    def run(self):
        try:
            while not self.stop_event.is_set():
                try:
                    config = normalize_config(self.provider.get_plugin_config("general", default={}))
                    enabled = self.provider.get_db_gateway("general").get_setting(
                        "PLUGIN_ENABLED_audiobook_opds", None)
                    if enabled is not None and not _bool(enabled["value"]):
                        config["service_enabled"] = False
                    if self.server is not None and (config != self.current_config or
                                                    not self.worker.is_alive()):
                        self.close_listener()
                    if config["service_enabled"] and self.server is None:
                        server = _LimitedServer(config["bind_host"], config["port"],
                                                create_app(self.provider, config))
                        self.server = server
                        self.current_config = config
                        self.worker = threading.Thread(target=server.serve_forever,
                                                       kwargs={"poll_interval": 0.2},
                                                       name="audiobook_opds_http", daemon=True)
                        self.worker.start()
                        self.last_problem = None
                        LOG.info("Listening on %s:%s", config["bind_host"], config["port"])
                except Exception as error:
                    self.close_listener()
                    self.problem(error)
                self.stop_event.wait(5)
        finally:
            self.close_listener()


def _positive_duration(value):
    try:
        result = float(value or 0)
        return result if math.isfinite(result) and 0 < result <= 31536000 else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def _listening_summary(row, tracks, cached=None):
    """Read-only whole-book location, never seconds divided by track count.

    Earlier episodes count towards location, not actual time spent listening.
    Unknown lengths are explicitly distinguished from time-based progress.
    """
    cached = cached if isinstance(cached, dict) else {}
    lengths = [_positive_duration(cached.get(str(t['id']))) or
               _positive_duration(t['duration']) for t in tracks]
    index = next((i for i, t in enumerate(tracks) if t['id'] == row['current_track_id']), None)
    position = _positive_duration(row['current_time'])
    completed = row['is_completed'] == 1
    result = {'trackIndex': index + 1 if index is not None else None,
              'trackCount': len(tracks), 'completed': completed,
              'percent': None, 'basis': 'unknown', 'elapsed': None,
              'total': None, 'remaining': None}
    total = sum(lengths) if lengths and all(lengths) else None
    if completed:
        result.update(percent=100, basis='completed', elapsed=total, total=total,
                      remaining=0 if total is not None else None)
    elif index is not None and total is not None:
        elapsed = sum(lengths[:index]) + min(position, lengths[index])
        result.update(percent=elapsed / total * 100, basis='time',
                      elapsed=elapsed, total=total, remaining=max(0, total - elapsed))
    elif index is not None and lengths[index]:
        result.update(percent=(index + min(position / lengths[index], 1)) / len(tracks) * 100,
                      basis='tracks')
    return result


class AudiobookOpdsMetadataProvider(BaseMetadataProvider):
    id = "audiobook_opds"
    name = "오디오북 OPDS"
    is_searchable = False
    enabled = True
    home_widget = {
        'title': '오디오북 청취 진행률', 'subtitle': '전체 회차 기준 · 이어 듣기',
        'icon': 'fa-solid fa-headphones', 'order': 15, 'limit': 6,
        'sessions': ['audiobook'], 'layout': 'full', 'frame': 'card',
    }
    config_schema = [
        {"key": "service_enabled", "label": "OPDS 서비스 시작", "type": "checkbox", "default": False,
         "description": "켜면 별도 포트에서 기존 BookOasis 계정으로 접속합니다."},
        {"key": "bind_host", "label": "수신 주소", "type": "text", "default": "0.0.0.0",
         "description": "Docker 포트 게시: 0.0.0.0 / 같은 컨테이너 프록시 전용: 127.0.0.1"},
        {"key": "port", "label": "컨테이너 내부 포트", "type": "number", "default": 5941},
        {"key": "public_base_url", "label": "앱에서 접속할 기본 URL", "type": "text", "default": "",
         "description": "예: https://audio.example.org (끝에 /opds를 붙이지 마세요). 비우면 요청 주소 사용."},
        {"key": "page_size", "label": "페이지당 목록 항목 수", "type": "number", "default": 30},
        {"key": "title", "label": "카탈로그 제목", "type": "text", "default": "BookOasis Audiobooks"},
    ]

    def search(self, db_type, query):
        return []

    def apply(self, db_type, book_id, item_data):
        return False, "오디오북 OPDS는 메타데이터 적용 기능을 제공하지 않습니다."

    def get_dashboard_data(self, db_type, limit=6):
        # The core route does not require login itself. Authenticate the web
        # session against general users here; never accept a user id from input.
        if not has_request_context() or not session.get('user_id'):
            return {'success': False, 'error': '로그인이 필요합니다.'}
        if db_type != 'audiobook':
            return {'success': True, 'items': []}
        try:
            general = self.get_db_gateway('general')
            enabled = general.get_setting('PLUGIN_ENABLED_audiobook_opds', None)
            user = general.fetch_one('SELECT id,role,is_default_password,has_audiobook_access '
                                     'FROM users WHERE id=?', [session['user_id']])
            if (not user or user['is_default_password'] == 1 or
                    (user['role'] != 'admin' and user['has_audiobook_access'] != 1) or
                    (enabled is not None and not _bool(enabled['value']))):
                return {'success': False, 'error': '오디오북 접근 권한이 없습니다.'}
            limit = min(20, max(1, int(limit)))
            audio = self.get_db_gateway('audiobook')
            clause, params = _permission(user)
            rows = audio.fetch_all('''SELECT a.id,a.title,a.author,l.hide_cover,
                p.current_track_id,p.current_time,p.is_completed,p.last_listened_at
                FROM audiobook_progress p JOIN audiobooks a ON a.id=p.audiobook_id
                JOIN libraries l ON l.id=a.library_id
                WHERE p.user_id=? AND COALESCE(a.is_deleted,0)=0
                AND COALESCE(l.pending_delete,0)=0
                AND EXISTS (SELECT 1 FROM audiobook_tracks t WHERE t.audiobook_id=a.id)
                ''' + clause + ' ORDER BY p.last_listened_at DESC,a.id DESC LIMIT ?',
                [user['id']] + params + [limit])
            items = []
            for row in rows:
                tracks = audio.fetch_all('SELECT id,duration FROM audiobook_tracks WHERE audiobook_id=? '
                                         'ORDER BY track_number,id', [row['id']])
                cache = general.fetch_one('SELECT `value` FROM user_settings WHERE user_id=? AND `key`=?',
                    [user['id'], 'AUDIOBOOK_OPDS_SYNC_V1_U' + str(user['id']) + '_B' + str(row['id'])])
                try:
                    cached = json.loads(cache['value']).get('_durations', {}) if cache else {}
                except (ValueError, AttributeError, TypeError):
                    cached = {}
                items.append({'bookId': int(row['id']), 'title': row['title'] or '제목 없음',
                    'author': row['author'] or '',
                    'cover': '' if row['hide_cover'] == 1 else
                        '/api/media/audiobooks/' + str(int(row['id'])) + '/cover',
                    **_listening_summary(row, tracks, cached)})
            return {'success': True, 'items': items}
        except Exception as error:
            LOG.error('Dashboard unavailable: %s', type(error).__name__)
            return {'success': False, 'error': '청취 진행률을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'}

    def start_background_service(self, db_type):
        # The official factory supplies 'general'. Never use that value for audio.
        global _SUPERVISOR
        with _START_LOCK:
            if (_SUPERVISOR is not None and _SUPERVISOR.pid == os.getpid()
                    and _SUPERVISOR.thread.is_alive()):
                return
            _SUPERVISOR = _Supervisor(self)
            atexit.register(_SUPERVISOR.stop)
            _SUPERVISOR.thread.start()
