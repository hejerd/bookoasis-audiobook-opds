"""Track navigation, parent scoping, formats, and permissions through real DBs."""
from pathlib import Path
import shutil
import sqlite3
import xml.etree.ElementTree as ET

import pytest

NS = {"a": "http://www.w3.org/2005/Atom"}

def rows(case, book=5):
    with sqlite3.connect(case.paths['audiobook']) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(
            'SELECT * FROM audiobook_tracks WHERE audiobook_id=? ORDER BY track_number,id', (book,))]

def xml(response):
    assert response.status_code == 200
    return ET.fromstring(response.data)

def test_book_catalog_is_acquisition_with_track_subsection(bookcase, plugin):
    response = bookcase.client.get('/opds/books', headers=bookcase.auth())
    assert response.content_type.startswith(plugin.FEED_TYPE)
    for entry in xml(response).findall('a:entry', NS):
        links = entry.findall('a:link', NS)
        assert any(link.get('rel') == plugin.ACQUISITION for link in links)
        subsection = next(link for link in links if link.get('rel') == 'subsection')
        assert subsection.get('type') == plugin.FEED_TYPE
        assert subsection.get('href').endswith('/tracks')
    response = bookcase.client.get('/opds/books/5/tracks', headers=bookcase.auth())
    assert response.content_type.startswith(plugin.FEED_TYPE)
    assert len(xml(response).findall('a:entry', NS)) == 2


def test_tracks_order_metadata_pagination_and_xml_escaping(bookcase, plugin):
    tracks = rows(bookcase)
    bookcase.sql('audiobook', 'UPDATE audiobook_tracks SET track_number=9,title=? WHERE id=?', ('Late & <track>\x01', tracks[0]['id']))
    bookcase.sql('audiobook', 'UPDATE audiobook_tracks SET track_number=2,title=? WHERE id=?', ('Early track', tracks[1]['id']))
    app = plugin.create_app(bookcase.provider, {'page_size': 1})
    client = app.test_client()
    first = xml(client.get('/opds/books/5/tracks', headers=bookcase.auth()))
    item = first.find('a:entry', NS)
    assert item.findtext('a:title', namespaces=NS) == 'Early track'
    assert item.findtext('{http://purl.org/dc/terms/}isPartOf') == 'urn:bookoasis:audiobook:5'
    assert item.findtext('a:id', namespaces=NS).endswith(':track:' + str(tracks[1]['id']))
    assert any(link.get('rel') == 'next' and link.get('type') == plugin.FEED_TYPE for link in first.findall('a:link', NS))
    second = xml(client.get('/opds/books/5/tracks?page=2', headers=bookcase.auth()))
    assert second.findtext('a:entry/a:title', namespaces=NS) == 'Late & <track>'
    assert any(link.get('rel') == 'previous' for link in second.findall('a:link', NS))


@pytest.mark.parametrize('endpoint', ['stream', 'download'])
def test_each_multi_track_is_exact_and_seekable(bookcase, endpoint):
    for track in rows(bookcase):
        expected = Path(track['file_path']).read_bytes()
        url = f"/opds/books/5/tracks/{track['id']}/{endpoint}"
        auth = bookcase.auth()
        full = bookcase.client.get(url, headers=auth)
        assert full.status_code == 200 and full.data == expected
        if endpoint == 'download':
            assert 'attachment' in full.headers['Content-Disposition']
        piece = bookcase.client.get(url, headers={**auth, 'Range': 'bytes=4-99', 'If-Range': full.headers['ETag']})
        assert piece.status_code == 206 and piece.data == expected[4:100]
        head = bookcase.client.head(url, headers={**auth, 'Range': 'bytes=4-99'})
        assert head.status_code == 206 and head.data == b'' and head.headers['Content-Length'] == '96'
        invalid = bookcase.client.get(url, headers={**auth, 'Range': 'bytes=99999999-'})
        assert invalid.status_code == 416 and invalid.headers['Content-Range'] == f'bytes */{len(expected)}'


@pytest.mark.parametrize('endpoint', ['stream', 'download'])
def test_track_cannot_be_requested_through_another_book(bookcase, endpoint):
    tid = rows(bookcase)[0]['id']
    for bid in (1, 2, 3, 4, 6, 99999):
        assert bookcase.client.get(f'/opds/books/{bid}/tracks/{tid}/{endpoint}', headers=bookcase.auth()).status_code == 404
    assert bookcase.client.get(f'/opds/books/5/tracks/99999/{endpoint}', headers=bookcase.auth()).status_code == 404


def test_multi_book_details_and_legacy_single_aliases(bookcase):
    assert xml(bookcase.client.get('/opds/books/5', headers=bookcase.auth())).tag.endswith('entry')
    assert bookcase.client.get('/opds/books/5/cover', headers=bookcase.auth()).status_code == 200
    for endpoint in ('stream', 'download'):
        assert bookcase.client.get('/opds/books/5/' + endpoint, headers=bookcase.auth()).status_code == 404


def test_multi_download_restriction_and_live_category_revocation(bookcase, plugin):
    tid = rows(bookcase)[0]['id']
    prefix = f'/opds/books/5/tracks/{tid}'
    auth = bookcase.auth('nodownload')
    assert bookcase.client.get(prefix + '/stream', headers=auth).status_code == 200
    assert bookcase.client.get(prefix + '/download', headers=auth).status_code == 403
    root = xml(bookcase.client.get('/opds/books/5/tracks', headers=auth))
    assert not any('/download' in link.get('href', '') for link in root.findall('.//a:link', NS))
    bookcase.sql('audiobook', 'UPDATE user_category_permissions SET has_access=0 WHERE library_id=1')
    for url in ('/opds/books/5/tracks', prefix + '/stream', prefix + '/download'):
        assert bookcase.client.get(url, headers=auth).status_code == 404


def test_m4a_catalog_and_scoped_track_mime(bookcase):
    bookcase.add_book(8, 'Multi M4A', 'm4a', count=2, file_type='multi')
    root = xml(bookcase.client.get('/opds/books/8/tracks', headers=bookcase.auth()))
    assert len(root.findall('a:entry', NS)) == 2
    for link in root.findall('.//a:link', NS):
        if link.get('rel') == 'http://opds-spec.org/acquisition':
            assert link.get('type') == 'audio/mp4'
    for track in rows(bookcase, 8):
        response = bookcase.client.get(f"/opds/books/8/tracks/{track['id']}/stream", headers=bookcase.auth())
        assert response.status_code == 200 and response.mimetype == 'audio/mp4'
        assert response.data == Path(track['file_path']).read_bytes()


def test_mixed_format_book_hides_unsupported_track_without_single_alias(bookcase):
    track = rows(bookcase)[0]
    bad = Path(track['file_path']).with_suffix('.flac')
    shutil.copyfile(track['file_path'], bad)
    bookcase.sql('audiobook', 'UPDATE audiobook_tracks SET file_path=? WHERE id=?', (str(bad), track['id']))
    root = xml(bookcase.client.get('/opds/books/5/tracks', headers=bookcase.auth()))
    assert len(root.findall('a:entry', NS)) == 1
    assert bookcase.client.get(f"/opds/books/5/tracks/{track['id']}/stream", headers=bookcase.auth()).status_code == 404
    assert bookcase.client.get('/opds/books/5/stream', headers=bookcase.auth()).status_code == 404


def test_scoped_track_respects_folder_boundary(bookcase):
    track = rows(bookcase)[0]
    outside = bookcase.roots[1] / 'another-book.mp3'
    shutil.copyfile(track['file_path'], outside)
    bookcase.sql('audiobook', 'UPDATE audiobook_tracks SET file_path=? WHERE id=?', (str(outside), track['id']))
    for suffix in ('stream', 'download'):
        response = bookcase.client.get(f"/opds/books/5/tracks/{track['id']}/{suffix}", headers=bookcase.auth())
        assert response.status_code == 404


@pytest.mark.parametrize('page', ['0', '-1', '10001', 'wrong'])
def test_bad_track_page_is_rejected(bookcase, page):
    assert bookcase.client.get('/opds/books/5/tracks?page=' + page, headers=bookcase.auth()).status_code == 400
