"""Synthetic-demo auth: signed sessions and explicit role allowlists, no government data."""
import os, json, time, hmac, hashlib, base64, secrets
from pathlib import Path
from cryptography.fernet import Fernet
from fastapi import HTTPException, Request

DATA_DIR=Path(os.environ.get('IDSHIELD_DATA_DIR','./data'))
DATA_DIR.mkdir(parents=True,exist_ok=True)
def secret(name,filename):
    val=os.environ.get(name)
    if val: return val.encode()
    path=DATA_DIR/filename
    if not path.exists():
        path.write_bytes(Fernet.generate_key())
        try: path.chmod(0o600)
        except OSError: pass
    return path.read_bytes().strip()
FERNET=Fernet(secret('ENCRYPTION_KEY','.encryption.key'))
AUTH_SECRET=secret('AUTH_SECRET','.auth.key')
DISCLAIMER='SYNTHETIC DATA — DEMO ONLY. No live government integration. Risk + evidence only; a human officer records the final decision.'
def encrypt(value): return FERNET.encrypt(json.dumps(value,separators=(',',':')).encode()).decode()
def decrypt(value): return json.loads(FERNET.decrypt(value.encode()))
def issue_token(user,role,seconds=28800,**extra):
    payload=base64.urlsafe_b64encode(json.dumps({'sub':user,'role':role,'exp':time.time()+seconds,**extra},separators=(',',':')).encode()).decode().rstrip('=')
    sig=hmac.new(AUTH_SECRET,payload.encode(),hashlib.sha256).hexdigest()
    return payload+'.'+sig
def verify_token(token):
    try:
        payload,sig=token.split('.')
        if not hmac.compare_digest(sig,hmac.new(AUTH_SECRET,payload.encode(),hashlib.sha256).hexdigest()): raise ValueError()
        data=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        if data['exp']<time.time(): raise ValueError()
        return data
    except Exception: raise HTTPException(401,'Session expired or invalid')
def require(*roles):
    def dependency(request:Request):
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        who=verify_token(token)
        if who.get('role') not in roles: raise HTTPException(403,'This action requires a different role')
        return who
    return dependency
READ=require('officer','supervisor','admin')
REVIEW=require('officer','supervisor')
SUPERVISE=require('supervisor','admin')
ADMIN=require('admin')

DEMO_ACCOUNTS={'officer':('Ananya Sharma','officer-demo'), 'supervisor':('Rohan Iyer','supervisor-demo'),'admin':('Demo Administrator','admin-demo')}
