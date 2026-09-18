-- ============================================================
-- Enrollment photos + semester gating (run in Supabase SQL Editor)
-- Syncs with student portal enrollment step-by-step flow
-- Safe to re-run anytime
-- ============================================================

ALTER TABLE students
  ADD COLUMN IF NOT EXISTS enrollment_photo_upload_path TEXT,
  ADD COLUMN IF NOT EXISTS enrollment_photo_camera_path TEXT,
  ADD COLUMN IF NOT EXISTS enrollment_photos_semester_id UUID REFERENCES semesters(id);

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'enrollment-photos',
  'enrollment-photos',
  true,
  5242880,
  ARRAY['image/jpeg', 'image/png', 'image/webp']::text[]
)
ON CONFLICT (id) DO UPDATE
SET
  public = EXCLUDED.public,
  file_size_limit = EXCLUDED.file_size_limit,
  allowed_mime_types = EXCLUDED.allowed_mime_types;

DROP POLICY IF EXISTS "Public read enrollment photos" ON storage.objects;
CREATE POLICY "Public read enrollment photos"
ON storage.objects FOR SELECT
USING (bucket_id = 'enrollment-photos');

-- Save uploaded/captured enrollment photos for current semester
CREATE OR REPLACE FUNCTION save_student_enrollment_photos(
  p_student_id TEXT,
  p_photo_type TEXT,
  p_object_path TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_semester UUID;
  v_type TEXT := LOWER(TRIM(COALESCE(p_photo_type, '')));
  v_path TEXT := NULLIF(TRIM(p_object_path), '');
BEGIN
  IF v_path IS NULL THEN
    RAISE EXCEPTION 'Photo path is required';
  END IF;

  IF v_type NOT IN ('upload', 'camera') THEN
    RAISE EXCEPTION 'Invalid photo type. Use upload or camera.';
  END IF;

  SELECT s.id INTO v_student
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RAISE EXCEPTION 'Student not found';
  END IF;

  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'No active semester configured';
  END IF;

  IF v_type = 'upload' THEN
    UPDATE students
    SET
      enrollment_photo_upload_path = v_path,
      enrollment_photos_semester_id = v_semester,
      updated_at = NOW()
    WHERE id = v_student;
  ELSE
    UPDATE students
    SET
      enrollment_photo_camera_path = v_path,
      enrollment_photos_semester_id = v_semester,
      updated_at = NOW()
    WHERE id = v_student;
  END IF;

  RETURN get_student_enrollment_photos(p_student_id);
END;
$$;

-- Load enrollment photo status for current semester
CREATE OR REPLACE FUNCTION get_student_enrollment_photos(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_semester UUID;
  v_upload TEXT;
  v_camera TEXT;
  v_photos_semester UUID;
  v_semester_name TEXT;
BEGIN
  SELECT s.id, s.enrollment_photo_upload_path, s.enrollment_photo_camera_path, s.enrollment_photos_semester_id
  INTO v_student, v_upload, v_camera, v_photos_semester
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object(
      'uploadDone', FALSE,
      'cameraDone', FALSE,
      'photosReady', FALSE
    );
  END IF;

  SELECT id, name INTO v_semester, v_semester_name
  FROM semesters
  WHERE is_current = TRUE
  LIMIT 1;

  IF v_semester IS NULL OR v_photos_semester IS DISTINCT FROM v_semester THEN
    RETURN json_build_object(
      'uploadDone', FALSE,
      'cameraDone', FALSE,
      'photosReady', FALSE,
      'semester', v_semester_name
    );
  END IF;

  RETURN json_build_object(
    'uploadDone', v_upload IS NOT NULL AND TRIM(v_upload) <> '',
    'cameraDone', v_camera IS NOT NULL AND TRIM(v_camera) <> '',
    'photosReady', (
      v_upload IS NOT NULL AND TRIM(v_upload) <> ''
      AND v_camera IS NOT NULL AND TRIM(v_camera) <> ''
    ),
    'uploadPath', v_upload,
    'cameraPath', v_camera,
    'semester', v_semester_name
  );
END;
$$;

-- Improved enrollment access with semester-aware blocking
CREATE OR REPLACE FUNCTION get_student_enrollment_access(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_grade_level TEXT;
  v_account_status TEXT;
  v_progression TEXT;
  v_enrollment_open BOOLEAN;
  v_target_grade TEXT;
  v_current_status TEXT;
  v_semester_name TEXT;
  v_semester_code TEXT;
  v_can_enroll BOOLEAN := FALSE;
  v_reason TEXT := '';
  v_next_semester TEXT;
BEGIN
  SELECT s.id, s.grade_level, s.account_status, s.progression_status
  INTO v_student, v_grade_level, v_account_status, v_progression
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object('canEnroll', FALSE, 'reason', 'Student not found.');
  END IF;

  SELECT sem.enrollment_open, sem.target_grade_level, sem.name, sem.code
  INTO v_enrollment_open, v_target_grade, v_semester_name, v_semester_code
  FROM semesters sem
  WHERE sem.is_current = TRUE
  LIMIT 1;

  v_next_semester := CASE
    WHEN COALESCE(v_semester_code, '1st') = '1st' THEN '2nd Semester'
    ELSE 'the next school year (1st Semester)'
  END;

  SELECT e.status INTO v_current_status
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  WHERE e.student_id = v_student AND sem.is_current = TRUE
  LIMIT 1;

  IF v_account_status = 'frozen' THEN
    v_reason := 'Your account has been frozen due to non-enrollment during the official registration period. Please contact the registrar''s office.';
  ELSIF v_account_status = 'inactive' THEN
    v_reason := 'Your account is inactive. Please contact the registrar''s office.';
  ELSIF NOT COALESCE(v_enrollment_open, FALSE) THEN
    v_reason := format(
      'Enrollment is currently closed for %s. Please wait for the registrar to open the registration period.',
      COALESCE(v_semester_name, 'this term')
    );
  ELSIF v_current_status IN ('pending', 'approved', 'enrolled') THEN
    v_reason := format(
      'You already completed enrollment for %s (%s). Please wait for the registrar to open %s before enrolling again.',
      COALESCE(v_semester_name, 'this term'),
      COALESCE(v_grade_level, 'your grade level'),
      v_next_semester
    );
  ELSIF v_progression = 'retained_g11' AND v_grade_level = 'Grade 11' AND COALESCE(v_target_grade, v_grade_level) = 'Grade 12' THEN
    v_reason := 'You have unresolved failing grades in Grade 11. Grade 12 enrollment is not available until requirements are fulfilled. Please contact the registrar.';
  ELSIF v_progression = 'retained_g11' AND v_target_grade = 'Grade 12' THEN
    v_reason := 'You have unresolved failing grades in Grade 11. Grade 12 enrollment is locked.';
  ELSIF v_target_grade IS NOT NULL AND v_target_grade <> v_grade_level AND v_progression <> 'eligible_g12' THEN
    v_reason := format('Enrollment is open for %s only. You are currently listed as %s.', v_target_grade, v_grade_level);
  ELSE
    v_can_enroll := TRUE;
    v_reason := format('You may enroll for %s (%s).', COALESCE(v_semester_name, 'the current term'), COALESCE(v_grade_level, 'your grade level'));
  END IF;

  RETURN json_build_object(
    'canEnroll', v_can_enroll,
    'reason', v_reason,
    'enrollmentOpen', COALESCE(v_enrollment_open, FALSE),
    'accountStatus', v_account_status,
    'progressionStatus', v_progression,
    'gradeLevel', v_grade_level,
    'targetGradeLevel', v_target_grade,
    'currentEnrollmentStatus', v_current_status,
    'semesterName', v_semester_name,
    'semesterCode', v_semester_code,
    'nextSemesterLabel', v_next_semester
  );
END;
$$;

-- Require enrollment photos before subject submission
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
  v_max_subjects INT := 20;
  v_access JSON;
  v_enrollment_open BOOLEAN;
  v_account_status TEXT;
  v_upload_path TEXT;
  v_camera_path TEXT;
  v_photos_semester UUID;
BEGIN
  SELECT s.id, s.strand_id, s.grade_level, s.section_id, s.account_status,
         s.enrollment_photo_upload_path, s.enrollment_photo_camera_path, s.enrollment_photos_semester_id
  INTO v_student, v_strand_id, v_grade_level, v_section, v_account_status,
       v_upload_path, v_camera_path, v_photos_semester
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RAISE EXCEPTION 'Student not found';
  END IF;

  IF v_account_status IN ('frozen', 'inactive') THEN
    RAISE EXCEPTION 'Your account cannot enroll. Contact the registrar.';
  END IF;

  IF v_strand_id IS NULL THEN
    RAISE EXCEPTION 'Student has no assigned strand. Contact the registrar.';
  END IF;

  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'No active semester configured';
  END IF;

  IF v_photos_semester IS DISTINCT FROM v_semester
     OR v_upload_path IS NULL OR TRIM(v_upload_path) = ''
     OR v_camera_path IS NULL OR TRIM(v_camera_path) = '' THEN
    RAISE EXCEPTION 'Please complete Step 1 (Upload Photo) and Step 2 (Take Photo) before submitting enrollment.';
  END IF;

  v_access := get_student_enrollment_access(p_student_id);
  IF NOT COALESCE((v_access->>'canEnroll')::BOOLEAN, FALSE) THEN
    RAISE EXCEPTION '%', COALESCE(v_access->>'reason', 'Enrollment is not available.');
  END IF;

  SELECT enrollment_open INTO v_enrollment_open FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF NOT COALESCE(v_enrollment_open, FALSE) THEN
    RAISE EXCEPTION 'Enrollment is closed for the current term.';
  END IF;

  v_count := json_array_length(p_subjects);
  IF v_count IS NULL OR v_count = 0 THEN
    RAISE EXCEPTION 'Select at least one subject';
  END IF;

  IF v_count > v_max_subjects THEN
    RAISE EXCEPTION 'Maximum % subjects allowed', v_max_subjects;
  END IF;

  FOR v_item IN SELECT * FROM json_array_elements(p_subjects)
  LOOP
    SELECT sub.id, sub.units, sub.strand_id, sub.grade_level, sub.code
    INTO v_subject, v_units, v_sub_strand, v_sub_grade, v_sub_code
    FROM subjects sub
    WHERE sub.code = v_item->>'code' AND sub.is_active = TRUE
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
    WHERE cs.id = resolve_class_schedule_id(v_item->>'scheduleId', v_subject, v_strand_id, v_grade_level)
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
    enrollment_number, student_id, semester_id, section_id,
    status, total_units, enrolled_at
  )
  VALUES (
    'ENR-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(FLOOR(random() * 10000)::TEXT, 4, '0'),
    v_student, v_semester, v_section,
    'pending', v_total_units, NOW()
  )
  ON CONFLICT (student_id, semester_id)
  DO UPDATE SET
    status = 'pending',
    total_units = EXCLUDED.total_units,
    enrolled_at = NOW(),
    updated_at = NOW(),
    rejection_reason = NULL,
    reviewed_by = NULL,
    reviewed_at = NULL
  RETURNING id INTO v_enrollment;

  DELETE FROM enrollment_subjects WHERE enrollment_id = v_enrollment;

  FOR v_item IN SELECT * FROM json_array_elements(p_subjects)
  LOOP
    SELECT sub.id, sub.units INTO v_subject, v_units
    FROM subjects sub WHERE sub.code = v_item->>'code' LIMIT 1;

    SELECT cs.id, cs.schedule_label INTO v_schedule, v_schedule_label
    FROM class_schedules cs
    WHERE cs.id = resolve_class_schedule_id(v_item->>'scheduleId', v_subject, v_strand_id, v_grade_level)
      AND cs.subject_id = v_subject
    LIMIT 1;

    INSERT INTO enrollment_subjects (
      enrollment_id, subject_id, class_schedule_id, units, schedule_label, status
    ) VALUES (
      v_enrollment, v_subject, v_schedule, v_units,
      COALESCE(v_schedule_label, v_item->>'scheduleLabel'), 'enrolled'
    );
  END LOOP;

  PERFORM insert_student_notification(
    v_student,
    'Enrollment Submitted',
    'Your enrollment submission is pending review and approval by the Administrator.',
    'enrollment'
  );

  RETURN json_build_object(
    'success', TRUE,
    'enrollmentId', v_enrollment,
    'status', 'pending',
    'totalUnits', v_total_units
  );
END;
$$;

GRANT EXECUTE ON FUNCTION save_student_enrollment_photos TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_enrollment_photos TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_enrollment_access TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION submit_student_enrollment TO anon, authenticated, service_role;
