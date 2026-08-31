"""Lightweight proxies, NOT trained fraud/biometric/security-feature classifiers.
OpenCV quality + actual local OCR with bundled Paddle-derived ONNX models.
"""
import io,re,threading
import cv2
import numpy as np
from PIL import Image, ImageDraw
from .mrz import parse_mrz
from .synthetic import make_signal, font
OCR=None;OCR_LOCK=threading.Lock()

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

def embedding(image):
    # Fixed image descriptor for SYNTHETIC portrait comparison. No claim of ArcFace accuracy.
    arr=np.array(image.convert('L').resize((32,32)),dtype=np.float32)/255
    try:
        import torch
        tensor=torch.from_numpy(arr)[None,None]
        desc=torch.nn.functional.adaptive_avg_pool2d(tensor,(16,16)).flatten().numpy()
        method='PyTorch pooled visual descriptor (untrained synthetic portrait proxy)'
    except ImportError:
        desc=cv2.resize(arr,(16,16)).flatten();method='OpenCV/NumPy pooled visual descriptor (desktop lightweight substitution)'
    desc=desc-desc.mean();norm=np.linalg.norm(desc)
    return (desc/max(norm,1e-8)).tolist(),method

def compare(a,b):return round(float(np.clip(np.dot(a,b),0,1))*100,1)
