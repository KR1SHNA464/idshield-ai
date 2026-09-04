"""Meaningful invariant tests: MRZ arithmetic, actual pixel OCR, quality gating, RBAC,
encryption, optimistic decisions, append-only audit and full PNG/PDF intake.
"""
import os,io,base64,copy
from pathlib import Path
import pytest
from sqlalchemy import text,select
from fastapi.testclient import TestClient
from backend.app.mrz import check_digit,parse_mrz,make_td3
from backend.app.synthetic import specimen,png_bytes
from backend.app.vision import quality,extract,pairwise_document_difference
from backend.app.main import app
from backend.app.database import engine,Session,Case,Audit

def test_icao_golden_td3():
    # Public ICAO example, used as a checksum test vector only, never as a live ID.
    mrz=['P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<','L898902C36UTO7408122F1204159ZE184226B<<<<<10']
    result=parse_mrz(mrz)
    assert result['format']=='TD3' and all(c['valid'] for c in result['checks'])
    assert check_digit('L898902C3')=='6'
def test_td1_td2_and_corruption():
    # Standard TD1 example, with filler padded explicitly to prevent transcription omissions.
    td1=parse_mrz(['I<UTOD231458907'.ljust(30,'<'),'7408122F1204159UTO'+'<'*11+'6','ERIKSSON<<ANNA<MARIA'.ljust(30,'<')])
    assert td1['format']=='TD1' and all(c['valid'] for c in td1['checks'])
    td2=parse_mrz(['I<UTOERIKSSON<<ANNA<MARIA'.ljust(36,'<'),'D231458907UTO7408122F1204159<<<<<<<6'])
    assert td2['format']=='TD2' and all(c['valid'] for c in td2['checks'])
    # Explicit size checking rejects shortened OCR lines rather than inventing filler.
    assert parse_mrz([td2['lines'][0][:-1],td2['lines'][1]])['error'] is not None
    bad=parse_mrz(make_td3('Mira Sen','D00000002',invalid=True))
    assert {c['field'] for c in bad['checks'] if not c['valid']}=={'Document number','Composite'}
def test_actual_ocr_and_quality_gate():
    f=specimen(1);assert quality(f['image'])['ok']
    result=extract(f['image'])
    assert result['fields']['name']=='MIRA SEN'
    assert result['fields']['expiry']=='310314'
    assert result['mrz']['format']=='TD3' and all(c['valid'] for c in result['mrz']['checks'])
    assert not quality(specimen(8)['image'])['ok']
def test_pdf_decode():
    from backend.app.vision import decode_image
    b=io.BytesIO();specimen(1)['image'].save(b,format='PDF')
    im=decode_image(b.getvalue(),'specimen.pdf');assert im.width>=600

def test_reference_vs_edited_copy_localizes_real_pixel_change():
    reference=specimen(1)['image'].copy();edited=reference.copy();other=specimen(4)['image']
    width,height=edited.size;box=(int(.03*width),int(.19*height),int(.23*width),int(.57*height))
    edited.paste(other.crop(box),box)
    assert not pairwise_document_difference(reference,reference)['flagged']
    result=pairwise_document_difference(reference,edited)
    assert result['assessed'] and result['flagged'] and result['region']

@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c:yield c
def auth(client,role='officer'):
    r=client.post('/api/session',json={'role':role,'password':role+'-demo'});assert r.status_code==200
    return {'Authorization':'Bearer '+r.json()['data']['token']}
def test_api_auth_and_rbac(client):
    assert client.get('/api/bootstrap').status_code==401
    officer=auth(client);admin=auth(client,'admin')
    assert client.get('/api/bootstrap',headers=officer).status_code==200
    assert client.post('/api/admin/purge-expired',headers=officer).status_code==403
    assert client.post('/api/cases/IDS-2026-0019/decision',headers=admin,json={'action':'Approve','note':'Demo review','revision':1}).status_code==403
    assert client.post('/api/session',json={'role':'admin','password':'wrong'}).status_code==401
    assert client.get('/api/bootstrap',headers={**officer,'Origin':'https://unrelated.example'}).status_code==403
def test_seed_count_and_encryption(client):
    live_only=client.get('/api/bootstrap',headers=auth(client)).json()['data']['cases']
    assert all(case.get('created_by')!='system' for case in live_only)
    data=client.get('/api/bootstrap?include_seeded=true',headers=auth(client)).json()
    assert data['human_decision_required'] is True and len(data['data']['cases'])>=10
    assert data['data']['face']=='OpenCV SFace trained embeddings with YuNet detection'
    with engine.connect() as c:
        raw=c.execute(text("SELECT payload FROM cases WHERE id='IDS-2026-0019'")).scalar_one()
        assert 'Mira' not in raw and raw.startswith('gAAAA')
        original=c.execute(text('SELECT payload FROM documents LIMIT 1')).scalar_one()
        assert 'bytes' not in original and original.startswith('gAAAA')
def test_decision_snapshot_immutability_and_chain(client):
    officer=auth(client);supervisor=auth(client,'supervisor')
    c=client.get('/api/cases/IDS-2026-0019',headers=officer).json()['data']
    revision=c['revision'];payload={'action':'Approve','note':'Reviewed synthetic MRZ and all disclosed evidence.','revision':revision}
    assert client.post('/api/cases/IDS-2026-0019/decision',headers=officer,json=payload).status_code==200
    assert client.post('/api/cases/IDS-2026-0019/decision',headers=officer,json=payload).status_code==409
    payload['revision']=revision+1
    assert client.post('/api/cases/IDS-2026-0019/decision',headers=officer,json=payload).status_code==403
    assert client.get('/api/audit/verify-chain',headers=supervisor).json()['data']['valid']
    with engine.begin() as db:
        with pytest.raises(Exception):db.execute(text("UPDATE audit_log SET action='tampered' WHERE seq=1"))
    with engine.begin() as db:
        with pytest.raises(Exception):db.execute(text('DELETE FROM audit_log WHERE seq=1'))
def test_full_upload_and_recapture_pipeline(client):
    officer=auth(client)
    f=specimen(1)
    before=client.get('/api/bootstrap',headers=officer).json()['data']['cases']
    response=client.post('/api/cases',headers=officer,data={'consent_confirmed':'true'},files=[('files',('reference.png',png_bytes(f['image']),'image/png')),('files',('comparison.png',png_bytes(f['image']),'image/png')),('traveller',('portrait.png',png_bytes(f['portrait']),'image/png'))])
    assert response.status_code==200,response.text
    cid=response.json()['data']['id'];case=client.get('/api/cases/'+cid,headers=officer).json()['data']
    assert [s['name'] for s in case['stages']]==['Intake','Extraction','Forensics','Intelligence','Decision']
    assert case['status']=='In review',case.get('error')
    assert all(s['status']=='complete' for s in case['stages'])
    assert case['risk']==sum(s['points'] for s in case['signals']) and not case['decision']
    assert case['documents'][0]['fields']['name']=='MIRA SEN'
    assert len(case['documents'])==2 and any(s.get('documentIndex')==1 for s in case['signals'])
    assert case['storage'].startswith('Session only')
    with Session() as db:assert db.get(Case,cid) is None
    other_session=auth(client)
    assert client.get('/api/cases/'+cid,headers=other_session).status_code==404
    assert client.post('/api/cases/'+cid+'/save',headers=officer).status_code==200
    with Session() as db:
        assert db.get(Case,cid) is not None
        saved_audit=db.scalars(select(Audit).where(Audit.case_id==cid)).all()
        evidence=saved_audit[-1].payload['evidence']
        assert saved_audit and 'embedding' not in evidence and all('image' not in document for document in evidence['documents'])
    assert client.delete('/api/cases/'+cid,headers=officer).json()['data']['deleted']
    with Session() as db:assert db.get(Case,cid) is None
    blur=client.post('/api/cases',headers=officer,data={'consent_confirmed':'true'},files=[('files',('blur-1.png',png_bytes(specimen(8)['image']),'image/png')),('files',('blur-2.png',png_bytes(specimen(8)['image']),'image/png'))])
    bc=client.get('/api/cases/'+blur.json()['data']['id'],headers=officer).json()['data']
    assert bc['status']=='Recapture' and bc['stages'][1]['status']=='waiting'
    assert client.post('/api/cases/'+bc['id']+'/decision',headers=officer,json={'action':'Approve','note':'Cannot approve incomplete evidence','revision':bc['revision']}).status_code==400
def test_upload_consent_and_type_rejection(client):
    officer=auth(client)
    assert client.post('/api/cases',headers=officer,files=[('files',('x.png',b'not an image','image/png'))]).status_code==400
    assert client.post('/api/cases',headers=officer,data={'consent_confirmed':'true'},files=[('files',('x.png',b'not an image','image/png'))]).status_code==400

def test_hosted_ui_cors_for_tunnel(client,monkeypatch):
    origin='https://idshield-ai-sih2026-21688.vivek420pandia.chatgpt.site'
    monkeypatch.setenv('IDSHIELD_ALLOW_TUNNEL','1')
    response=client.options('/api/session',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'content-type'})
    assert response.status_code==204
    assert response.headers['access-control-allow-origin']==origin
    assert client.options('/api/session',headers={'Origin':'https://untrusted.example'}).status_code==403
