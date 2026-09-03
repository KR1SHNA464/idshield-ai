import time,base64,copy
from sqlalchemy import select
from .database import Session,Case,Document,append_audit
from .synthetic import make_signal,data_uri
from .vision import quality,extract,forensics,face_embedding,compare,decode_image
from . import session_store

STAGES=['Intake','Extraction','Forensics','Intelligence','Decision']
SFACE_COSINE_THRESHOLD=36.3

def persist(case_id,payload,status=None,ephemeral=False):
    if ephemeral:
        session_store.persist(case_id,payload,status);return
    with Session() as db:
        c=db.get(Case,case_id)
        if not c:raise KeyError('Case no longer exists')
        c.payload=copy.deepcopy(payload)
        if status:c.status=status
        db.commit()

def audit(case_id,action,who,payload,ephemeral):
    if ephemeral:session_store.append_event(case_id,action,who,payload)
    else:
        with Session() as db:append_audit(db,case_id,action,who,payload);db.commit()

def load(case_id,ephemeral):
    if ephemeral:
        item=session_store.get(case_id)
        if not item:raise KeyError('Session-scoped case expired or was deleted')
        p=copy.deepcopy(item['payload']);docs=copy.deepcopy(item['documents'])
        traveller=decode_image(item['traveller'][1],item['traveller'][0]) if item.get('traveller') else None
        return p,docs,traveller,bool(item.get('capture_fresh'))
    with Session() as db:
        c=db.get(Case,case_id);p=copy.deepcopy(c.payload)
        rows=list(db.scalars(select(Document).where(Document.case_id==case_id,Document.kind=='document')))
        docs=[{'id':d.id,'filename':d.payload['filename'],'raw':base64.b64decode(d.payload['bytes'])} for d in rows]
    return p,docs,None,False

def identity_records(who,case_id):
    with Session() as db:records=[copy.deepcopy(c.payload) for c in db.scalars(select(Case).where(Case.id!=case_id))]
    if who.get('sid'):records.extend(p for p in session_store.list_cases(who['sid']) if p['id']!=case_id)
    return records

def run_pipeline(case_id,who,traveller=None,capture_fresh=False,corrected_mrz=None,ephemeral=False):
    started=time.monotonic();images=[]
    try:
        p,docs,stored_traveller,stored_fresh=load(case_id,ephemeral)
        traveller=stored_traveller if ephemeral else traveller;capture_fresh=stored_fresh if ephemeral else capture_fresh
        p.update(signals=[],documents=[],decision=None,mode='Local Python screening engine',revision=p.get('revision',0)+1)
        p['storage']='Session only · automatically discarded' if ephemeral else 'Encrypted saved case'
        p['stages']=[{'name':n,'status':'waiting','summary':'Waiting for upstream evidence'} for n in STAGES]
        def stage(i,fn,summary):
            p['stages'][i].update(status='running',summary='Processing');persist(case_id,p,'Processing',ephemeral);t=time.monotonic();fn()
            p['stages'][i].update(status='complete',summary=summary,elapsed=round(time.monotonic()-t,2));persist(case_id,p,None,ephemeral)
        def intake():
            for d in docs:
                im=decode_image(d['raw'],d['filename']);images.append(im);q=quality(im);thumb=im.copy();thumb.thumbnail((1200,900))
                p['documents'].append({'id':d['id'],'label':d['filename'],'image':data_uri(thumb),'quality':q,'fields':{},'mrz':{'fields':{},'checks':[],'lines':[]},'source':'Awaiting OCR'})
                detail=('; '.join(q['reasons']) or 'Resolution, sharpness and lighting meet the configured thresholds.')+f" Laplacian variance {q['blur_variance']}; brightness {q['brightness']}/255."
                p['signals'].append(make_signal('quality-'+d['id'],'Intake','Capture quality — '+d['filename'],detail,25 if not q['ok'] else 0,95,method='Measured OpenCV heuristics'))
        stage(0,intake,'Resolution, blur and lighting evaluated')
        if any(not d['quality']['ok'] for d in p['documents']):
            p['stages'][0].update(status='blocked',summary='Recapture required before OCR');p.update(status='Recapture',risk=25,riskLevel='Medium')
            persist(case_id,p,'Recapture',ephemeral);audit(case_id,'Quality recapture required',who,p,ephemeral);return
        def extraction():
            for i,im in enumerate(images):
                doc=p['documents'][i];result=extract(im,corrected_mrz if i==0 else None);doc.update(result)
                checks=result['mrz']['checks'];failures=[x['field'] for x in checks if not x['valid']];missing=bool(result['mrz'].get('error'))
                p['signals'].append(make_signal('mrz-'+str(i),'Extraction','MRZ check digits',result['mrz'].get('error') or ('Failed check digits: '+', '.join(failures) if failures else 'All available MRZ check digits are internally consistent; authenticity is not established.'),30 if failures else 12 if missing else 0,100 if not missing else 0,[3,76,94,17],'ICAO Doc 9303 arithmetic'))
                mismatches=[];unknown=[]
                for field in ['name','dob','document_number','nationality','expiry']:
                    visible=result['fields'].get(field);mrz=result['mrz']['fields'].get(field)
                    if not visible or not mrz:unknown.append(field)
                    elif ''.join(visible.upper().split())!=''.join(mrz.upper().split()):mismatches.append(f'{field}: visible {visible} vs MRZ {mrz}')
                explanation='; '.join(mismatches) or 'Available visible and MRZ fields match.'
                if unknown:explanation+=' Unreadable or unavailable fields requiring review: '+', '.join(unknown)+'.'
                p['signals'].append(make_signal('fields-'+str(i),'Extraction','Visible fields vs. MRZ',explanation,26 if mismatches else 8 if unknown else 0,90,[25,16,53,49],'Measured OCR field comparison'))
            p['name']=p['documents'][0]['fields'].get('name') or p['documents'][0]['mrz']['fields'].get('name') or 'Unresolved identity';p['initials']=''.join(x[0] for x in p['name'].split()[:2]) or 'UI'
        stage(1,extraction,'OCR fields decoded and MRZ check digits validated')
        def forensic():
            for i,im in enumerate(images):
                for s in forensics(im):s['id']+=f'-{i}';s['documentIndex']=i;p['signals'].append(s)
        stage(2,forensic,'Four independent pixel-level checks evaluated')
        def intelligence():
            doc_vectors=[];doc_face=None;methods=[]
            for im in images:
                vector,method,crop=face_embedding(im);methods.append(method)
                if vector:doc_vectors.append(vector)
                if doc_face is None and crop is not None:doc_face=crop
            emb=doc_vectors[0] if doc_vectors else None
            if emb:p['embedding']=emb
            if doc_face is not None:p['portrait']=data_uri(doc_face)
            similarity=None;traveller_method='No comparison face supplied'
            if traveller is not None:
                other,traveller_method,other_crop=face_embedding(traveller);similarity=compare(emb,other)
                if other_crop is not None:p['comparisonPortrait']=data_uri(other_crop)
            p['faceSimilarity']=similarity;method='; '.join(dict.fromkeys(methods+[traveller_method]))
            if similarity is None:detail='A usable face was not found in both the document and comparison capture. Portrait similarity is unassessed. '+method;points=6;confidence=0
            else:detail=f'{similarity}% SFace cosine similarity; OpenCV model threshold {SFACE_COSINE_THRESHOLD}%. This is a measured prototype score, not a calibrated identity probability.';points=35 if similarity<SFACE_COSINE_THRESHOLD else 0;confidence=80
            p['signals'].append(make_signal('face','Intelligence','Portrait similarity',detail,points,confidence,method='Trained OpenCV SFace embedding + cosine similarity'))
            p['signals'].append(make_signal('liveness','Intelligence','Liveness proxy','A fresh, short-lived webcam capture challenge was supplied. This establishes capture-path freshness but does not defeat sophisticated replay attacks.' if capture_fresh else 'No fresh webcam challenge. Liveness is unassessed; an uploaded static image is not evidence of liveness.',0 if capture_fresh else 4,30 if capture_fresh else 0,method='Signed fresh-webcam capture challenge'))
            conflicts=[];names={};dobs={}
            for d in p['documents']:
                fields=d['fields'] or d['mrz']['fields'];names[d['id']]=fields.get('name');dobs[d['id']]=fields.get('dob')
            if len(set(x for x in names.values() if x))>1:conflicts.append('Names differ across submitted documents: '+str(names))
            if len(set(x for x in dobs.values() if x))>1:conflicts.append('DOB differs across submitted documents: '+str(dobs))
            if len(doc_vectors)>1:
                for index,vector in enumerate(doc_vectors[1:],2):
                    score=compare(doc_vectors[0],vector)
                    if score is not None and score<SFACE_COSINE_THRESHOLD:conflicts.append(f'Document 1 and document {index} faces differ ({score}% similarity).')
            if emb:
                for other_case in identity_records(who,case_id):
                    score=compare(emb,other_case.get('embedding'))
                    if score is not None and score>=SFACE_COSINE_THRESHOLD and other_case.get('name','').upper()!=p['name'].upper():conflicts.append(f"A retained face embedding matches a different extracted name: {other_case.get('name')} ({other_case.get('id')}, {score}%).")
            p['signals'].append(make_signal('identity','Intelligence','Cross-document identity consistency',' '.join(conflicts) or 'No contradictory fields or trained face-embedding relationships were found in available consented/saved cases.',28 if conflicts else 0,80 if emb else 45,method='Exact field checks + SFace embedding query'))
        stage(3,intelligence,'Trained face comparison, capture freshness and identity consistency evaluated')
        def decision():
            p['risk']=min(100,sum(s['points'] for s in p['signals']));p['riskLevel']='High' if p['risk']>=50 else 'Medium' if p['risk']>=25 else 'Low';p['status']='In review';p['duration']=round(time.monotonic()-started,2)
        stage(4,decision,'Evidence ready. A human officer must record the outcome.')
        persist(case_id,p,'In review',ephemeral);audit(case_id,'Screening completed',who,p,ephemeral)
    except Exception as exc:
        try:
            for s in p['stages']:
                if s['status']=='running':s.update(status='error',summary='This stage needs attention')
            p['error']=str(exc)[:240];p['status']='Error';persist(case_id,p,'Error',ephemeral);audit(case_id,'Screening error',who,p,ephemeral)
        except Exception:pass
    finally:
        traveller=None;images.clear()
