import os, json, hashlib, threading, copy
from datetime import datetime, timezone
from sqlalchemy import create_engine, String, Text, DateTime, event, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator
from .security import encrypt, decrypt, DATA_DIR

class EncryptedJSON(TypeDecorator):
    impl=Text; cache_ok=True
    def process_bind_param(self,value,dialect): return encrypt(value) if value is not None else None
    def process_result_value(self,value,dialect): return decrypt(value) if value else None
class Base(DeclarativeBase): pass
class Case(Base):
    __tablename__='cases'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    created_at:Mapped[str]=mapped_column(String(40))
    status:Mapped[str]=mapped_column(String(24),default='Pending',index=True)
    payload:Mapped[dict]=mapped_column(EncryptedJSON)
class Document(Base):
    __tablename__='documents'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    case_id:Mapped[str]=mapped_column(String(64),index=True)
    kind:Mapped[str]=mapped_column(String(20))
    expires_at:Mapped[str]=mapped_column(String(40),index=True)
    payload:Mapped[dict]=mapped_column(EncryptedJSON)
class Audit(Base):
    __tablename__='audit_log'
    id:Mapped[str]=mapped_column(String(64),primary_key=True)
    seq:Mapped[int]=mapped_column(unique=True,index=True)
    created_at:Mapped[str]=mapped_column(String(40))
    case_id:Mapped[str]=mapped_column(String(64),index=True)
    action:Mapped[str]=mapped_column(String(40))
    payload:Mapped[dict]=mapped_column(EncryptedJSON)
    previous_hash:Mapped[str]=mapped_column(String(64))
    record_hash:Mapped[str]=mapped_column(String(64))

url=os.environ.get('DATABASE_URL',f'sqlite:///{(DATA_DIR/"idshield.db").as_posix()}')
engine=create_engine(url,connect_args={'check_same_thread':False} if url.startswith('sqlite') else {},pool_pre_ping=True)
Session=sessionmaker(engine,expire_on_commit=False)
AUDIT_LOCK=threading.RLock()
def now(): return datetime.now(timezone.utc).isoformat()
def init_db():
    Base.metadata.create_all(engine)
    with engine.begin() as c:
        if engine.dialect.name=='sqlite':
            for operation in ('UPDATE','DELETE'):
                c.execute(text(f"CREATE TRIGGER IF NOT EXISTS audit_no_{operation.lower()} BEFORE {operation} ON audit_log BEGIN SELECT RAISE(ABORT, 'Audit log is append-only'); END;"))
        elif engine.dialect.name=='postgresql':
            c.execute(text("CREATE OR REPLACE FUNCTION idshield_audit_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Audit log is append-only'; END; $$ LANGUAGE plpgsql"))
            c.execute(text('DROP TRIGGER IF EXISTS audit_immutable ON audit_log'))
            c.execute(text('CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION idshield_audit_immutable()'))
def hash_record(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def minimize_snapshot(snapshot):
    """Keep decision evidence while excluding stored images and biometric vectors from audit rows."""
    value=copy.deepcopy(snapshot)
    if not isinstance(value,dict):return value
    value.pop('embedding',None)
    value.pop('portrait',None)
    value.pop('comparisonPortrait',None)
    for document in value.get('documents',[]):
        document.pop('image',None)
    value['audit_media_retention']='Images and face embeddings are case-linked, not copied into the immutable audit row.'
    return value
def append_audit(db,case_id,action,who,snapshot):
    import uuid
    # Single-process lock for desktop; PostgreSQL advisory transaction lock for multiple cloud workers.
    with AUDIT_LOCK:
        if engine.dialect.name=='postgresql': db.execute(text('SELECT pg_advisory_xact_lock(21688)'))
        previous=db.scalar(select(Audit).order_by(Audit.seq.desc()).limit(1))
        previous_hash=previous.record_hash if previous else '0'*64
        stamp=now(); payload={'officer':who['sub'],'role':who['role'],'evidence':minimize_snapshot(snapshot),'disclaimer':'Decision support. Final outcomes are human-recorded.'}
        seq=previous.seq+1 if previous else 1
        digest=hash_record({'seq':seq,'created_at':stamp,'case_id':case_id,'action':action,'payload':payload,'previous_hash':previous_hash})
        row=Audit(id=str(uuid.uuid4()),seq=seq,created_at=stamp,case_id=case_id,action=action,payload=payload,previous_hash=previous_hash,record_hash=digest)
        db.add(row); db.flush()
        return row
