-- Fix "column updated_at of relation class_schedules does not exist" on Save & Publish
-- Run once in Supabase SQL Editor, then run schedule-sync.sql (or retry save after admin server restart).

ALTER TABLE class_schedules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
