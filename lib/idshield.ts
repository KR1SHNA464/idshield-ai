export type Signal={id:string;stage:string;title:string;detail:string;points:number;confidence:number;flagged:boolean;method:string;region?:number[]|null;documentIndex?:number};
export type MRZ={format?:string;fields:Record<string,string>;lines:string[];checks:{field:string;input:string;expected:string;actual:string;valid:boolean;rule:string}[];error?:string|null};
export type EvidenceDocument={id:string;label:string;image:string;fields:Record<string,string>;mrz:MRZ;quality:{ok:boolean;blur_variance:number;width:number;height:number;brightness:number;overexposed_fraction:number;reasons?:string[]};source:string;ocr_text?:string};
export type CaseRecord={id:string;name:string;initials:string;scenario:string;scenarioLabel:string;status:string;risk:number|null;riskLevel:string;created_at:string;documents:EvidenceDocument[];signals:Signal[];stages:{name:string;status:string;summary:string;elapsed?:number}[];faceSimilarity?:number|null;portrait?:string;comparisonPortrait?:string;decision?:{action:string;officer:string;note:string;at:string;role?:string}|null;mode:string;storage?:string;created_by?:string;revision:number;error?:string;duration?:number};
export type AuditRecord={id:string;seq:number;case_id:string;action:string;created_at:string;officer:string;role:string;snapshot:CaseRecord;record_hash:string;previous_hash:string};
export type User={name:string;role:string};
declare global{interface Window{__IDSHIELD_NATIVE__?:boolean}}
let token='';
const ENGINE_KEY='idshield.liveEngine';
function normalizeEngineUrl(value:string){
 const url=new URL(value.trim());
 if(!['http:','https:'].includes(url.protocol))throw new Error('Use an http:// or https:// engine link.')
 if(typeof window!=='undefined'&&window.location.protocol==='https:'&&url.protocol!=='https:')throw new Error('This page requires the HTTPS tunnel link, not a local http:// address.')
 return url.origin
}
export function getEngineUrl(){
 if(typeof window==='undefined'||window.__IDSHIELD_NATIVE__)return ''
 const query=new URLSearchParams(window.location.search).get('engine');
 if(query){try{const normalized=normalizeEngineUrl(query);window.localStorage.setItem(ENGINE_KEY,normalized);return normalized}catch{return ''}}
 return window.localStorage.getItem(ENGINE_KEY)||''
}
export function configureEngine(value:string){const normalized=normalizeEngineUrl(value);window.localStorage.setItem(ENGINE_KEY,normalized);token='';return normalized}
export function clearEngine(){if(typeof window!=='undefined')window.localStorage.removeItem(ENGINE_KEY);token=''}
export const isNative=()=>typeof window!=='undefined'&&(!!window.__IDSHIELD_NATIVE__||!!getEngineUrl());
export async function api<T=unknown>(path:string,method='GET',body?:unknown):Promise<T>{
 const multipart=body instanceof FormData;
 const r=await fetch(getEngineUrl()+'/api'+path,{method,headers:{...(token?{Authorization:'Bearer '+token}:{}),...(!multipart&&body?{'Content-Type':'application/json'}:{})},body:body?(multipart?body:JSON.stringify(body)):undefined});
 const payload=await r.json() as {data:T & {error?:string};detail?:string};if(!r.ok)throw new Error(payload.data?.error||payload.detail||'Unable to complete request');return payload.data;
}
export async function login(role='officer',password='officer-demo'){
 const result=await api<{token:string;user:User}>('/session','POST',{role,password});token=result.token;return result.user;
}
export const riskClass=(value:string)=>value.toLowerCase();
export const timeLabel=(value:string)=>new Date(value).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit',hour12:false});
export const dateLabel=(value:string)=>new Date(value).toLocaleString('en-IN',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'});
export function downloadJson(name:string,value:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url)}
export async function hash(value:unknown){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(value)));return Array.from(new Uint8Array(bytes)).map(x=>x.toString(16).padStart(2,'0')).join('')}
