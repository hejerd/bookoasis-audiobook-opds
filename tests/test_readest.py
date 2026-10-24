"""Readest's complete-entry contract: ordered audio once, with a usable Play action."""
import importlib.util
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest
NS={'a':'http://www.w3.org/2005/Atom'}
ACQ='http://opds-spec.org/acquisition'
def detail(case,bid=5,user='reader'):
    response=case.client.get(f'/opds/books/{bid}',headers=case.auth(user))
    assert response.status_code==200
    return ET.fromstring(response.data)
def audio_links(node):return [dict(n.attrib) for n in node.findall('a:link',NS) if n.get('rel','').startswith(ACQ)]

@pytest.mark.parametrize('user',['reader','nodownload'])
def test_complete_multi_entry_advertises_every_track_once(bookcase,user):
    node=detail(bookcase,user=user);links=audio_links(node)
    assert len(links)==2 and len({link['href'] for link in links})==2
    assert all(link['type']=='audio/mpeg' and '/tracks/' in link['href'] and link['href'].endswith('/stream') for link in links)
    downloads=[n for n in node.findall('a:link',NS) if n.get('href','').endswith('/download')]
    assert len(downloads)==(2 if user=='reader' else 0)
    assert all(link.get('rel')=='related' for link in downloads)
    for link in links:
        assert bookcase.client.get(link['href'],headers={**bookcase.auth(user),'Range':'bytes=0-31'}).status_code==206


def test_detail_track_order_is_the_database_track_order(bookcase):
    bookcase.sql('audiobook','UPDATE audiobook_tracks SET track_number=20,title=? WHERE id=5',('Late & <track>\x01',))
    bookcase.sql('audiobook','UPDATE audiobook_tracks SET track_number=1,title=? WHERE id=6',('Early track',))
    links=audio_links(detail(bookcase))
    assert links[0]['href'].endswith('/tracks/6/stream') and links[1]['href'].endswith('/tracks/5/stream')
    assert links[1]['title']=='Late & <track>'


def test_single_detail_keeps_one_legacy_acquisition(bookcase):
    links=audio_links(detail(bookcase,1))
    assert len(links)==1 and links[0]['href'].endswith('/books/1/stream')


def test_mixed_formats_do_not_create_duplicate_audio_acquisitions(bookcase):
    bookcase.add_book(8,'Readest M4A','m4a',count=2,file_type='multi')
    node=detail(bookcase,8);assert len(audio_links(node))==2
    assert all(link['type']=='audio/mp4' for link in audio_links(node))
    bookcase.sql('audiobook',"UPDATE audiobook_tracks SET file_path=file_path||'.flac' WHERE audiobook_id=8 AND track_number=2")
    links=audio_links(detail(bookcase,8));assert len(links)==1 and '/tracks/' in links[0]['href']


def test_readest_view_regression_inputs(bookcase,request,tmp_path):
    # Both XML responses come from real plugin code using the same temporary
    # schema/gateway. Export them for the upstream React component regression.
    bookcase.add_book(8,'Reported two-track M4A','m4a',count=2,file_type='multi')
    old_path=Path(__file__).resolve().parents[2]/'audiobook_opds-0.3.0-release/plugins/metadata/audiobook_opds/audiobook_opds.py'
    # The old source is optional for standalone release test reproductions.
    old_source=(old_path if old_path.is_file() else None)
    node=detail(bookcase,8)
    cases=[]
    def publication(xml):
        return {'metadata':{'title':xml.findtext('a:title',namespaces=NS),'author':[xml.findtext('a:author/a:name',namespaces=NS)],'description':xml.findtext('a:summary',namespaces=NS)},'links':[dict(n.attrib) for n in xml.findall('a:link',NS)]}
    if old_source:
        spec=importlib.util.spec_from_file_location('opds_before_readest_fix',old_source)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        response=old.create_app(bookcase.provider,{}).test_client().get('/opds/books/8',headers=bookcase.auth())
        before=ET.fromstring(response.data);assert audio_links(before)==[]
        cases.append({'name':'before_multi','expect_play':False,'expect_tracks':0,'publication':publication(before)})
    cases.append({'name':'after_multi','expect_play':True,'expect_tracks':2,'publication':publication(node)})
    cases.append({'name':'after_single','expect_play':True,'expect_tracks':1,'publication':publication(detail(bookcase,1))})
    cases.append({'name':'after_no_download','expect_play':True,'expect_tracks':2,'publication':publication(detail(bookcase,8,'nodownload'))})
    target=Path(request.config.getoption('--readest-fixtures') or tmp_path)
    target.mkdir(parents=True,exist_ok=True)
    (target/'publication-cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    assert len(audio_links(node))==2
