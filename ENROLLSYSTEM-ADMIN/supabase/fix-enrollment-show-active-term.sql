-- Show pending/approved enrollment even when Admin set a different "current" semester.
-- Run once in Supabase SQL Editor.

CREATE OR REPLACE FUNCTION get_student_enrollment(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'status', e.status,
    'totalUnits', e.total_units,
    'enrolledAt', TO_CHAR(COALESCE(e.enrolled_at, e.created_at), 'Mon DD, YYYY HH12:MI AM'),
    'schoolYear', sy.label,
    'semester', sem.name,
    'semesterCode', sem.code,
    'subjects', (
      SELECT COALESCE(json_agg(json_build_object(
        'code', sub.code,
        'description', sub.name,
        'units', es.units,
        'schedule', es.schedule_label
      ) ORDER BY sub.code), '[]'::json)
      FROM enrollment_subjects es
      JOIN subjects sub ON sub.id = es.subject_id
      WHERE es.enrollment_id = e.id
    )
  )
  INTO result
  FROM enrollments e
  JOIN students s ON s.id = e.student_id
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE s.student_id = UPPER(TRIM(p_student_id))
    AND e.status IN ('pending', 'approved', 'enrolled', 'rejected')
  ORDER BY
    CASE e.status
      WHEN 'pending' THEN 0
      WHEN 'approved' THEN 1
      WHEN 'enrolled' THEN 2
      WHEN 'rejected' THEN 3
      ELSE 4
    END,
    e.created_at DESC
  LIMIT 1;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_student_enrollment(TEXT) TO anon, authenticated, service_role;
