-- Enrollment Period: 1st/2nd semester + close blocks student sem enrollment
-- Run entire script in Supabase SQL Editor.

ALTER TABLE semesters ADD COLUMN IF NOT EXISTS target_grade_level TEXT
  CHECK (target_grade_level IS NULL OR target_grade_level IN ('Grade 11', 'Grade 12'));

DROP FUNCTION IF EXISTS set_enrollment_period(BOOLEAN, TEXT);
DROP FUNCTION IF EXISTS set_enrollment_period(BOOLEAN, TEXT, TEXT);
DROP FUNCTION IF EXISTS switch_enrollment_semester(TEXT);

CREATE OR REPLACE FUNCTION ensure_enrollment_semesters()
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sy UUID;
  v_semester UUID;
BEGIN
  SELECT id INTO v_sy FROM school_years WHERE is_current = TRUE LIMIT 1;
  IF v_sy IS NULL THEN
    SELECT id INTO v_sy FROM school_years WHERE code = '2627' LIMIT 1;
  END IF;
  IF v_sy IS NULL THEN
    INSERT INTO school_years (label, code, is_current, enrollment_open)
    VALUES ('2026-2027', '2627', TRUE, FALSE)
    RETURNING id INTO v_sy;
  ELSE
    UPDATE school_years SET is_current = TRUE WHERE id = v_sy;
    UPDATE school_years SET is_current = FALSE WHERE id <> v_sy;
  END IF;

  INSERT INTO semesters (school_year_id, name, code, is_current, enrollment_open, start_date, end_date)
  VALUES (v_sy, 'First Semester', '1st', TRUE, FALSE, '2026-08-01', '2026-12-15')
  ON CONFLICT (school_year_id, name) DO NOTHING;

  INSERT INTO semesters (school_year_id, name, code, is_current, enrollment_open, start_date, end_date)
  VALUES (v_sy, 'Second Semester', '2nd', FALSE, FALSE, '2027-01-05', '2027-05-30')
  ON CONFLICT (school_year_id, name) DO NOTHING;

  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE AND school_year_id = v_sy LIMIT 1;
  IF v_semester IS NULL THEN
    UPDATE semesters SET is_current = TRUE
    WHERE id = (
      SELECT id FROM semesters
      WHERE school_year_id = v_sy AND code = '1st'
      LIMIT 1
    );
    SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE AND school_year_id = v_sy LIMIT 1;
  END IF;

  UPDATE semesters SET is_current = FALSE
  WHERE school_year_id = v_sy AND id <> v_semester;

  RETURN v_semester;
END;
$$;

CREATE OR REPLACE FUNCTION close_semester_enrollment(p_semester_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_rejected INT := 0;
  v_frozen JSON;
BEGIN
  UPDATE enrollments e
  SET
    status = 'rejected',
    rejection_reason = 'Enrollment period closed by the registrar.',
    reviewed_at = NOW(),
    updated_at = NOW()
  WHERE e.semester_id = p_semester_id
    AND e.status = 'pending';

  GET DIAGNOSTICS v_rejected = ROW_COUNT;

  v_frozen := freeze_inactive_students();

  RETURN json_build_object(
    'rejectedPending', v_rejected,
    'frozenStudents', COALESCE((v_frozen->>'frozenCount')::INT, 0)
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_period()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sy UUID;
  result JSON;
BEGIN
  PERFORM ensure_enrollment_semesters();

  SELECT sy.id INTO v_sy
  FROM school_years sy
  WHERE sy.is_current = TRUE
  LIMIT 1;

  SELECT json_build_object(
    'schoolYearId', sy.id,
    'schoolYear', sy.label,
    'schoolYearCode', sy.code,
    'schoolYearOpen', sy.enrollment_open,
    'semesterId', sem.id,
    'semester', sem.name,
    'semesterCode', sem.code,
    'enrollmentOpen', sem.enrollment_open,
    'targetGradeLevel', sem.target_grade_level,
    'startDate', sem.start_date,
    'endDate', sem.end_date,
    'isCurrent', sem.is_current,
    'semesters', COALESCE((
      SELECT json_agg(
        json_build_object(
          'id', s.id,
          'name', s.name,
          'code', s.code,
          'enrollmentOpen', s.enrollment_open,
          'targetGradeLevel', s.target_grade_level,
          'startDate', s.start_date,
          'endDate', s.end_date,
          'isCurrent', s.is_current
        )
        ORDER BY CASE s.code WHEN '1st' THEN 1 WHEN '2nd' THEN 2 ELSE 3 END
      )
      FROM semesters s
      WHERE s.school_year_id = sy.id
    ), '[]'::json)
  )
  INTO result
  FROM semesters sem
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE sem.is_current = TRUE
    AND sy.id = v_sy
  LIMIT 1;

  RETURN COALESCE(result, '{}'::json);
END;
$$;

CREATE OR REPLACE FUNCTION switch_enrollment_semester(p_semester_code TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sy UUID;
  v_code TEXT;
BEGIN
  PERFORM ensure_enrollment_semesters();

  v_code := NULLIF(LOWER(TRIM(COALESCE(p_semester_code, ''))), '');
  IF v_code IS NULL OR v_code NOT IN ('1st', '2nd') THEN
    RAISE EXCEPTION 'Invalid semester code. Use 1st or 2nd.';
  END IF;

  SELECT id INTO v_sy FROM school_years WHERE is_current = TRUE LIMIT 1;
  IF v_sy IS NULL THEN
    RAISE EXCEPTION 'No active school year configured';
  END IF;

  UPDATE semesters SET is_current = FALSE WHERE school_year_id = v_sy;
  UPDATE semesters SET is_current = TRUE
  WHERE school_year_id = v_sy AND code = v_code;

  RETURN get_enrollment_period();
END;
$$;

CREATE OR REPLACE FUNCTION set_enrollment_period(
  p_enrollment_open BOOLEAN,
  p_target_grade_level TEXT DEFAULT NULL,
  p_semester_code TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sy UUID;
  v_semester UUID;
  v_code TEXT;
  v_close_result JSON;
BEGIN
  PERFORM ensure_enrollment_semesters();

  SELECT id INTO v_sy FROM school_years WHERE is_current = TRUE LIMIT 1;
  IF v_sy IS NULL THEN
    RAISE EXCEPTION 'No active school year configured';
  END IF;

  v_code := NULLIF(LOWER(TRIM(COALESCE(p_semester_code, ''))), '');
  IF v_code IS NOT NULL THEN
    IF v_code NOT IN ('1st', '2nd') THEN
      RAISE EXCEPTION 'Invalid semester code. Use 1st or 2nd.';
    END IF;

    UPDATE semesters SET is_current = FALSE WHERE school_year_id = v_sy;
    UPDATE semesters SET is_current = TRUE
    WHERE school_year_id = v_sy AND code = v_code;
  END IF;

  SELECT id INTO v_semester
  FROM semesters
  WHERE school_year_id = v_sy AND is_current = TRUE
  LIMIT 1;

  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'Semester not found';
  END IF;

  UPDATE semesters
  SET
    enrollment_open = p_enrollment_open,
    target_grade_level = NULLIF(TRIM(p_target_grade_level), '')
  WHERE id = v_semester;

  UPDATE school_years
  SET enrollment_open = p_enrollment_open
  WHERE id = v_sy;

  IF NOT p_enrollment_open THEN
    v_close_result := close_semester_enrollment(v_semester);
  END IF;

  RETURN json_build_object(
    'success', TRUE,
    'enrollmentOpen', p_enrollment_open,
    'targetGradeLevel', NULLIF(TRIM(p_target_grade_level), ''),
    'semesterCode', (SELECT code FROM semesters WHERE id = v_semester),
    'closeSummary', v_close_result,
    'period', get_enrollment_period()
  );
END;
$$;

GRANT EXECUTE ON FUNCTION ensure_enrollment_semesters() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION close_semester_enrollment(UUID) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_enrollment_period() TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION switch_enrollment_semester(TEXT) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION set_enrollment_period(BOOLEAN, TEXT, TEXT) TO anon, authenticated, service_role;

NOTIFY pgrst, 'reload schema';
