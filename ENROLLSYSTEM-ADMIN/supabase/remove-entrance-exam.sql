-- Run this in Supabase SQL Editor if admission-schema.sql was already applied
-- Removes Entrance Examination from stored application documents

UPDATE admission_applications
SET documents = documents - 'entrance_exam'
WHERE documents ? 'entrance_exam';
