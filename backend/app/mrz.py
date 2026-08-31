"""ICAO 9303 TD1/TD2/TD3 parsing. Fictional UTO specimens only in seeds.
Checksums validate transcription consistency, never document authenticity.
"""
import re

def check_digit(value: str) -> str:
    values = {str(i): i for i in range(10)} | {chr(65+i): 10+i for i in range(26)} | {'<': 0}
    if any(c not in values for c in value):
        raise ValueError('MRZ permits A-Z, 0-9 and < only')
    return str(sum(values[c] * (7, 3, 1)[i % 3] for i, c in enumerate(value)) % 10)

def parse_mrz(raw: str | list[str]) -> dict:
    lines = raw.splitlines() if isinstance(raw, str) else raw
    lines = [re.sub(r'\s', '', l.upper()) for l in lines if l.strip()]
    if any(re.search(r'[^A-Z0-9<]', l) for l in lines):
        return {'format': 'unreadable', 'fields': {}, 'checks': [], 'lines': lines, 'error': 'Unsupported MRZ characters; officer correction required.'}
    checks = []
    def add(name, value, actual):
        expected = check_digit(value)
        checks.append({'field': name, 'input': value, 'expected': expected, 'actual': actual,
                       'valid': actual == expected or (name == 'Optional data' and actual == '<' and set(value) == {'<'}),
                       'rule': 'ICAO 9303: repeating 7, 3, 1 weights; sum modulo 10'})
    if len(lines) == 2 and all(len(l) == 44 for l in lines):
        kind = 'TD3'; a,b = lines
        names = a[5:44]; number=b[:9]; dob=b[13:19]; expiry=b[21:27]; nation=b[10:13]; sex=b[20]
        add('Document number', number, b[9]); add('Date of birth',dob,b[19]); add('Expiry date',expiry,b[27])
        add('Optional data',b[28:42],b[42]); add('Composite',b[:10]+b[13:20]+b[21:43],b[43])
    elif len(lines) == 2 and all(len(l) == 36 for l in lines):
        kind = 'TD2'; a,b = lines
        names=a[5:]; number=b[:9]; dob=b[13:19]; expiry=b[21:27]; nation=b[10:13]; sex=b[20]
        add('Document number',number,b[9]); add('Date of birth',dob,b[19]); add('Expiry date',expiry,b[27]); add('Composite',b[:10]+b[13:20]+b[21:35],b[35])
    elif len(lines) == 3 and all(len(l) == 30 for l in lines):
        kind = 'TD1'; a,b,names=lines
        number=a[5:14]; dob=b[:6]; expiry=b[8:14]; nation=b[15:18]; sex=b[7]
        add('Document number',number,a[14]); add('Date of birth',dob,b[6]); add('Expiry date',expiry,b[14]); add('Composite',a[5:]+b[:7]+b[8:15]+b[18:29],b[29])
    else:
        return {'format':'unreadable','fields':{},'checks':[],'lines':lines,'error':'Expected TD3 (2×44), TD2 (2×36) or TD1 (3×30). No checks assumed valid.'}
    parts=names.split('<<',1)
    surname=parts[0].replace('<',' ').strip(); given=parts[1].replace('<',' ').strip() if len(parts)>1 else ''
    return {'format':kind,'lines':lines,'fields':{'name':f'{given} {surname}'.strip(),'document_number':number.replace('<',''),'dob':dob,'expiry':expiry,'nationality':nation,'sex':sex},'checks':checks,'error':None}

def make_td3(name, number, dob='950314', expiry='310314', invalid=False):
    parts=name.upper().split(); names=parts[-1]+'<<'+'<'.join(parts[:-1])
    a=('P<UTO'+names).ljust(44,'<')[:44]
    optional='SPECIMEN'.ljust(14,'<')
    digit=check_digit(number)
    if invalid: digit=str((int(digit)+1)%10)
    b=number+digit+'UTO'+dob+check_digit(dob)+'X'+expiry+check_digit(expiry)+optional+check_digit(optional)
    # Deliberately invalid document digit also invalidates the composite of the clean source.
    composite=check_digit(b[:10]+b[13:20]+b[21:43])
    if invalid: composite=str((int(composite)+3)%10)
    return [a,b+composite]
