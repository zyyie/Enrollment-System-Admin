-- Registrar / admin accounts (separate from faculty teachers)
-- Run once in Supabase SQL Editor (safe to re-run).

CREATE TABLE IF NOT EXISTS admins (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  admin_id TEXT NOT NULL UNIQUE,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  middle_name TEXT,
  role TEXT NOT NULL DEFAULT 'Registrar',
  department TEXT,
  email TEXT,
  password TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  last_login TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admins_admin_id ON admins (UPPER(admin_id));

-- Move default registrar out of faculty (teachers stay in faculty)
INSERT INTO admins (
  admin_id, last_name, first_name, middle_name, role, department, password, is_active, last_login
)
VALUES (
  'FAC-2026-0001', 'Admin', 'System', '', 'Registrar', 'Registrar Office', 'admin123', TRUE, NOW()
)
ON CONFLICT (admin_id) DO UPDATE SET
  last_name = EXCLUDED.last_name,
  first_name = EXCLUDED.first_name,
  middle_name = EXCLUDED.middle_name,
  role = EXCLUDED.role,
  department = EXCLUDED.department,
  password = EXCLUDED.password,
  is_active = TRUE,
  updated_at = NOW();

-- Copy password from existing faculty row if present (keeps your current password on migrate)
UPDATE admins a
SET password = f.password, updated_at = NOW()
FROM faculty f
WHERE f.faculty_id = a.admin_id
  AND f.password IS NOT NULL
  AND f.password <> ''
  AND a.admin_id = 'FAC-2026-0001';

UPDATE faculty
SET is_active = FALSE, updated_at = NOW()
WHERE faculty_id = 'FAC-2026-0001'
  AND LOWER(TRIM(COALESCE(role, ''))) IN ('registrar', 'admin', 'administrator');

CREATE OR REPLACE FUNCTION authenticate_admin(
  p_admin_id TEXT,
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
  UPDATE admins
  SET last_login = NOW(), updated_at = NOW()
  WHERE admin_id = UPPER(TRIM(p_admin_id))
    AND password = p_password
    AND COALESCE(is_active, TRUE) = TRUE;

  SELECT json_build_object(
    'id', a.admin_id,
    'supabaseId', a.id,
    'lastName', a.last_name,
    'firstName', a.first_name,
    'middleName', COALESCE(a.middle_name, ''),
    'role', a.role,
    'department', COALESCE(a.department, ''),
    'lastLogin', TO_CHAR(a.last_login, 'Mon DD, YYYY HH12:MI AM')
  )
  INTO result
  FROM admins a
  WHERE a.admin_id = UPPER(TRIM(p_admin_id))
    AND a.password = p_password
    AND COALESCE(a.is_active, TRUE) = TRUE
  LIMIT 1;

  RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION seed_default_admin()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO admins (
    admin_id, last_name, first_name, middle_name, role, department, password, is_active, last_login
  )
  VALUES (
    'FAC-2026-0001', 'Admin', 'System', '', 'Registrar', 'Registrar Office', 'admin123', TRUE, NOW()
  )
  ON CONFLICT (admin_id) DO UPDATE SET
    last_name = EXCLUDED.last_name,
    first_name = EXCLUDED.first_name,
    middle_name = EXCLUDED.middle_name,
    role = EXCLUDED.role,
    department = EXCLUDED.department,
    password = EXCLUDED.password,
    is_active = TRUE,
    updated_at = NOW();

  UPDATE faculty
  SET is_active = FALSE, updated_at = NOW()
  WHERE faculty_id = 'FAC-2026-0001';

  RETURN json_build_object('success', TRUE, 'adminId', 'FAC-2026-0001');
END;
$$;

-- Faculty portal: teachers only (registrar accounts use admins table)
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

GRANT EXECUTE ON FUNCTION authenticate_admin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION seed_default_admin TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION authenticate_faculty TO anon, authenticated, service_role;
