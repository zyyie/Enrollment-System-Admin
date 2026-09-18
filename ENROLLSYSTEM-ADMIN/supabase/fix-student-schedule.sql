-- Fix student schedule page ("Schedule Unavailable" even when enrolled)
-- Run ONCE in Supabase SQL Editor (requires schedule-sync.sql columns: sessions_json, is_published)

ALTER TABLE class_schedules ADD COLUMN IF NOT EXISTS sessions_json JSONB;
ALTER TABLE class_schedules ADD COLUMN IF NOT EXISTS is_published BOOLEAN DEFAULT FALSE;

-- Publish existing schedules so enrolled students can view them
UPDATE class_schedules
SET is_published = TRUE
WHERE is_active = TRUE
  AND COALESCE(is_published, FALSE) = FALSE;

CREATE OR REPLACE FUNCTION get_student_strand_schedule(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_enrollment_status TEXT;
  schedule_rows JSON;
BEGIN
  SELECT s.id INTO v_student
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object(
      'enrollmentStatus', 'none',
      'message', 'Student account not found.',
      'schedule', '[]'::json
    );
  END IF;

  SELECT e.status INTO v_enrollment_status
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id AND sem.is_current = TRUE
  WHERE e.student_id = v_student
  ORDER BY e.created_at DESC
  LIMIT 1;

  IF v_enrollment_status IS NULL THEN
    RETURN json_build_object(
      'enrollmentStatus', 'none',
      'message', 'You have not enrolled for this semester yet. Go to Enrollment to select your subjects.',
      'schedule', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'pending' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'pending',
      'message', 'Your enrollment is pending admin approval. Your class schedule will appear here once approved.',
      'schedule', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'rejected' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'rejected',
      'message', 'Your enrollment was not approved. Please contact the registrar office.',
      'schedule', '[]'::json
    );
  END IF;

  SELECT COALESCE(json_agg(row_data ORDER BY row_data->>'code'), '[]'::json)
  INTO schedule_rows
  FROM (
    SELECT json_build_object(
      'code', sub.code,
      'description', sub.name,
      'lec', sub.lec_hours,
      'lab', sub.lab_hours,
      'unit', sub.units,
      'section', sec.name,
      'professor', TRIM(COALESCE(f.first_name, '') || ' ' || COALESCE(f.last_name, '')),
      'schedule', CASE
        WHEN cs.sessions_json IS NOT NULL AND jsonb_array_length(cs.sessions_json) > 0 THEN
          (
            SELECT string_agg(
              (s->>'day') || ' ' || (s->>'start') || '-' || (s->>'end') || ' @ ' || COALESCE(s->>'room', 'TBA'),
              ' · '
            )
            FROM jsonb_array_elements(cs.sessions_json) s
          )
        ELSE
          COALESCE(NULLIF(TRIM(es.schedule_label), ''), cs.schedule_label, 'TBA') ||
          CASE WHEN r.name IS NOT NULL THEN ' @ ' || r.name ELSE '' END
      END
    ) AS row_data
    FROM enrollments e
    JOIN semesters sem ON sem.id = e.semester_id AND sem.is_current = TRUE
    JOIN enrollment_subjects es ON es.enrollment_id = e.id
    JOIN class_schedules cs ON cs.id = es.class_schedule_id
    JOIN subjects sub ON sub.id = es.subject_id
    JOIN sections sec ON sec.id = cs.section_id
    LEFT JOIN rooms r ON r.id = cs.room_id
    LEFT JOIN faculty f ON f.id = cs.faculty_id
    WHERE e.student_id = v_student
      AND e.status IN ('approved', 'enrolled')
      AND COALESCE(es.status, 'enrolled') = 'enrolled'
      AND cs.is_active = TRUE
  ) rows;

  IF schedule_rows IS NULL OR COALESCE(json_array_length(schedule_rows), 0) = 0 THEN
    RETURN json_build_object(
      'enrollmentStatus', v_enrollment_status,
      'message', 'Your enrollment is approved, but no class schedule is linked yet. Please contact the registrar or wait for the admin to publish schedules.',
      'schedule', '[]'::json
    );
  END IF;

  RETURN json_build_object(
    'enrollmentStatus', v_enrollment_status,
    'message', NULL,
    'schedule', schedule_rows
  );
END;
$$;

GRANT EXECUTE ON FUNCTION get_student_strand_schedule TO anon, authenticated, service_role;
