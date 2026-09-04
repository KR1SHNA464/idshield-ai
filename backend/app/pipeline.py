import time,base64,copy,re,difflib
from sqlalchemy import select
from .database import Session,Case,Document,append_audit
from .synthetic import make_signal,data_uri
from .vision import quality,extract,forensics,pairwise_document_difference,face_embedding,compare,decode_image
from . import session_store

STAGES=['Intake','Extraction','Forensics','Intelligence','Decision']
SFACE_COSINE_THRESHOLD=36.3

def _identity_fields(document):
    fields={key:value for key,value in document.get('mrz',{}).get('fields',{}).items() if value}
    fields.update({key:value for key,value in document.get('fields',{}).items() if value})
    return fields

def _normalized_name(value):
    return re.sub(r'[^A-Z0-9]','',str(value or '').upper())

def _name_similarity(left,right):
    a=_normalized_name(left);b=_normalized_name(right)
    if not a or not b:return 1.0
    ordered=difflib.SequenceMatcher(None,a,b).ratio()
    sorted_a=''.join(sorted(re.findall(r'[A-Z0-9]+',str(left).upper())))
    sorted_b=''.join(sorted(re.findall(r'[A-Z0-9]+',str(right).upper())))
    return max(ordered,difflib.SequenceMatcher(None,sorted_a,sorted_b).ratio())

def _normalized_dob(value):
    digits=re.sub(r'\D','',str(value or ''))
    if len(digits)==6:return digits
    if len(digits)==8:
        year_first=1900<=int(digits[:4])<=2100
        return digits[2:4]+digits[4:6]+digits[6:8] if year_first else digits[6:8]+digits[2:4]+digits[:2]
    return digits

def cross_document_field_conflicts(documents):
    evidence=[_identity_fields(document) for document in documents];conflicts=[];comparable=False
    for i in range(len(evidence)):
        for j in range(i+1,len(evidence)):
            left=evidence[i];right=evidence[j]
            if left.get('name') and right.get('name'):
                comparable=True
                if _name_similarity(left['name'],right['name'])<.78:conflicts.append(f"Names differ: Document {i+1} '{left['name']}' vs Document {j+1} '{right['name']}'.")
            if left.get('dob') and right.get('dob'):
                comparable=True
                if _normalized_dob(left['dob'])!=_normalized_dob(right['dob']):conflicts.append(f"Dates of birth differ: Document {i+1} '{left['dob']}' vs Document {j+1} '{right['dob']}'.")
            left_type=documents[i].get('document_type','UNKNOWN');right_type=documents[j].get('document_type','UNKNOWN')
            if left_type==right_type and left_type!='UNKNOWN' and left.get('document_number') and right.get('document_number'):
                comparable=True;left_number=re.sub(r'[^A-Z0-9]','',str(left['document_number']).upper());right_number=re.sub(r'[^A-Z0-9]','',str(right['document_number']).upper())
                if left_number!=right_number:conflicts.append(f"{left_type} numbers differ between Document {i+1} and Document {j+1}.")
    return conflicts,comparable

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
                checks=result['mrz']['checks'];failures=[x['field'] for x in checks if not x['valid']];mrz_present=result['mrz'].get('format') in {'TD1','TD2','TD3'}
                mrz_detail=('No passport-style MRZ was detected. This is normal for PAN, Aadhaar, driving licences, college IDs, and other non-MRZ documents, so no risk points are added.' if not mrz_present else ('Failed check digits: '+', '.join(failures) if failures else 'All available MRZ check digits are internally consistent; authenticity is not established.'))
                p['signals'].append(make_signal('mrz-'+str(i),'Extraction','MRZ check digits',mrz_detail,30 if failures else 0,100 if mrz_present else 0,[3,76,94,17],'ICAO Doc 9303 arithmetic when an MRZ is present'))
                mismatches=[];unknown=[]
                if mrz_present:
                    for field in ['name','dob','document_number','nationality','expiry']:
                        visible=result['fields'].get(field);mrz=result['mrz']['fields'].get(field)
                        if not visible or not mrz:unknown.append(field)
                        elif ''.join(visible.upper().split())!=''.join(mrz.upper().split()):mismatches.append(f'{field}: visible {visible} vs MRZ {mrz}')
                    explanation='; '.join(mismatches) or 'Available visible and MRZ fields match.'
                    if unknown:explanation+=' Unreadable or unavailable fields requiring review: '+', '.join(unknown)+'.'
                    field_points=26 if mismatches else 8 if unknown else 0;field_confidence=90
                else:explanation='Visible fields were extracted where legible. MRZ comparison is not applicable to this document type.';field_points=0;field_confidence=0
                p['signals'].append(make_signal('fields-'+str(i),'Extraction','Visible fields vs. MRZ',explanation,field_points,field_confidence,[25,16,53,49],'Measured OCR field comparison when both sources exist'))
            p['name']=p['documents'][0]['fields'].get('name') or p['documents'][0]['mrz']['fields'].get('name') or 'Unresolved identity';p['initials']=''.join(x[0] for x in p['name'].split()[:2]) or 'UI'
        stage(1,extraction,'OCR fields decoded and MRZ check digits validated')
        def forensic():
            for i,im in enumerate(images):
                passport_layout=p['documents'][i]['mrz'].get('format') in {'TD1','TD2','TD3'}
                for s in forensics(im):
                    if not passport_layout and s['id'] in {'font','photo','security'}:
                        s['detail']='Measured but not scored: this fixed passport-region heuristic is not applicable to a non-MRZ document such as a PAN card. '+s['detail'];s['points']=0;s['flagged']=False;s['confidence']=0
                    s['id']+=f'-{i}';s['documentIndex']=i;p['signals'].append(s)
            if len(images)>1:
                reference_fields=p['documents'][0]['fields'] or p['documents'][0]['mrz']['fields']
                for i,im in enumerate(images[1:],1):
                    candidate_fields=p['documents'][i]['fields'] or p['documents'][i]['mrz']['fields']
                    same_subject=bool(reference_fields.get('name') and candidate_fields.get('name') and _name_similarity(reference_fields.get('name'),candidate_fields.get('name'))>=.78)
                    result=pairwise_document_difference(images[0],im);flagged=result['flagged'] and same_subject
                    detail=result['detail']+(' Extracted names match, so the localized difference needs officer review.' if flagged else ' No same-subject edit threshold was crossed.')
                    signal=make_signal(f'pairwise-{i}','Forensics',f'Original/reference vs. Document {i+1}',detail,18 if flagged else 0,75 if result['assessed'] else 0,result['region'],'ORB alignment + measured pixel-difference localization')
                    signal['documentIndex']=i;p['signals'].append(signal)
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
            if traveller is None:detail='No traveller portrait was requested. Portrait similarity is unassessed and does not add risk.';points=0;confidence=0
            elif similarity is None:detail='A usable face was not found in both the document and comparison capture. Portrait similarity is unassessed and does not add risk. '+method;points=0;confidence=0
            else:detail=f'{similarity}% SFace cosine similarity; OpenCV model threshold {SFACE_COSINE_THRESHOLD}%. This is a measured prototype score, not a calibrated identity probability.';points=35 if similarity<SFACE_COSINE_THRESHOLD else 0;confidence=80
            p['signals'].append(make_signal('face','Intelligence','Portrait similarity',detail,points,confidence,method='Trained OpenCV SFace embedding + cosine similarity'))
            liveness_detail='No traveller portrait was requested, so liveness is not applicable and adds no risk.' if traveller is None else 'A fresh, short-lived webcam capture challenge was supplied. This establishes capture-path freshness but does not defeat sophisticated replay attacks.' if capture_fresh else 'A static traveller image was supplied without a fresh webcam challenge. Liveness is unassessed.'
            p['signals'].append(make_signal('liveness','Intelligence','Liveness proxy',liveness_detail,0 if traveller is None or capture_fresh else 4,30 if capture_fresh else 0,method='Signed fresh-webcam capture challenge'))
            conflicts,comparable_identity=cross_document_field_conflicts(p['documents'])
            if len(doc_vectors)>1:
                for index,vector in enumerate(doc_vectors[1:],2):
                    score=compare(doc_vectors[0],vector)
                    if score is not None:
                        comparable_identity=True
                        if score<SFACE_COSINE_THRESHOLD:conflicts.append(f'Document 1 and document {index} faces differ ({score}% similarity).')
            if emb:
                for other_case in identity_records(who,case_id):
                    score=compare(emb,other_case.get('embedding'))
                    if score is not None and score>=SFACE_COSINE_THRESHOLD and other_case.get('name','').upper()!=p['name'].upper():conflicts.append(f"A retained face embedding matches a different extracted name: {other_case.get('name')} ({other_case.get('id')}, {score}%).")
            identity_detail=' '.join(conflicts) if conflicts else 'No contradictory normalized identity fields or trained face-embedding relationships were found.' if comparable_identity else 'Fewer than two reliable identity fields or faces were extracted, so cross-document identity consistency is unassessed.'
            p['signals'].append(make_signal('identity','Intelligence','Cross-document identity consistency',identity_detail,50 if conflicts else 0,88 if conflicts else 65 if comparable_identity else 0,method='Normalized OCR/MRZ name, DOB and same-type ID-number checks + SFace embedding query'))
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
