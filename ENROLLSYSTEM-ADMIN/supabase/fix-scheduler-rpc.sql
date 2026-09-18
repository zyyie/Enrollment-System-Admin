-- Run this FIRST if schedule-sync.sql fails with:
--   function name "get_scheduler_existing_schedules" is not unique
--
-- Removes the old 3-parameter overload from ENROLLSYSTEM/supabase/schedule-sync.sql
-- so the 4-parameter ADMIN version can be created and granted cleanly.

DROP FUNCTION IF EXISTS public.get_scheduler_existing_schedules(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS public.get_scheduler_existing_schedules(TEXT, TEXT, TEXT, TEXT);
