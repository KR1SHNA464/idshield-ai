"""One Windows launcher for the engine, LAN access and an optional HTTPS tunnel."""
import os,sys,time,socket,threading,webbrowser,urllib.request,json,logging,subprocess,re
from pathlib import Path

def local_ip():
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as probe:
            probe.connect(('8.8.8.8',80));return probe.getsockname()[0]
    except OSError:
        try:return socket.gethostbyname(socket.gethostname())
        except OSError:return '127.0.0.1'

def launch():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
    os.environ.setdefault('FRONTEND_DIR',str(root/'desktop-dist'))
    os.environ.setdefault('IDSHIELD_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'IDShieldAI-LivePrototype'))
    os.environ.setdefault('FACE_MODEL_DIR',str(root/'backend'/'models'))
    os.environ.setdefault('IDSHIELD_ALLOW_TUNNEL','1')
    data=Path(os.environ['IDSHIELD_DATA_DIR']);data.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=data/'launcher.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    with socket.socket() as s:s.bind(('0.0.0.0',0));port=s.getsockname()[1]
    import uvicorn
    from backend.app.main import app
    config=uvicorn.Config(app,host='0.0.0.0',port=port,log_config=None,access_log=False)
    server=uvicorn.Server(config);server_thread=threading.Thread(target=server.run,daemon=True);server_thread.start()
    browser_url=f'http://127.0.0.1:{port}/';lan_url=f'http://{local_ip()}:{port}/'
    deadline=time.time()+90
    while not server.started and server_thread.is_alive() and time.time()<deadline:time.sleep(.1)
    if not server.started:raise RuntimeError('Engine did not start. See '+str(data/'launcher.log'))
    if '--smoke-test' in sys.argv:
        session=urllib.request.Request(browser_url+'api/session',data=b'{"role":"officer","password":"officer-demo"}',headers={'Content-Type':'application/json'})
        token=json.load(urllib.request.urlopen(session))['data']['token'];headers={'Authorization':'Bearer '+token}
        response=json.load(urllib.request.urlopen(urllib.request.Request(browser_url+'api/bootstrap?include_seeded=true',headers=headers)))
        assert len(response['data']['cases'])>=10;assert urllib.request.urlopen(browser_url).status==200;assert response['data']['face_models_ready']
        sample_req=urllib.request.Request(browser_url+'api/samples/run',data=b'{"index":1}',headers={'Content-Type':'application/json',**headers});sample_id=json.load(urllib.request.urlopen(sample_req))['data']['id']
        deadline=time.time()+150
        while time.time()<deadline:
            case=json.load(urllib.request.urlopen(urllib.request.Request(browser_url+'api/cases/'+sample_id,headers=headers)))['data']
            if case['status'] not in ('Processing','Pending'):break
            time.sleep(.5)
        assert case['status']=='In review',case.get('error',case['status']);assert case['documents'][0]['fields']['name']=='MIRA SEN';assert all(c['valid'] for c in case['documents'][0]['mrz']['checks'])
        report={'ok':True,'seeded_cases':len(response['data']['cases']),'database':response['data']['database'],'ocr':response['data']['ocr'],'face':response['data']['face'],'packaged_ocr':'MIRA SEN extracted from generated image','mrz':'All five TD3 check digits validated','pipeline':[s['name']+': '+s['status'] for s in case['stages']]};(data/'smoke-test.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        server.should_exit=True;server_thread.join(10);return
    import tkinter as tk
    window=tk.Tk();window.title('IDShield AI · Live screening launcher');window.geometry('620x500');window.resizable(False,False);window.configure(bg='#102238')
    tunnel_process=[None];tunnel_url=tk.StringVar(value='Starting a fresh public HTTPS link…');status=tk.StringVar(value='Local engine ready · starting direct access');closing=threading.Event();retry_count=[0];public_opened=[False]
    cloudflared=root/'cloudflared.exe'
    def copy(value):window.clipboard_clear();window.clipboard_append(value);status.set('Link copied')
    def start_tunnel():
        if tunnel_process[0] is not None and tunnel_process[0].poll() is None:return
        if not cloudflared.exists():status.set('Tunnel component is unavailable in this build.');return
        status.set('Starting temporary HTTPS tunnel…');tunnel_url.set('Waiting for Cloudflare Quick Tunnel URL…')
        def verify(link):
            for _ in range(15):
                if closing.is_set():return
                try:
                    if urllib.request.urlopen(link+'/',timeout=5).status==200:
                        def ready():
                            tunnel_url.set(link);copy(link)
                            if not public_opened[0]:webbrowser.open(link);public_opened[0]=True
                            status.set('Direct live dashboard opened · no connection step · keep this window open')
                        window.after(0,ready);return
                except Exception:time.sleep(1)
            window.after(0,lambda:(tunnel_url.set(link),status.set('Link created; allow a few seconds and retry if it is still warming up.')))
        def worker():
            try:
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
                process=subprocess.Popen([str(cloudflared),'tunnel','--url',browser_url,'--no-autoupdate','--protocol','http2'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=flags);tunnel_process[0]=process
                for line in process.stdout or []:
                    logging.info('tunnel %s',line.rstrip());match=re.search(r'https://[a-z0-9-]+\.trycloudflare\.com',line)
                    if match:
                        link=match.group(0);window.after(0,lambda u=link:tunnel_url.set(u+' · checking…'));threading.Thread(target=verify,args=(link,),daemon=True).start()
                process.wait()
                tunnel_process[0]=None
                if not closing.is_set() and retry_count[0]<2:
                    retry_count[0]+=1;window.after(0,lambda:status.set('Public link stopped · creating a fresh one…'));window.after(1500,start_tunnel)
                elif process.returncode and 'trycloudflare.com' not in tunnel_url.get():window.after(0,lambda:status.set('Tunnel could not start; local and LAN links still work.'))
            except Exception as exc:logging.exception('Tunnel failed');window.after(0,lambda:status.set('Tunnel could not start; see launcher.log.'))
        threading.Thread(target=worker,daemon=True).start()
    def restart_tunnel():
        retry_count[0]=0;public_opened[0]=False
        if tunnel_process[0] is not None and tunnel_process[0].poll() is None:tunnel_process[0].terminate()
        else:start_tunnel()
    tk.Label(window,text='IDShield AI',bg='#102238',fg='#62d3bb',font=('Segoe UI',24,'bold')).pack(pady=(22,3))
    tk.Label(window,text='Local identity and document risk screening',bg='#102238',fg='#e4eef3',font=('Segoe UI',11)).pack()
    tk.Label(window,text='NO LIVE GOVERNMENT DATABASE INTEGRATION\nALL VERIFICATION RUNS LOCALLY WITHIN THIS APP',bg='#102238',fg='#9cb1c3',font=('Segoe UI',9,'bold'),justify='center').pack(pady=12)
    tk.Button(window,text='Open direct live dashboard',command=lambda:webbrowser.open(tunnel_url.get()) if tunnel_url.get().startswith('https://') and ' · ' not in tunnel_url.get() else start_tunnel(),bg='#178c79',fg='white',font=('Segoe UI',11,'bold'),relief='flat',padx=18,pady=8).pack()
    links=tk.Frame(window,bg='#102238');links.pack(fill='x',padx=35,pady=14)
    for title,value in [('This computer',browser_url),('Same Wi-Fi / LAN',lan_url)]:
        row=tk.Frame(links,bg='#172f49');row.pack(fill='x',pady=3);tk.Label(row,text=title,width=17,anchor='w',bg='#172f49',fg='#9cb1c3',font=('Segoe UI',9,'bold')).pack(side='left',padx=10,pady=8);tk.Label(row,text=value,anchor='w',bg='#172f49',fg='#e4eef3',font=('Consolas',9)).pack(side='left',fill='x',expand=True);tk.Button(row,text='Copy',command=lambda u=value:copy(u),bg='#26445f',fg='white',relief='flat').pack(side='right',padx=7)
    tunnel=tk.Frame(window,bg='#172f49');tunnel.pack(fill='x',padx=35,pady=3);tk.Label(tunnel,text='Public HTTPS',width=17,anchor='w',bg='#172f49',fg='#9cb1c3',font=('Segoe UI',9,'bold')).pack(side='left',padx=10,pady=8);tk.Label(tunnel,textvariable=tunnel_url,anchor='w',bg='#172f49',fg='#e4eef3',font=('Segoe UI',8),wraplength=285,justify='left').pack(side='left',fill='x',expand=True);tk.Button(tunnel,text='Restart',command=restart_tunnel,bg='#26445f',fg='white',relief='flat').pack(side='right',padx=7)
    public_actions=tk.Frame(window,bg='#102238');public_actions.pack();tk.Button(public_actions,text='Open public link',command=lambda:webbrowser.open(tunnel_url.get()) if tunnel_url.get().startswith('https://') else start_tunnel(),bg='#102238',fg='#62d3bb',relief='flat').pack(side='left',padx=8);tk.Button(public_actions,text='Copy public link',command=lambda:copy(tunnel_url.get()) if tunnel_url.get().startswith('https://') else start_tunnel(),bg='#102238',fg='#62d3bb',relief='flat').pack(side='left',padx=8)
    tk.Label(window,textvariable=status,bg='#102238',fg='#d6b971',font=('Segoe UI',9)).pack(pady=(6,2));tk.Label(window,text='The direct live page opens automatically. No engine URL needs to be pasted.\nThe temporary link works while this window stays open; share only with consenting participants.',bg='#102238',fg='#839caf',font=('Segoe UI',8),justify='center').pack()
    def close():
        closing.set()
        if tunnel_process[0] is not None:tunnel_process[0].terminate()
        server.should_exit=True;window.destroy()
    window.protocol('WM_DELETE_WINDOW',close);window.after(600,start_tunnel);window.mainloop();server_thread.join(8)

if __name__=='__main__':
    try:launch()
    except Exception as exc:
        try:
            data=Path(os.environ.get('IDSHIELD_DATA_DIR','.'));data.mkdir(parents=True,exist_ok=True);(data/'launch-error.txt').write_text(str(exc),encoding='utf8')
            if '--smoke-test' not in sys.argv:
                import tkinter.messagebox as messagebox;messagebox.showerror('IDShield AI',str(exc))
        finally:sys.exit(1)
