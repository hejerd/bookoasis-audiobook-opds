"""Sorting contract against the real BookOasis gateway and temporary SQLite DBs."""
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET
import pytest

NS={'a':'http://www.w3.org/2005/Atom'}
FACET='http://opds-spec.org/facet'
OPDS='http://opds-spec.org/2010/catalog'
SORTS=['title_asc','title_desc','added_desc','added_asc','updated_desc']

def parsed(response):
    assert response.status_code==200
    return ET.fromstring(response.data)

def ids(response):
    return [int(e.findtext('a:id',namespaces=NS).rsplit(':',1)[1]) for e in parsed(response).findall('a:entry',NS)]

def arrange(case):
    for bid,title,created,updated in [
        (1,'하늘 책','2026-03-01 00:00:00','2026-03-02 00:00:00'),
        (2,'가방 책','2026-01-01 00:00:00','2026-04-03 00:00:00'),
        (5,'나무 책','2026-02-01 00:00:00','2026-03-03 00:00:00')]:
        case.sql('audiobook','UPDATE audiobooks SET title=?,created_at=?,updated_at=? WHERE id=?',(title,created,updated,bid))

@pytest.mark.parametrize('endpoint',['/opds/books','/opds?library_id=1','/opds?q=책'])
def test_default_is_title_ascending_not_reverse_database_id(bookcase,endpoint):
    arrange(bookcase)
    assert ids(bookcase.client.get(endpoint,headers=bookcase.auth()))==[2,5,1]

@pytest.mark.parametrize('sort,expected',[
    ('title_asc',[2,5,1]),('title_desc',[1,5,2]),
    ('added_desc',[1,5,2]),('added_asc',[2,5,1]),('updated_desc',[2,5,1])])
def test_sort_uses_real_title_and_timestamps(bookcase,sort,expected):
    arrange(bookcase)
    assert ids(bookcase.client.get('/opds?library_id=1&sort='+sort,headers=bookcase.auth()))==expected

@pytest.mark.parametrize('sort',SORTS)
def test_facets_keep_scope_search_and_reset_page(bookcase,sort):
    root=parsed(bookcase.client.get('/opds?library_id=1&q=book&page=3&sort='+sort,headers=bookcase.auth()))
    links=[l for l in root.findall('a:link',NS) if l.get('rel')==FACET]
    assert len(links)==5
    assert {l.get('{'+OPDS+'}facetGroup') for l in links}=={'정렬'}
    assert sum(l.get('{'+OPDS+'}activeFacet')=='true' for l in links)==1
    for link in links:
        query=parse_qs(urlsplit(link.get('href')).query)
        assert query['library_id']==['1'] and query['q']==['book']
        assert query['sort'][0] in SORTS and 'page' not in query
        if link.get('{'+OPDS+'}activeFacet')=='true':assert query['sort']==[sort]

@pytest.mark.parametrize('sort',SORTS)
def test_pagination_and_search_retain_sort_and_scope(bookcase,plugin,sort):
    arrange(bookcase)
    client=plugin.create_app(bookcase.provider,{'page_size':1,'public_base_url':'https://audio.example.test/audio'}).test_client()
    root=parsed(client.get('/opds?library_id=1&q=책&sort='+sort,headers=bookcase.auth()))
    next_link=next(l for l in root.findall('a:link',NS) if l.get('rel')=='next')
    q=parse_qs(urlsplit(next_link.get('href')).query)
    assert q=={'page':['2'],'q':['책'],'library_id':['1'],'sort':[sort]}
    search=next(l for l in root.findall('a:link',NS) if l.get('rel')=='search')
    assert parse_qs(urlsplit(search.get('href')).query)=={'library_id':['1'],'sort':[sort]}
    description=parsed(client.get('/opds/search.xml?library_id=1&sort='+sort,headers=bookcase.auth()))
    template=description.find('{http://a9.com/-/spec/opensearch/1.1/}Url').get('template')
    query=parse_qs(urlsplit(template).query)
    assert query=={'library_id':['1'],'sort':[sort],'q':['{searchTerms}']}

@pytest.mark.parametrize('sort',SORTS)
def test_sorting_never_bypasses_library_permissions(bookcase,sort):
    assert bookcase.client.get('/opds?library_id=2&sort='+sort,headers=bookcase.auth()).status_code==404
    assert set(ids(bookcase.client.get('/opds/books?sort='+sort,headers=bookcase.auth())))=={1,2,5}

@pytest.mark.parametrize('sort',['id_desc','title_asc; DROP TABLE audiobooks','a.title DESC','',"' OR 1=1 --"])
@pytest.mark.parametrize('endpoint',['/opds/books','/opds/search.xml'])
def test_unknown_sort_rejected_before_sql(bookcase,endpoint,sort):
    assert bookcase.client.get(endpoint,query_string={'sort':sort},headers=bookcase.auth()).status_code==400

@pytest.mark.parametrize('sort',SORTS)
def test_equal_sort_values_have_stable_pagination(bookcase,plugin,sort):
    bookcase.sql('audiobook',"UPDATE audiobooks SET title='같은 제목',created_at='2026-01-01 00:00:00',updated_at='2026-01-01 00:00:00'")
    client=plugin.create_app(bookcase.provider,{'page_size':1}).test_client()
    result=[]
    for page in range(1,4):result+=ids(client.get('/opds/books',query_string={'sort':sort,'page':page},headers=bookcase.auth()))
    assert len(result)==len(set(result))==3 and set(result)=={1,2,5}

def test_export_actual_facet_xml_for_readest_parser(bookcase,request):
    destination=request.config.getoption('--readest-fixtures')
    if destination:
        from pathlib import Path
        arrange(bookcase)
        path=Path(destination);path.mkdir(parents=True,exist_ok=True)
        response=bookcase.client.get('/opds?library_id=1&sort=added_desc',headers=bookcase.auth())
        assert response.status_code==200
        (path/'sorting-feed.xml').write_bytes(response.data)
