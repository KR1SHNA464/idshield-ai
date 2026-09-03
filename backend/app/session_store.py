"""Process live uploads in RAM unless a user explicitly saves the case."""
import copy, threading, time, uuid
from .database import hash_record, minimize_snapshot, now

TTL_SECONDS = 4 * 60 * 60
LOCK = threading.RLock()
CASES: dict[str, dict] = {}

def _purge_expired():
    cutoff = time.monotonic()
    for case_id in [key for key, value in CASES.items() if value['expires_at'] <= cutoff]:
        CASES.pop(case_id, None)

def create(case_id, owner_sid, payload, documents, traveller, capture_fresh, who):
    with LOCK:
        _purge_expired()
        CASES[case_id] = {
            'owner_sid': owner_sid,
            'payload': copy.deepcopy(payload),
            'documents': documents,
            'traveller': traveller,
            'capture_fresh': capture_fresh,
            'who': copy.deepcopy(who),
            'audit': [],
            'expires_at': time.monotonic() + TTL_SECONDS,
        }

def get(case_id, owner_sid=None):
    with LOCK:
        _purge_expired()
        item = CASES.get(case_id)
        if not item or (owner_sid is not None and item['owner_sid'] != owner_sid):
            return None
        item['expires_at'] = time.monotonic() + TTL_SECONDS
        return item

def persist(case_id, payload, status=None):
    with LOCK:
        item = CASES.get(case_id)
        if not item:
            raise KeyError('Session-scoped case expired or was deleted')
        item['payload'] = copy.deepcopy(payload)
        if status:
            item['payload']['status'] = status
        item['expires_at'] = time.monotonic() + TTL_SECONDS

def append_event(case_id, action, who, snapshot):
    with LOCK:
        item = CASES.get(case_id)
        if not item:
            return
        previous = item['audit'][-1]['record_hash'] if item['audit'] else '0' * 64
        stamp = now()
        seq = int(time.time_ns())
        evidence = minimize_snapshot(snapshot)
        body = {'seq': seq, 'created_at': stamp, 'case_id': case_id, 'action': action,
                'officer': who['sub'], 'role': who['role'], 'snapshot': evidence,
                'previous_hash': previous}
        body['record_hash'] = hash_record(body)
        body['id'] = str(uuid.uuid4())
        item['audit'].append(body)

def list_cases(owner_sid):
    with LOCK:
        _purge_expired()
        return [copy.deepcopy(v['payload']) for v in CASES.values() if v['owner_sid'] == owner_sid]

def list_audit(owner_sid):
    with LOCK:
        _purge_expired()
        rows = [copy.deepcopy(row) for v in CASES.values() if v['owner_sid'] == owner_sid for row in v['audit']]
        return sorted(rows, key=lambda row: row['created_at'], reverse=True)

def remove(case_id, owner_sid=None):
    with LOCK:
        item = CASES.get(case_id)
        if not item or (owner_sid is not None and item['owner_sid'] != owner_sid):
            return False
        del CASES[case_id]
        return True
