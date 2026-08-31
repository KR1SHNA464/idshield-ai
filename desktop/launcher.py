"""Single Windows launcher; Python/OCR/React bundled by PyInstaller, no terminal required."""
import os,sys,time,socket,threading,webbrowser,urllib.request,json,logging
from pathlib import Path

def launch():
    frozen=getattr(sys,'frozen',False)
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    os.environ.setdefault('FRONTEND_DIR',str(root/'desktop-dist'))
    os.environ.setdefault('IDSHIELD_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'IDShieldAI'))
    data=Path(os.environ['IDSHIELD_DATA_DIR']);data.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=data/'launcher.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    import uvicorn
    from backend.app.main import app
    config=uvicorn.Config(app,host='127.0.0.1',port=port,log_config=None,access_log=False)
    server=uvicorn.Server(config)
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    url=f'http://127.0.0.1:{port}/'
    deadline=time.time()+90
    while not server.started and thread.is_alive() and time.time()<deadline:time.sleep(.1)
    if not server.started:raise RuntimeError('Engine did not start. See '+str(data/'launcher.log'))
    if '--smoke-test' in sys.argv:
        session=urllib.request.Request(url+'api/session',data=b'{"role":"officer","password":"officer-demo"}',headers={'Content-Type':'application/json'})
        token=json.load(urllib.request.urlopen(session))['data']['token']
        req=urllib.request.Request(url+'api/bootstrap',headers={'Authorization':'Bearer '+token})
        response=json.load(urllib.request.urlopen(req))
        assert len(response['data']['cases'])>=20
        assert urllib.request.urlopen(url).status==200
        sample_req=urllib.request.Request(url+'api/samples/run',data=b'{"index":1}',headers={'Content-Type':'application/json','Authorization':'Bearer '+token})
        sample_id=json.load(urllib.request.urlopen(sample_req))['data']['id']
        deadline=time.time()+150
        while time.time()<deadline:
            req=urllib.request.Request(url+'api/cases/'+sample_id,headers={'Authorization':'Bearer '+token})
            case=json.load(urllib.request.urlopen(req))['data']
            if case['status'] not in ('Processing','Pending'):break
            time.sleep(.5)
        assert case['status']=='In review',case.get('error',case['status'])
        assert case['documents'][0]['fields']['name']=='MIRA SEN'
        assert all(c['valid'] for c in case['documents'][0]['mrz']['checks'])
        report={'ok':True,'seeded_cases':len(response['data']['cases']),'database':response['data']['database'],'ocr':response['data']['ocr'],'packaged_ocr':'MIRA SEN extracted from generated image','mrz':'All five TD3 check digits validated','pipeline':[s['name']+': '+s['status'] for s in case['stages']]}
        (data/'smoke-test.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        server.should_exit=True;thread.join(10);return
    import tkinter as tk
    window=tk.Tk();window.title('IDShield AI · Demo launcher');window.geometry('450x260');window.resizable(False,False);window.configure(bg='#102238')
    tk.Label(window,text='IDShield AI',bg='#102238',fg='#62d3bb',font=('Segoe UI',23,'bold')).pack(pady=(24,5))
    tk.Label(window,text='Your local screening engine is ready.',bg='#102238',fg='#e4eef3',font=('Segoe UI',11)).pack(pady=7)
    tk.Label(window,text='SYNTHETIC DATA — DEMO ONLY\nHuman officers make every final decision.',bg='#102238',fg='#9cb1c3',font=('Segoe UI',9),justify='center').pack(pady=7)
    tk.Button(window,text='Open officer dashboard',command=lambda:webbrowser.open(url),bg='#178c79',fg='white',font=('Segoe UI',11),relief='flat',padx=15,pady=8).pack(pady=10)
    tk.Label(window,text='Keep this launcher open while using the dashboard.',bg='#102238',fg='#839caf',font=('Segoe UI',8)).pack()
    def close():server.should_exit=True;window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);webbrowser.open(url);window.mainloop();thread.join(8)

if __name__=='__main__':
    try:launch()
    except Exception as exc:
        try:
            data=Path(os.environ.get('IDSHIELD_DATA_DIR','.'));data.mkdir(parents=True,exist_ok=True);(data/'launch-error.txt').write_text(str(exc),encoding='utf8')
            if '--smoke-test' not in sys.argv:
                import tkinter.messagebox as messagebox
                messagebox.showerror('IDShield AI',str(exc))
        finally:sys.exit(1)
