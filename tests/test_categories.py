"""Category-first OPDS navigation with real upstream schema and permission DB."""
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import pytest

NS={'a':'http://www.w3.org/2005/Atom'}
def root(response):
    assert response.status_code==200
    return ET.fromstring(response.data)
def items(response):return root(response).findall('a:entry',NS)
def title(node):return node.findtext('a:title',namespaces=NS)
def add_category(case,lid,name,order=0):
    case.sql('audiobook','INSERT INTO libraries(id,name,physical_path,sort_order) VALUES(?,?,?,?)',(lid,name,str(case.tmp_path/('category-'+str(lid))),order))
    case.sql('audiobook','INSERT INTO user_category_permissions(user_id,library_id,has_access) VALUES(1,?,1)',(lid,))

def test_root_contains_only_authorized_categories_and_book_counts(bookcase,plugin):
    response=bookcase.client.get('/opds',headers=bookcase.auth())
    assert response.content_type.startswith(plugin.NAV_TYPE)
    entries=items(response)
    assert [title(item) for item in entries]==['Allowed library']
    category=entries[0]
    assert category.findtext('a:summary',namespaces=NS)=='3권'
    assert category.findtext('a:id',namespaces=NS)=='urn:bookoasis:audiobook:library:1'
    links=category.findall('a:link',NS)
    assert len(links)==1 and links[0].get('rel')=='subsection' and links[0].get('type')==plugin.FEED_TYPE
    assert links[0].get('href').endswith('/opds?library_id=1')
    assert not any(link.get('rel')==plugin.ACQUISITION for link in links)


def test_category_book_track_navigation_and_breadcrumb(bookcase,plugin):
    cat=items(bookcase.client.get('/opds',headers=bookcase.auth()))[0]
    href=cat.find('a:link',NS).get('href')
    books=root(bookcase.client.get(href,headers=bookcase.auth()))
    assert books.findtext('a:title',namespaces=NS)=='Allowed library'
    assert len(books.findall('a:entry',NS))==3
    first=next(e for e in books.findall('a:entry',NS) if e.findtext('a:id',namespaces=NS)=='urn:bookoasis:audiobook:5')
    link=next(item for item in first.findall('a:link',NS) if item.get('rel')=='subsection')
    tracks=root(bookcase.client.get(link.get('href'),headers=bookcase.auth()))
    assert len(tracks.findall('a:entry',NS))==2
    up=next(item for item in tracks.findall('a:link',NS) if item.get('rel')=='up')
    assert up.get('href').endswith('/opds?library_id=1')
    audio=next(item for item in tracks.findall('a:entry/a:link',NS) if item.get('rel')==plugin.ACQUISITION)
    assert bookcase.client.get(audio.get('href'),headers={**bookcase.auth(),'Range':'bytes=0-31'}).status_code==206


def test_category_order_pagination_empty_categories_and_xml(bookcase,plugin):
    add_category(bookcase,4,'가정 & <실용>\x01',-2)
    add_category(bookcase,5,'두 번째',-1)
    app=plugin.create_app(bookcase.provider,{'page_size':1,'public_base_url':'https://audio.example.test/prefix'})
    client=app.test_client()
    first=root(client.get('/opds',headers=bookcase.auth()))
    assert first.findtext('a:entry/a:title',namespaces=NS)=='가정 & <실용>'
    assert first.findtext('a:entry/a:summary',namespaces=NS)=='0권'
    link=next(item for item in first.findall('a:link',NS) if item.get('rel')=='next')
    assert link.get('href')=='https://audio.example.test/prefix/opds?page=2'
    second=root(client.get('/opds?page=2',headers=bookcase.auth()))
    assert second.findtext('a:entry/a:title',namespaces=NS)=='두 번째'
    assert any(item.get('rel')=='previous' for item in second.findall('a:link',NS))


def test_legacy_libraries_catalog_matches_root_categories(bookcase):
    auth=bookcase.auth()
    assert [title(i) for i in items(bookcase.client.get('/opds',headers=auth))]==[title(i) for i in items(bookcase.client.get('/opds/libraries',headers=auth))]
    assert [title(i) for i in items(bookcase.client.get('/opds/',headers=auth))]==['Allowed library']


@pytest.mark.parametrize('lid',[2,3,99999])
@pytest.mark.parametrize('endpoint',['/opds?library_id=','/opds/search.xml?library_id='])
def test_denied_pending_and_missing_category_urls_are_hidden(bookcase,lid,endpoint):
    response=bookcase.client.get(endpoint+str(lid),headers=bookcase.auth())
    assert response.status_code==404
    assert b'Denied library' not in response.data and b'Pending removal' not in response.data


def test_global_search_finds_books_without_flattening_root(bookcase):
    auth=bookcase.auth()
    assert [title(i) for i in items(bookcase.client.get('/opds?q=Beta',headers=auth))]==['Beta M4B']
    assert [title(i) for i in items(bookcase.client.get('/opds',headers=auth))]==['Allowed library']


def test_category_search_stays_in_selected_category(bookcase):
    add_category(bookcase,4,'Empty category')
    auth=bookcase.auth()
    response=bookcase.client.get('/opds?library_id=1',headers=auth)
    search=next(i for i in root(response).findall('a:link',NS) if i.get('rel')=='search')
    assert search.get('href').endswith('/opds/search.xml?library_id=1&sort=title_asc')
    description=root(bookcase.client.get('/opds/search.xml?library_id=4',headers=auth))
    template=description.find('{http://a9.com/-/spec/opensearch/1.1/}Url').get('template')
    assert 'library_id=4&q={searchTerms}' in template
    assert items(bookcase.client.get(template.replace('{searchTerms}','Beta'),headers=auth))==[]


def test_category_count_excludes_deleted_and_unsupported_books(bookcase):
    bookcase.sql('audiobook',"UPDATE audiobook_tracks SET file_path=file_path||'.flac' WHERE audiobook_id=2")
    category=items(bookcase.client.get('/opds',headers=bookcase.auth()))[0]
    assert category.findtext('a:summary',namespaces=NS)=='2권'


def test_admin_categories_and_permission_revocation(bookcase):
    admin=bookcase.auth('admin')
    assert [title(i) for i in items(bookcase.client.get('/opds',headers=admin))]==['Allowed library','Denied library']
    assert bookcase.client.get('/opds?library_id=2',headers=admin).status_code==200
    bookcase.sql('audiobook','UPDATE user_category_permissions SET has_access=0 WHERE user_id=1')
    assert items(bookcase.client.get('/opds',headers=bookcase.auth()))==[]
    assert bookcase.client.get('/opds?library_id=1',headers=bookcase.auth()).status_code==404


def test_missing_category_count_source_fails_closed(bookcase):
    bookcase.sql('audiobook','DROP TABLE audiobook_tracks')
    response=bookcase.client.get('/opds',headers=bookcase.auth())
    assert response.status_code==503 and b'audiobook_tracks' not in response.data


@pytest.mark.parametrize('query',['library_id=0','library_id=-1','library_id=invalid'])
def test_bad_scoped_search_category_is_rejected(bookcase,query):
    assert bookcase.client.get('/opds/search.xml?'+query,headers=bookcase.auth()).status_code==400
