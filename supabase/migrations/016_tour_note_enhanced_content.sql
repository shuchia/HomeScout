/* ============================================================================
   Stop AI enhancement from destroying the transcript
   Run in the Supabase SQL Editor.

   ADDITIVE — one nullable column. No existing data is rewritten.

   WHY
   enhance_voice_note wrote the Claude cleanup over tour_notes.content. That
   column is the only text store for a note, so the Whisper transcript was
   gone the moment enhancement succeeded. The note's audio is the only other
   copy, and it is on a 365-day S3 expiry on non-prod — with no expiry rule
   configured for prod at all (infra/main.tf:116, count = environment !=
   "prod"). So the recording outlives the words it produced, which is the
   wrong way round: we kept the high-sensitivity artifact and discarded the
   ~1 KB of derived text.

   It also mattered for correctness, not just tidiness:

   - The decision brief reads `content` (tours.py:342), so it reasoned over
     the paraphrase. If enhancement dropped a qualifier -- "no in-unit
     laundry, but there is a basement" collapsing toward "laundry available"
     -- the brief inherited it and no artifact remained to check against.

   - Whisper is the weaker link in the chain, not Claude. It is called with
     no `prompt` biasing and no `language` (whisper_service.py:29), so it
     mishears street names and rental vocabulary even though we know exactly
     which listing the note belongs to. The transcript is the only cheap way
     to tell a mishearing from something the renter actually said.

   WHAT CHANGES
   `content` returns to meaning "what the user said or typed" and is never
   overwritten by a model. `enhanced_content` holds the cleanup and stays
   NULL until one runs. Readers show enhanced_content when present and fall
   back to content.

   DEPLOY ORDER — APPLY THIS BEFORE THE CODE
   The task writes `enhanced_content`. Against a database without the column
   PostgREST rejects the update; enhancement is wrapped in a non-fatal
   try/except, so the note would silently keep its raw transcript and no
   cleanup would ever appear. That is the safe direction to fail, but it is
   still broken. Apply this first.

   NOT BACKFILLABLE
   Notes enhanced before this already hold the paraphrase in `content` and
   the transcript is unrecoverable -- there is nothing to migrate them from.
   They keep enhanced_content NULL, with `content` holding a cleanup rather
   than a transcript. Only notes enhanced from here on carry both, so a
   reader cannot assume `content` is verbatim for a historical row.
   ========================================================================= */

alter table public.tour_notes
  add column if not exists enhanced_content text;

comment on column public.tour_notes.content is
  'What the user actually said (Whisper transcript) or typed. Never '
  'overwritten by AI. Rows enhanced before migration 016 hold a cleanup '
  'here instead, because the original was overwritten.';

comment on column public.tour_notes.enhanced_content is
  'Claude grammar/clarity cleanup of content. NULL when no enhancement has '
  'run. Display prefers this and falls back to content.';
