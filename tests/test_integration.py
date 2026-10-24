"""HTTP/security integration tests against real upstream DB access code."""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import importlib
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import imageio_ffmpeg
from PIL import Image
import pytest


ATOM = {"a": "http://www.w3.org/2005/Atom"}
ROUTES = ["/opds", "/opds/books", "/opds?library_id=1", "/opds/books/1", "/opds/books/1/cover", "/opds/books/1/stream",
          "/opds/books/1/download", "/opds/libraries", "/opds/search.xml", "/opds/books/5/tracks",
          "/opds/books/5/tracks/5/stream", "/opds/books/5/tracks/5/download"]


def feed(response):
    assert response.status_code == 200
    assert "xml" in response.content_type
    return ET.fromstring(response.data)


def entries(response):
    return feed(response).findall("a:entry", ATOM)


def titles(response):
    return [item.findtext("a:title", namespaces=ATOM) for item in entries(response)]


@pytest.mark.parametrize("route", ROUTES)
def test_every_resource_requires_basic_auth(bookcase, route):
    response = bookcase.client.get(route)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"].startswith("Basic ")
    assert str(bookcase.tmp_path).encode() not in response.data


@pytest.mark.parametrize("header", ["Basic !!!", "Bearer invalid", "Basic Og=="])
def test_invalid_auth_is_unauthorized(bookcase, header):
    assert bookcase.client.get("/opds", headers={"Authorization": header}).status_code == 401


def test_auth_uses_general_identity_and_audiobook_category_permissions(bookcase):
    assert titles(bookcase.client.get("/opds/books", headers=bookcase.auth())) == ["Alpha MP3 & <tone>", "Beta M4B", "Multiple tracks"]
    assert {"general", "audiobook"}.issubset(bookcase.calls)
    response = bookcase.client.get("/opds", headers=bookcase.auth(password="wrong-audiobook-db-password"))
    assert response.status_code == 401
    assert bookcase.client.get("/opds", headers=bookcase.auth(username="' OR 1=1 --")).status_code == 401


@pytest.mark.parametrize("username", ["blocked", "default"])
def test_session_access_and_default_password_blocked(bookcase, username):
    for route in ROUTES:
        assert bookcase.client.get(route, headers=bookcase.auth(username)).status_code == 403


def test_unassigned_user_has_no_implicit_category_access(bookcase):
    assert titles(bookcase.client.get("/opds", headers=bookcase.auth("unassigned"))) == []
    assert bookcase.client.get("/opds/books/1/stream", headers=bookcase.auth("unassigned")).status_code == 404


@pytest.mark.parametrize("bid", [3, 4, 6, 99999])
@pytest.mark.parametrize("suffix", ["", "/cover", "/stream", "/download", "/tracks", "/tracks/1/stream", "/tracks/1/download"])
def test_hidden_or_unavailable_books_cannot_be_accessed_directly(bookcase, bid, suffix):
    response = bookcase.client.get(f"/opds/books/{bid}{suffix}", headers=bookcase.auth())
    assert response.status_code == 404
    assert str(bookcase.tmp_path).encode() not in response.data


def test_admin_bypasses_category_and_session_flags_but_not_deleted_books(bookcase):
    response = bookcase.client.get("/opds/books/3/stream", headers=bookcase.auth("admin"))
    assert response.status_code == 200
    assert response.data == bookcase.media[3].read_bytes()
    assert bookcase.client.get("/opds/books/4/stream", headers=bookcase.auth("admin")).status_code == 404


def test_download_permission_applies_without_breaking_streaming(bookcase):
    auth = bookcase.auth("nodownload")
    assert bookcase.client.get("/opds/books/1/download", headers=auth).status_code == 403
    assert bookcase.client.get("/opds/books/1/stream", headers=auth).status_code == 200
    item = entries(bookcase.client.get("/opds/books/1/tracks", headers=auth))[0]
    assert not any("/download" in link.attrib.get("href", "") for link in item.findall("a:link", ATOM))


def test_live_permission_change_takes_effect_without_restart(bookcase):
    auth = bookcase.auth()
    assert bookcase.client.get("/opds/books/1/stream", headers=auth).status_code == 200
    bookcase.sql("audiobook", "UPDATE user_category_permissions SET has_access=0 WHERE user_id=1 AND library_id=1")
    assert bookcase.client.get("/opds/books/1/stream", headers=auth).status_code == 404
    assert titles(bookcase.client.get("/opds", headers=auth)) == []


def test_feed_metadata_links_filters_and_pagination(bookcase, plugin):
    first = entries(bookcase.client.get("/opds/books/1/tracks", headers=bookcase.auth()))[0]
    assert first.findtext("a:author/a:name", namespaces=ATOM) == "Test author"
    links = first.findall("a:link", ATOM)
    for ending in ("/cover", "/stream", "/download"):
        assert any(link.attrib.get("href", "").endswith(ending) for link in links)
    assert titles(bookcase.client.get("/opds?q=Beta", headers=bookcase.auth())) == ["Beta M4B"]
    assert bookcase.client.get("/opds?library_id=2", headers=bookcase.auth()).status_code == 404
    app = plugin.create_app(bookcase.provider, {"page_size": 1, "public_base_url": "https://audio.example.test"})
    app.config.update(TESTING=True)
    response = app.test_client().get("/opds/books", headers=bookcase.auth())
    assert len(entries(response)) == 1
    assert any(link.attrib.get("rel") == "next" for link in feed(response).findall("a:link", ATOM))
    assert b"https://audio.example.test/opds" in response.data
    assert titles(app.test_client().get("/opds/books?page=2", headers=bookcase.auth())) == ["Beta M4B"]


def test_catalog_alternate_and_standalone_entry_follow_opds_contract(bookcase, plugin):
    catalog_entry = entries(bookcase.client.get("/opds/books", headers=bookcase.auth()))[0]
    alternate = next(link for link in catalog_entry.findall("a:link", ATOM)
                     if link.attrib.get("rel") == "alternate")
    assert alternate.attrib["type"] == plugin.ENTRY_TYPE
    assert alternate.attrib["href"].endswith("/opds/books/1")
    response = bookcase.client.get("/opds/books/1", headers=bookcase.auth())
    assert response.status_code == 200
    assert response.content_type.startswith(plugin.ENTRY_TYPE)
    detail = ET.fromstring(response.data)
    assert detail.tag == "{http://www.w3.org/2005/Atom}entry"
    assert detail.findtext("a:id", namespaces=ATOM) == catalog_entry.findtext("a:id", namespaces=ATOM)
    self_link = next(link for link in detail.findall("a:link", ATOM) if link.attrib.get("rel") == "self")
    assert self_link.attrib["type"] == plugin.ENTRY_TYPE
    assert self_link.attrib["href"] == alternate.attrib["href"]
    assert detail.findtext("a:title", namespaces=ATOM) == "Alpha MP3 & <tone>"
    assert detail.findtext("a:summary", namespaces=ATOM) == "Original test tone & <sample>"


def test_xml_control_characters_do_not_break_catalog(bookcase):
    bookcase.sql("audiobook", "UPDATE audiobooks SET title=?,description=? WHERE id=1",
                ("A\x01 & <title>", "Example\x00 description"))
    response = bookcase.client.get("/opds/books", headers=bookcase.auth())
    assert "A & <title>" in titles(response)
    assert b"\x01" not in response.data
    assert b"\x00" not in response.data


@pytest.mark.parametrize("query", ["page=0", "page=-1", "page=hello", "library_id=hello"])
def test_invalid_query_is_rejected_cleanly(bookcase, query):
    response = bookcase.client.get(f"/opds?{query}", headers=bookcase.auth())
    assert response.status_code in (200, 400)
    if response.status_code == 200:
        feed(response)


def test_library_navigation_and_opensearch(bookcase):
    response = bookcase.client.get("/opds/libraries", headers=bookcase.auth())
    assert "Allowed library" in titles(response)
    assert "Denied library" not in titles(response)
    assert "Pending removal" not in titles(response)
    response = bookcase.client.get("/opds/search.xml", headers=bookcase.auth())
    assert response.status_code == 200
    root = ET.fromstring(response.data)
    assert root.tag.endswith("OpenSearchDescription")
    assert b"{searchTerms}" in response.data


@pytest.mark.parametrize("bid,mime", [(1, "audio/mpeg"), (2, "audio/mp4"), (7, "audio/mp4")])
def test_stream_download_and_head_are_byte_exact(bookcase, bid, mime):
    if bid == 7:
        bookcase.add_book(7, "Gamma M4A", "m4a")
    expected = bookcase.media[bid].read_bytes()
    for endpoint in ("stream", "download"):
        url = f"/opds/books/{bid}/{endpoint}"
        response = bookcase.client.get(url, headers=bookcase.auth())
        assert response.status_code == 200
        assert response.data == expected
        assert response.mimetype == mime
        assert int(response.headers["Content-Length"]) == len(expected)
        assert response.headers["ETag"]
        if endpoint == "download":
            assert "attachment" in response.headers["Content-Disposition"]
        response = bookcase.client.head(url, headers=bookcase.auth())
        assert response.status_code == 200
        assert response.data == b""
        assert int(response.headers["Content-Length"]) == len(expected)


@pytest.mark.parametrize("bid", [1, 2, 7])
def test_seek_ranges_if_range_reassembly_and_real_audio_decode(bookcase, bid):
    if bid == 7:
        bookcase.add_book(7, "Gamma M4A", "m4a")
    original = bookcase.media[bid].read_bytes()
    url = f"/opds/books/{bid}/stream"
    auth = bookcase.auth()
    full = bookcase.client.get(url, headers=auth)
    etag = full.headers["ETag"]
    parts = []
    # The exact downloaded pieces are concatenated and decoded, catching off-by-one
    # bugs that a status-code-only range test cannot detect.
    for begin in range(0, len(original), 4096):
        end = min(begin + 4095, len(original) - 1)
        response = bookcase.client.get(url, headers={**auth, "Range": f"bytes={begin}-{end}"})
        assert response.status_code == 206
        assert response.headers["Content-Range"] == f"bytes {begin}-{end}/{len(original)}"
        assert response.headers["Accept-Ranges"] == "bytes"
        assert response.data == original[begin:end + 1]
        parts.append(response.data)
    reassembled = b"".join(parts)
    assert reassembled == original
    output = bookcase.tmp_path / f"reassembled{bookcase.media[bid].suffix}"
    output.write_bytes(reassembled)
    decoded = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error",
                              "-i", str(output), "-f", "s16le", "-ac", "1", "-ar", "44100", "pipe:1"],
                             check=True, capture_output=True).stdout
    assert 1.9 <= len(decoded) / 2 / 44100 <= 2.15
    assert any(decoded)
    for range_value, expected in (("bytes=10-", original[10:]), ("bytes=-10", original[-10:])):
        response = bookcase.client.get(url, headers={**auth, "Range": range_value})
        assert response.status_code == 206
        assert response.data == expected
    matched = bookcase.client.get(url, headers={**auth, "Range": "bytes=4-9", "If-Range": etag})
    assert matched.status_code == 206
    assert matched.data == original[4:10]
    date_match = bookcase.client.get(url, headers={**auth, "Range": "bytes=4-9", "If-Range": full.headers["Last-Modified"]})
    assert date_match.status_code == 206
    changed = bookcase.client.get(url, headers={**auth, "Range": "bytes=4-9", "If-Range": '"obsolete"'})
    assert changed.status_code == 200
    assert changed.data == original
    head = bookcase.client.head(url, headers={**auth, "Range": "bytes=4-9"})
    assert head.status_code == 206
    assert head.data == b""
    assert head.headers["Content-Length"] == "6"


@pytest.mark.parametrize("range_value", ["bytes=99999999-", "bytes=10-5", "bytes=0-2,4-6", "bytes=nonsense"])
def test_unsatisfiable_and_unsupported_ranges_return_416(bookcase, range_value):
    response = bookcase.client.get("/opds/books/1/stream", headers={**bookcase.auth(), "Range": range_value})
    assert response.status_code == 416
    assert response.headers["Content-Range"] == f"bytes */{bookcase.media[1].stat().st_size}"


def test_cover_and_hide_cover(bookcase):
    url = "/opds/books/1/cover"
    response = bookcase.client.get(url, headers=bookcase.auth())
    assert response.status_code == 200
    actual = response.data
    assert Image.open(BytesIO(actual)).size == (240, 240)
    bookcase.sql("audiobook", "UPDATE libraries SET hide_cover=1 WHERE id=1")
    response = bookcase.client.get(url, headers=bookcase.auth())
    assert response.status_code == 200
    assert response.data != actual
    assert Image.open(BytesIO(response.data)).format in ("JPEG", "PNG")


@pytest.mark.parametrize("location", ["outside_library", "outside_book", "prefix_sibling", "missing"])
def test_media_paths_are_confined_and_missing_files_are_hidden(bookcase, location):
    source = bookcase.media[1]
    candidates = {
        "outside_library": bookcase.tmp_path / "secret.mp3",
        "outside_book": bookcase.roots[1] / "another-book.mp3",
        "prefix_sibling": bookcase.tmp_path / "library-1-evil" / "secret.mp3",
        "missing": source.parent / "missing.mp3",
    }
    target = candidates[location]
    if location != "missing":
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
    bookcase.sql("audiobook", "UPDATE audiobook_tracks SET file_path=? WHERE audiobook_id=1", (str(target),))
    for endpoint in ("stream", "download"):
        response = bookcase.client.get(f"/opds/books/1/{endpoint}", headers=bookcase.auth())
        assert response.status_code == 404


def test_cover_path_outside_library_never_leaks_image(bookcase):
    outside = bookcase.tmp_path / "private-cover.jpg"
    Image.new("RGB", (27, 31), "red").save(outside)
    bookcase.sql("audiobook", "UPDATE audiobooks SET poster=? WHERE id=1", (str(outside),))
    response = bookcase.client.get("/opds/books/1/cover", headers=bookcase.auth())
    assert response.status_code == 200
    assert response.data != outside.read_bytes()
    assert Image.open(BytesIO(response.data)).size != (27, 31)


def test_folder_boundary_cannot_escape_library(bookcase):
    bookcase.sql("audiobook", "UPDATE libraries SET physical_path=? WHERE id=1", (str(bookcase.tmp_path / "unrelated"),))
    assert bookcase.client.get("/opds/books/1/stream", headers=bookcase.auth()).status_code == 404


def test_unsupported_formats_are_not_advertised(bookcase):
    original = bookcase.media[1]
    renamed = original.with_suffix(".flac")
    shutil.copyfile(original, renamed)
    bookcase.sql("audiobook", "UPDATE audiobook_tracks SET file_path=?,filename=?,format='flac' WHERE audiobook_id=1", (str(renamed), renamed.name))
    assert titles(bookcase.client.get("/opds/books", headers=bookcase.auth())) == ["Beta M4B", "Multiple tracks"]
    assert bookcase.client.get("/opds/books/1/stream", headers=bookcase.auth()).status_code == 404


def test_real_local_http_listener_supports_concurrent_authenticated_seeks(bookcase, plugin):
    # A real loopback listener supplements Flask's client tests without touching
    # the running BookOasis container or any operating-server port.
    server = plugin._LimitedServer("127.0.0.1", 0, bookcase.app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    expected = bookcase.media[1].read_bytes()[100:200]

    def fetch_piece(_):
        request = urllib.request.Request(base + "/opds/books/1/stream", headers={**bookcase.auth(), "Range": "bytes=100-199"})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read()

    try:
        with ThreadPoolExecutor(max_workers=4) as workers:
            assert list(workers.map(fetch_piece, range(8))) == [(206, expected)] * 8
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base + "/opds", timeout=5)
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_actual_metadata_factory_loader_accepts_plugin(source, plugin, tmp_path, monkeypatch):
    from services import metadata_factory
    import plugins.metadata
    package_root = Path(plugin.__file__).resolve().parent
    fake_root = tmp_path / "isolated-bookoasis"
    installed = fake_root / "plugins" / "metadata" / "audiobook_opds"
    shutil.copytree(package_root, installed)
    monkeypatch.setattr(metadata_factory, "__file__", str(fake_root / "services" / "metadata_factory.py"))
    monkeypatch.setattr(plugins.metadata, "__path__", [str(installed.parent)] + list(plugins.metadata.__path__))
    importlib.invalidate_caches()
    loaded, cls = metadata_factory.MetadataFactory._import_provider_module_and_class("audiobook_opds")
    provider = cls()
    assert provider.id == "audiobook_opds"
    assert provider.is_searchable is False
    assert callable(provider.start_background_service)
    assert callable(provider.get_db_gateway)
