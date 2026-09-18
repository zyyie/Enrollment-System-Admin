-- Enrollment workflow, grades, progression, and account freezing
-- Run in Supabase SQL Editor AFTER schema.sql

-- ── 0. Patch enrollment tables (safe re-run) ─────────────────
ALTER TABLE enrollment_subjects ADD COLUMN IF NOT EXISTS schedule_label TEXT;
ALTER TABLE enrollment_subjects ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'enrolled';

-- Notifications — fix legacy recipient_id FK + support student_id column
CREATE TABLE IF NOT EXISTS notifications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  student_id UUID REFERENCES students(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  message TEXT,
  type TEXT DEFAULT 'announcement',
  has_pdf BOOLEAN DEFAULT FALSE,
  is_read BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

DO $$
DECLARE
  v_fk_name TEXT;
  v_fk_table TEXT;
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = 'public' AND table_name = 'notifications'
  ) THEN
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'student_id'
  ) THEN
    ALTER TABLE notifications ADD COLUMN student_id UUID REFERENCES students(id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'recipient_id'
  ) THEN
    ALTER TABLE notifications ADD COLUMN recipient_id UUID REFERENCES students(id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'recipient_type'
  ) THEN
    ALTER TABLE notifications ADD COLUMN recipient_type TEXT DEFAULT 'student';
  END IF;

  SELECT tc.constraint_name, ccu.table_name
  INTO v_fk_name, v_fk_table
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
  JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.table_schema = tc.table_schema
  WHERE tc.table_schema = 'public'
    AND tc.table_name = 'notifications'
    AND tc.constraint_type = 'FOREIGN KEY'
    AND kcu.column_name = 'recipient_id'
  LIMIT 1;

  IF v_fk_name IS NOT NULL AND COALESCE(v_fk_table, '') <> 'students' THEN
    EXECUTE format('ALTER TABLE public.notifications DROP CONSTRAINT IF EXISTS %I', v_fk_name);
    ALTER TABLE notifications ALTER COLUMN recipient_id DROP NOT NULL;
    UPDATE notifications SET recipient_id = NULL
    WHERE recipient_id IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM students s WHERE s.id = notifications.recipient_id);
    BEGIN
      ALTER TABLE notifications
        ADD CONSTRAINT notifications_recipient_id_fkey
        FOREIGN KEY (recipient_id) REFERENCES students(id) ON DELETE SET NULL;
    EXCEPTION WHEN duplicate_object THEN
      NULL;
    END;
  END IF;

  BEGIN
    ALTER TABLE notifications ALTER COLUMN recipient_id DROP NOT NULL;
  EXCEPTION WHEN OTHERS THEN
    NULL;
  END;

  UPDATE notifications SET student_id = recipient_id
  WHERE student_id IS NULL AND recipient_id IS NOT NULL
    AND EXISTS (SELECT 1 FROM students s WHERE s.id = notifications.recipient_id);

  UPDATE notifications SET recipient_id = student_id
  WHERE recipient_id IS NULL AND student_id IS NOT NULL
    AND EXISTS (SELECT 1 FROM students s WHERE s.id = notifications.student_id);

  UPDATE notifications SET recipient_type = COALESCE(recipient_type, 'student')
  WHERE recipient_type IS NULL;
END $$;

ALTER TABLE notifications ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS message TEXT;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'announcement';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS has_pdf BOOLEAN DEFAULT FALSE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT FALSE;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS recipient_type TEXT DEFAULT 'student';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS student_id UUID;

CREATE INDEX IF NOT EXISTS idx_notifications_student ON notifications(student_id);
CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_id);

CREATE OR REPLACE FUNCTION insert_student_notification(
  p_student UUID,
  p_title TEXT,
  p_message TEXT DEFAULT NULL,
  p_type TEXT DEFAULT 'announcement'
)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_id UUID;
  v_has_recipient BOOLEAN;
  v_has_student BOOLEAN;
  v_has_recipient_type BOOLEAN;
  v_recipient_fk_table TEXT;
  v_use_recipient BOOLEAN;
BEGIN
  IF p_student IS NULL THEN
    RETURN NULL;
  END IF;

  IF NOT EXISTS (SELECT 1 FROM students s WHERE s.id = p_student) THEN
    RETURN NULL;
  END IF;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'recipient_id'
  ) INTO v_has_recipient;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'student_id'
  ) INTO v_has_student;

  SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public' AND table_name = 'notifications' AND column_name = 'recipient_type'
  ) INTO v_has_recipient_type;

  SELECT ccu.table_name INTO v_recipient_fk_table
  FROM information_schema.table_constraints tc
  JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema = kcu.table_schema
  JOIN information_schema.constraint_column_usage ccu
    ON ccu.constraint_name = tc.constraint_name
   AND ccu.table_schema = tc.table_schema
  WHERE tc.table_schema = 'public'
    AND tc.table_name = 'notifications'
    AND tc.constraint_type = 'FOREIGN KEY'
    AND kcu.column_name = 'recipient_id'
  LIMIT 1;

  v_use_recipient := v_has_recipient
    AND (v_recipient_fk_table IS NULL OR v_recipient_fk_table = 'students');

  IF v_use_recipient AND v_has_student AND v_has_recipient_type THEN
    INSERT INTO notifications (recipient_id, recipient_type, student_id, title, message, type)
    VALUES (p_student, 'student', p_student, p_title, p_message, p_type)
    RETURNING id INTO v_id;
  ELSIF v_use_recipient AND v_has_student THEN
    INSERT INTO notifications (recipient_id, student_id, title, message, type)
    VALUES (p_student, p_student, p_title, p_message, p_type)
    RETURNING id INTO v_id;
  ELSIF v_use_recipient AND v_has_recipient_type THEN
    INSERT INTO notifications (recipient_id, recipient_type, title, message, type)
    VALUES (p_student, 'student', p_title, p_message, p_type)
    RETURNING id INTO v_id;
  ELSIF v_use_recipient THEN
    INSERT INTO notifications (recipient_id, title, message, type)
    VALUES (p_student, p_title, p_message, p_type)
    RETURNING id INTO v_id;
  ELSIF v_has_student THEN
    INSERT INTO notifications (student_id, title, message, type)
    VALUES (p_student, p_title, p_message, p_type)
    RETURNING id INTO v_id;
  ELSE
    INSERT INTO notifications (title, message, type)
    VALUES (p_title, p_message, p_type)
    RETURNING id INTO v_id;
  END IF;

  RETURN v_id;
EXCEPTION WHEN OTHERS THEN
  RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION get_student_notifications(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    FROM (
      SELECT
        TO_CHAR(n.created_at, 'Month DD, YYYY') AS date,
        n.title,
        COALESCE(n.has_pdf, FALSE) AS "hasPdf"
      FROM notifications n
      JOIN students s ON s.id = COALESCE(n.student_id, n.recipient_id)
      WHERE s.student_id = UPPER(TRIM(p_student_id))
      ORDER BY n.created_at DESC
    ) t
  );
END;
$$;

ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS rejection_reason TEXT;
ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS enrolled_at TIMESTAMPTZ;
ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS max_subjects_allowed INT DEFAULT 20;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'enrollments'
      AND column_name = 'reviewed_by'
  ) THEN
    ALTER TABLE enrollments ADD COLUMN reviewed_by UUID REFERENCES faculty(id);
  END IF;
END $$;

-- ── 1. Student account & progression fields ─────────────────
ALTER TABLE students ADD COLUMN IF NOT EXISTS account_status TEXT NOT NULL DEFAULT 'active'
  CHECK (account_status IN ('active', 'frozen', 'inactive'));

ALTER TABLE students ADD COLUMN IF NOT EXISTS progression_status TEXT NOT NULL DEFAULT 'in_progress'
  CHECK (progression_status IN ('in_progress', 'eligible_g12', 'retained_g11', 'graduated'));

ALTER TABLE students ADD COLUMN IF NOT EXISTS grade11_completed BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE semesters ADD COLUMN IF NOT EXISTS target_grade_level TEXT
  CHECK (target_grade_level IS NULL OR target_grade_level IN ('Grade 11', 'Grade 12'));

-- ── 2. Grades table ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS student_grades (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  enrollment_subject_id UUID NOT NULL UNIQUE REFERENCES enrollment_subjects(id) ON DELETE CASCADE,
  midterm_grade NUMERIC(5,2),
  final_grade NUMERIC(5,2),
  grade_status TEXT NOT NULL DEFAULT 'incomplete'
    CHECK (grade_status IN ('passed', 'failed', 'incomplete', 'dropped')),
  encoded_by UUID REFERENCES faculty(id),
  encoded_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_student_grades_enrollment_subject ON student_grades(enrollment_subject_id);

-- ── 3. Authenticate — approval email credentials + frozen check ──
-- Sync student row with Gmail approval credentials before login attempts
UPDATE students s
SET
  password = a.temp_password,
  birthdate = COALESCE(s.birthdate, a.birthdate),
  is_active = TRUE,
  updated_at = NOW()
FROM admission_applications a
WHERE a.status = 'approved'
  AND UPPER(a.student_id_generated) = UPPER(s.student_id)
  AND a.temp_password IS NOT NULL
  AND (
    s.password IS NULL OR TRIM(s.password) = ''
    OR TRIM(s.password) <> TRIM(a.temp_password)
  );

CREATE OR REPLACE FUNCTION authenticate_student(
  p_student_id TEXT,
  p_birth_month INT,
  p_birth_day INT,
  p_birth_year INT,
  p_password TEXT
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
  v_password TEXT := TRIM(p_password);
  v_student_id TEXT := UPPER(TRIM(p_student_id));
  v_account_status TEXT;
BEGIN
  IF v_student_id = '' OR v_password = '' THEN
    RETURN NULL;
  END IF;

  -- 1) Primary: students table (created on approve)
  SELECT
    COALESCE(s.account_status, 'active'),
    json_build_object(
      'id', s.student_id,
      'supabaseId', s.id,
      'lastName', s.last_name,
      'firstName', s.first_name,
      'middleName', COALESCE(s.middle_name, ''),
      'birthMonth', EXTRACT(MONTH FROM s.birthdate)::TEXT,
      'birthDay', EXTRACT(DAY FROM s.birthdate)::TEXT,
      'birthYear', EXTRACT(YEAR FROM s.birthdate)::TEXT,
      'gradeLevel', s.grade_level,
      'strand', COALESCE(st.code, 'GAS'),
      'strandFull', COALESCE(st.name, st.code, 'GAS'),
      'section', COALESCE(sec.name, ''),
      'track', COALESCE(s.track, 'Academic'),
      'admissionStatus', COALESCE(s.admission_status, 'approved'),
      'scholasticStatus', COALESCE(s.scholastic_status, 'Regular'),
      'accountStatus', COALESCE(s.account_status, 'active'),
      'progressionStatus', COALESCE(s.progression_status, 'in_progress'),
      'grade11Completed', COALESCE(s.grade11_completed, FALSE),
      'schoolYear', COALESCE(sy.label, '2026-2027'),
      'semester', COALESCE(sem.name, 'First Semester'),
      'semesterCode', COALESCE(sem.code, '1st'),
      'enrollmentOpen', COALESCE(sem.enrollment_open, FALSE),
      'voucherQualified', COALESCE(s.voucher_qualified, FALSE)
    )
  INTO v_account_status, result
  FROM students s
  LEFT JOIN strands st ON st.id = s.strand_id
  LEFT JOIN sections sec ON sec.id = s.section_id
  LEFT JOIN semesters sem ON sem.is_current = TRUE
  LEFT JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE UPPER(s.student_id) = v_student_id
    AND TRIM(s.password) = v_password
    AND s.birthdate IS NOT NULL
    AND EXTRACT(MONTH FROM s.birthdate)::INT = p_birth_month
    AND EXTRACT(DAY FROM s.birthdate)::INT = p_birth_day
    AND EXTRACT(YEAR FROM s.birthdate)::INT = p_birth_year
    AND COALESCE(s.is_active, TRUE) = TRUE
  LIMIT 1;

  IF result IS NOT NULL THEN
    IF v_account_status = 'frozen' THEN
      RETURN json_build_object(
        'error', 'ACCOUNT_FROZEN',
        'message', 'Your account has been frozen due to non-enrollment during the official registration period. Please contact the registrar''s office.'
      );
    END IF;
    IF v_account_status = 'inactive' THEN
      RETURN json_build_object(
        'error', 'ACCOUNT_INACTIVE',
        'message', 'Your account is inactive. Please contact the registrar''s office.'
      );
    END IF;
    RETURN result;
  END IF;

  -- 2) Fallback: approved admission (exact Gmail credentials)
  SELECT json_build_object(
    'id', a.student_id_generated,
    'supabaseId', NULL,
    'lastName', a.last_name,
    'firstName', a.first_name,
    'middleName', COALESCE(a.middle_name, ''),
    'birthMonth', EXTRACT(MONTH FROM a.birthdate)::TEXT,
    'birthDay', EXTRACT(DAY FROM a.birthdate)::TEXT,
    'birthYear', EXTRACT(YEAR FROM a.birthdate)::TEXT,
    'gradeLevel', a.grade_level,
    'strand', COALESCE(st.code, 'GAS'),
    'strandFull', COALESCE(st.name, st.code, 'GAS'),
    'section', '',
    'track', 'Academic',
    'admissionStatus', 'approved',
    'scholasticStatus', 'Regular',
    'accountStatus', 'active',
    'progressionStatus', 'in_progress',
    'grade11Completed', FALSE,
    'schoolYear', '2026-2027',
    'semester', 'First Semester',
    'semesterCode', '1st',
    'enrollmentOpen', FALSE,
    'voucherQualified', FALSE
  )
  INTO result
  FROM admission_applications a
  LEFT JOIN strands st ON st.id = a.strand_id
  WHERE a.status = 'approved'
    AND UPPER(a.student_id_generated) = v_student_id
    AND TRIM(a.temp_password) = v_password
    AND a.birthdate IS NOT NULL
    AND EXTRACT(MONTH FROM a.birthdate)::INT = p_birth_month
    AND EXTRACT(DAY FROM a.birthdate)::INT = p_birth_day
    AND EXTRACT(YEAR FROM a.birthdate)::INT = p_birth_year
  LIMIT 1;

  IF result IS NOT NULL THEN
    INSERT INTO students (
      student_id, last_name, first_name, middle_name, birthdate, password,
      gender, address, contact_number, admission_type, admission_status,
      grade_level, strand_id, scholastic_status, track, is_active, account_status
    )
    SELECT
      a.student_id_generated, a.last_name, a.first_name, a.middle_name,
      a.birthdate, a.temp_password, a.gender, a.address, a.contact_number,
      COALESCE(a.admission_type, 'new'), 'approved', a.grade_level, a.strand_id,
      'Regular', 'Academic', TRUE, 'active'
    FROM admission_applications a
    WHERE a.status = 'approved'
      AND UPPER(a.student_id_generated) = v_student_id
    ON CONFLICT (student_id) DO UPDATE SET
      password = EXCLUDED.password,
      birthdate = EXCLUDED.birthdate,
      is_active = TRUE,
      account_status = 'active',
      updated_at = NOW();
  END IF;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION authenticate_student TO anon, authenticated, service_role;

-- ── 4. Enrollment access check ──────────────────────────────
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

-- ── 5. Submit enrollment (with schedule resolution) ─────────
CREATE OR REPLACE FUNCTION resolve_class_schedule_id(
  p_schedule_id TEXT,
  p_subject_id UUID,
  p_strand_id UUID,
  p_grade_level TEXT
)
RETURNS UUID
LANGUAGE plpgsql
STABLE
SET search_path = public
AS $$
DECLARE
  v_id UUID;
BEGIN
  IF COALESCE(TRIM(p_schedule_id), '') ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$' THEN
    RETURN p_schedule_id::UUID;
  END IF;

  SELECT cs.id INTO v_id
  FROM class_schedules cs
  JOIN sections sec ON sec.id = cs.section_id
  JOIN semesters sem ON sem.id = cs.semester_id
  WHERE cs.subject_id = p_subject_id
    AND sec.strand_id = p_strand_id
    AND sec.grade_level = p_grade_level
    AND sem.is_current = TRUE
    AND cs.is_active = TRUE
  ORDER BY sec.name, cs.schedule_label
  LIMIT 1;

  RETURN v_id;
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

  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF v_semester IS NULL THEN
    RAISE EXCEPTION 'No active semester configured';
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

-- ── 6. Review enrollment — approve sets ENROLLED ────────────
CREATE OR REPLACE FUNCTION review_enrollment(
  p_enrollment_id UUID,
  p_faculty_id TEXT,
  p_action TEXT,
  p_reason TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_faculty UUID;
  v_new_status TEXT;
  v_student UUID;
BEGIN
  SELECT id INTO v_faculty
  FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  v_new_status := CASE
    WHEN LOWER(p_action) = 'approve' THEN 'enrolled'
    WHEN LOWER(p_action) = 'reject' THEN 'rejected'
    ELSE NULL
  END;

  IF v_new_status IS NULL THEN
    RAISE EXCEPTION 'Invalid action';
  END IF;

  UPDATE enrollments e
  SET
    status = v_new_status,
    reviewed_by = v_faculty,
    reviewed_at = NOW(),
    rejection_reason = CASE WHEN v_new_status = 'rejected' THEN p_reason ELSE NULL END,
    updated_at = NOW(),
    enrolled_at = CASE WHEN v_new_status = 'enrolled' THEN NOW() ELSE enrolled_at END
  WHERE e.id = p_enrollment_id
  RETURNING e.student_id INTO v_student;

  IF v_student IS NOT NULL THEN
    PERFORM insert_student_notification(
      v_student,
      CASE WHEN v_new_status = 'enrolled' THEN 'Enrollment Approved' ELSE 'Enrollment Rejected' END,
      CASE WHEN v_new_status = 'enrolled'
        THEN 'Your enrollment has been approved. You are now officially enrolled for this term.'
        ELSE COALESCE('Your enrollment was rejected. ' || p_reason, 'Your enrollment was rejected. Contact the registrar.')
      END,
      'enrollment'
    );
  END IF;

  IF v_new_status = 'enrolled' THEN
    PERFORM ensure_enrollment_payment(p_enrollment_id);

    UPDATE class_schedules cs
    SET enrolled_count = sub.cnt
    FROM (
      SELECT es.class_schedule_id, COUNT(*) AS cnt
      FROM enrollment_subjects es
      JOIN enrollments e ON e.id = es.enrollment_id
      WHERE e.status = 'enrolled'
        AND COALESCE(es.status, 'enrolled') = 'enrolled'
      GROUP BY es.class_schedule_id
    ) sub
    WHERE cs.id = sub.class_schedule_id;
  END IF;

  RETURN json_build_object('success', TRUE, 'status', v_new_status);
END;
$$;

-- ── 7. Enrollment detail for admin review ───────────────────
CREATE OR REPLACE FUNCTION get_enrollment_detail(p_enrollment_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'id', e.id,
    'enrollmentNumber', e.enrollment_number,
    'status', e.status,
    'totalUnits', e.total_units,
    'submittedAt', TO_CHAR(e.created_at, 'Mon DD, YYYY HH12:MI AM'),
    'student', json_build_object(
      'id', st.student_id,
      'name', CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(st.middle_name, '')),
      'gradeLevel', st.grade_level,
      'strand', str.code,
      'strandFull', str.name,
      'section', COALESCE(sec.name, ''),
      'progressionStatus', st.progression_status,
      'accountStatus', st.account_status
    ),
    'term', json_build_object(
      'schoolYear', sy.label,
      'semester', sem.name,
      'semesterCode', sem.code
    ),
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
  JOIN students st ON st.id = e.student_id
  LEFT JOIN strands str ON str.id = st.strand_id
  LEFT JOIN sections sec ON sec.id = st.section_id
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE e.id = p_enrollment_id;

  RETURN result;
END;
$$;

-- ── 8. Term / enrollment period controls ────────────────────
CREATE OR REPLACE FUNCTION ensure_current_enrollment_term()
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_sy UUID;
  v_semester UUID;
BEGIN
  SELECT id INTO v_semester FROM semesters WHERE is_current = TRUE LIMIT 1;
  IF v_semester IS NOT NULL THEN
    RETURN v_semester;
  END IF;

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

  SELECT id INTO v_semester
  FROM semesters
  WHERE school_year_id = v_sy AND name = 'First Semester'
  LIMIT 1;

  IF v_semester IS NULL THEN
    INSERT INTO semesters (school_year_id, name, code, is_current, enrollment_open, start_date, end_date)
    VALUES (v_sy, 'First Semester', '1st', TRUE, FALSE, '2026-08-01', '2026-12-15')
    RETURNING id INTO v_semester;
  ELSE
    UPDATE semesters SET is_current = TRUE WHERE id = v_semester;
  END IF;

  UPDATE semesters SET is_current = FALSE WHERE school_year_id = v_sy AND id <> v_semester;
  RETURN v_semester;
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_period()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  PERFORM ensure_current_enrollment_term();

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
    'isCurrent', sem.is_current
  )
  INTO result
  FROM semesters sem
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE sem.is_current = TRUE
  LIMIT 1;

  RETURN COALESCE(result, '{}'::json);
END;
$$;

CREATE OR REPLACE FUNCTION set_enrollment_period(
  p_enrollment_open BOOLEAN,
  p_target_grade_level TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_semester UUID;
BEGIN
  v_semester := ensure_current_enrollment_term();

  UPDATE semesters
  SET
    enrollment_open = p_enrollment_open,
    target_grade_level = NULLIF(TRIM(p_target_grade_level), '')
  WHERE id = v_semester;

  IF NOT p_enrollment_open THEN
    PERFORM freeze_inactive_students();
  END IF;

  RETURN json_build_object(
    'success', TRUE,
    'enrollmentOpen', p_enrollment_open,
    'targetGradeLevel', NULLIF(TRIM(p_target_grade_level), '')
  );
END;
$$;

-- ── 9. Freeze inactive students when period closes ───────────
CREATE OR REPLACE FUNCTION freeze_inactive_students()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_frozen INT := 0;
BEGIN
  UPDATE students s
  SET
    account_status = 'frozen',
    updated_at = NOW()
  WHERE s.is_active = TRUE
    AND s.account_status = 'active'
    AND s.admission_status IN ('approved', 'enrolled')
    AND NOT EXISTS (
      SELECT 1 FROM enrollments e
      JOIN semesters sem ON sem.id = e.semester_id
      WHERE e.student_id = s.id
        AND sem.is_current = TRUE
        AND e.status IN ('pending', 'approved', 'enrolled')
    );

  GET DIAGNOSTICS v_frozen = ROW_COUNT;

  RETURN json_build_object('success', TRUE, 'frozenCount', v_frozen);
END;
$$;

-- ── 10. Student grades ──────────────────────────────────────
CREATE OR REPLACE FUNCTION get_student_grades(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_student UUID;
  v_enrollment_status TEXT;
  v_terms JSON;
BEGIN
  SELECT s.id INTO v_student
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object(
      'enrollmentStatus', 'none',
      'message', 'Student account not found.',
      'terms', '[]'::json
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
      'terms', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'pending' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'pending',
      'message', 'Your enrollment is pending admin approval. Your subjects and grades will appear here once you are officially enrolled.',
      'terms', '[]'::json
    );
  END IF;

  IF v_enrollment_status = 'rejected' THEN
    RETURN json_build_object(
      'enrollmentStatus', 'rejected',
      'message', 'Your enrollment was not approved. Please contact the registrar office.',
      'terms', '[]'::json
    );
  END IF;

  SELECT COALESCE(json_agg(term_row ORDER BY label DESC, code), '[]'::json)
  INTO v_terms
  FROM (
    SELECT json_build_object(
      'schoolYear', sy.label,
      'semester', sem.name,
      'semesterCode', sem.code,
      'gpa', (
        SELECT ROUND(AVG(sg.final_grade)::numeric, 2)
        FROM enrollment_subjects es2
        LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es2.id
        WHERE es2.enrollment_id = e.id
          AND sg.final_grade IS NOT NULL
          AND sg.grade_status = 'passed'
      ),
      'subjects', (
        SELECT COALESCE(json_agg(json_build_object(
          'code', sub.code,
          'description', sub.name,
          'faculty', COALESCE(NULLIF(TRIM(CONCAT(f.last_name, ', ', f.first_name)), ','), 'TBA'),
          'units', es.units,
          'sectCode', COALESCE(sec.name, ''),
          'midtermGrade', sg.midterm_grade,
          'finalGrade', sg.final_grade,
          'status', CASE
            WHEN sg.id IS NULL OR sg.grade_status IS NULL OR sg.grade_status = 'incomplete' THEN 'INC'
            WHEN sg.grade_status = 'passed' THEN 'P'
            WHEN sg.grade_status = 'failed' THEN 'F'
            WHEN sg.grade_status = 'dropped' THEN 'D'
            ELSE 'INC'
          END
        ) ORDER BY sub.code), '[]'::json)
        FROM enrollment_subjects es
        JOIN subjects sub ON sub.id = es.subject_id
        LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
        LEFT JOIN class_schedules cs ON cs.id = es.class_schedule_id
        LEFT JOIN faculty f ON f.id = cs.faculty_id
        LEFT JOIN sections sec ON sec.id = cs.section_id
        WHERE es.enrollment_id = e.id
          AND es.status = 'enrolled'
      )
    ) AS term_row,
    sy.label AS label,
    sem.code AS code
    FROM enrollments e
    JOIN students st ON st.id = e.student_id
    JOIN semesters sem ON sem.id = e.semester_id
    JOIN school_years sy ON sy.id = sem.school_year_id
    WHERE st.student_id = UPPER(TRIM(p_student_id))
      AND e.status IN ('approved', 'enrolled')
    GROUP BY e.id, sy.label, sem.name, sem.code
  ) t;

  RETURN json_build_object(
    'enrollmentStatus', v_enrollment_status,
    'message', NULL,
    'terms', v_terms
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_students_for_grading(
  p_grade_level TEXT DEFAULT NULL,
  p_strand_code TEXT DEFAULT NULL
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    FROM (
      SELECT
        st.student_id AS "studentId",
        CONCAT(st.last_name, ', ', st.first_name) AS student,
        st.grade_level AS "gradeLevel",
        str.code AS strand,
        e.id AS "enrollmentId",
        sem.name AS semester
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      WHERE e.status IN ('enrolled', 'approved')
        AND sem.is_current = TRUE
        AND (p_grade_level IS NULL OR st.grade_level = p_grade_level)
        AND (p_strand_code IS NULL OR str.code = UPPER(TRIM(p_strand_code)))
      ORDER BY st.last_name, st.first_name
    ) t
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_grades_sheet(p_enrollment_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN (
    SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
    FROM (
      SELECT
        es.id AS "enrollmentSubjectId",
        sub.code,
        sub.name AS description,
        es.units,
        sg.midterm_grade AS "midtermGrade",
        sg.final_grade AS "finalGrade",
        COALESCE(sg.grade_status, 'incomplete') AS "gradeStatus"
      FROM enrollment_subjects es
      JOIN subjects sub ON sub.id = es.subject_id
      LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
      WHERE es.enrollment_id = p_enrollment_id
      ORDER BY sub.code
    ) t
  );
END;
$$;

CREATE OR REPLACE FUNCTION save_student_grades(
  p_enrollment_id UUID,
  p_faculty_id TEXT,
  p_grades JSON
)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_faculty UUID;
  v_student UUID;
  v_grade_level TEXT;
  v_item JSON;
  v_es_id UUID;
  v_final NUMERIC;
  v_midterm NUMERIC;
  v_status TEXT;
  v_passing NUMERIC := 75;
BEGIN
  SELECT id INTO v_faculty FROM faculty WHERE faculty_id = UPPER(TRIM(p_faculty_id)) LIMIT 1;

  SELECT e.student_id, st.grade_level
  INTO v_student, v_grade_level
  FROM enrollments e
  JOIN students st ON st.id = e.student_id
  WHERE e.id = p_enrollment_id AND e.status = 'enrolled'
  LIMIT 1;

  IF v_student IS NULL THEN
    RAISE EXCEPTION 'Enrollment not found or not enrolled';
  END IF;

  FOR v_item IN SELECT * FROM json_array_elements(p_grades)
  LOOP
    v_es_id := (v_item->>'enrollmentSubjectId')::UUID;
    v_midterm := NULLIF(v_item->>'midtermGrade', '')::NUMERIC;
    v_final := NULLIF(v_item->>'finalGrade', '')::NUMERIC;

    IF v_final IS NULL THEN
      v_status := 'incomplete';
    ELSIF v_final >= v_passing THEN
      v_status := 'passed';
    ELSE
      v_status := 'failed';
    END IF;

    INSERT INTO student_grades (
      enrollment_subject_id, midterm_grade, final_grade, grade_status, encoded_by, updated_at
    )
    VALUES (v_es_id, v_midterm, v_final, v_status, v_faculty, NOW())
    ON CONFLICT (enrollment_subject_id)
    DO UPDATE SET
      midterm_grade = EXCLUDED.midterm_grade,
      final_grade = EXCLUDED.final_grade,
      grade_status = EXCLUDED.grade_status,
      encoded_by = EXCLUDED.encoded_by,
      updated_at = NOW();

    UPDATE enrollment_subjects
    SET status = CASE WHEN v_status IN ('passed', 'failed') THEN 'completed' ELSE status END
    WHERE id = v_es_id;
  END LOOP;

  PERFORM evaluate_student_progression(v_student);

  RETURN json_build_object('success', TRUE);
END;
$$;

CREATE OR REPLACE FUNCTION evaluate_student_progression(p_student_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_grade_level TEXT;
  v_total INT := 0;
  v_graded INT := 0;
  v_failed INT := 0;
  v_new_progression TEXT;
BEGIN
  SELECT grade_level INTO v_grade_level FROM students WHERE id = p_student_id;

  IF v_grade_level <> 'Grade 11' THEN
    RETURN json_build_object('evaluated', FALSE, 'reason', 'Not Grade 11');
  END IF;

  SELECT
    COUNT(*),
    COUNT(*) FILTER (WHERE sg.id IS NOT NULL AND sg.final_grade IS NOT NULL),
    COUNT(*) FILTER (WHERE sg.grade_status = 'failed')
  INTO v_total, v_graded, v_failed
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  JOIN enrollment_subjects es ON es.enrollment_id = e.id
  LEFT JOIN student_grades sg ON sg.enrollment_subject_id = es.id
  WHERE e.student_id = p_student_id
    AND e.status = 'enrolled';

  IF v_total = 0 OR v_graded < v_total THEN
    RETURN json_build_object('evaluated', FALSE, 'reason', 'Grades incomplete', 'graded', v_graded, 'total', v_total);
  END IF;

  IF v_failed > 0 THEN
    v_new_progression := 'retained_g11';
    UPDATE students SET
      progression_status = v_new_progression,
      grade11_completed = FALSE,
      updated_at = NOW()
    WHERE id = p_student_id;
  ELSE
    v_new_progression := 'eligible_g12';
    UPDATE students SET
      progression_status = v_new_progression,
      grade_level = 'Grade 12',
      grade11_completed = TRUE,
      updated_at = NOW()
    WHERE id = p_student_id;
  END IF;

  RETURN json_build_object(
    'evaluated', TRUE,
    'progressionStatus', v_new_progression,
    'failedCount', v_failed
  );
END;
$$;

-- ── Offerings: only subjects with real schedules in DB ──────
ALTER TABLE subjects ADD COLUMN IF NOT EXISTS semester_code TEXT
  CHECK (semester_code IS NULL OR semester_code IN ('1st', '2nd'));

CREATE OR REPLACE FUNCTION ensure_enrollment_schedules(
  p_strand_id UUID,
  p_grade_level TEXT,
  p_semester_code TEXT DEFAULT NULL
)
RETURNS INT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_semester UUID;
  v_semester_code TEXT;
  v_section UUID;
  v_section_name TEXT;
  v_grade_num TEXT;
  v_inserted INT := 0;
BEGIN
  IF p_strand_id IS NULL OR p_grade_level IS NULL THEN
    RETURN 0;
  END IF;

  SELECT id, code INTO v_semester, v_semester_code
  FROM semesters
  WHERE is_current = TRUE
  LIMIT 1;

  IF v_semester IS NULL THEN
    RETURN 0;
  END IF;

  v_semester_code := COALESCE(NULLIF(TRIM(p_semester_code), ''), v_semester_code, '1st');
  v_grade_num := CASE WHEN p_grade_level LIKE '%11%' THEN '11' ELSE '12' END;

  SELECT build_section_name(code, p_grade_level, 'A')
  INTO v_section_name
  FROM strands
  WHERE id = p_strand_id;

  INSERT INTO sections (name, strand_id, grade_level)
  VALUES (v_section_name, p_strand_id, p_grade_level)
  ON CONFLICT (name, strand_id, grade_level) DO NOTHING;

  SELECT id INTO v_section
  FROM sections
  WHERE name = v_section_name
    AND strand_id = p_strand_id
    AND grade_level = p_grade_level
  LIMIT 1;

  IF v_section IS NULL THEN
    RETURN 0;
  END IF;

  INSERT INTO class_schedules (
    subject_id, section_id, semester_id, schedule_label, day_of_week,
    start_time, end_time, max_slots, is_active, is_published
  )
  SELECT sub.id, v_section, v_semester, 'MW 9:00AM-10:30AM', 'MW',
    TIME '09:00:00', TIME '10:30:00', 40, TRUE, TRUE
  FROM subjects sub
  WHERE sub.is_active = TRUE
    AND sub.grade_level = p_grade_level
    AND (sub.semester_code IS NULL OR sub.semester_code = v_semester_code)
    AND (sub.strand_id IS NULL OR sub.strand_id = p_strand_id)
    AND NOT EXISTS (
      SELECT 1
      FROM class_schedules cs
      WHERE cs.subject_id = sub.id
        AND cs.section_id = v_section
        AND cs.semester_id = v_semester
    );

  GET DIAGNOSTICS v_inserted = ROW_COUNT;
  RETURN v_inserted;
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_offerings(p_student_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_strand_id UUID;
  v_grade_level TEXT;
  v_semester_code TEXT;
  v_section_id UUID;
  result JSON;
BEGIN
  SELECT s.strand_id, s.grade_level, sem.code, s.section_id
  INTO v_strand_id, v_grade_level, v_semester_code, v_section_id
  FROM students s
  CROSS JOIN semesters sem
  WHERE s.student_id = UPPER(TRIM(p_student_id))
    AND sem.is_current = TRUE
  LIMIT 1;

  IF v_grade_level IS NULL THEN
    RETURN '[]'::json;
  END IF;

  IF v_strand_id IS NOT NULL THEN
    PERFORM ensure_enrollment_schedules(v_strand_id, v_grade_level, v_semester_code);
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
      'gradeLevel', sub.grade_level,
      'semester', sub.semester_code,
      'type', CASE
        WHEN sub.strand_id IS NULL AND sub.code LIKE 'G%-A%' THEN 'applied'
        WHEN sub.strand_id IS NULL THEN 'core'
        ELSE 'specialized'
      END,
      'strandCode', str_sub.code,
      'schedules', (
        SELECT COALESCE(json_agg(json_build_object(
          'id', cs.id,
          'slots', GREATEST(cs.max_slots - COALESCE(cs.enrolled_count, 0), 0),
          'section', sec.name,
          'dayTime', cs.schedule_label
        ) ORDER BY
          CASE WHEN v_section_id IS NOT NULL AND sec.id = v_section_id THEN 0 ELSE 1 END,
          sec.name
        ), '[]'::json)
        FROM class_schedules cs
        JOIN sections sec ON sec.id = cs.section_id
        JOIN semesters sem ON sem.id = cs.semester_id
        WHERE cs.subject_id = sub.id
          AND COALESCE(cs.is_active, TRUE) = TRUE
          AND sem.is_current = TRUE
          AND sec.strand_id = v_strand_id
          AND sec.grade_level = v_grade_level
      )
    ) AS subject_row
    FROM subjects sub
    LEFT JOIN strands str_sub ON str_sub.id = sub.strand_id
    WHERE sub.is_active = TRUE
      AND v_strand_id IS NOT NULL
      AND sub.grade_level = v_grade_level
      AND (sub.semester_code IS NULL OR sub.semester_code = v_semester_code)
      AND (sub.strand_id IS NULL OR sub.strand_id = v_strand_id)
      AND EXISTS (
        SELECT 1
        FROM class_schedules cs
        JOIN sections sec ON sec.id = cs.section_id
        JOIN semesters sem ON sem.id = cs.semester_id
        WHERE cs.subject_id = sub.id
          AND COALESCE(cs.is_active, TRUE) = TRUE
          AND sem.is_current = TRUE
          AND sec.strand_id = v_strand_id
          AND sec.grade_level = v_grade_level
      )
  ) offerings;

  RETURN COALESCE(result, '[]'::json);
END;
$$;

-- ── Admin: student enrollment record (student portal) ───────
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
    AND sem.is_current = TRUE
  ORDER BY e.created_at DESC
  LIMIT 1;

  RETURN result;
END;
$$;

-- ── Admin: pending subject enrollments list ─────────────────
CREATE OR REPLACE FUNCTION get_pending_enrollments()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN COALESCE((
    SELECT json_agg(row_to_json(t))
    FROM (
      SELECT
        e.id,
        e.enrollment_number AS "enrollmentNumber",
        CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
        st.student_id AS "studentId",
        str.code AS strand,
        st.grade_level AS grade,
        e.status,
        TO_CHAR(COALESCE(e.enrolled_at, e.created_at), 'Mon DD, YYYY HH12:MI AM') AS date,
        e.total_units AS "totalUnits",
        sem.name AS semester,
        sy.label AS "schoolYear"
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      JOIN school_years sy ON sy.id = sem.school_year_id
      WHERE e.status = 'pending'
      ORDER BY COALESCE(e.enrolled_at, e.created_at) DESC
    ) t
  ), '[]'::json);
END;
$$;

-- ── Admin: enrollment review history ────────────────────────
CREATE OR REPLACE FUNCTION get_enrollment_history()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  RETURN COALESCE((
    SELECT json_agg(row_to_json(t))
    FROM (
      SELECT
        e.id,
        e.enrollment_number AS "enrollmentNumber",
        CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
        st.student_id AS "studentId",
        str.code AS strand,
        st.grade_level AS grade,
        sem.name AS semester,
        TO_CHAR(COALESCE(e.reviewed_at, e.enrolled_at, e.created_at), 'Mon DD, YYYY') AS date,
        INITCAP(e.status) AS status
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      WHERE e.status IN ('approved', 'enrolled', 'rejected')
      ORDER BY COALESCE(e.reviewed_at, e.enrolled_at, e.created_at) DESC
    ) t
  ), '[]'::json);
END;
$$;

-- ── Grants ──────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION get_student_enrollment TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_pending_enrollments TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_enrollment_history TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION review_enrollment TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION insert_student_notification TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION get_student_notifications TO anon, authenticated;
GRANT EXECUTE ON FUNCTION ensure_enrollment_schedules TO anon, authenticated;
GRANT EXECUTE ON FUNCTION resolve_class_schedule_id TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_offerings TO anon, authenticated;
GRANT EXECUTE ON FUNCTION submit_student_enrollment TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_student_enrollment_access TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_detail TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_period TO anon, authenticated;
GRANT EXECUTE ON FUNCTION set_enrollment_period TO anon, authenticated;
GRANT EXECUTE ON FUNCTION freeze_inactive_students TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_student_grades TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_students_for_grading TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_grades_sheet TO anon, authenticated;
GRANT EXECUTE ON FUNCTION save_student_grades TO anon, authenticated;
GRANT EXECUTE ON FUNCTION evaluate_student_progression TO anon, authenticated;

-- Ensure a current school year + semester exist (safe to re-run)
SELECT ensure_current_enrollment_term();

GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE student_grades TO service_role;
