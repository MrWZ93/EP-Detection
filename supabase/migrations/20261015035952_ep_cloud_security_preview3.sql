-- EP cloud schema maintenance preview.3. Fresh installation only; no Auth configuration.
-- Generated local migration filename by Supabase CLI 2.121.0.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
-- REVIEW BEFORE APPLYING. Dedicated EP project only. Not executed by this release.
-- Requires administrator SQL privileges. No service-role credentials go in the app.
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
CREATE TABLE public.ep_decisions(operation_id uuid PRIMARY KEY,source_id text NOT NULL,actor uuid NOT NULL REFERENCES auth.users(id),payload jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT now());
ALTER TABLE public.ep_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.ep_decisions FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.ep_decisions TO authenticated;
CREATE POLICY admins_read_decisions ON public.ep_decisions FOR SELECT TO authenticated USING(ep_private.ep_is_admin());
CREATE TRIGGER ep_decision_immutable BEFORE UPDATE OR DELETE ON public.ep_decisions FOR EACH ROW EXECUTE FUNCTION ep_private.ep_immutable_revision();
CREATE FUNCTION ep_private.ep_save_decision(p jsonb) RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE old public.ep_decisions; selected public.ep_revisions; previous uuid; previous_created timestamptz; ids jsonb; kind text; field text; t jsonb; boundary bigint; sample bigint; n bigint;
BEGIN
 IF auth.uid() IS NULL OR NOT ep_private.ep_is_admin() THEN RAISE EXCEPTION 'Administrator required' USING ERRCODE='42501';END IF;
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Decision object required';END IF;
 IF NOT p ?& ARRAY['operation_id','source_id','source_sha256','selected_revision_id','observed_revision_ids','thresholds','reason','supersedes','conditions'] OR (p - ARRAY['operation_id','source_id','source_sha256','selected_revision_id','observed_revision_ids','thresholds','reason','supersedes','conditions','conditions_confirmed'])<>'{}'::jsonb THEN RAISE EXCEPTION 'Decision fields required';END IF;
 FOREACH field IN ARRAY ARRAY['operation_id','source_id','source_sha256','selected_revision_id','reason','conditions'] LOOP
  IF jsonb_typeof(p->field) IS DISTINCT FROM 'string' THEN RAISE EXCEPTION 'Required string: %',field;END IF;
 END LOOP;
 IF (p->>'source_id') !~ '^[a-f0-9]{64}$' OR (p->>'source_sha256') !~ '^[a-f0-9]{64}$' OR jsonb_typeof(p->'observed_revision_ids') IS DISTINCT FROM 'array' OR jsonb_typeof(p->'thresholds') IS DISTINCT FROM 'object' OR jsonb_typeof(p->'supersedes') NOT IN ('null','string') THEN RAISE EXCEPTION 'Invalid decision evidence';END IF;
 IF p ? 'conditions_confirmed' AND jsonb_typeof(p->'conditions_confirmed') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Boolean conditions confirmation required';END IF;
 -- Validate UUIDs even for a first write.
 PERFORM (p->>'operation_id')::uuid,(p->>'selected_revision_id')::uuid,(p->>'supersedes')::uuid;
 IF length(trim(p->>'reason'))=0 OR p->>'reason' IS NULL OR octet_length(p::text)>1000000 THEN RAISE EXCEPTION 'Rationale required';END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('ep:source:'||(p->>'source_id'),0));
 SELECT * INTO old FROM public.ep_decisions WHERE operation_id=(p->>'operation_id')::uuid;
 IF FOUND THEN
  IF old.actor<>auth.uid() OR old.payload<>p THEN RAISE EXCEPTION 'Decision ID collision' USING ERRCODE='23505';END IF;
  RETURN jsonb_build_object('operation_id',old.operation_id);
 END IF;
 SELECT * INTO selected FROM public.ep_revisions WHERE operation_id=(p->>'selected_revision_id')::uuid;
 IF NOT FOUND OR (selected.payload->>'source_id') IS DISTINCT FROM (p->>'source_id') OR (selected.payload->>'source_sha256') IS DISTINCT FROM (p->>'source_sha256') OR NOT (selected.payload->>'submitted')::boolean OR selected.payload->'annotation'->>'decision'<>'yes' THEN RAISE EXCEPTION 'Invalid selected review';END IF;
 SELECT jsonb_agg(operation_id::text ORDER BY operation_id::text) INTO ids FROM public.ep_revisions WHERE payload->>'source_id'=p->>'source_id';
 IF ids IS DISTINCT FROM p->'observed_revision_ids' THEN RAISE EXCEPTION 'Reviews changed' USING ERRCODE='23505';END IF;
 SELECT operation_id,created_at INTO previous,previous_created FROM public.ep_decisions WHERE source_id=p->>'source_id' ORDER BY created_at DESC,operation_id DESC LIMIT 1;
 IF previous IS DISTINCT FROM (p->>'supersedes')::uuid THEN RAISE EXCEPTION 'Decision changed' USING ERRCODE='23505';END IF;
 n:=(selected.payload->>'sample_count')::bigint;
 FOREACH kind IN ARRAY ARRAY['EV','BV'] LOOP
  t:=p->'thresholds'->kind;
  IF jsonb_typeof(t) IS DISTINCT FROM 'object' OR jsonb_typeof(t->'status') IS DISTINCT FROM 'string' OR t->>'status' IS NULL OR t->>'status' NOT IN ('include','missing','censored','saturated','calibration_unknown','definition_unconfirmed','exclude') THEN RAISE EXCEPTION 'Qualification required';END IF;
  IF t->>'status'='include' THEN
   FOREACH field IN ARRAY ARRAY['definition_confirmed','calibration_confirmed','edge_unobscured'] LOOP
    IF jsonb_typeof(t->field) IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Boolean evidence required';END IF;
   END LOOP;
   FOREACH field IN ARRAY ARRAY['boundary_idx','sample_idx'] LOOP
    IF jsonb_typeof(t->field) IS DISTINCT FROM 'number' OR (t->>field) !~ '^[0-9]+$' THEN RAISE EXCEPTION 'Integer evidence required';END IF;
   END LOOP;
   IF jsonb_typeof(t->'edge') IS DISTINCT FROM 'string' OR jsonb_typeof(t->'stage') IS DISTINCT FROM 'string' OR (t->>'source_sha256') IS DISTINCT FROM (p->>'source_sha256') OR jsonb_typeof(t->'voltage_V') IS DISTINCT FROM 'number' THEN RAISE EXCEPTION 'Required boundary evidence';END IF;
   IF NOT (abs((t->>'voltage_V')::double precision)<'Infinity'::double precision) THEN RAISE EXCEPTION 'Finite voltage required';END IF;
   IF jsonb_typeof(selected.payload->'annotation'->'profile_confirmed') IS DISTINCT FROM 'boolean' THEN RAISE EXCEPTION 'Boolean profile confirmation required';END IF;
   IF (t->>'definition_confirmed')::boolean IS DISTINCT FROM true OR (t->>'calibration_confirmed')::boolean IS DISTINCT FROM true OR (t->>'edge_unobscured')::boolean IS DISTINCT FROM true OR (selected.payload->'annotation'->>'profile_confirmed')::boolean IS DISTINCT FROM true THEN RAISE EXCEPTION 'Confirmation required';END IF;
   boundary:=(t->>'boundary_idx')::bigint;sample:=(t->>'sample_idx')::bigint;
   IF boundary IS NULL OR sample IS NULL OR sample<0 OR sample>=n OR t->>'source_sha256'<>p->>'source_sha256' OR jsonb_typeof(t->'voltage_V') IS DISTINCT FROM 'number' OR t->>'edge' NOT IN ('start','end') OR t->>'stage' NOT IN ('S1','S2','S3','S4') THEN RAISE EXCEPTION 'Invalid boundary evidence';END IF;
   IF sample<>boundary-(CASE WHEN t->>'edge'='end' THEN 1 ELSE 0 END) THEN RAISE EXCEPTION 'Invalid boundary sample';END IF;
   -- Raw waveform is intentionally absent from cloud: voltage is an administrator's
   -- attested exact local sample, never represented as server-verified raw evidence.
   IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements_text(selected.payload->'annotation'->'partition'->'labels') WITH ORDINALITY AS l(value,pos) WHERE l.value=t->>'stage' AND (selected.payload->'annotation'->'partition'->'cuts'->>(CASE WHEN t->>'edge'='start' THEN l.pos-1 ELSE l.pos END)::integer)::bigint=boundary) THEN RAISE EXCEPTION 'Evidence does not match annotated boundary';END IF;
  END IF;
 END LOOP;
 IF p->'thresholds'->'EV'->>'status'='include' AND p->'thresholds'->'BV'->>'status'='include' AND (p->'thresholds'->'EV'->>'boundary_idx')::bigint>(p->'thresholds'->'BV'->>'boundary_idx')::bigint THEN RAISE EXCEPTION 'EV follows BV';END IF;
 INSERT INTO public.ep_decisions VALUES((p->>'operation_id')::uuid,p->>'source_id',auth.uid(),p,greatest(clock_timestamp(),previous_created+interval '1 microsecond'));
 RETURN jsonb_build_object('operation_id',p->>'operation_id');
END$$;
REVOKE ALL ON FUNCTION ep_private.ep_save_decision(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION ep_private.ep_save_decision(jsonb) TO authenticated;
CREATE FUNCTION public.ep_save_decision(p jsonb) RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path=pg_catalog AS $$SELECT ep_private.ep_save_decision(p)$$;
REVOKE ALL ON FUNCTION public.ep_save_decision(jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.ep_save_decision(jsonb) TO authenticated;
CREATE INDEX ep_decisions_actor_idx ON public.ep_decisions(actor);
CREATE INDEX ep_decisions_source_idx ON public.ep_decisions(source_id,created_at DESC,operation_id DESC);
COMMIT;
