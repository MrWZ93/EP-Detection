BEGIN;
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
