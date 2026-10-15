"""One executable, loopback-only server, native folder selection, no Python setup."""
import argparse,json,os,pathlib,queue,sys,threading,time,webbrowser
import uvicorn
from server import Desktop,create_app,VERSION

def state_directory():
 if sys.platform=='darwin':return pathlib.Path.home()/'Library'/'Application Support'/'EP Desktop'
 if os.name=='nt':return pathlib.Path(os.environ.get('LOCALAPPDATA',pathlib.Path.home()))/'EP Desktop'
 return pathlib.Path.home()/'.local'/'share'/'ep-desktop'

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--headless',action='store_true');parser.add_argument('--self-test',action='store_true');parser.add_argument('--state-dir');parser.add_argument('--port',type=int,default=8780);args=parser.parse_args()
 assets=pathlib.Path(getattr(sys,'_MEIPASS',pathlib.Path(__file__).resolve().parent.parent))/'web'
 if args.self_test:
  import tempfile
  from store import Store
  import numpy,nptdms
  with tempfile.TemporaryDirectory() as p:Store(pathlib.Path(p)/'test.db')
  assert (assets/'index.html').is_file()
  print(json.dumps({'ok':True,'version':VERSION,'platform':sys.platform,'numpy':numpy.__version__,'tdms':nptdms.__version__}));return
 requests=queue.Queue();tk=None
 if not args.headless:
  import tkinter as Tk
  from tkinter import filedialog,messagebox
  tk=Tk.Tk();tk.withdraw()
  def poll():
   try:
    kind,reply=requests.get_nowait();tk.attributes('-topmost',True)
    p=filedialog.askdirectory(parent=tk,title='Choose your local TDMS folder') if kind=='folder' else filedialog.askopenfilename(parent=tk,title='Choose a coordinator-provided dataset profile',filetypes=[('Dataset profile','*.json')]);reply.put(p);tk.attributes('-topmost',False)
   except queue.Empty:pass
   tk.after(100,poll)
  tk.after(100,poll)
 def picker(kind):
  q=queue.Queue();requests.put((kind,q));return q.get()
 state=pathlib.Path(args.state_dir) if args.state_dir else state_directory();state.mkdir(parents=True,exist_ok=True);os.chmod(state,0o700)
 d=Desktop(state,assets,picker if tk else None,args.port);app=create_app(d)
 config=uvicorn.Config(app,host='127.0.0.1',port=args.port,log_level='warning',access_log=False);server=uvicorn.Server(config)
 def run():server.run()
 worker=threading.Thread(target=run,daemon=True);worker.start()
 for _ in range(100):
  if server.started:break
  if not worker.is_alive():raise SystemExit('Could not start: the port may already be in use. Existing tools were not stopped.')
  time.sleep(.05)
 if not server.started:raise SystemExit('Local server did not start')
 url=f'http://127.0.0.1:{args.port}/#session={d.secret}'
 # Private session URL is written only to the private local state directory for recovery/testing.
 (state/'launch.json').write_text(json.dumps({'url':url,'port':args.port,'pid':os.getpid(),'version':VERSION}));os.chmod(state/'launch.json',0o600)
 if tk:
  webbrowser.open(url)
  # A small app window provides an explicit shutdown action.
  tk.deiconify();tk.title('EP Desktop');tk.geometry('390x150');tk.attributes('-topmost',False)
  Tk.Label(tk,text='EP Desktop is running locally.\nKeep this window open while annotating.',padx=15,pady=15).pack()
  Tk.Button(tk,text='Open annotation window',command=lambda:webbrowser.open(url)).pack()
  def close():server.should_exit=True;tk.destroy()
  Tk.Button(tk,text='Quit EP Desktop',command=close).pack();tk.protocol('WM_DELETE_WINDOW',close);tk.mainloop();worker.join(timeout=5)
 else:
  print('EP Desktop listening on loopback port '+str(args.port),flush=True)
  try:worker.join()
  except KeyboardInterrupt:server.should_exit=True;worker.join(timeout=5)
if __name__=='__main__':main()
