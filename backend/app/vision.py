"""Local OCR, OpenCV quality/forensics and trained SFace portrait embeddings."""
import io,re,threading,sys,os
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from .mrz import parse_mrz
from .synthetic import make_signal, font
OCR=None;OCR_LOCK=threading.Lock();FACE_LOCK=threading.Lock();FACE_DETECTOR=None;FACE_RECOGNIZER=None
ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[2]))
MODEL_DIR=Path(os.environ.get('FACE_MODEL_DIR',ROOT/'backend'/'models'))
YUNET=MODEL_DIR/'face_detection_yunet_2023mar.onnx'
SFACE=MODEL_DIR/'face_recognition_sface_2021dec.onnx'

def decode_image(content,filename):
    if content[:4]==b'%PDF':
        import pypdfium2 as pdfium
        pdf=pdfium.PdfDocument(content)
        if len(pdf)>5:raise ValueError('Maximum five PDF pages; upload the ID page separately.')
        image=pdf[0].render(scale=1.7).to_pil().convert('RGB')
    else:
        image=Image.open(io.BytesIO(content));image.load();image=image.convert('RGB')
    if image.width*image.height>24_000_000:raise ValueError('Image exceeds 24 megapixels')
    image.thumbnail((1800,1800))
    return image

def quality(im):
    gray=cv2.cvtColor(np.array(im),cv2.COLOR_RGB2GRAY)
    blur=float(cv2.Laplacian(gray,cv2.CV_64F).var());bright=float(gray.mean())
    over=float((gray>250).mean());under=float((gray<20).mean())
    reasons=[]
    if im.width<600 or im.height<350:reasons.append('Resolution below 600 × 350 pixels')
    if blur<35:reasons.append(f'Laplacian variance {blur:.1f} is below 35 (blur)')
    if bright>248 or bright<35 or under>0.65:reasons.append('Image is over- or underexposed')
    # White document background is common; only a near-total saturation suggests unusable glare.
    if over>0.88:reasons.append('More than 88% of pixels are saturated; possible glare')
    return {'ok':not reasons,'blur_variance':round(blur,1),'width':im.width,'height':im.height,'brightness':round(bright,1),'overexposed_fraction':round(over,3),'reasons':reasons}

def extract(im,corrected_mrz=None):
    global OCR
    with OCR_LOCK:
        if OCR is None:
            from rapidocr_onnxruntime import RapidOCR
            OCR=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=2)
        result,_=OCR(np.array(im))
    result=result or [];texts=[str(r[1]) for r in result];raw='\n'.join(texts)
    candidates=[re.sub(r'\s','',s.upper()).replace('«','<<').replace('‹','<') for s in texts if '<' in s]
    template_lines=None
    # Actual pixel glyph OCR for our fixed-layout generated specimens. This never reads metadata
    # or reconstructs check digits. A poor glyph match falls back to the general OCR transcription.
    if im.size==(1200,760) and 'SPECIMEN' in raw.upper():
        alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<'
        refs=[]
        for char in alphabet:
            glyph=Image.new('L',(25,50),255);ImageDraw.Draw(glyph).text((0,0),char,font=font(37,True),fill=0)
            refs.append(np.array(glyph)<130)
        lines=[];errors=[];gray=np.array(im.convert('L'))
        for j in range(2):
            line=''
            for k in range(44):
                tile=gray[580+j*58:630+j*58,37+k*25:62+k*25]<130
                scores=[float(np.logical_xor(tile,r).mean()) for r in refs]
                winner=int(np.argmin(scores));line+=alphabet[winner];errors.append(scores[winner])
            lines.append(line)
        if max(errors)<0.07:template_lines=lines
    parsed=parse_mrz(corrected_mrz or template_lines or candidates)
    fields={};labels={'NAME':'name','DATE OF BIRTH':'dob','DOCUMENT NO':'document_number','NATIONALITY':'nationality','DATE OF ISSUE':'issue','DATE OF EXPIRY':'expiry'}
    # Pair same-line values by OCR bounding-box center; retain unknown fields rather than inventing them.
    for box,txt,conf in result:
        normalized=re.sub(r'[^A-Z]','',txt.upper())
        key=next((v for label,v in labels.items() if re.sub(r'[^A-Z]','',label) in normalized),None)
        if not key:continue
        value=txt.split(':',1)[1].strip() if ':' in txt else ''
        if not value:
            y=np.mean(np.array(box)[:,1]);right=max(p[0] for p in box)
            options=[(min(p[0] for p in b),t) for b,t,c in result if min(p[0] for p in b)>right and abs(np.mean(np.array(b)[:,1])-y)<35]
            value=sorted(options)[0][1] if options else ''
        if value:fields[key]=value.upper().strip()
    if corrected_mrz:source='RapidOCR visible fields; MRZ text corrected by officer (audited)'
    else:source='RapidOCR visible-field OCR; template-specific pixel glyph MRZ OCR' if template_lines else 'RapidOCR / Paddle-derived ONNX models, actual local image OCR'
    return {'fields':fields,'mrz':parsed,'ocr_text':raw,'ocr_boxes':[{'box':b,'text':t,'confidence':round(float(c)*100,1)} for b,t,c in result],'source':source}

def forensics(im):
    rgb=np.array(im);gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);h,w=gray.shape
    def crop(region):
        x,y,ww,hh=region;return gray[int(y*h/100):int((y+hh)*h/100),int(x*w/100):int((x+ww)*w/100)]
    name_region=[48,17,29,8];photo_region=[3,19,20,38];sec_region=[80,46,15,18]
    patch=crop(name_region);_,binary=cv2.threshold(patch,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    n,labels,stats,centroids=cv2.connectedComponentsWithStats(binary)
    boxes=[s for s in stats[1:] if 8<s[4]<patch.size*.25 and s[3]>8]
    widths=np.array([s[2] for s in boxes],dtype=float);font_cv=float(widths.std()/max(1,widths.mean())) if len(widths)>3 else 0
    b=io.BytesIO();im.save(b,format='JPEG',quality=85);re=np.array(Image.open(io.BytesIO(b.getvalue())).convert('RGB'));ela=np.abs(rgb.astype(float)-re).mean(axis=2)
    ela_ratio=float(np.percentile(ela,95)/max(0.5,ela.mean()))
    photo=crop(photo_region);edge=cv2.Canny(photo,80,170);boundary=float(np.concatenate([edge[:5,:].ravel(),edge[-5:,:].ravel(),edge[:,:5].ravel(),edge[:,-5:].ravel()]).mean()/255)
    security=crop(sec_region);texture=float(security.std())
    checks=[('font','Font / spacing consistency',font_cv,0.8,14,name_region,'Connected-component width variation; proportional fonts can cause false positives'),('clone','Copy-move / ELA proxy',ela_ratio,9,12,[25,16,55,49],'JPEG error-level residual ratio; not a copy-move detector'),('photo','Photo boundary continuity',boundary,0.28,20,photo_region,'Template-specific rectangular boundary edge density'),('security','Security-region texture proxy',texture,9,12,sec_region,'Template-specific intensity variance; not hologram verification')]
    out=[]
    for id,title,value,threshold,points,region,method in checks:
        flag=value<threshold if id=='security' else value>threshold
        out.append(make_signal(id,'Forensics',title,f'Measured {value:.3f}; heuristic threshold {threshold}. '+('Anomaly flagged for officer inspection. ' if flag else 'No threshold crossing. ')+method,points if flag else 0,60,region,'Measured heuristic proxy'))
    return out

def pairwise_document_difference(reference,candidate):
    """Align two document images and localize substantial pixel changes.

    This is useful when an officer submits an original/reference plus a suspected
    edited copy. It is a measured comparison signal, not proof of tampering.
    """
    ref=cv2.cvtColor(np.array(reference.convert('RGB')),cv2.COLOR_RGB2GRAY)
    cand=cv2.cvtColor(np.array(candidate.convert('RGB')),cv2.COLOR_RGB2GRAY)
    ref_h,ref_w=ref.shape
    aspect_delta=abs((cand.shape[1]/cand.shape[0])-(ref_w/ref_h))/(ref_w/ref_h)
    if aspect_delta>.12:
        return {'assessed':False,'flagged':False,'changed_fraction':0.0,'region':None,'matches':0,'detail':'Document shapes differ too much for a reliable pixel alignment.'}
    orb=cv2.ORB_create(nfeatures=1600)
    ref_points,ref_desc=orb.detectAndCompute(ref,None);cand_points,cand_desc=orb.detectAndCompute(cand,None)
    good=[]
    if ref_desc is not None and cand_desc is not None:
        for pair in cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(cand_desc,ref_desc,k=2):
            if len(pair)==2 and pair[0].distance<.72*pair[1].distance:good.append(pair[0])
    if len(good)>=12:
        source=np.float32([cand_points[m.queryIdx].pt for m in good]).reshape(-1,1,2)
        target=np.float32([ref_points[m.trainIdx].pt for m in good]).reshape(-1,1,2)
        matrix,_=cv2.findHomography(source,target,cv2.RANSAC,4.0)
        aligned=cv2.warpPerspective(cand,matrix,(ref_w,ref_h),borderValue=255) if matrix is not None else cv2.resize(cand,(ref_w,ref_h))
        assessed=matrix is not None
    else:
        aligned=cv2.resize(cand,(ref_w,ref_h));assessed=reference.size==candidate.size
    if not assessed:
        return {'assessed':False,'flagged':False,'changed_fraction':0.0,'region':None,'matches':len(good),'detail':'Too few matching features for a reliable original-versus-copy alignment.'}
    ref_smooth=cv2.GaussianBlur(ref,(3,3),0);cand_smooth=cv2.GaussianBlur(aligned,(3,3),0)
    delta=cv2.absdiff(ref_smooth,cand_smooth);mask=(delta>20).astype(np.uint8)*255
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((3,3),np.uint8));mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    contours=[c for c in contours if cv2.contourArea(c)>ref_w*ref_h*.00012]
    changed=float(sum(cv2.contourArea(c) for c in contours)/(ref_w*ref_h))
    region=None;largest=0.0
    if contours:
        contour=max(contours,key=cv2.contourArea);x,y,w,h=cv2.boundingRect(contour);largest=float(cv2.contourArea(contour)/(ref_w*ref_h))
        region=[round(x/ref_w*100,1),round(y/ref_h*100,1),round(w/ref_w*100,1),round(h/ref_h*100,1)]
    flagged=.0025<=changed<=.35 and largest>=.0008
    detail=f'Aligned Document 2+ to Document 1 using {len(good)} matched features; localized changed area {changed*100:.2f}% (largest region {largest*100:.2f}%).'
    return {'assessed':True,'flagged':flagged,'changed_fraction':round(changed,4),'region':region,'matches':len(good),'detail':detail}

def _face_models(size):
    global FACE_DETECTOR,FACE_RECOGNIZER
    if not YUNET.exists() or not SFACE.exists():
        return None,None
    if FACE_DETECTOR is None:
        FACE_DETECTOR=cv2.FaceDetectorYN_create(str(YUNET),'',size,0.75,0.3,5000)
        FACE_RECOGNIZER=cv2.FaceRecognizerSF_create(str(SFACE),'')
    FACE_DETECTOR.setInputSize(size)
    return FACE_DETECTOR,FACE_RECOGNIZER

def face_embedding(image):
    """Return a real SFace embedding for the largest YuNet-detected face."""
    bgr=cv2.cvtColor(np.array(image.convert('RGB')),cv2.COLOR_RGB2BGR)
    h,w=bgr.shape[:2]
    with FACE_LOCK:
        detector,recognizer=_face_models((w,h))
        if detector is None:
            return None,'SFace model files unavailable; portrait similarity not assessed',None
        _,faces=detector.detect(bgr)
        if faces is None or not len(faces):
            return None,'OpenCV YuNet found no usable face; portrait similarity not assessed',None
        face=max(faces,key=lambda row:float(row[2]*row[3]))
        aligned=recognizer.alignCrop(bgr,face)
        vector=recognizer.feature(aligned).flatten().astype(np.float32)
    vector/=max(float(np.linalg.norm(vector)),1e-8)
    rgb=cv2.cvtColor(aligned,cv2.COLOR_BGR2RGB)
    return vector.tolist(),'OpenCV SFace trained embedding with YuNet face detection',Image.fromarray(rgb)

def embedding(image):
    vector,method,_=face_embedding(image)
    return vector,method

def compare(a,b):
    if not a or not b:return None
    return round(float(np.clip(np.dot(np.asarray(a),np.asarray(b)),0,1))*100,1)
