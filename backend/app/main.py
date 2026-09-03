import os,sys,base64,copy,uuid,time,hmac
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Form,BackgroundTasks,Request
from fastapi.responses import JSONResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from sqlalchemy import select,delete
from .security import READ,REVIEW,SUPERVISE,ADMIN,DEMO_ACCOUNTS,issue_token,verify_token,DISCLAIMER
from .database import init_db,Session,Case,Document,Audit,append_audit,hash_record,now,engine,AUDIT_LOCK
from .synthetic import fixture_case,specimen,png_bytes,data_uri
from .vision import decode_image,YUNET,SFACE
from .pipeline import run_pipeline
from . import session_store

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
FRONTEND=Path(os.environ.get('FRONTEND_DIR',ROOT/'desktop-dist'))
def envelope(data):return {'data':data,'disclaimer':DISCLAIMER,'human_decision_required':True}
def case_out(c):
    p=copy.deepcopy(c.payload);p['status']=c.status;p.pop('embedding',None);return p
def public_payload(p):
    p=copy.deepcopy(p);p.pop('embedding',None);return p
def audit_out(a):return {'id':a.id,'seq':a.seq,'case_id':a.case_id,'action':a.action,'created_at':a.created_at,'officer':a.payload['officer'],'role':a.payload['role'],'snapshot':a.payload['evidence'],'previous_hash':a.previous_hash,'record_hash':a.record_hash}

def seed():
    with Session() as db:
        if db.scalar(select(Case).limit(1)):return
        for i in range(10):
            p=fixture_case(i);f=specimen(i);p['documents'][0]['image']=data_uri(f['image']);p['portrait']=data_uri(f['portrait']);p['comparisonPortrait']=data_uri(specimen((i+3)%10 if p['scenario']=='face' else (0 if p['scenario']=='identity' else i))['portrait']);p['storage']='Seeded synthetic fixture';p['created_by']='system'
            docid=p['documents'][0]['id'];db.add(Case(id=p['id'],created_at=p['created_at'],status=p['status'],payload=p))
            db.add(Document(id=docid,case_id=p['id'],kind='document',expires_at='9999-12-31T00:00:00+00:00',payload={'filename':f'specimen-{i}.png','bytes':base64.b64encode(png_bytes(f['image'])).decode()}))
            db.flush()
            if p['decision']:append_audit(db,p['id'],p['decision']['action'],{'sub':'Ananya Sharma','role':'officer'},p)
        db.commit()

@asynccontextmanager
async def lifespan(app):
    init_db();seed();yield
app=FastAPI(title='IDShield AI — local identity risk decision support',description=DISCLAIMER,lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)

@app.middleware('http')
async def boundaries(request,call_next):
    origin=request.headers.get('origin');host=request.headers.get('host','')
    allowed=not origin or origin in {f'http://{host}',f'https://{host}'}
    if origin and os.environ.get('IDSHIELD_ALLOW_TUNNEL')=='1':
        allowed=allowed or (urlparse(origin).scheme=='https' and (urlparse(origin).hostname or '').endswith('.trycloudflare.com'))
    if not allowed:return JSONResponse(envelope({'error':'Cross-origin API use is disabled'}),status_code=403)
    if request.method in ('POST','PUT','PATCH'):
        try:length=int(request.headers.get('content-length','0') or 0)
        except ValueError:length=0
        if length>25*1024*1024:return JSONResponse(envelope({'error':'Request exceeds 25 MB'}),status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer';response.headers['X-IDShield-Use']='Local decision support; human decision required'
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    return response

@app.exception_handler(HTTPException)
async def http_error(request,exc):return JSONResponse(envelope({'error':exc.detail}),status_code=exc.status_code)

class Login(BaseModel):role:str='officer';password:str='officer-demo'
@app.post('/api/session')
def login(body:Login):
    account=DEMO_ACCOUNTS.get(body.role);password=os.environ.get('DEMO_'+body.role.upper()+'_PASSWORD',account[1] if account else '')
    if not account or not hmac.compare_digest(body.password,password):raise HTTPException(401,'Incorrect demo credentials')
    sid=uuid.uuid4().hex
    return envelope({'token':issue_token(account[0],body.role,sid=sid),'user':{'name':account[0],'role':body.role}})

@app.get('/api/bootstrap')
def bootstrap(who=Depends(READ)):
    with Session() as db:
        cases=[case_out(c) for c in db.scalars(select(Case).order_by(Case.id.desc()))]
        audit=[audit_out(a) for a in db.scalars(select(Audit).order_by(Audit.seq.desc()))]
    cases=session_store.list_cases(who['sid'])+cases;audit=session_store.list_audit(who['sid'])+audit
    return envelope({'cases':[public_payload(p) for p in cases],'audit':audit,'mode':'native','user':{'name':who['sub'],'role':who['role']},'database':engine.dialect.name,'ocr':'RapidOCR / Paddle-derived ONNX models','face':'OpenCV SFace trained embeddings with YuNet detection','face_models_ready':YUNET.exists() and SFACE.exists(),'retention':'Live uploads remain only in this signed session for up to four idle hours. Explicitly saved cases use encrypted storage until deletion.'})

@app.get('/api/cases/{case_id}')
def get_case(case_id:str,who=Depends(READ)):
    item=session_store.get(case_id,who['sid'])
    if item:return envelope(public_payload(item['payload']))
    with Session() as db:
        c=db.get(Case,case_id)
        if not c:raise HTTPException(404,'Case not found')
        return envelope(case_out(c))

@app.get('/api/audit')
def get_audit(who=Depends(READ)):
    with Session() as db:rows=[audit_out(a) for a in db.scalars(select(Audit).order_by(Audit.seq.desc()))]
    return envelope(session_store.list_audit(who['sid'])+rows)

@app.get('/api/capture-challenge')
def challenge(who=Depends(REVIEW)):
    return envelope({'challenge':issue_token(who['sub'],who['role'],90,purpose='capture',nonce=uuid.uuid4().hex,sid=who['sid']),'expires_in':90,'proxy_only':True})

def base_case(label,storage,who):
    case_id='IDS-'+datetime.now().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:6].upper()
    p={'id':case_id,'name':label,'initials':'NS','scenario':'upload','scenarioLabel':'Live local screening','created_at':now(),'status':'Processing','risk':None,'riskLevel':'Unassessed','signals':[],'documents':[],'stages':[{'name':n,'status':'waiting','summary':'Waiting'} for n in ['Intake','Extraction','Forensics','Intelligence','Decision']],'revision':0,'decision':None,'mode':'Local Python screening engine','storage':storage,'created_by':who['sub']}
    return case_id,p

def create_persistent_case(db,who,documents,label):
    case_id,p=base_case(label,'Encrypted saved case',who);db.add(Case(id=case_id,created_at=p['created_at'],status='Processing',payload=p))
    for d in documents:db.add(Document(id=d['id'],case_id=case_id,kind='document',expires_at='9999-12-31T00:00:00+00:00',payload={'filename':d['filename'],'bytes':base64.b64encode(d['raw']).decode()}))
    db.flush();append_audit(db,case_id,'Intake submitted',who,p);db.commit();return case_id

@app.post('/api/cases')
async def upload_case(background:BackgroundTasks,files:list[UploadFile]=File(...),consent_confirmed:bool=Form(False),traveller:UploadFile|None=File(None),capture_challenge:str|None=Form(None),who=Depends(REVIEW)):
    if not consent_confirmed:raise HTTPException(400,'Confirm that every person shown consented to this local screening')
    if not 1<=len(files)<=4:raise HTTPException(400,'Upload or capture one to four documents')
    documents=[]
    for f in files:
        raw=await f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise HTTPException(413,'Each document must be under 8 MB')
        try:decode_image(raw,f.filename or 'document')
        except Exception as exc:raise HTTPException(400,f'Cannot read document: {exc}')
        documents.append({'id':uuid.uuid4().hex,'filename':Path(f.filename or 'document.png').name,'raw':raw})
    face_record=None
    if traveller:
        raw=await traveller.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise HTTPException(413,'Portrait must be under 8 MB')
        try:decode_image(raw,'portrait.png')
        except Exception:raise HTTPException(400,'Portrait is not a valid image')
        face_record=(Path(traveller.filename or 'portrait.png').name,raw)
    fresh=False
    if capture_challenge:
        token=verify_token(capture_challenge);fresh=token.get('purpose')=='capture' and token.get('sub')==who['sub'] and token.get('sid')==who['sid'] and face_record is not None
    case_id,p=base_case('Unresolved identity','Session only · automatically discarded',who)
    session_store.create(case_id,who['sid'],p,documents,face_record,fresh,who);session_store.append_event(case_id,'Session intake submitted',who,p)
    background.add_task(run_pipeline,case_id,who,None,False,None,True)
    return envelope({'id':case_id,'storage':'session'})

class Sample(BaseModel):index:int=Field(0,ge=0,le=9)
@app.post('/api/samples/run')
def run_sample(body:Sample,background:BackgroundTasks,who=Depends(REVIEW)):
    f=specimen(body.index);face=specimen((body.index+3)%10)['portrait'] if f['scenario']=='face' else f['portrait'];document={'id':uuid.uuid4().hex,'filename':f'synthetic-{body.index}.png','raw':png_bytes(f['image'])}
    with Session() as db:case_id=create_persistent_case(db,who,[document],f['name'])
    background.add_task(run_pipeline,case_id,who,face,False);return envelope({'id':case_id})

class Decision(BaseModel):action:str;note:str=Field(min_length=3,max_length=2000);revision:int
@app.post('/api/cases/{case_id}/decision')
def decide(case_id:str,body:Decision,who=Depends(REVIEW)):
    if body.action not in ['Approve','Escalate','Reject','Request Recapture']:raise HTTPException(400,'Unknown officer action')
    item=session_store.get(case_id,who['sid'])
    if item:
        p=copy.deepcopy(item['payload'])
        if p.get('revision')!=body.revision:raise HTTPException(409,'Evidence changed. Refresh and review the current case.')
        if p['status']=='Processing':raise HTTPException(409,'Wait for pipeline processing to finish')
        if p.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Only a supervisor can revise a recorded decision')
        if p['status'] in ('Recapture','Error') and body.action=='Approve':raise HTTPException(400,'Resolve the incomplete capture before approval')
        p['decision']={'action':body.action,'note':body.note,'officer':who['sub'],'role':who['role'],'at':now()};p['revision']+=1;p['status']='Recapture' if body.action=='Request Recapture' else 'In review' if body.action=='Escalate' else 'Decided'
        session_store.persist(case_id,p,p['status']);session_store.append_event(case_id,body.action,who,p);return envelope(public_payload(p))
    with AUDIT_LOCK,Session() as db:
        c=db.scalar(select(Case).where(Case.id==case_id).with_for_update())
        if not c:raise HTTPException(404,'Case not found')
        p=copy.deepcopy(c.payload)
        if p.get('revision')!=body.revision:raise HTTPException(409,'Evidence changed. Refresh and review the current case.')
        if c.status=='Processing':raise HTTPException(409,'Wait for pipeline processing to finish')
        if p.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Only a supervisor can revise a recorded decision')
        if c.status in ('Recapture','Error') and body.action=='Approve':raise HTTPException(400,'Resolve the incomplete capture before approval')
        p['decision']={'action':body.action,'note':body.note,'officer':who['sub'],'role':who['role'],'at':now()};p['revision']+=1;c.status='Recapture' if body.action=='Request Recapture' else 'In review' if body.action=='Escalate' else 'Decided';p['status']=c.status;c.payload=p
        append_audit(db,case_id,body.action,who,p);db.commit();return envelope(case_out(c))

class Rerun(BaseModel):corrected_mrz:str|None=Field(default=None,max_length=160)
@app.post('/api/cases/{case_id}/rerun')
def rerun(case_id:str,body:Rerun,background:BackgroundTasks,who=Depends(REVIEW)):
    item=session_store.get(case_id,who['sid'])
    if item:
        p=copy.deepcopy(item['payload'])
        if p['status']=='Processing':raise HTTPException(409,'Case is already processing')
        if p.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Supervisor role required to reopen decided evidence')
        p['status']='Processing';session_store.persist(case_id,p,'Processing');session_store.append_event(case_id,'Officer-corrected MRZ' if body.corrected_mrz else 'Reanalysis requested',who,{'previous_evidence':p,'corrected_mrz':body.corrected_mrz});background.add_task(run_pipeline,case_id,who,None,False,body.corrected_mrz,True);return envelope({'id':case_id})
    with Session() as db:
        c=db.get(Case,case_id)
        if not c:raise HTTPException(404,'Case not found')
        if c.status=='Processing':raise HTTPException(409,'Case is already processing')
        if c.payload.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Supervisor role required to reopen decided evidence')
        if not db.scalar(select(Document).where(Document.case_id==case_id)):raise HTTPException(410,'Original bytes were deleted. Request a new capture.')
        c.status='Processing';append_audit(db,case_id,'Officer-corrected MRZ' if body.corrected_mrz else 'Reanalysis requested',who,{'previous_evidence':c.payload,'corrected_mrz':body.corrected_mrz});db.commit()
    background.add_task(run_pipeline,case_id,who,None,False,body.corrected_mrz);return envelope({'id':case_id})

@app.post('/api/cases/{case_id}/save')
def save_case(case_id:str,who=Depends(REVIEW)):
    item=session_store.get(case_id,who['sid'])
    if not item:raise HTTPException(404,'Session-scoped case not found or already saved')
    p=copy.deepcopy(item['payload'])
    if p['status']=='Processing':raise HTTPException(409,'Wait for processing to finish before saving')
    p['storage']='Encrypted saved case';p['created_by']=who['sub']
    with AUDIT_LOCK,Session() as db:
        if db.get(Case,case_id):raise HTTPException(409,'Case is already saved')
        db.add(Case(id=case_id,created_at=p['created_at'],status=p['status'],payload=p))
        for d in item['documents']:db.add(Document(id=d['id'],case_id=case_id,kind='document',expires_at='9999-12-31T00:00:00+00:00',payload={'filename':d['filename'],'bytes':base64.b64encode(d['raw']).decode()}))
        db.flush();append_audit(db,case_id,'Case saved with consent',who,p);db.commit()
    session_store.remove(case_id,who['sid']);return envelope(public_payload(p))

@app.delete('/api/cases/{case_id}')
def delete_case(case_id:str,who=Depends(READ)):
    if session_store.remove(case_id,who['sid']):return envelope({'deleted':True,'scope':'session','case_id':case_id})
    with AUDIT_LOCK,Session() as db:
        c=db.get(Case,case_id)
        if not c:raise HTTPException(404,'Case not found')
        if who['role'] not in ('supervisor','admin') and c.payload.get('created_by')!=who['sub']:raise HTTPException(403,'Only the creator, a supervisor, or an administrator may delete a saved case')
        db.execute(delete(Document).where(Document.case_id==case_id));db.delete(c);db.flush();append_audit(db,case_id,'Case media and embedding deleted',who,{'case_id':case_id,'deleted_at':now(),'retained':'Non-media audit metadata only'});db.commit()
    return envelope({'deleted':True,'scope':'saved','case_id':case_id})

@app.post('/api/admin/purge-expired')
def purge(who=Depends(ADMIN)):
    with AUDIT_LOCK,Session() as db:
        result=db.execute(delete(Document).where(Document.expires_at<now()));count=result.rowcount;append_audit(db,'SYSTEM','Expired source bytes purged',who,{'deleted_document_count':count});db.commit();return envelope({'deleted':count})

@app.get('/api/audit/verify-chain')
def verify_chain(who=Depends(SUPERVISE)):
    with Session() as db:
        previous='0'*64;count=0
        for a in db.scalars(select(Audit).order_by(Audit.seq)):
            expected=hash_record({'seq':a.seq,'created_at':a.created_at,'case_id':a.case_id,'action':a.action,'payload':a.payload,'previous_hash':a.previous_hash})
            if expected!=a.record_hash or a.previous_hash!=previous:return envelope({'valid':False,'checked':count,'failed_at':a.seq})
            previous=a.record_hash;count+=1
        return envelope({'valid':True,'checked':count,'head':previous})

@app.get('/api/config')
def config(who=Depends(READ)):
    return envelope({'rules':{'quality':25,'mrz':30,'fields':26,'font':14,'clone':12,'photo':20,'security':12,'face':35,'identity':28,'liveness':4},'risk_bands':{'Low':'0–24','Medium':'25–49','High':'50–100'},'formula':'min(100, sum of disclosed signal contributions). No automated disposition.','source_retention':'Session only by default; encrypted until explicit deletion after Save this case.','audit_storage':'Encrypted append-only non-media snapshots, database triggers and SHA-256 chain; not externally notarized.'})

if FRONTEND.exists():
    if (FRONTEND/'assets').exists():app.mount('/assets',StaticFiles(directory=FRONTEND/'assets'),name='assets')
    if (FRONTEND/'demo').exists():app.mount('/demo',StaticFiles(directory=FRONTEND/'demo'),name='demo')
    if (FRONTEND/'downloads').exists():app.mount('/downloads',StaticFiles(directory=FRONTEND/'downloads'),name='downloads')
    @app.get('/{path:path}')
    def spa(path:str):
        if path.startswith('api/'):raise HTTPException(404,'Endpoint not found')
        content=(FRONTEND/'index.html').read_text(encoding='utf8').replace('</head>','<script>window.__IDSHIELD_NATIVE__=true</script></head>')
        return HTMLResponse(content,headers={'Cache-Control':'no-store'})
