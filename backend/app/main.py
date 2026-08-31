import os,sys,json,base64,copy,uuid,time,hmac
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime,timedelta,timezone
from fastapi import FastAPI,Depends,HTTPException,UploadFile,File,Form,BackgroundTasks,Request
from fastapi.responses import JSONResponse,FileResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from sqlalchemy import select,delete
from .security import READ,REVIEW,SUPERVISE,ADMIN,DEMO_ACCOUNTS,issue_token,verify_token,DISCLAIMER,DATA_DIR
from .database import init_db,Session,Case,Document,Audit,append_audit,hash_record,now,engine,AUDIT_LOCK
from .synthetic import fixture_case,specimen,png_bytes,data_uri,NAMES
from .vision import decode_image,embedding
from .pipeline import run_pipeline

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
FRONTEND=Path(os.environ.get('FRONTEND_DIR',ROOT/'desktop-dist'))
def envelope(data):return {'data':data,'disclaimer':DISCLAIMER,'human_decision_required':True}
def case_out(c):
    p=copy.deepcopy(c.payload);p['status']=c.status;p.pop('embedding',None);return p
def audit_out(a):return {'id':a.id,'seq':a.seq,'case_id':a.case_id,'action':a.action,'created_at':a.created_at,'officer':a.payload['officer'],'role':a.payload['role'],'snapshot':a.payload['evidence'],'previous_hash':a.previous_hash,'record_hash':a.record_hash}
def seed():
    with Session() as db:
        if db.scalar(select(Case).limit(1)):return
        for i in range(20):
            p=fixture_case(i);f=specimen(i);p['documents'][0]['image']=data_uri(f['image']);p['portrait']=data_uri(f['portrait']);p['comparisonPortrait']=data_uri(specimen((i+3)%20 if p['scenario']=='face' else (0 if p['scenario']=='identity' else i))['portrait'])
            p['embedding']=embedding(f['portrait'])[0]
            docid=p['documents'][0]['id'];db.add(Case(id=p['id'],created_at=p['created_at'],status=p['status'],payload=p))
            db.add(Document(id=docid,case_id=p['id'],kind='document',expires_at=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),payload={'filename':f'specimen-{i}.png','bytes':base64.b64encode(png_bytes(f['image'])).decode()}))
            db.flush()
            if p['decision']:append_audit(db,p['id'],p['decision']['action'],{'sub':'Ananya Sharma','role':'officer'},p)
        db.commit()
@asynccontextmanager
async def lifespan(app):
    init_db();seed();yield
app=FastAPI(title='IDShield AI — synthetic decision support',description=DISCLAIMER,lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
@app.middleware('http')
async def boundaries(request,call_next):
    # Origin validation prevents unrelated websites from using the localhost demo engine.
    origin=request.headers.get('origin')
    host=request.headers.get('host','')
    if origin and origin not in {f'http://{host}',f'https://{host}'}:
        return JSONResponse(envelope({'error':'Cross-origin API use is disabled'}),status_code=403)
    if request.method in ('POST','PUT','PATCH'):
        length=int(request.headers.get('content-length','0') or 0)
        if length>25*1024*1024:return JSONResponse(envelope({'error':'Request exceeds 25 MB'}),status_code=413)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-IDShield-Use']='Synthetic decision support; human decision required'
    if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
    return response
@app.exception_handler(HTTPException)
async def http_error(request,exc):return JSONResponse(envelope({'error':exc.detail}),status_code=exc.status_code)

class Login(BaseModel):
    role:str='officer';password:str='officer-demo'
@app.post('/api/session')
def login(body:Login):
    # Intentional public demo authentication entry point; all data endpoints require the resulting signed role.
    account=DEMO_ACCOUNTS.get(body.role)
    password=os.environ.get('DEMO_'+body.role.upper()+'_PASSWORD',account[1] if account else '')
    if not account or not hmac.compare_digest(body.password,password):raise HTTPException(401,'Incorrect demo credentials')
    return envelope({'token':issue_token(account[0],body.role),'user':{'name':account[0],'role':body.role}})
@app.get('/api/bootstrap')
def bootstrap(who=Depends(READ)):
    with Session() as db:
        return envelope({'cases':[case_out(c) for c in db.scalars(select(Case).order_by(Case.id.desc()))],'audit':[audit_out(a) for a in db.scalars(select(Audit).order_by(Audit.seq.desc()))],'mode':'native','user':{'name':who['sub'],'role':who['role']},'database':engine.dialect.name,'ocr':'RapidOCR / Paddle-derived ONNX models','face':'Untrained pooled descriptor proxy; not ArcFace','retention':'24 hours for source document bytes; traveller originals discarded after inference; encrypted thumbnails retained in audit snapshots.'})
@app.get('/api/cases/{case_id}')
def get_case(case_id:str,who=Depends(READ)):
    with Session() as db:
        c=db.get(Case,case_id)
        if not c:raise HTTPException(404,'Case not found')
        return envelope(case_out(c))
@app.get('/api/audit')
def get_audit(who=Depends(READ)):
    with Session() as db:return envelope([audit_out(a) for a in db.scalars(select(Audit).order_by(Audit.seq.desc()))])
@app.get('/api/capture-challenge')
def challenge(who=Depends(REVIEW)):
    return envelope({'challenge':issue_token(who['sub'],who['role'],90,purpose='capture',nonce=uuid.uuid4().hex),'expires_in':90,'proxy_only':True})

def create_case(db,who,documents,label):
    case_id='IDS-'+datetime.now().strftime('%Y%m%d')+'-'+uuid.uuid4().hex[:6].upper()
    p={'id':case_id,'name':label,'initials':'NS','scenario':'upload','scenarioLabel':'New synthetic screening','created_at':now(),'status':'Processing','risk':None,'riskLevel':'Unassessed','signals':[],'documents':[],'stages':[{'name':n,'status':'waiting','summary':'Waiting'} for n in ['Intake','Extraction','Forensics','Intelligence','Decision']],'revision':0,'decision':None,'mode':'Local Python screening engine'}
    db.add(Case(id=case_id,created_at=p['created_at'],status='Processing',payload=p))
    for filename,raw in documents:
        db.add(Document(id=uuid.uuid4().hex,case_id=case_id,kind='document',expires_at=(datetime.now(timezone.utc)+timedelta(hours=24)).isoformat(),payload={'filename':filename,'bytes':base64.b64encode(raw).decode()}))
    db.flush();append_audit(db,case_id,'Intake submitted',who,p);db.commit();return case_id
@app.post('/api/cases')
async def upload_case(background:BackgroundTasks,files:list[UploadFile]=File(...),synthetic_confirmed:bool=Form(False),traveller:UploadFile|None=File(None),capture_challenge:str|None=Form(None),who=Depends(REVIEW)):
    if not synthetic_confirmed:raise HTTPException(400,'Confirm synthetic documents and consent before uploading')
    if not 1<=len(files)<=4:raise HTTPException(400,'Upload one to four documents')
    documents=[]
    for f in files:
        raw=await f.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise HTTPException(413,'Each document must be under 8 MB')
        try:decode_image(raw,f.filename or 'specimen')
        except Exception as exc:raise HTTPException(400,f'Cannot read document: {exc}')
        documents.append((Path(f.filename or 'specimen.png').name,raw))
    face=None
    if traveller:
        raw=await traveller.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:raise HTTPException(413,'Portrait must be under 8 MB')
        try:face=decode_image(raw,'portrait.png')
        except Exception:raise HTTPException(400,'Portrait is not a valid image')
    fresh=False
    if capture_challenge:
        token=verify_token(capture_challenge);fresh=token.get('purpose')=='capture' and token.get('sub')==who['sub'] and face is not None
    with Session() as db:case_id=create_case(db,who,documents,'New synthetic specimen')
    background.add_task(run_pipeline,case_id,who,face,fresh)
    return envelope({'id':case_id})
class Sample(BaseModel):index:int=Field(0,ge=0,le=19)
@app.post('/api/samples/run')
def run_sample(body:Sample,background:BackgroundTasks,who=Depends(REVIEW)):
    f=specimen(body.index);face=specimen((body.index+3)%20)['portrait'] if f['scenario']=='face' else f['portrait']
    with Session() as db:case_id=create_case(db,who,[(f'synthetic-{body.index}.png',png_bytes(f['image']))],f['name'])
    background.add_task(run_pipeline,case_id,who,face,False);return envelope({'id':case_id})
class Decision(BaseModel):
    action:str;note:str=Field(min_length=3,max_length=2000);revision:int
@app.post('/api/cases/{case_id}/decision')
def decide(case_id:str,body:Decision,who=Depends(REVIEW)):
    if body.action not in ['Approve','Escalate','Reject','Request Recapture']:raise HTTPException(400,'Unknown officer action')
    with AUDIT_LOCK,Session() as db:
        c=db.scalar(select(Case).where(Case.id==case_id).with_for_update())
        if not c:raise HTTPException(404,'Case not found')
        p=copy.deepcopy(c.payload)
        if p.get('revision')!=body.revision:raise HTTPException(409,'Evidence changed. Refresh and review the current case.')
        if c.status=='Processing':raise HTTPException(409,'Wait for pipeline processing to finish')
        if p.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Only a supervisor can revise a recorded decision')
        if c.status in ('Recapture','Error') and body.action=='Approve':raise HTTPException(400,'Resolve the incomplete capture before approval')
        p['decision']={'action':body.action,'note':body.note,'officer':who['sub'],'role':who['role'],'at':now()};p['revision']+=1
        c.status='Recapture' if body.action=='Request Recapture' else 'In review' if body.action=='Escalate' else 'Decided';p['status']=c.status;c.payload=p
        append_audit(db,case_id,body.action,who,p);db.commit();return envelope(case_out(c))
class Rerun(BaseModel):corrected_mrz:str|None=Field(default=None,max_length=160)
@app.post('/api/cases/{case_id}/rerun')
def rerun(case_id:str,body:Rerun,background:BackgroundTasks,who=Depends(REVIEW)):
    with Session() as db:
        c=db.get(Case,case_id)
        if not c:raise HTTPException(404,'Case not found')
        if c.status=='Processing':raise HTTPException(409,'Case is already processing')
        if c.payload.get('decision') and who['role']!='supervisor':raise HTTPException(403,'Supervisor role required to reopen decided evidence')
        if not db.scalar(select(Document).where(Document.case_id==case_id)):raise HTTPException(410,'Original bytes expired. Request a new capture.')
        c.status='Processing';append_audit(db,case_id,'Officer-corrected MRZ' if body.corrected_mrz else 'Reanalysis requested',who,{'previous_evidence':c.payload,'corrected_mrz':body.corrected_mrz});db.commit()
    background.add_task(run_pipeline,case_id,who,None,False,body.corrected_mrz);return envelope({'id':case_id})
@app.post('/api/admin/purge-expired')
def purge(who=Depends(ADMIN)):
    with AUDIT_LOCK,Session() as db:
        result=db.execute(delete(Document).where(Document.expires_at<now()));count=result.rowcount
        append_audit(db,'SYSTEM','Expired source bytes purged',who,{'deleted_document_count':count});db.commit();return envelope({'deleted':count})
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
    return envelope({'rules':{'quality':25,'mrz':30,'fields':26,'font':14,'clone':12,'photo':20,'security':12,'face':35,'identity':28,'liveness':4},'risk_bands':{'Low':'0–24','Medium':'25–49','High':'50–100'},'formula':'min(100, sum of disclosed signal contributions). No automated disposition.','source_retention_hours':24,'audit_storage':'Encrypted append-only snapshots, database triggers and SHA-256 chain; not externally notarized.'})

if FRONTEND.exists():
    if (FRONTEND/'assets').exists():app.mount('/assets',StaticFiles(directory=FRONTEND/'assets'),name='assets')
    if (FRONTEND/'demo').exists():app.mount('/demo',StaticFiles(directory=FRONTEND/'demo'),name='demo')
    if (FRONTEND/'downloads').exists():app.mount('/downloads',StaticFiles(directory=FRONTEND/'downloads'),name='downloads')
    @app.get('/{path:path}')
    def spa(path:str):
        if path.startswith('api/'):raise HTTPException(404,'Endpoint not found')
        content=(FRONTEND/'index.html').read_text(encoding='utf8').replace('</head>','<script>window.__IDSHIELD_NATIVE__=true</script></head>')
        return HTMLResponse(content,headers={'Cache-Control':'no-store'})
