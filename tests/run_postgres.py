"""Run the complete suite against a new Unix-socket-only disposable cluster."""
import os,pathlib,shutil,subprocess,sys,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
bindir=pathlib.Path(os.environ.get('EP_PG_BIN','/opt/homebrew/opt/postgresql@16/bin'))
with tempfile.TemporaryDirectory(prefix='ep-sql-') as temporary:
 root=pathlib.Path(temporary); data=root/'data'; socket=root/'socket';socket.mkdir(mode=0o700)
 def run(*args,**kwargs):return subprocess.run([str(x) for x in args],check=True,**kwargs)
 run(bindir/'initdb','-D',data,'-A','trust','-U','ep_test','--no-locale','--encoding=UTF8',stdout=subprocess.DEVNULL)
 run(bindir/'pg_ctl','-D',data,'-l',root/'server.log','-o',f"-k {socket} -c listen_addresses=''",'-w','start',stdout=subprocess.DEVNULL)
 try:
  import psycopg
  dsn=f'host={socket} dbname=postgres user=ep_test'
  with psycopg.connect(dsn,autocommit=True) as db:
   db.execute("CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY); CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid$$; GRANT USAGE ON SCHEMA auth TO anon,authenticated; GRANT EXECUTE ON FUNCTION auth.uid() TO anon,authenticated;")
   # Deliberately hostile default ACLs exercise explicit revocation in the migration.
   db.execute('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO anon, authenticated; ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated;')
   migration=next((ROOT/'supabase/migrations').glob('*_ep_cloud_security_preview3.sql')).read_text()
   # A late collision must roll back every earlier object and preserve the existing table.
   db.execute('CREATE TABLE public.ep_decisions(sentinel integer); INSERT INTO public.ep_decisions VALUES(17)')
   try:db.execute(migration)
   except psycopg.errors.DuplicateTable:db.execute('ROLLBACK')
   else:raise AssertionError('Existing object must cause migration failure')
   assert db.execute("SELECT to_regnamespace('ep_private'),to_regclass('public.ep_members')").fetchone()==(None,None)
   assert db.execute('SELECT sentinel FROM ep_decisions').fetchone()==(17,)
   db.execute('DROP TABLE public.ep_decisions') # Synthetic collision fixture in this disposable cluster only.
   db.execute(migration)
   try:db.execute(migration)
   except psycopg.errors.DuplicateSchema:db.execute('ROLLBACK')
   else:raise AssertionError('Repeated migration must fail without replacement')
   print('Migration late-collision rollback, original-object preservation and repeat refusal: PASS',flush=True)
  env=dict(os.environ,EP_DESKTOP_TEST_DB=dsn)
  result=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v',*sys.argv[1:]],cwd=ROOT,env=env)
 finally:run(bindir/'pg_ctl','-D',data,'-m','fast','-w','stop',stdout=subprocess.DEVNULL)
 raise SystemExit(result.returncode)
