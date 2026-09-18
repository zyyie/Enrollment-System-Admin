-- Strand–subject enrollment validation
-- Run in Supabase SQL Editor after schema.sql
--
-- Rules:
--   • Core subjects (subjects.strand_id IS NULL) → all strands
--   • Specialized subjects → only matching student.strand_id
--   • Schedules must belong to student's strand + grade level

CREATE OR REPLACE FUNCTION get_enrollment_offerings(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_strand_id UUID;
  v_grade_level TEXT;
  result JSON;
BEGIN
  SELECT s.strand_id, s.grade_level
  INTO v_strand_id, v_grade_level
  FROM students s
  LEFT JOIN strands st ON st.id = s.strand_id
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_grade_level IS NULL THEN
    RETURN '[]'::json;
  END IF;

  SELECT COALESCE(json_agg(subject_row ORDER BY subject_row->>'code'), '[]'::json)
  INTO result
  FROM (
    SELECT json_build_object(
      'code', sub.code,
      'description', sub.name,
      'lec', sub.lec_hours,
      'lab', sub.lab_hours,
      'units', sub.units,
      'type', CASE WHEN sub.strand_id IS NULL THEN 'core' ELSE 'specialized' END,
      'strandCode', str_sub.code,
      'schedules', (
        SELECT COALESCE(json_agg(json_build_object(
          'id', cs.id,
          'slots', GREATEST(cs.max_slots - cs.enrolled_count, 0),
          'section', sec.name,
          'dayTime', cs.schedule_label
        ) ORDER BY sec.name), '[]'::json)
        FROM class_schedules cs
        JOIN sections sec ON sec.id = cs.section_id
        JOIN semesters sem ON sem.id = cs.semester_id
        WHERE cs.subject_id = sub.id
          AND cs.is_active = TRUE
          AND sem.is_current = TRUE
          AND sec.strand_id = v_strand_id
          AND sec.grade_level = v_grade_level
      )
    ) AS subject_row
    FROM subjects sub
    LEFT JOIN strands str_sub ON str_sub.id = sub.strand_id
    WHERE sub.is_active = TRUE
      AND sub.grade_level = v_grade_level
      AND (sub.strand_id IS NULL OR sub.strand_id = v_strand_id)
  ) offerings;

  RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION submit_student_enrollment(
  p_student_id TEXT,
  p_subjects JSON
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_strand_id UUID;
  v_grade_level TEXT;
  v_semester UUID;
  v_section UUID;
  v_enrollment UUID;
  v_total_units INT := 0;
  v_item JSON;
  v_subject UUID;
  v_sub_strand UUID;
  v_sub_grade TEXT;
  v_sub_code TEXT;
  v_schedule UUID;
  v_units INT;
  v_schedule_label TEXT;
  v_sched_strand UUID;
  v_sched_grade TEXT;
  v_count INT;
  v_max_subjects INT := 8;
BEGIN
  SELECT s.id, s.strand_id, s.grade_level, s.section_id
  INTO v_student, v_strand_id, v_grade_level, v_section
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RAISE EXCEPTION 'Student not found';
  END IF;

  IF v_strand_id IS NULL THEN
    RAISE EXCEPTION 'Student has no assigned strand. Contact the registrar.';
  END IF;

  v_count := json_array_length(p_subjects);
  IF v_count IS NULL OR v_count = 0 THEN
    RAISE EXCEPTION 'Select at least one subject';
  END IF;

  IF v_count > v_max_subjects THEN
    RAISE EXCEPTION 'Maximum % subjects allowed', v_max_subjects;
  END IF;

  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'No active semester configured';
  END IF;

  -- Validate every subject + schedule before writing
  FOR v_item IN SELECT * FROM json_array_elements(p_subjects)
  LOOP
    SELECT sub.id, sub.units, sub.strand_id, sub.grade_level, sub.code
    INTO v_subject, v_units, v_sub_strand, v_sub_grade, v_sub_code
    FROM subjects sub
    WHERE sub.code = v_item->>'code'
      AND sub.is_active = TRUE
    LIMIT 1;

    IF v_subject IS NULL THEN
      RAISE EXCEPTION 'Subject not found: %', v_item->>'code';
    END IF;

    IF v_sub_grade <> v_grade_level THEN
      RAISE EXCEPTION 'Subject % is not offered for %', v_sub_code, v_grade_level;
    END IF;

    IF v_sub_strand IS NOT NULL AND v_sub_strand <> v_strand_id THEN
      RAISE EXCEPTION 'Subject % is not available for your strand', v_sub_code;
    END IF;

    SELECT cs.id, cs.schedule_label, sec.strand_id, sec.grade_level
    INTO v_schedule, v_schedule_label, v_sched_strand, v_sched_grade
    FROM class_schedules cs
    JOIN sections sec ON sec.id = cs.section_id
    JOIN semesters sem ON sem.id = cs.semester_id
    WHERE cs.id = (v_item->>'scheduleId')::UUID
      AND cs.subject_id = v_subject
      AND cs.is_active = TRUE
      AND sem.is_current = TRUE
    LIMIT 1;

    IF v_schedule IS NULL THEN
      RAISE EXCEPTION 'Invalid schedule for subject %', v_sub_code;
    END IF;

    IF v_sched_strand <> v_strand_id THEN
      RAISE EXCEPTION 'Schedule for % does not match your strand', v_sub_code;
    END IF;

    IF v_sched_grade <> v_grade_level THEN
      RAISE EXCEPTION 'Schedule for % does not match your grade level', v_sub_code;
    END IF;

    v_total_units := v_total_units + COALESCE(v_units, 0);
  END LOOP;

  INSERT INTO enrollments (
    enrollment_number,
    student_id,
    semester_id,
    section_id,
    status,
    total_units,
    enrolled_at
  )
  VALUES (
    'ENR-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(FLOOR(random() * 10000)::TEXT, 4, '0'),
    v_student,
    v_semester,
    v_section,
    'pending',
    v_total_units,
    NOW()
  )
  ON CONFLICT (student_id, semester_id)
  DO UPDATE SET
    status = 'pending',
    total_units = EXCLUDED.total_units,
    enrolled_at = NOW(),
    updated_at = NOW()
  RETURNING id INTO v_enrollment;

  DELETE FROM enrollment_subjects WHERE enrollment_id = v_enrollment;

  FOR v_item IN SELECT * FROM json_array_elements(p_subjects)
  LOOP
    SELECT sub.id, sub.units
    INTO v_subject, v_units
    FROM subjects sub
    WHERE sub.code = v_item->>'code'
    LIMIT 1;

    SELECT cs.id, cs.schedule_label
    INTO v_schedule, v_schedule_label
    FROM class_schedules cs
    WHERE cs.id = (v_item->>'scheduleId')::UUID
      AND cs.subject_id = v_subject
    LIMIT 1;

    INSERT INTO enrollment_subjects (
      enrollment_id,
      subject_id,
      class_schedule_id,
      units,
      schedule_label
    )
    VALUES (
      v_enrollment,
      v_subject,
      v_schedule,
      v_units,
      COALESCE(v_schedule_label, v_item->>'scheduleLabel')
    );
  END LOOP;

  RETURN json_build_object(
    'success', TRUE,
    'enrollmentId', v_enrollment,
    'status', 'pending',
    'totalUnits', v_total_units
  );
END;
$$;

GRANT EXECUTE ON FUNCTION get_enrollment_offerings TO anon, authenticated;
GRANT EXECUTE ON FUNCTION submit_student_enrollment TO anon, authenticated;
