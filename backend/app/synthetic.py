"""Self-generated specimen documents. No real identities or document images.
Seed analyses are explicitly labeled controlled fixtures; live sample reruns use OCR/CV.
"""
import io, base64, random, math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from .mrz import make_td3, parse_mrz

NAMES=['Aarav Mehta','Mira Sen','Dev Khanna','Leela Rao','Nikhil Das','Zoya Nair','Ishan Roy','Tara Bose','Kabir Sethi','Anika Shah','Riya Menon','Arjun Kale','Sana Kapur','Vihaan Patel','Noor Jha','Aditi Vora','Rehan Dutt','Diya Suri','Kiran Bediya','Samar Lal']
SCENARIOS=['combined','clean','face','fields','clean','identity','checksum','forensics','blur','clean','clean','fields','clean','security','clean','clean','checksum','clean','clean','clean']
LABELS={'combined':'Checksum failure + photo splice','clean':'Consistent synthetic specimen','face':'Low portrait similarity','fields':'Visible / MRZ field mismatch','identity':'Same portrait, different identity','checksum':'Invalid MRZ check digits','forensics':'Font-spacing + clone proxy','blur':'Blurred capture — recapture needed','security':'Blank security-feature region'}

def font(size,mono=False):
    names=['DejaVuSansMono.ttf','C:/Windows/Fonts/consola.ttf'] if mono else ['DejaVuSans.ttf','C:/Windows/Fonts/arial.ttf']
    for p in names:
        try:return ImageFont.truetype(p,size)
        except OSError:pass
    return ImageFont.load_default(size=size)

def portrait(seed):
    # Intentionally illustrated, non-biometric specimen; NEVER represented as a real human photo.
    rng=random.Random(seed); im=Image.new('RGB',(220,260),(205,221,220)); d=ImageDraw.Draw(im)
    color=(rng.randint(70,130),rng.randint(85,140),rng.randint(105,160))
    d.rectangle((0,0,220,260),fill=(225,235,231))
    for _ in range(30):
        x=rng.randrange(220);y=rng.randrange(260);d.line((x,y,x+20,y+30),fill=(195,211,208),width=2)
    skin=(rng.randint(170,220),rng.randint(140,185),rng.randint(110,155))
    d.ellipse((20,170,200,360),fill=color);d.rounded_rectangle((90,139,130,201),radius=10,fill=skin)
    d.ellipse((55,38,166,177),fill=skin);d.pieslice((48,22,174,126),180,360,fill=(46,50,55))
    d.ellipse((77,91,84,97),fill=(40,43,43));d.ellipse((137,91,144,97),fill=(40,43,43));d.arc((92,112,129,142),0,180,fill=(86,64,59),width=3)
    d.rectangle((0,233,220,260),fill=(16,34,56));d.text((14,239),'SYNTHETIC AVATAR',font=font(16),fill='white')
    return im

def png_bytes(im):
    b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
def data_uri(im):return 'data:image/png;base64,'+base64.b64encode(png_bytes(im)).decode()

def specimen(index=0,scenario=None):
    name=NAMES[index%20];scenario=scenario or SCENARIOS[index%20];number=f'D{index+1:08d}'
    mrz=make_td3(name,number,invalid=scenario in ('combined','checksum'))
    fields={'name':name.upper(),'dob':'950314','document_number':number,'nationality':'UTO','issue':'210314','expiry':'310314','sex':'X'}
    if scenario=='fields': fields['dob']='960314'
    im=Image.new('RGB',(1200,760),'#eff3e8');d=ImageDraw.Draw(im)
    d.rectangle((0,0,1200,88),fill='#153a48');d.text((34,22),'UTOPIA / SPECIMEN PASSPORT',font=font(30),fill='#e4efe7');d.text((830,32),'NOT VALID FOR TRAVEL',font=font(18),fill='#9bdbc8')
    seed=0 if scenario=='identity' else index
    photo=portrait(seed);im.paste(photo,(45,156))
    d.text((45,434),'GENERATED PORTRAIT',font=font(16),fill='#829797')
    specs=[('NAME',fields['name']),('DATE OF BIRTH',fields['dob']),('DOCUMENT NO.',number),('NATIONALITY','UTO'),('DATE OF ISSUE','210314'),('DATE OF EXPIRY','310314')]
    for n,(label,value) in enumerate(specs):
        y=138+n*57;d.text((320,y),label+':',font=font(20),fill='#627578');d.text((595,y-2),value,font=font(25),fill='#163b45')
    d.rectangle((960,350,1135,480),outline='#9bb8a8',width=2)
    if scenario!='security':
        for k in range(8):d.ellipse((980+k*4,362+k*4,1115-k*4,468-k*4),outline='#7fa497',width=2)
        d.text((985,411),'DEMO',font=font(24),fill='#668c7d')
    if scenario in ('combined','forensics'):
        d.rectangle((39,151,270,423),outline='#536474',width=8)
    if scenario=='forensics':
        d.rectangle((590,135,900,175),fill='#e6e9e1');d.text((595,139),'D E V  K H A N N A',font=font(23),fill='#243247')
    d.text((35,521),'SYNTHETIC DATA - DEMO ONLY - NO GOVERNMENT INTEGRATION',font=font(21),fill='#8a7460')
    d.rectangle((25,566,1175,710),fill='#fcfdf8',outline='#c8d3c8')
    # Fixed-width, generously spaced glyphs support OCR and visually inspectable check digits.
    for j,line in enumerate(mrz):
        for k,c in enumerate(line):d.text((37+k*25,580+j*58),c,font=font(37,True),fill='#273c40')
    d.text((39,725),'FICTIONAL UTO ISSUER · MATHEMATICALLY TESTABLE SPECIMEN CHECK DIGITS',font=font(14),fill='#82938b')
    if scenario=='blur':im=im.resize((360,228)).filter(ImageFilter.GaussianBlur(3)).resize((1200,760))
    return {'name':name,'scenario':scenario,'fields':fields,'mrz':mrz,'image':im,'portrait':photo,'number':number}

def make_signal(id,stage,title,detail,points=0,confidence=90,region=None,method='Controlled synthetic fixture'):
    return {'id':id,'stage':stage,'title':title,'detail':detail,'points':points,'confidence':confidence,'flagged':points>0,'method':method,'region':region}

def fixture_case(index):
    f=specimen(index);sc=f['scenario'];checks=parse_mrz(f['mrz']);face=61 if sc=='face' else 97
    signals=[make_signal('quality','Intake','Capture quality', 'Blur, resolution and lighting are acceptable.',0,96),
      make_signal('mrz','Extraction','MRZ check digits','All synthetic check digits are consistent. This does not authenticate the document.',0,100,[3,76,94,17]),
      make_signal('fields','Extraction','Visible fields vs. MRZ','Name, date of birth, document number and expiry are consistent.',0,94,[25,16,53,49]),
      make_signal('font','Forensics','Font / spacing consistency','No injected spacing anomaly in this fixture.',0,79,[48,17,29,8]),
      make_signal('clone','Forensics','Copy-move / ELA proxy','No injected compression-residual anomaly in this fixture.',0,72,[42,16,40,42]),
      make_signal('photo','Forensics','Photo boundary continuity','No injected photo boundary anomaly in this fixture.',0,84,[3,19,20,38]),
      make_signal('security','Forensics','Security-region texture proxy','Expected specimen texture is present. This is not hologram verification.',0,68,[80,46,15,18]),
      make_signal('face','Intelligence','Portrait similarity',f'{face}% visual embedding similarity; illustrative 80% threshold. Synthetic portrait proxy, not validated biometrics.',0,75,[3,19,20,38]),
      make_signal('liveness','Intelligence','Liveness proxy','Seeded specimen: no live capture. Liveness is not assessed.',4,0),
      make_signal('identity','Intelligence','Identity consistency','No contradictory synthetic identity linked in this fixture.',0,90)]
    by={s['id']:s for s in signals}
    def flag(id,points,detail):by[id].update(points=points,flagged=True,detail=detail)
    if sc in ('combined','checksum'):flag('mrz',30,'Document-number and composite check digits fail. Expand the MRZ evidence to inspect expected vs. observed values.')
    if sc=='combined':flag('photo',20,'Injected rectangular photo boundary creates an edge discontinuity, consistent with the photo-splice test scenario.');flag('clone',12,'Injected edit creates a local compression-residual difference. ELA proxy is not proof of tampering.')
    if sc=='fields':flag('fields',26,'Visible DOB 960314 differs from MRZ DOB 950314. Officer must resolve the discrepancy.')
    if sc=='forensics':flag('font',14,'Injected irregular spacing in the name field.');flag('clone',12,'Synthetic edited field produces an ELA-style inconsistency.');flag('photo',20,'Injected photo boundary is discontinuous.')
    if sc=='security':flag('security',12,'The expected specimen security region is blank. A texture check cannot authenticate holograms.')
    if sc=='face':flag('face',35,'Portrait similarity is 61%, below the illustrative 80% threshold. This is a controlled fixture, not a calibrated biometric probability.')
    if sc=='identity':flag('identity',28,'The same synthetic portrait is linked to Aarav Mehta (IDS-2026-0020) and Zoya Nair. Names conflict.');flag('fields',26,'A linked synthetic record has a conflicting name.')
    if sc=='blur':flag('quality',25,'Blurred, downsampled capture. Processing pauses at Intake; request recapture before OCR.')
    risk=min(100,sum(s['points'] for s in signals));status='Decided' if index in (3,4,9) else ('In review' if index in (0,2,5,6,7) else 'Pending')
    if sc=='blur':status='Recapture'
    doc={'id':f'doc-{index}-1','label':'Specimen passport','image':f'/demo/passport-{index}.png','fields':f['fields'],'mrz':checks,'quality':{'ok':sc!='blur','blur_variance':8 if sc=='blur' else 328,'width':1200,'height':760,'brightness':204,'overexposed_fraction':0.03},'source':'Synthetic generator ground truth — seeded fixture, not a live OCR result'}
    stages=[{'name':n,'status':('blocked' if j==0 else 'waiting') if sc=='blur' else 'complete','summary':s} for j,(n,s) in enumerate([('Intake','Capture quality checked'),('Extraction','Structured fields and MRZ checks'),('Forensics','Four independent image proxies'),('Intelligence','Similarity and identity links'),('Decision','Human officer review')])]
    return {'id':f'IDS-2026-{20-index:04d}','name':f['name'],'initials':''.join(x[0] for x in f['name'].split()),'scenario':sc,'scenarioLabel':LABELS[sc],'status':status,'risk':risk,'riskLevel':'High' if risk>=50 else 'Medium' if risk>=25 else 'Low','created_at':f'2026-09-{1 if index<3 else 1:02d}T09:{max(0,42-index*2):02d}:00+05:30','documents':[doc],'signals':signals,'stages':stages,'faceSimilarity':face,'portrait':f'/demo/portrait-{index}.png','comparisonPortrait':f'/demo/portrait-{(index+3)%10 if sc=="face" else (0 if sc=="identity" else index)}.png','decision':{'action':'Approve','officer':'Ananya Sharma','note':'Reviewed all synthetic evidence; recorded for demo.','at':'2026-09-01T09:30:00+05:30'} if status=='Decided' else None,'mode':'Seeded, controlled synthetic scenario','storage':'Seeded synthetic fixture','revision':1}

def export_demo(directory,frontend_data=None):
    import json
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    for pattern in ('passport-*.png','portrait-*.png'):
        for old in directory.glob(pattern):old.unlink()
    cases=[]
    for i in range(10):
        f=specimen(i);f['image'].save(directory/f'passport-{i}.png');f['portrait'].save(directory/f'portrait-{i}.png');cases.append(fixture_case(i))
    (directory/'cases.json').write_text(json.dumps(cases,indent=2),encoding='utf8')
    if frontend_data:Path(frontend_data).write_text(json.dumps(cases,indent=2),encoding='utf8')
    return cases
