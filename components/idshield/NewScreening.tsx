'use client';
import { useEffect,useRef,useState } from 'react';
import { UploadCloud,FileText,Camera,Check,LoaderCircle,Play,Info,Trash2,ShieldCheck } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription } from '@/components/ui/dialog';
import { api } from '@/lib/idshield';

const samples=[{i:1,name:'Consistent specimen',detail:'Readable fields · valid check digits',kind:'low'},{i:6,name:'MRZ checksum failure',detail:'Document + composite digits altered',kind:'high'},{i:7,name:'Forensic anomalies',detail:'Edited text · photo boundary proxy',kind:'high'},{i:2,name:'Portrait mismatch',detail:'Controlled low-similarity scenario',kind:'high'},{i:8,name:'Blurred capture',detail:'Intake stops for recapture',kind:'medium'},{i:5,name:'Identity relationship',detail:'Same synthetic portrait · different name',kind:'high'}];
type CameraTarget='document'|'face'|null;

export function NewScreening({open,onClose,native,onSample,onCreated,notify}:{open:boolean;onClose:()=>void;native:boolean;onSample:(i:number)=>Promise<void>;onCreated:(id:string)=>void;notify:(s:string)=>void}){
 const [mode,setMode]=useState('upload');const [sample,setSample]=useState(1);const [files,setFiles]=useState<File[]>([]);const [portrait,setPortrait]=useState<File|null>(null);const [consent,setConsent]=useState(false);const [busy,setBusy]=useState(false);const [cameraTarget,setCameraTarget]=useState<CameraTarget>(null);const [challenge,setChallenge]=useState('');const video=useRef<HTMLVideoElement>(null);const stream=useRef<MediaStream|null>(null);const fileRef=useRef<HTMLInputElement>(null);
 useEffect(()=>()=>stream.current?.getTracks().forEach(t=>t.stop()),[]);
 useEffect(()=>{if(!open){stream.current?.getTracks().forEach(t=>t.stop());setCameraTarget(null)}},[open]);
 function stopCamera(){stream.current?.getTracks().forEach(t=>t.stop());stream.current=null;setCameraTarget(null)}
 async function startCamera(target:Exclude<CameraTarget,null>){
  if(!consent){notify('Confirm the subject’s consent before opening the camera.');return}
  if(!native){notify('Live camera processing is available in the Windows/local engine.');return}
  try{
   if(target==='face'){const x=await api<{challenge:string}>('/capture-challenge');setChallenge(x.challenge)}
   stream.current=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720},facingMode:target==='document'?{ideal:'environment'}:{ideal:'user'}},audio:false});setCameraTarget(target)
   setTimeout(()=>{if(video.current){video.current.srcObject=stream.current;void video.current.play()}},80)
  }catch(e){notify((e as Error).message)}
 }
 function capture(){
  const v=video.current,target=cameraTarget;if(!v?.videoWidth||!target)return
  const c=document.createElement('canvas');c.width=v.videoWidth;c.height=v.videoHeight;c.getContext('2d')?.drawImage(v,0,0)
  c.toBlob(blob=>{if(!blob)return;const captured=new File([blob],target==='document'?`document-capture-${Date.now()}.png`:'consented-live-face.png',{type:'image/png'});if(target==='document')addFiles([captured]);else setPortrait(captured);stopCamera()},'image/png',0.96)
 }
 function addFiles(next:File[]){if(next.length+files.length>4){notify('Choose up to four documents.');return}if(next.some(f=>f.size>8*1024*1024)){notify('Each document must be under 8 MB.');return}setFiles(current=>[...current,...next])}
 async function submit(){
  setBusy(true)
  try{
   if(mode==='sample')await onSample(sample)
   else{
    if(!native)throw new Error('Use the Windows/local launcher for live OCR and face processing.')
    if(!consent)throw new Error('Confirm consent before processing personal documents or faces.')
    if(!files.length)throw new Error('Upload or capture at least one document.')
    const form=new FormData();files.forEach(f=>form.append('files',f));form.append('consent_confirmed','true');if(portrait)form.append('traveller',portrait);if(challenge)form.append('capture_challenge',challenge)
    const result=await api<{id:string}>('/cases','POST',form);onCreated(result.id)
   }
   onClose()
  }catch(e){notify((e as Error).message)}finally{setBusy(false)}
 }
 return <Dialog open={open} onOpenChange={value=>!value&&onClose()}><DialogContent className="intake-dialog"><DialogHeader><div className="eyebrow">STAGE 1 · INTAKE</div><DialogTitle>Start a new screening</DialogTitle><DialogDescription>Process a consented live document locally, or replay a seeded synthetic edge case. A human officer always decides.</DialogDescription></DialogHeader>
  <div className="intake-tabs"><Button variant={mode==='upload'?'secondary':'ghost'} onClick={()=>setMode('upload')}><UploadCloud/>Live screening</Button><Button variant={mode==='sample'?'secondary':'ghost'} onClick={()=>setMode('sample')}><Play/>Seeded scenarios</Button></div>
  {mode==='sample'?<><div className="sample-grid">{samples.map(s=><button key={s.i} className={'sample-card '+(sample===s.i?'selected':'')} onClick={()=>setSample(s.i)}><span className={'risk-badge '+s.kind}>{s.kind} risk scenario</span><strong>{s.name}</strong><small>{s.detail}</small>{sample===s.i&&<Check size={16}/>}</button>)}</div><div className="module-note"><Info size={15}/>{native?'Runs local OCR and CV on a newly generated fictional specimen.':'Browser companion replays a clearly labeled fixture. Use the Windows launcher for actual OCR and CV.'}</div></>:<>
   <label className="consent-row"><Checkbox checked={consent} onCheckedChange={v=>setConsent(!!v)}/><span>I confirm that every person shown knows about this screening and explicitly consented to local processing of their ID and face.</span></label>
   <div className="upload-dropzone" role="button" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'||e.key===' ')fileRef.current?.click()}} onClick={()=>fileRef.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();addFiles(Array.from(e.dataTransfer.files))}}><UploadCloud/><strong>Drop document images or PDFs here</strong><span>PNG, JPG, PDF · 8 MB each · up to 4 documents</span><input ref={fileRef} type="file" accept="image/png,image/jpeg,application/pdf" multiple hidden onChange={e=>addFiles(Array.from(e.target.files||[]))}/></div>
   <Button variant="outline" disabled={!native||!consent} onClick={()=>startCamera('document')}><Camera/>Capture document with camera</Button>
   {files.map((f,i)=><div className="upload-file" key={`${f.name}-${i}`}><FileText size={16}/><span>{f.name}</span><small>{(f.size/1024).toFixed(0)} KB</small><Button variant="ghost" size="icon-sm" aria-label={'Remove '+f.name} onClick={()=>setFiles(files.filter((_,n)=>n!==i))}><Trash2/></Button></div>)}
   <div className="portrait-input"><label className="form-label">Traveller portrait (optional static comparison)<input type="file" accept="image/png,image/jpeg" onChange={e=>{setPortrait(e.target.files?.[0]||null);setChallenge('')}}/></label><Button variant="outline" disabled={!native||!consent} onClick={()=>startCamera('face')}><Camera/>Fresh face capture</Button></div>
   {portrait&&<p className="success-text"><ShieldCheck size={15}/>Selected: {portrait.name}{challenge?' · webcam freshness challenge':''}</p>}
   {cameraTarget&&<div className="camera-box"><video ref={video} playsInline muted/><p>{cameraTarget==='document'?'Fill the frame with the document and hold it steady.':'Center the consenting subject’s face in the frame.'}</p><div><Button onClick={capture}><Camera/>Capture {cameraTarget}</Button><Button variant="outline" onClick={stopCamera}>Cancel</Button></div></div>}
   <div className="module-note"><Info size={15}/>{native?'Default privacy: source images, face capture, embedding, OCR and evidence remain in this signed session and are discarded after four idle hours or when deleted. Use “Save this case” only with consent. First PDF page is analyzed.':'This hosted companion never uploads selected files. Open the Windows launcher to run the local engine.'}</div>
  </>}
  <Button className="primary-button intake-submit" disabled={busy||(mode==='upload'&&(!native||!consent||!files.length))} onClick={submit}>{busy?<LoaderCircle className="spin"/>:mode==='sample'?<Play/>:<ShieldCheck/>}{mode==='sample'?'Run seeded scenario':'Process locally in this session'}</Button>
 </DialogContent></Dialog>
}
