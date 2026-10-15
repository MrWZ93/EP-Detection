-- Read-only inspection. Run only against the explicitly selected study project.
SELECT current_database(),current_user,current_setting('server_version') AS postgres_version;
SELECT nspname,nspacl FROM pg_namespace WHERE nspname IN ('public','ep_private');
SELECT n.nspname,c.relname,c.relkind,c.relrowsecurity,c.relacl
FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='ep_private' OR (n.nspname='public' AND c.relname LIKE 'ep\_%' ESCAPE '\');
SELECT n.nspname,p.proname,pg_get_function_identity_arguments(p.oid) AS arguments,p.prosecdef,p.proconfig,p.proacl
FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='ep_private' OR (n.nspname='public' AND p.proname LIKE 'ep\_%' ESCAPE '\');
SELECT defaclrole::regrole,defaclnamespace::regnamespace,defaclobjtype,defaclacl FROM pg_default_acl;
SELECT current_setting('pgrst.db_schemas',true) AS session_exposed_schemas;
-- NULL above does not prove the private schema is unexposed: inspect Data API settings too.
-- Counts only; no user emails, tokens, password hashes or keys.
SELECT count(*) AS auth_user_count FROM auth.users;
SELECT provider,count(*) AS identities FROM auth.identities GROUP BY provider;
-- Identity counts do not prove a provider is currently enabled.
