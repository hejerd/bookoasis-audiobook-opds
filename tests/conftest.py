"""Integration fixtures: upstream schema, gateway, repository and SQLite pool.

Only temporary DB filenames and pool state are redirected. SQL/gateway behavior
is the actual BookOasis implementation, rather than a mock gateway.
"""
import base64
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import sys
from types import SimpleNamespace

import pytest
from werkzeug.security import generate_password_hash


HERE = Path(__file__).resolve().parent
RELEASE = HERE.parent


def pytest_addoption(parser):
    parser.addoption("--readest-fixtures", default=None, help="Optional directory for actual Readest UI regression inputs.")
    parser.addoption("--bookoasis-source", default=os.environ.get("BOOKOASIS_SOURCE"),
                     help="Path to the inspected BookOasis_stable checkout (required).")


@pytest.fixture(scope="session")
def source(request):
    configured = request.config.getoption("--bookoasis-source")
    candidate = Path(configured).resolve() if configured else RELEASE.parent.parent / "work" / "BookOasis_stable"
    if not (candidate / "services" / "plugin_db_gateway.py").is_file():
        pytest.fail("Set --bookoasis-source to the real BookOasis_stable source directory.")
    sys.path.insert(0, str(candidate))
    yield candidate
    sys.path.remove(str(candidate))


@pytest.fixture(scope="session")
def plugin(source):
    path = RELEASE / "plugins" / "metadata" / "audiobook_opds" / "audiobook_opds.py"
    spec = importlib.util.spec_from_file_location("audiobook_opds_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def authorization(username="reader", password="test-reader-password"):
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture
def bookcase(tmp_path, monkeypatch, source, plugin):
    monkeypatch.setenv("DB_ENGINE", "sqlite")
    from services.db_migration_service import _SCHEMA_SQL
    from services.plugin_db_gateway import PluginDatabaseGateway
    import database

    paths = {kind: tmp_path / f"media_{kind}.db" for kind in ("general", "audiobook")}
    for path in paths.values():
        with sqlite3.connect(path) as connection:
            connection.executescript(_SCHEMA_SQL)
    monkeypatch.setattr(database, "DB_GENERAL_PATH", str(paths["general"]))
    monkeypatch.setattr(database, "DB_AUDIOBOOK_PATH", str(paths["audiobook"]))
    monkeypatch.setattr(database, "_pools", dict.fromkeys(("general", "audiobook", "adult", "video")))
    monkeypatch.setattr(database, "_cached_pool_size", 5)
    monkeypatch.setattr(database, "_shutdown_in_progress", False)

    def sql(kind, query, params=()):
        with sqlite3.connect(paths[kind]) as connection:
            return connection.execute(query, params).lastrowid

    password_hash = generate_password_hash("test-reader-password")
    # Identity is deliberately different in the audiobook DB: auth must use general.
    users = [(1, "reader", "user", 0, 1, 1), (2, "blocked", "user", 0, 0, 1),
             (3, "default", "user", 1, 1, 1), (4, "admin", "admin", 0, 0, 0),
             (5, "nodownload", "user", 0, 1, 0), (6, "unassigned", "user", 0, 1, 1)]
    for uid, name, role, default, audio, download in users:
        sql("general", "INSERT INTO users (id,username,password_hash,role,is_default_password,has_audiobook_access,has_download_access) VALUES(?,?,?,?,?,?,?)",
            (uid, name, password_hash, role, default, audio, download))
    sql("audiobook", "INSERT INTO users (id,username,password_hash,is_default_password) VALUES(1,'reader',?,0)",
        (generate_password_hash("wrong-audiobook-db-password"),))

    roots = {}
    for lid, name in ((1, "Allowed library"), (2, "Denied library"), (3, "Pending removal")):
        roots[lid] = tmp_path / f"library-{lid}"
        roots[lid].mkdir()
        sql("audiobook", "INSERT INTO libraries (id,name,physical_path,pending_delete) VALUES(?,?,?,?)",
            (lid, name, str(roots[lid]), int(lid == 3)))
    for uid in (1, 5):
        sql("audiobook", "INSERT INTO user_category_permissions (user_id,library_id,has_access) VALUES(?,1,1)", (uid,))
        sql("audiobook", "INSERT INTO user_category_permissions (user_id,library_id,has_access) VALUES(?,2,0)", (uid,))
        sql("audiobook", "INSERT INTO user_category_permissions (user_id,library_id,has_access) VALUES(?,3,1)", (uid,))

    media = {}

    def add_book(bid, title, extension="mp3", lid=1, deleted=0, count=1, file_type="single"):
        folder = roots[lid] / f"book-{bid}"
        folder.mkdir()
        cover = folder / "cover.jpg"
        shutil.copyfile(HERE / "samples" / "cover.jpg", cover)
        sql("audiobook", "INSERT INTO audiobooks (id,library_id,title,author,description,folder_name,folder_path,poster,total_duration,total_tracks,file_type,is_deleted) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (bid, lid, title, "Test author", "Original test tone & <sample>", folder.name, str(folder), str(cover), 2, count, file_type, deleted))
        for number in range(1, count + 1):
            path = folder / f"track-{number}.{extension}"
            shutil.copyfile(HERE / "samples" / f"tone.{extension}", path)
            sql("audiobook", "INSERT INTO audiobook_tracks (audiobook_id,track_number,filename,file_path,file_size,duration,format,title) VALUES(?,?,?,?,?,?,?,?)",
                (bid, number, path.name, str(path), path.stat().st_size, 2, extension, title))
            media.setdefault(bid, path)
        return bid

    add_book(1, "Alpha MP3 & <tone>")
    add_book(2, "Beta M4B", "m4b")
    add_book(3, "Denied title", lid=2)
    add_book(4, "Deleted title", deleted=1)
    add_book(5, "Multiple tracks", count=2, file_type="multi")
    add_book(6, "Pending title", lid=3)

    calls = []

    class Provider(plugin.AudiobookOpdsMetadataProvider):
        def get_db_gateway(self, kind):
            calls.append(kind)
            return super().get_db_gateway(kind)

    provider = Provider()
    app = plugin.create_app(provider, {})
    app.config.update(TESTING=True)
    result = SimpleNamespace(app=app, client=app.test_client(), provider=provider, paths=paths,
                             roots=roots, media=media, sql=sql, add_book=add_book,
                             auth=authorization, calls=calls, tmp_path=tmp_path)
    yield result
    for pool in database._pools.values():
        if pool is not None:
            pool.shutdown()
