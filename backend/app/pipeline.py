import time,uuid,base64,io,copy
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from .database import Session,Case,Document,append_audit,now
from .synthetic import make_signal,data_uri
from .vision import quality,extract,forensics,embedding,compare,decode_image

STAGES=['Intake','Extraction','Forensics','Intelligence','Decision']
def persist(case_id,payload,status=None):
    with Session() as db:
        c=db.get(Case,case_id);c.payload=copy.deepcopy(payload)
        if status:c.status=status
        db.commit()
def run_pipeline(case_id,who,traveller=None,capture_fresh=False,corrected_mrz=None):
    started=time.monotonic()
    with Session() as db:
        c=db.get(Case,case_id);p=copy.deepcopy(c.payload)
        docs=list(db.scalars(select(Document).where(Document.case_id==case_id,Document.kind=='document')))
    p.update(signals=[],documents=[],decision=None,mode='Local Python screening engine',revision=p.get('revision',0)+1)
    p['stages']=[{'name':n,'status':'waiting','summary':'Waiting for upstream evidence'} for n in STAGES]
    def stage(i,fn,summary):
        p['stages'][i].update(status='running',summary='Processing');persist(case_id,p,'Processing');t=time.monotonic();fn()
        p['stages'][i].update(status='complete',summary=summary,elapsed=round(time.monotonic()-t,2));persist(case_id,p)
    images=[]
    def intake():
        for d in docs:
            raw=base64.b64decode(d.payload['bytes']);im=decode_image(raw,d.payload['filename']);images.append(im)
            q=quality(im);thumb=im.copy();thumb.thumbnail((1200,900))
            p['documents'].append({'id':d.id,'label':d.payload['filename'],'image':data_uri(thumb),'quality':q,'fields':{},'mrz':{'fields':{},'checks':[],'lines':[]},'source':'Awaiting OCR'})
            p['signals'].append(make_signal('quality-'+d.id,'Intake','Capture quality — '+d.payload['filename'],('; '.join(q['reasons']) or 'Resolution, sharpness and lighting meet the demo thresholds.')+f" Laplacian variance {q['blur_variance']}; brightness {q['brightness']}/255.",25 if not q['ok'] else 0,95,method='Measured OpenCV heuristics'))
    try:
        stage(0,intake,'Resolution, blur and lighting evaluated')
        if any(not d['quality']['ok'] for d in p['documents']):
            p['stages'][0].update(status='blocked',summary='Recapture required before OCR');p.update(status='Recapture',risk=25,riskLevel='Medium');persist(case_id,p,'Recapture')
            with Session() as db:append_audit(db,case_id,'Quality recapture required',who,p);db.commit()
            return
        def extraction():
            for i,im in enumerate(images):
                doc=p['documents'][i];result=extract(im,corrected_mrz if i==0 else None);doc.update(result)
                checks=result['mrz']['checks'];failures=[x['field'] for x in checks if not x['valid']]
                missing=bool(result['mrz'].get('error'))
                p['signals'].append(make_signal('mrz-'+str(i),'Extraction','MRZ check digits',result['mrz'].get('error') or ('Failed check digits: '+', '.join(failures) if failures else 'All MRZ check digits are consistent; authenticity is not established.'),30 if failures else 12 if missing else 0,100 if not missing else 0,[3,76,94,17],'ICAO 9303 arithmetic'))
                mismatches=[];unknown=[]
                for field in ['name','dob','document_number','nationality','expiry']:
                    visible=result['fields'].get(field);mrz=result['mrz']['fields'].get(field)
                    if not visible or not mrz:unknown.append(field)
                    elif ''.join(visible.upper().split())!=''.join(mrz.upper().split()):mismatches.append(f'{field}: visible {visible} vs MRZ {mrz}')
                explanation='; '.join(mismatches) or 'Available visible and MRZ fields match.'
                if unknown:explanation+=' Unreadable fields requiring review: '+', '.join(unknown)+'.'
                p['signals'].append(make_signal('fields-'+str(i),'Extraction','Visible fields vs. MRZ',explanation,26 if mismatches else 8 if unknown else 0,90,[25,16,53,49],'Measured OCR field comparison'))
            p['name']=p['documents'][0]['fields'].get('name') or p['documents'][0]['mrz']['fields'].get('name') or 'Unnamed synthetic specimen'
            p['initials']=''.join(x[0] for x in p['name'].split()[:2])
        stage(1,extraction,'OCR fields decoded and MRZ check digits validated')
        def forensic():
            for i,im in enumerate(images):
                for s in forensics(im):s['id']+=f'-{i}';s['documentIndex']=i;p['signals'].append(s)
        stage(2,forensic,'Four independent image-region heuristics evaluated')
        def intelligence():
            im=images[0];docphoto=im.crop((im.width*.0375,im.height*.205,im.width*.221,im.height*.548))
            emb,method=embedding(docphoto);p['embedding']=emb;p['portrait']=data_uri(docphoto);similarity=None
            if traveller:
                other,_=embedding(traveller);similarity=compare(emb,other);small=traveller.copy();small.thumbnail((250,300));p['comparisonPortrait']=data_uri(small)
            p['faceSimilarity']=similarity
            p['signals'].append(make_signal('face','Intelligence','Portrait similarity',f'{similarity}% visual descriptor cosine similarity against an illustrative 80% threshold. {method}. NOT a calibrated biometric verification score.' if similarity is not None else 'No comparison image supplied. Portrait comparison not assessed.',35 if similarity is not None and similarity<80 else 6 if similarity is None else 0,60,[3,19,20,38],method))
            p['signals'].append(make_signal('liveness','Intelligence','Liveness proxy','A fresh, short-lived capture challenge was supplied; this cannot detect replay attacks or prove liveness.' if capture_fresh else 'No fresh webcam challenge. Liveness not assessed; uploaded static images are not evidence of liveness.',0 if capture_fresh else 4,20 if capture_fresh else 0,method='Fresh-capture challenge proxy only'))
            conflicts=[];names={};dobs={}
            for d in p['documents']:
                fields=d['fields'] or d['mrz']['fields'];names[d['id']]=fields.get('name');dobs[d['id']]=fields.get('dob')
            if len(set(x for x in names.values() if x))>1:conflicts.append('Names differ across submitted documents: '+str(names))
            if len(set(x for x in dobs.values() if x))>1:conflicts.append('DOB differs across submitted documents: '+str(dobs))
            with Session() as db:
                for other in db.scalars(select(Case).where(Case.id!=case_id)):
                    op=other.payload
                    if op.get('embedding') and compare(emb,op['embedding'])>=99.95 and op['name'].upper()!=p['name'].upper():conflicts.append(f"Same synthetic visual descriptor under a different name: {op['name']} ({other.id}).")
            p['signals'].append(make_signal('identity','Intelligence','Cross-document identity consistency',' '.join(conflicts) or 'No contradictory fields or near-identical synthetic descriptors found in retained demo cases.',28 if conflicts else 0,75,method='Exact field checks + synthetic descriptor linkage'))
        stage(3,intelligence,'Visual comparison, liveness proxy and identity consistency evaluated')
        def decision():
            p['risk']=min(100,sum(s['points'] for s in p['signals']));p['riskLevel']='High' if p['risk']>=50 else 'Medium' if p['risk']>=25 else 'Low'
            p['status']='In review';p['duration']=round(time.monotonic()-started,2)
        stage(4,decision,'Evidence ready. A human officer must record the outcome.')
        persist(case_id,p,'In review')
        with Session() as db:append_audit(db,case_id,'Screening completed',who,p);db.commit()
    except Exception as exc:
        for s in p['stages']:
            if s['status']=='running':s.update(status='error',summary='This stage needs attention')
        p['error']=str(exc)[:240];p['status']='Error';persist(case_id,p,'Error')
        with Session() as db:append_audit(db,case_id,'Screening error',who,p);db.commit()
    finally:
        # Traveller full-resolution bytes live only in this call. Only a small evidence thumbnail/descriptor is retained.
        traveller=None;images.clear()
