-- Set default registrar password (admins table — not faculty)
-- Run in Supabase SQL Editor if admin login fails after migration.

UPDATE admins
SET password = 'admin123', updated_at = NOW()
WHERE admin_id = 'FAC-2026-0001';
