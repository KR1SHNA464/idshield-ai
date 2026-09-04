"""One Windows launcher for the engine, LAN access and a self-healing HTTPS tunnel."""
import os,sys,time,socket,threading,webbrowser,urllib.request,json,logging,subprocess,re,ctypes,shutil
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
    if str(root) not in sys.path:sys.path.insert(0,str(root))
    os.environ.setdefault('FRONTEND_DIR',str(root/'desktop-dist'))
    os.environ.setdefault('IDSHIELD_DATA_DIR',str(Path(os.environ.get('LOCALAPPDATA',Path.home()))/'IDShieldAI-LivePrototype'))
    os.environ.setdefault('FACE_MODEL_DIR',str(root/'backend'/'models'))
    os.environ.setdefault('IDSHIELD_ALLOW_TUNNEL','1')
    data=Path(os.environ['IDSHIELD_DATA_DIR']);data.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(filename=data/'launcher.log',level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    smoke_test='--smoke-test' in sys.argv;stable_port=8765;mutex_handle=None;window_title='IDShield AI · Stable live screening launcher'
    if not smoke_test and os.name=='nt':
        kernel32=ctypes.WinDLL('kernel32',use_last_error=True);kernel32.CreateMutexW.argtypes=[ctypes.c_void_p,ctypes.c_bool,ctypes.c_wchar_p];kernel32.CreateMutexW.restype=ctypes.c_void_p;kernel32.CloseHandle.argtypes=[ctypes.c_void_p]
        mutex_handle=kernel32.CreateMutexW(None,False,'Local\\IDShieldAI_LiveScreening_8765')
        if not mutex_handle:raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error()==183:
            kernel32.CloseHandle(mutex_handle);mutex_handle=None
            user32=ctypes.WinDLL('user32',use_last_error=True);user32.FindWindowW.argtypes=[ctypes.c_wchar_p,ctypes.c_wchar_p];user32.FindWindowW.restype=ctypes.c_void_p
            existing_window=user32.FindWindowW(None,window_title)
            if existing_window:user32.ShowWindow(existing_window,9);user32.SetForegroundWindow(existing_window)
            existing_url=f'http://127.0.0.1:{stable_port}/'
            for _ in range(90):
                try:
                    if urllib.request.urlopen(existing_url,timeout=2).status==200:webbrowser.open(existing_url);return
                except Exception:time.sleep(.25)
            raise RuntimeError('IDShield AI is already starting. Wait a few seconds, then open '+existing_url)
    if smoke_test:
        with socket.socket() as s:s.bind(('0.0.0.0',0));port=s.getsockname()[1]
    else:port=stable_port
    import uvicorn
    from backend.app.main import app
    config=uvicorn.Config(app,host='0.0.0.0',port=port,log_config=None,access_log=False)
    server=uvicorn.Server(config);server_thread=threading.Thread(target=server.run,daemon=True);server_thread.start()
    browser_url=f'http://127.0.0.1:{port}/';lan_url=f'http://{local_ip()}:{port}/'
    deadline=time.time()+90
    while not server.started and server_thread.is_alive() and time.time()<deadline:time.sleep(.1)
    if not server.started:raise RuntimeError('Engine did not start. See '+str(data/'launcher.log'))
    if smoke_test:
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
    window=tk.Tk();window.title(window_title);window.geometry('620x540');window.resizable(False,False);window.configure(bg='#102238')
    tunnel_process=[None];tunnel_url=tk.StringVar(value='Creating optional public HTTPS link…');status=tk.StringVar(value='Stable local dashboard ready · creating remote access');closing=threading.Event();retry_count=[0]
    cloudflared=root/'cloudflared.exe'
    def copy(value):window.clipboard_clear();window.clipboard_append(value);status.set('Link copied')
    def start_tunnel():
        if tunnel_process[0] is not None and tunnel_process[0].poll() is None:return
        ssh_path=shutil.which('ssh.exe') or shutil.which('ssh');use_ssh=bool(ssh_path) and retry_count[0]<2
        if use_ssh:
            known_hosts=data/'localhost-run-known-hosts';args=[ssh_path,'-T','-o','StrictHostKeyChecking=accept-new','-o',f'UserKnownHostsFile={known_hosts}','-o','ExitOnForwardFailure=yes','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-R',f'80:127.0.0.1:{port}','nokey@localhost.run'];link_pattern=r'https://[a-z0-9-]+\.lhr\.life';provider='localhost.run'
        elif cloudflared.exists():
            args=[str(cloudflared),'tunnel','--url',browser_url,'--no-autoupdate','--protocol','auto'];link_pattern=r'https://[a-z0-9-]+\.trycloudflare\.com';provider='Cloudflare'
        else:status.set('No public-tunnel component is available; local and LAN links still work.');return
        status.set(f'Starting mobile HTTPS through {provider}…');tunnel_url.set(f'Waiting for {provider} mobile link…')
        def verify(link,process):
            for _ in range(15):
                if closing.is_set():return
                try:
                    if urllib.request.urlopen(link+'/',timeout=5).status==200:
                        def ready():
                            tunnel_url.set(link);copy(link);retry_count[0]=0;status.set('Public link ready and copied · local dashboard stays stable')
                        window.after(0,ready);break
                except Exception:time.sleep(1)
            else:
                window.after(0,lambda:status.set('Mobile link did not become reachable · replacing it…'))
                try:process.terminate()
                except Exception:pass
                return
            failures=0
            while not closing.wait(15):
                if tunnel_process[0] is not process or process.poll() is not None:return
                try:
                    if urllib.request.urlopen(link+'/',timeout=6).status==200:failures=0;continue
                except Exception:failures+=1
                if failures>=3:
                    window.after(0,lambda:status.set('Public link expired · replacing it automatically…'))
                    try:process.terminate()
                    except Exception:pass
                    return
        def worker():
            try:
                flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
                process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,creationflags=flags);tunnel_process[0]=process
                for line in process.stdout or []:
                    if '\x1b' not in line:logging.info('%s tunnel %s',provider,line.rstrip())
                    match=re.search(link_pattern,line)
                    if match:
                        link=match.group(0);window.after(0,lambda u=link:tunnel_url.set(u+' · checking…'));threading.Thread(target=verify,args=(link,process),daemon=True).start()
                process.wait()
                tunnel_process[0]=None
                if not closing.is_set() and retry_count[0]<4:
                    retry_count[0]+=1;window.after(0,lambda:status.set('Public link stopped · creating a fresh one…'));window.after(1500,start_tunnel)
                elif process.returncode and not tunnel_url.get().startswith('https://'):window.after(0,lambda:status.set('Mobile tunnel could not start; local and LAN links still work.'))
            except Exception as exc:logging.exception('Tunnel failed');window.after(0,lambda:status.set('Tunnel could not start; see launcher.log.'))
        threading.Thread(target=worker,daemon=True).start()
    def restart_tunnel():
        retry_count[0]=0
        if tunnel_process[0] is not None and tunnel_process[0].poll() is None:tunnel_process[0].terminate()
        else:start_tunnel()
    tk.Label(window,text='IDShield AI',bg='#102238',fg='#62d3bb',font=('Segoe UI',24,'bold')).pack(pady=(22,3))
    tk.Label(window,text='Local identity and document risk screening',bg='#102238',fg='#e4eef3',font=('Segoe UI',11)).pack()
    tk.Label(window,text='NO LIVE GOVERNMENT DATABASE INTEGRATION\nALL VERIFICATION RUNS LOCALLY WITHIN THIS APP',bg='#102238',fg='#9cb1c3',font=('Segoe UI',9,'bold'),justify='center').pack(pady=12)
    tk.Button(window,text='Open stable live dashboard',command=lambda:webbrowser.open(browser_url),bg='#178c79',fg='white',font=('Segoe UI',11,'bold'),relief='flat',padx=18,pady=8).pack()
    links=tk.Frame(window,bg='#102238');links.pack(fill='x',padx=35,pady=14)
    for title,value in [('Stable on this PC',browser_url),('Same Wi-Fi / LAN',lan_url)]:
        row=tk.Frame(links,bg='#172f49');row.pack(fill='x',pady=3);tk.Label(row,text=title,width=17,anchor='w',bg='#172f49',fg='#9cb1c3',font=('Segoe UI',9,'bold')).pack(side='left',padx=10,pady=8);tk.Label(row,text=value,anchor='w',bg='#172f49',fg='#e4eef3',font=('Consolas',9)).pack(side='left',fill='x',expand=True);tk.Button(row,text='Copy',command=lambda u=value:copy(u),bg='#26445f',fg='white',relief='flat').pack(side='right',padx=7)
    tunnel=tk.Frame(window,bg='#172f49');tunnel.pack(fill='x',padx=35,pady=3);tk.Label(tunnel,text='Mobile HTTPS',width=17,anchor='w',bg='#172f49',fg='#9cb1c3',font=('Segoe UI',9,'bold')).pack(side='left',padx=10,pady=8);tk.Label(tunnel,textvariable=tunnel_url,anchor='w',bg='#172f49',fg='#e4eef3',font=('Segoe UI',8),wraplength=285,justify='left').pack(side='left',fill='x',expand=True);tk.Button(tunnel,text='Restart',command=restart_tunnel,bg='#26445f',fg='white',relief='flat').pack(side='right',padx=7)
    public_actions=tk.Frame(window,bg='#102238');public_actions.pack();tk.Button(public_actions,text='Open public link',command=lambda:webbrowser.open(tunnel_url.get()) if tunnel_url.get().startswith('https://') else start_tunnel(),bg='#102238',fg='#62d3bb',relief='flat').pack(side='left',padx=8);tk.Button(public_actions,text='Copy public link',command=lambda:copy(tunnel_url.get()) if tunnel_url.get().startswith('https://') else start_tunnel(),bg='#102238',fg='#62d3bb',relief='flat').pack(side='left',padx=8)
    tk.Label(window,textvariable=status,bg='#102238',fg='#d6b971',font=('Segoe UI',9)).pack(pady=(6,2));tk.Label(window,text='Closing X minimizes this launcher and keeps screening online.\nUse Stop engine and exit only when you want both computer and mobile links to stop.',bg='#102238',fg='#839caf',font=('Segoe UI',8),justify='center').pack()
    def shutdown():
        closing.set()
        if tunnel_process[0] is not None:tunnel_process[0].terminate()
        server.should_exit=True;window.destroy()
    def minimize():status.set('Engine remains online · click this taskbar icon to restore');window.iconify()
    tk.Button(window,text='Stop engine and exit',command=shutdown,bg='#102238',fg='#839caf',relief='flat').pack(pady=(3,0))
    window.protocol('WM_DELETE_WINDOW',minimize);window.after(250,lambda:webbrowser.open(browser_url));window.after(600,start_tunnel);window.mainloop();server_thread.join(8)
    if mutex_handle is not None:kernel32.CloseHandle(mutex_handle)

if __name__=='__main__':
    try:launch()
    except Exception as exc:
        try:
            data=Path(os.environ.get('IDSHIELD_DATA_DIR','.'));data.mkdir(parents=True,exist_ok=True);(data/'launch-error.txt').write_text(str(exc),encoding='utf8')
            if '--smoke-test' not in sys.argv:
                import tkinter.messagebox as messagebox;messagebox.showerror('IDShield AI',str(exc))
        finally:sys.exit(1)
