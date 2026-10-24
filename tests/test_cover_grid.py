"""Book listings must be publications with artwork and a complete, ordered playlist."""
import xml.etree.ElementTree as ET
from pathlib import Path
import pytest
NS={'a':'http://www.w3.org/2005/Atom'}
ACQ='http://opds-spec.org/acquisition'
def parse(response):
    assert response.status_code==200
    return ET.fromstring(response.data)
def audio(node):
    return [dict(n.attrib) for n in node.findall('a:link',NS) if n.get('rel','').startswith(ACQ)]
@pytest.mark.parametrize('url',['/opds/books','/opds?library_id=1','/opds?q=Multiple'])
def test_list_is_acquisition_feed_with_cover_and_all_tracks(bookcase,plugin,url):
    response=bookcase.client.get(url,headers=bookcase.auth())
    assert response.content_type.startswith(plugin.FEED_TYPE)
    root=parse(response)
    for entry in root.findall('a:entry',NS):
        bid=int(entry.findtext('a:id',namespaces=NS).rsplit(':',1)[1])
        assert audio(entry)==audio(parse(bookcase.client.get(f'/opds/books/{bid}',headers=bookcase.auth())))
        assert len(audio(entry))==(2 if bid==5 else 1)
        assert any(n.get('rel')=='http://opds-spec.org/image' and n.get('href').endswith('/cover') for n in entry.findall('a:link',NS))
        assert entry.findtext('a:title',namespaces=NS)
def test_list_does_not_advertise_denied_books_or_downloads(bookcase):
    root=parse(bookcase.client.get('/opds/books',headers=bookcase.auth('nodownload')))
    assert len(root.findall('a:entry',NS))==3
    assert not any('/download' in n.get('href','') for n in root.findall('a:entry/a:link',NS))
    assert not any('/books/3/' in n.get('href','') for n in root.findall('a:entry/a:link',NS))
def test_list_track_order_and_supported_formats(bookcase):
    bookcase.sql('audiobook','UPDATE audiobook_tracks SET track_number=20 WHERE id=5')
    bookcase.sql('audiobook','UPDATE audiobook_tracks SET track_number=1 WHERE id=6')
    root=parse(bookcase.client.get('/opds?q=Multiple',headers=bookcase.auth()))
    assert [n['href'].rsplit('/',3)[-2] for n in audio(root.find('a:entry',NS))]==['6','5']
    bookcase.sql('audiobook',"UPDATE audiobook_tracks SET file_path=file_path||'.flac' WHERE id=6")
    links=audio(parse(bookcase.client.get('/opds?q=Multiple',headers=bookcase.auth())).find('a:entry',NS))
    assert len(links)==1 and '/tracks/5/stream' in links[0]['href']
def test_list_fetches_track_metadata_once_for_visible_page(bookcase,plugin,monkeypatch):
    from services.plugin_db_gateway import PluginDatabaseGateway
    original=PluginDatabaseGateway.fetch_all; calls=[]
    def fetch(self,query,params=None):
        calls.append((query,params))
        return original(self,query,params)
    monkeypatch.setattr(PluginDatabaseGateway,'fetch_all',fetch)
    app=plugin.create_app(bookcase.provider,{'page_size':2})
    root=parse(app.test_client().get('/opds/books',headers=bookcase.auth()))
    assert len(root.findall('a:entry',NS))==2
    track_queries=[(sql,params) for sql,params in calls if 'FROM audiobook_tracks t WHERE' in sql and 'SELECT t.id,' in sql]
    assert len(track_queries)==1
    assert set(track_queries[0][1])=={1,2}
def test_empty_list_needs_no_tracks_query(bookcase):
    assert parse(bookcase.client.get('/opds?q=no-such-book',headers=bookcase.auth())).findall('a:entry',NS)==[]
def test_export_cover_grid_feeds(bookcase,request,tmp_path):
    target=Path(request.config.getoption('--readest-fixtures') or tmp_path);target.mkdir(parents=True,exist_ok=True)
    for name,url in [('cover-grid','/opds/books'),('cover-categories','/opds'),('cover-no-download','/opds/books')]:
        response=bookcase.client.get(url,headers=bookcase.auth('nodownload' if name=='cover-no-download' else 'reader'))
        assert response.status_code==200
        (target/(name+'.xml')).write_bytes(response.data)
