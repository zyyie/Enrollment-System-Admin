-- ============================================================
-- GERANOVA SHS ENROLLMENT SYSTEM - Supabase Schema
-- Run this in Supabase SQL Editor
-- ============================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- REFERENCE TABLES
-- ============================================================

CREATE TABLE IF NOT EXISTS school_years (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  label TEXT NOT NULL UNIQUE,
  code TEXT NOT NULL UNIQUE,
  is_current BOOLEAN DEFAULT FALSE,
  enrollment_open BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS semesters (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  school_year_id UUID NOT NULL REFERENCES school_years(id) ON DELETE CASCADE,
  name TEXT NOT NULL CHECK (name IN ('First Semester', 'Second Semester')),
  code TEXT NOT NULL,
  is_current BOOLEAN DEFAULT FALSE,
  enrollment_open BOOLEAN DEFAULT FALSE,
  start_date DATE,
  end_date DATE,
  UNIQUE (school_year_id, name)
);

CREATE TABLE IF NOT EXISTS strands (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  track TEXT DEFAULT 'Academic',
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sections (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL,
  strand_id UUID NOT NULL REFERENCES strands(id),
  grade_level TEXT NOT NULL CHECK (grade_level IN ('Grade 11', 'Grade 12')),
  max_students INT DEFAULT 40,
  is_active BOOLEAN DEFAULT TRUE,
  UNIQUE (name, strand_id, grade_level)
);

CREATE TABLE IF NOT EXISTS subjects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  code TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT,
  strand_id UUID REFERENCES strands(id),
  grade_level TEXT NOT NULL CHECK (grade_level IN ('Grade 11', 'Grade 12')),
  lec_hours INT DEFAULT 0,
  lab_hours INT DEFAULT 0,
  units INT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS rooms (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name TEXT NOT NULL UNIQUE,
  capacity INT DEFAULT 40,
  room_type TEXT DEFAULT 'classroom',
  is_active BOOLEAN DEFAULT TRUE
);

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

CREATE TABLE IF NOT EXISTS faculty (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  faculty_id TEXT NOT NULL UNIQUE,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  middle_name TEXT,
  role TEXT NOT NULL DEFAULT 'Teacher',
  department TEXT,
  email TEXT,
  password TEXT NOT NULL,
  max_load_units INT DEFAULT 24,
  is_active BOOLEAN DEFAULT TRUE,
  last_login TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS students (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  student_id TEXT NOT NULL UNIQUE,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  middle_name TEXT,
  birthdate DATE NOT NULL,
  password TEXT NOT NULL,
  gender TEXT,
  address TEXT,
  contact_number TEXT,
  admission_type TEXT NOT NULL DEFAULT 'continuing'
    CHECK (admission_type IN ('new', 'continuing', 'transferee', 'returnee')),
  admission_status TEXT DEFAULT 'enrolled'
    CHECK (admission_status IN ('pending', 'approved', 'rejected', 'enrolled')),
  grade_level TEXT NOT NULL CHECK (grade_level IN ('Grade 11', 'Grade 12')),
  strand_id UUID REFERENCES strands(id),
  section_id UUID REFERENCES sections(id),
  scholastic_status TEXT DEFAULT 'Regular'
    CHECK (scholastic_status IN ('Regular', 'Irregular', 'Probationary')),
  track TEXT DEFAULT 'Academic',
  voucher_qualified BOOLEAN DEFAULT FALSE,
  is_active BOOLEAN DEFAULT TRUE,
  enrollment_photo_upload_path TEXT,
  enrollment_photo_camera_path TEXT,
  enrollment_photos_semester_id UUID REFERENCES semesters(id),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS class_schedules (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  subject_id UUID NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
  section_id UUID NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
  semester_id UUID NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
  faculty_id UUID REFERENCES faculty(id),
  room_id UUID REFERENCES rooms(id),
  day_of_week TEXT NOT NULL,
  start_time TIME,
  end_time TIME,
  max_slots INT DEFAULT 40,
  enrolled_count INT DEFAULT 0,
  schedule_label TEXT NOT NULL,
  is_active BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS enrollments (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  enrollment_number TEXT UNIQUE,
  student_id UUID NOT NULL REFERENCES students(id) ON DELETE CASCADE,
  semester_id UUID NOT NULL REFERENCES semesters(id) ON DELETE CASCADE,
  section_id UUID REFERENCES sections(id),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected', 'enrolled', 'cancelled')),
  total_units INT DEFAULT 0,
  max_subjects_allowed INT DEFAULT 20,
  scholastic_status TEXT DEFAULT 'Regular',
  voucher_qualified BOOLEAN DEFAULT FALSE,
  reviewed_by UUID REFERENCES faculty(id),
  reviewed_at TIMESTAMPTZ,
  rejection_reason TEXT,
  enrolled_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (student_id, semester_id)
);

CREATE TABLE IF NOT EXISTS enrollment_subjects (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  enrollment_id UUID NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
  subject_id UUID NOT NULL REFERENCES subjects(id),
  class_schedule_id UUID NOT NULL REFERENCES class_schedules(id),
  units INT NOT NULL,
  schedule_label TEXT,
  status TEXT DEFAULT 'enrolled'
    CHECK (status IN ('enrolled', 'dropped', 'completed')),
  UNIQUE (enrollment_id, subject_id)
);

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

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_students_student_id ON students(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_student ON enrollments(student_id);
CREATE INDEX IF NOT EXISTS idx_enrollments_status ON enrollments(status);
CREATE INDEX IF NOT EXISTS idx_class_schedules_semester ON class_schedules(semester_id);
CREATE INDEX IF NOT EXISTS idx_notifications_student ON notifications(student_id);

-- ============================================================
-- RPC: AUTHENTICATION
-- ============================================================

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
BEGIN
  SELECT json_build_object(
    'id', s.student_id,
    'supabaseId', s.id,
    'lastName', s.last_name,
    'firstName', s.first_name,
    'middleName', COALESCE(s.middle_name, ''),
    'birthMonth', EXTRACT(MONTH FROM s.birthdate)::TEXT,
    'birthDay', EXTRACT(DAY FROM s.birthdate)::TEXT,
    'birthYear', EXTRACT(YEAR FROM s.birthdate)::TEXT,
    'gradeLevel', s.grade_level,
    'strand', st.code,
    'strandFull', st.name,
    'section', COALESCE(sec.name, ''),
    'track', s.track,
    'admissionStatus', s.admission_status,
    'scholasticStatus', s.scholastic_status,
    'schoolYear', sy.label,
    'semester', sem.name,
    'voucherQualified', s.voucher_qualified
  )
  INTO result
  FROM students s
  LEFT JOIN strands st ON st.id = s.strand_id
  LEFT JOIN sections sec ON sec.id = s.section_id
  CROSS JOIN semesters sem
  JOIN school_years sy ON sy.id = sem.school_year_id
  WHERE s.student_id = UPPER(TRIM(p_student_id))
    AND s.password = p_password
    AND EXTRACT(MONTH FROM s.birthdate) = p_birth_month
    AND EXTRACT(DAY FROM s.birthdate) = p_birth_day
    AND EXTRACT(YEAR FROM s.birthdate) = p_birth_year
    AND s.is_active = TRUE
    AND sem.is_current = TRUE
  LIMIT 1;

  RETURN result;
END;
$$;

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

-- ============================================================
-- RPC: ENROLLMENT
-- ============================================================

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
    'enrolledAt', TO_CHAR(e.enrolled_at, 'Mon DD, YYYY HH12:MI AM'),
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
  LIMIT 1;

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
  v_max_subjects INT := 20;
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

CREATE OR REPLACE FUNCTION get_faculty_dashboard()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'totalStudents', (SELECT COUNT(*) FROM students WHERE is_active = TRUE),
    'totalStrands', (SELECT COUNT(*) FROM strands WHERE is_active = TRUE),
    'pendingEnrollments', (SELECT COUNT(*) FROM enrollments WHERE status = 'pending'),
    'totalAdmissions', (SELECT COUNT(*) FROM students WHERE admission_type = 'new'),
    'enrollmentStats', json_build_object(
      'approved', (SELECT COUNT(*) FROM enrollments WHERE status IN ('approved', 'enrolled')),
      'pending', (SELECT COUNT(*) FROM enrollments WHERE status = 'pending'),
      'rejected', (SELECT COUNT(*) FROM enrollments WHERE status = 'rejected')
    ),
    'recentActivity', (
      SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
      FROM (
        SELECT
          CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
          CONCAT(str.code, ' - ', st.grade_level) AS strand,
          sub.name AS subject,
          TO_CHAR(e.updated_at, 'Mon DD, YYYY HH12:MI AM') AS date,
          INITCAP(e.status) AS status
        FROM enrollments e
        JOIN students st ON st.id = e.student_id
        LEFT JOIN strands str ON str.id = st.strand_id
        LEFT JOIN enrollment_subjects es ON es.enrollment_id = e.id
        LEFT JOIN subjects sub ON sub.id = es.subject_id
        ORDER BY e.updated_at DESC
        LIMIT 5
      ) t
    ),
    'strandDistribution', (
      SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
      FROM (
        SELECT
          str.code AS name,
          'Grade 11 & 12' AS grade,
          (SELECT COUNT(*) FROM subjects s WHERE s.strand_id = str.id OR s.strand_id IS NULL) AS subjects
        FROM strands str
        WHERE str.is_active = TRUE
      ) t
    ),
    'pendingRequests', (
      SELECT COALESCE(json_agg(row_to_json(t)), '[]'::json)
      FROM (
        SELECT
          CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
          st.student_id AS "studentId",
          str.code AS strand,
          st.grade_level AS grade
        FROM enrollments e
        JOIN students st ON st.id = e.student_id
        LEFT JOIN strands str ON str.id = st.strand_id
        WHERE e.status = 'pending'
        ORDER BY e.created_at DESC
        LIMIT 10
      ) t
    )
  )
  INTO result;

  RETURN result;
END;
$$;

CREATE OR REPLACE FUNCTION get_pending_enrollments()
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
        e.id,
        e.enrollment_number,
        CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
        st.student_id AS "studentId",
        str.code AS strand,
        st.grade_level AS grade,
        e.status,
        TO_CHAR(e.created_at, 'Mon DD, YYYY HH12:MI AM') AS date,
        e.total_units AS "totalUnits"
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      WHERE e.status = 'pending'
      ORDER BY e.created_at DESC
    ) t
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_enrollment_history()
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
        e.enrollment_number AS id,
        CONCAT(st.last_name, ', ', st.first_name, ' ', COALESCE(LEFT(st.middle_name, 1) || '.', '')) AS student,
        str.code AS strand,
        st.grade_level AS grade,
        sem.name AS semester,
        TO_CHAR(e.created_at, 'Mon DD, YYYY') AS date,
        INITCAP(e.status) AS status
      FROM enrollments e
      JOIN students st ON st.id = e.student_id
      LEFT JOIN strands str ON str.id = st.strand_id
      JOIN semesters sem ON sem.id = e.semester_id
      ORDER BY e.created_at DESC
    ) t
  );
END;
$$;

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
BEGIN
  SELECT id INTO v_faculty
  FROM faculty
  WHERE faculty_id = UPPER(TRIM(p_faculty_id))
  LIMIT 1;

  v_new_status := CASE
    WHEN LOWER(p_action) = 'approve' THEN 'approved'
    WHEN LOWER(p_action) = 'reject' THEN 'rejected'
    ELSE NULL
  END;

  IF v_new_status IS NULL THEN
    RAISE EXCEPTION 'Invalid action';
  END IF;

  UPDATE enrollments
  SET
    status = v_new_status,
    reviewed_by = v_faculty,
    reviewed_at = NOW(),
    rejection_reason = CASE WHEN v_new_status = 'rejected' THEN p_reason ELSE NULL END,
    updated_at = NOW(),
    enrolled_at = CASE WHEN v_new_status = 'approved' THEN NOW() ELSE enrolled_at END
  WHERE id = p_enrollment_id;

  RETURN json_build_object('success', TRUE, 'status', v_new_status);
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
        n.has_pdf AS "hasPdf"
      FROM notifications n
      JOIN students s ON s.id = COALESCE(n.student_id, n.recipient_id)
      WHERE s.student_id = UPPER(TRIM(p_student_id))
      ORDER BY n.created_at DESC
    ) t
  );
END;
$$;

-- ============================================================
-- GRANTS
-- ============================================================

GRANT USAGE ON SCHEMA public TO anon, authenticated;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO anon, authenticated;
GRANT EXECUTE ON FUNCTION authenticate_student TO anon, authenticated;
GRANT EXECUTE ON FUNCTION authenticate_admin TO anon, authenticated;
GRANT EXECUTE ON FUNCTION authenticate_faculty TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_offerings TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_student_enrollment TO anon, authenticated;
GRANT EXECUTE ON FUNCTION submit_student_enrollment TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_faculty_dashboard TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_enrollments TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_enrollment_history TO anon, authenticated;
GRANT EXECUTE ON FUNCTION review_enrollment TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_student_notifications TO anon, authenticated;

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO school_years (label, code, is_current, enrollment_open)
VALUES ('2026-2027', '2627', TRUE, TRUE)
ON CONFLICT (code) DO UPDATE SET is_current = TRUE, enrollment_open = TRUE;

INSERT INTO semesters (school_year_id, name, code, is_current, enrollment_open, start_date, end_date)
SELECT sy.id, 'First Semester', '1st', TRUE, TRUE, '2026-08-01', '2026-12-15'
FROM school_years sy
WHERE sy.code = '2627'
ON CONFLICT (school_year_id, name) DO UPDATE SET is_current = TRUE;

INSERT INTO strands (code, name, track) VALUES
  ('STEM', 'STEM - Science, Technology, Engineering, and Mathematics', 'Academic'),
  ('ABM', 'Accountancy, Business & Management', 'Academic'),
  ('HUMSS', 'Humanities & Social Sciences', 'Academic'),
  ('ICT', 'Information and Communications Technology', 'TVL'),
  ('GAS', 'General Academic Strand', 'Academic')
ON CONFLICT (code) DO NOTHING;

INSERT INTO sections (name, strand_id, grade_level)
SELECT 'STEM 12-A', id, 'Grade 12' FROM strands WHERE code = 'STEM'
ON CONFLICT DO NOTHING;

INSERT INTO sections (name, strand_id, grade_level)
SELECT 'STEM 12-B', id, 'Grade 12' FROM strands WHERE code = 'STEM'
ON CONFLICT DO NOTHING;

INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT 'STEM-G12', 'Pre-Calculus', 'Pre-Calculus', id, 'Grade 12', 4, 0, 4 FROM strands WHERE code = 'STEM'
ON CONFLICT (code) DO NOTHING;

INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units)
SELECT 'STEM-02', 'General Physics 1', 'General Physics 1', id, 'Grade 12', 3, 1, 4 FROM strands WHERE code = 'STEM'
ON CONFLICT (code) DO NOTHING;

INSERT INTO subjects (code, name, description, strand_id, grade_level, lec_hours, lab_hours, units) VALUES
  ('CORE-03', 'Media and Information Literacy', 'Media and Information Literacy', NULL, 'Grade 12', 3, 0, 3),
  ('CORE-04', 'Philippine Politics and Governance', 'Philippine Politics and Governance', NULL, 'Grade 12', 3, 0, 3),
  ('APPL-02', 'Practical Research 2', 'Practical Research 2', NULL, 'Grade 12', 3, 0, 3),
  ('PE-04', 'Physical Education and Health 4', 'Physical Education and Health 4', NULL, 'Grade 12', 2, 0, 2),
  ('STEM-E01', 'Statistics and Probability', 'Statistics and Probability', NULL, 'Grade 12', 3, 0, 3),
  ('WORK-01', 'Work Immersion', 'Work Immersion', NULL, 'Grade 12', 3, 0, 3)
ON CONFLICT (code) DO NOTHING;

UPDATE subjects SET strand_id = (SELECT id FROM strands WHERE code = 'STEM')
WHERE code = 'STEM-E01';

INSERT INTO rooms (name, capacity, room_type) VALUES
  ('Room 201', 40, 'classroom'),
  ('Room 202', 40, 'classroom'),
  ('Lab 1', 30, 'laboratory')
ON CONFLICT (name) DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'MW 9:00AM-10:30AM', 'MW', 25
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'CORE-03' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'TTh 9:00AM-10:30AM', 'TTh', 20
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'CORE-03' AND sec.name = 'STEM 12-B' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'TTh 7:30AM-9:00AM', 'TTh', 30
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'STEM-G12' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'MW 7:30AM-9:00AM', 'MW', 18
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'STEM-G12' AND sec.name = 'STEM 12-B' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'TTh 1:00PM-2:30PM', 'TTh', 22
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'STEM-02' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'MW 1:00PM-2:30PM', 'MW', 15
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'STEM-02' AND sec.name = 'STEM 12-B' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'F 7:30AM-10:30AM', 'F', 20
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'APPL-02' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'F 1:00PM-3:00PM', 'F', 35
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'PE-04' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'MW 10:30AM-12:00PM', 'MW', 28
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'CORE-04' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'TTh 10:30AM-12:00PM', 'TTh', 20
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'CORE-04' AND sec.name = 'STEM 12-B' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'MW 1:00PM-2:30PM', 'MW', 18
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'STEM-E01' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO class_schedules (subject_id, section_id, semester_id, schedule_label, day_of_week, max_slots)
SELECT sub.id, sec.id, sem.id, 'Off-Campus / Practicum', 'Off', 30
FROM subjects sub, sections sec, semesters sem
WHERE sub.code = 'WORK-01' AND sec.name = 'STEM 12-A' AND sem.is_current = TRUE
ON CONFLICT DO NOTHING;

INSERT INTO admins (admin_id, last_name, first_name, middle_name, role, department, password, last_login)
VALUES ('FAC-2026-0001', 'DELA CRUZ', 'JUAN', 'MARTINEZ', 'Registrar', 'Registrar Office', 'admin123', NOW())
ON CONFLICT (admin_id) DO NOTHING;

INSERT INTO students (
  student_id, last_name, first_name, middle_name, birthdate, password,
  grade_level, strand_id, section_id, admission_type, admission_status,
  scholastic_status, track, voucher_qualified
)
SELECT
  '2026-00145-SHS-0',
  'SANTOS',
  'MARIA CLARA',
  'REYES',
  '2009-03-15',
  'student123',
  'Grade 12',
  st.id,
  sec.id,
  'continuing',
  'enrolled',
  'Regular',
  'Academic',
  TRUE
FROM strands st
JOIN sections sec ON sec.strand_id = st.id AND sec.name = 'STEM 12-A'
WHERE st.code = 'STEM'
ON CONFLICT (student_id) DO NOTHING;

INSERT INTO notifications (student_id, title, has_pdf)
SELECT s.id, 'Work Immersion Orientation 2026', TRUE
FROM students s WHERE s.student_id = '2026-00145-SHS-0'
ON CONFLICT DO NOTHING;

INSERT INTO notifications (student_id, title, has_pdf)
SELECT s.id, 'Enrollment Reminder - First Semester', FALSE
FROM students s WHERE s.student_id = '2026-00145-SHS-0'
ON CONFLICT DO NOTHING;
