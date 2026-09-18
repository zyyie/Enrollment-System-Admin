-- Faculty table helpers (teachers only — registrar uses admins table)
-- Run admin-table.sql first for admins + authenticate_admin.

ALTER TABLE faculty ADD COLUMN IF NOT EXISTS password TEXT;
ALTER TABLE faculty ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
ALTER TABLE faculty ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;
ALTER TABLE faculty ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE faculty ADD COLUMN IF NOT EXISTS middle_name TEXT;
ALTER TABLE faculty ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'Teacher';

CREATE OR REPLACE FUNCTION authenticate_faculty(
  p_faculty_id TEXT,
  p_password TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  UPDATE faculty
  SET last_login = NOW(), updated_at = NOW()
  WHERE faculty_id = UPPER(TRIM(p_faculty_id))
    AND password = p_password
    AND COALESCE(is_active, TRUE) = TRUE
    AND LOWER(TRIM(role)) = 'teacher';

  SELECT json_build_object(
    'id', f.faculty_id,
    'supabaseId', f.id,
    'lastName', f.last_name,
    'firstName', f.first_name,
    'middleName', COALESCE(f.middle_name, ''),
    'role', f.role,
    'department', COALESCE(f.department, ''),
    'lastLogin', TO_CHAR(f.last_login, 'Mon DD, YYYY HH12:MI AM')
  )
  INTO result
  FROM faculty f
  WHERE f.faculty_id = UPPER(TRIM(p_faculty_id))
    AND f.password = p_password
    AND COALESCE(f.is_active, TRUE) = TRUE
    AND LOWER(TRIM(f.role)) = 'teacher'
  LIMIT 1;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION authenticate_faculty TO anon, authenticated;
