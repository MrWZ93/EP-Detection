-- REVIEW BEFORE APPLYING. Dedicated EP project only. Not executed by this release.
-- Requires administrator SQL privileges. No service-role credentials go in the app.
BEGIN;
-- Fresh deployment only. The private schema must not be exposed by the Data API.
CREATE SCHEMA ep_private;
REVOKE ALL ON SCHEMA ep_private FROM PUBLIC,anon,authenticated;
GRANT USAGE ON SCHEMA ep_private TO authenticated;
CREATE TABLE public.ep_members(user_id uuid PRIMARY KEY REFERENCES auth.users(id), role text NOT NULL CHECK(role IN ('reviewer','admin')));
CREATE TABLE public.ep_assessments(id uuid PRIMARY KEY, owner uuid NOT NULL REFERENCES auth.users(id), source_id text NOT NULL, revision integer NOT NULL DEFAULT 0);
CREATE TABLE public.ep_revisions(operation_id uuid PRIMARY KEY, assessment_id uuid NOT NULL REFERENCES public.ep_assessments(id), owner uuid NOT NULL REFERENCES auth.users(id), revision integer NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(assessment_id,revision));
ALTER TABLE public.ep_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ep_assessments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ep_revisions ENABLE ROW LEVEL SECURITY;
CREATE FUNCTION ep_private.ep_is_admin() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$SELECT EXISTS(SELECT 1 FROM public.ep_members WHERE user_id=auth.uid() AND role='admin')$$;
REVOKE ALL ON FUNCTION ep_private.ep_is_admin() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION ep_private.ep_is_admin() TO authenticated;
CREATE FUNCTION ep_private.ep_is_member() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$SELECT auth.uid() IS NOT NULL AND EXISTS(SELECT 1 FROM public.ep_members WHERE user_id=auth.uid())$$;
REVOKE ALL ON FUNCTION ep_private.ep_is_member() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION ep_private.ep_is_member() TO authenticated;
CREATE POLICY own_membership ON public.ep_members FOR SELECT TO authenticated USING(user_id=auth.uid() OR ep_private.ep_is_admin());
CREATE POLICY own_assessments ON public.ep_assessments FOR SELECT TO authenticated USING((ep_private.ep_is_member() AND owner=auth.uid()) OR ep_private.ep_is_admin());
CREATE POLICY own_revisions ON public.ep_revisions FOR SELECT TO authenticated USING((ep_private.ep_is_member() AND owner=auth.uid()) OR ep_private.ep_is_admin());
REVOKE ALL ON public.ep_members,public.ep_assessments,public.ep_revisions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.ep_members,public.ep_assessments,public.ep_revisions TO authenticated;
CREATE FUNCTION ep_private.ep_immutable_revision() RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$BEGIN RAISE EXCEPTION 'Revision history is immutable';END$$;
CREATE TRIGGER ep_revision_immutable BEFORE UPDATE OR DELETE ON public.ep_revisions FOR EACH ROW EXECUTE FUNCTION ep_private.ep_immutable_revision();
CREATE FUNCTION ep_private.ep_save_revision(p jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE actor uuid:=auth.uid(); old public.ep_revisions; a public.ep_assessments; op uuid; aid uuid; base integer; n bigint; cuts jsonb; labels jsonb; previous bigint:=-1; cut bigint; label text; laststage integer:=0; stage integer; field text; j integer; lastlabel text:=NULL; seen text[]:=ARRAY[]::text[];
BEGIN
 IF actor IS NULL OR NOT EXISTS(SELECT 1 FROM public.ep_members WHERE user_id=actor) THEN RAISE EXCEPTION 'Study membership required' USING ERRCODE='42501';END IF;
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Object required';END IF;
 IF octet_length(p::text)>1000000 THEN RAISE EXCEPTION 'Payload too large';END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p))<>13 OR NOT p ?& ARRAY['operation_id','assessment_id','base_revision','revision','source_id','source_sha256','relative_path','sample_count','sample_rate','annotation','submitted','reviewer_name','client_version'] THEN RAISE EXCEPTION 'Invalid payload fields';END IF;
 -- Reject JSON null and coercible strings before casts (SQL NULL must fail closed).
 FOREACH field IN ARRAY ARRAY['operation_id','assessment_id','source_id','source_sha256','relative_path','reviewer_name','client_version'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' OR length(trim(p->>field))=0 THEN RAISE EXCEPTION 'Required string: %',field;END IF;
 END LOOP;
 FOREACH field IN ARRAY ARRAY['base_revision','revision','sample_count'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'number' OR (p->>field) !~ '^[0-9]+$' THEN RAISE EXCEPTION 'Required integer: %',field;END IF;
 END LOOP;
 IF jsonb_typeof(p->'sample_rate') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'Numeric sample rate required';END IF;
 IF NOT ((p->>'sample_rate')::double precision>0 AND (p->>'sample_rate')::double precision<'Infinity'::double precision) THEN RAISE EXCEPTION 'Finite positive sample rate required';END IF;
 IF jsonb_typeof(p->'annotation') IS DISTINCT FROM 'object' OR jsonb_typeof(p->'submitted') IS DISTINCT FROM 'boolean' OR jsonb_typeof(p->'relative_path') IS DISTINCT FROM 'string' OR jsonb_typeof(p->'reviewer_name') IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'Invalid field types';END IF;
 op:=(p->>'operation_id')::uuid;aid:=(p->>'assessment_id')::uuid;base:=(p->>'base_revision')::integer;n:=(p->>'sample_count')::bigint;
 IF op IS NULL OR aid IS NULL OR base IS NULL OR n IS NULL OR p->>'revision' IS NULL OR (p->>'revision')::integer<>base+1 OR base<0 OR n<=0 OR (p->>'sample_rate')::double precision<=0 OR coalesce(p->>'source_sha256','') !~ '^[a-f0-9]{64}$' OR coalesce(p->>'source_id','') !~ '^[a-f0-9]{64}$' OR length(trim(p->>'reviewer_name')) NOT BETWEEN 1 AND 100 OR left(p->>'relative_path',1)='/' OR p->>'relative_path' ~ '(^|/)\.\.(/|$)' THEN RAISE EXCEPTION 'Invalid source/revision/profile';END IF;
 IF coalesce(p->'annotation'->>'decision','') NOT IN ('yes','no','uncertain') AND (p->>'submitted')::boolean THEN RAISE EXCEPTION 'Decision required';END IF;
 IF coalesce(p->'annotation'->>'decision','') <> 'no' THEN
  cuts:=p->'annotation'->'partition'->'cuts';labels:=p->'annotation'->'partition'->'labels';
  IF jsonb_typeof(cuts) IS DISTINCT FROM 'array' OR jsonb_typeof(labels) IS DISTINCT FROM 'array' OR jsonb_array_length(cuts)<>jsonb_array_length(labels)+1 OR (cuts->>0)::bigint<>0 OR (cuts->>-1)::bigint<>n THEN RAISE EXCEPTION 'Invalid partition';END IF;
  FOR j IN 0..jsonb_array_length(cuts)-1 LOOP
   IF jsonb_typeof(cuts->j) IS DISTINCT FROM 'number' OR coalesce(cuts->>j,'') !~ '^[0-9]+$' THEN RAISE EXCEPTION 'Noninteger sample';END IF;
   cut:=(cuts->>j)::bigint;IF cut<=previous OR cut>n THEN RAISE EXCEPTION 'Invalid boundary order';END IF;previous:=cut;
  END LOOP;
  FOR j IN 0..jsonb_array_length(labels)-1 LOOP
   label:=labels->>j;
   IF label IS NOT NULL AND label NOT IN ('outside','S1','S2','S3','S4') THEN RAISE EXCEPTION 'Invalid stage label';END IF;
   IF label IS NULL AND (p->>'submitted')::boolean AND p->'annotation'->>'decision'='yes' THEN RAISE EXCEPTION 'Unlabelled region';END IF;
   IF label IN ('S1','S2','S3','S4') THEN
    stage:=right(label,1)::integer;
    IF stage<laststage OR (label=ANY(seen) AND lastlabel IS DISTINCT FROM label) THEN RAISE EXCEPTION 'Invalid stage order';END IF;
    laststage:=stage;seen:=array_append(seen,label);
   END IF;lastlabel:=label;
  END LOOP;
 END IF;
 IF p->>'source_id'<>encode(sha256(convert_to(p->>'source_sha256','UTF8') || decode('00','hex') || convert_to(p->>'relative_path','UTF8')),'hex') THEN RAISE EXCEPTION 'Source identity mismatch';END IF;
 -- Global order: source lock, then assessment lock. Adjudication takes the same source lock.
 PERFORM pg_advisory_xact_lock(hashtextextended('ep:source:'||(p->>'source_id'),0));
 -- Serializes retries and first-write races; one assessment is independently revisable.
 PERFORM pg_advisory_xact_lock(hashtextextended('ep:assessment:'||aid::text,0));
 SELECT * INTO old FROM public.ep_revisions WHERE operation_id=op;
 IF FOUND THEN
  IF old.owner<>actor OR old.payload<>p THEN RAISE EXCEPTION 'Operation collision' USING ERRCODE='23505';END IF;
  RETURN jsonb_build_object('operation_id',op,'revision',old.revision);
 END IF;
 INSERT INTO public.ep_assessments(id,owner,source_id) VALUES(aid,actor,p->>'source_id') ON CONFLICT DO NOTHING;
 SELECT * INTO a FROM public.ep_assessments WHERE id=aid FOR UPDATE;
 IF a.owner<>actor THEN RAISE EXCEPTION 'Assessment belongs to another user' USING ERRCODE='42501';END IF;
 IF a.source_id<>p->>'source_id' OR a.revision<>base THEN RAISE EXCEPTION 'Revision conflict' USING ERRCODE='23505';END IF;
 INSERT INTO public.ep_revisions VALUES(op,aid,actor,base+1,p,now());
 UPDATE public.ep_assessments SET revision=base+1 WHERE id=aid;
 RETURN jsonb_build_object('operation_id',op,'revision',base+1);
END$$;
REVOKE ALL ON FUNCTION ep_private.ep_save_revision(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION ep_private.ep_save_revision(jsonb) TO authenticated;
-- Public RPC wrapper uses invoker privileges; all authorization is in the private implementation.
CREATE FUNCTION public.ep_save_revision(p jsonb) RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$SELECT ep_private.ep_save_revision(p)$$;
REVOKE ALL ON FUNCTION public.ep_save_revision(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.ep_save_revision(jsonb) TO authenticated;
REVOKE ALL ON FUNCTION ep_private.ep_immutable_revision() FROM PUBLIC,anon,authenticated;
CREATE INDEX ep_assessments_owner_idx ON public.ep_assessments(owner);
CREATE INDEX ep_revisions_owner_idx ON public.ep_revisions(owner);
CREATE INDEX ep_revisions_source_idx ON public.ep_revisions((payload->>'source_id'));
COMMIT;
