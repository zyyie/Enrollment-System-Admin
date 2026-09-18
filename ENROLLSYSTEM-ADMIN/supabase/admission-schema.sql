-- ============================================================
-- ADMISSION APPLICATIONS (New Student Enrollment)
-- Run AFTER schema.sql in Supabase SQL Editor
-- ============================================================

CREATE TABLE IF NOT EXISTS admission_applications (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  application_number TEXT NOT NULL UNIQUE,
  last_name TEXT NOT NULL,
  first_name TEXT NOT NULL,
  middle_name TEXT,
  birthdate DATE NOT NULL,
  gender TEXT,
  address TEXT,
  addr_house_number TEXT,
  addr_street TEXT,
  addr_barangay TEXT,
  addr_city TEXT,
  addr_province TEXT,
  contact_number TEXT,
  email TEXT NOT NULL,
  grade_level TEXT NOT NULL CHECK (grade_level IN ('Grade 11', 'Grade 12')),
  strand_id UUID REFERENCES strands(id),
  admission_type TEXT NOT NULL DEFAULT 'new'
    CHECK (admission_type IN ('new', 'transferee', 'returnee')),
  previous_school TEXT,
  payment_mode TEXT NOT NULL CHECK (payment_mode IN ('gcash', 'cashier')),
  gcash_reference TEXT,
  gcash_sender_name TEXT,
  gcash_proof_path TEXT,
  payment_status TEXT DEFAULT 'pending'
    CHECK (payment_status IN ('pending', 'submitted', 'paid', 'failed', 'waived')),
  payment_amount NUMERIC(10, 2),
  doc_form_138_path TEXT,
  doc_form_137_path TEXT,
  doc_good_moral_path TEXT,
  doc_birth_certificate_path TEXT,
  documents JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected')),
  student_id_generated TEXT,
  temp_password TEXT,
  reviewed_by UUID REFERENCES faculty(id),
  reviewed_at TIMESTAMPTZ,
  rejection_reason TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admission_status ON admission_applications(status);
CREATE INDEX IF NOT EXISTS idx_admission_email ON admission_applications(email);

-- ============================================================
-- RPC: ADMISSION
-- ============================================================

CREATE OR REPLACE FUNCTION submit_admission_application(p_payload JSON)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_id UUID;
  v_app_number TEXT;
  v_count INT;
  v_docs JSONB;
  v_full_address TEXT;
BEGIN
  SELECT COUNT(*) + 1 INTO v_count FROM admission_applications;
  v_app_number := 'APP-' || TO_CHAR(NOW(), 'YYYY') || '-' || LPAD(v_count::TEXT, 5, '0');

  v_docs := COALESCE(p_payload->'documents', '{}'::json);

  v_full_address := NULLIF(CONCAT_WS(', ',
    NULLIF(TRIM(p_payload->>'houseNumber'), ''),
    NULLIF(TRIM(p_payload->>'street'), ''),
    NULLIF(TRIM(p_payload->>'barangay'), ''),
    NULLIF(TRIM(p_payload->>'city'), ''),
    NULLIF(TRIM(p_payload->>'province'), '')
  ), '');

  IF v_full_address IS NULL THEN
    v_full_address := NULLIF(TRIM(p_payload->>'address'), '');
  END IF;

  INSERT INTO admission_applications (
    application_number,
    last_name,
    first_name,
    middle_name,
    birthdate,
    gender,
    address,
    addr_house_number,
    addr_street,
    addr_barangay,
    addr_city,
    addr_province,
    contact_number,
    email,
    grade_level,
    strand_id,
    admission_type,
    previous_school,
    payment_mode,
    gcash_reference,
    gcash_sender_name,
    gcash_proof_path,
    payment_status,
    payment_amount,
    doc_form_138_path,
    doc_form_137_path,
    doc_good_moral_path,
    doc_birth_certificate_path,
    documents,
    status
  )
  VALUES (
    v_app_number,
    UPPER(TRIM(p_payload->>'lastName')),
    UPPER(TRIM(p_payload->>'firstName')),
    NULLIF(UPPER(TRIM(p_payload->>'middleName')), ''),
    (p_payload->>'birthdate')::DATE,
    NULLIF(p_payload->>'gender', ''),
    v_full_address,
    NULLIF(TRIM(p_payload->>'houseNumber'), ''),
    NULLIF(TRIM(p_payload->>'street'), ''),
    NULLIF(TRIM(p_payload->>'barangay'), ''),
    NULLIF(TRIM(p_payload->>'city'), ''),
    NULLIF(TRIM(p_payload->>'province'), ''),
    p_payload->>'contactNumber',
    LOWER(TRIM(p_payload->>'email')),
    p_payload->>'gradeLevel',
    COALESCE(
      NULLIF(p_payload->>'strandId', '')::UUID,
      (SELECT id FROM strands WHERE code = UPPER(TRIM(p_payload->>'strandCode')) LIMIT 1)
    ),
    COALESCE(p_payload->>'admissionType', 'new'),
    NULLIF(TRIM(p_payload->>'previousSchool'), ''),
    p_payload->>'paymentMode',
    NULLIF(p_payload->>'gcashReference', ''),
    NULLIF(p_payload->>'gcashSenderName', ''),
    NULLIF(p_payload->>'gcashProofPath', ''),
    COALESCE(p_payload->>'paymentStatus', 'submitted'),
    NULLIF(p_payload->>'paymentAmount', '')::NUMERIC,
    NULLIF(COALESCE(p_payload->>'docForm138Path', v_docs->>'form_138'), ''),
    NULLIF(COALESCE(p_payload->>'docForm137Path', v_docs->>'form_137'), ''),
    NULLIF(COALESCE(p_payload->>'docGoodMoralPath', v_docs->>'good_moral'), ''),
    NULLIF(COALESCE(p_payload->>'docBirthCertificatePath', v_docs->>'birth_certificate'), ''),
    jsonb_strip_nulls(jsonb_build_object(
      'form_138', NULLIF(COALESCE(p_payload->>'docForm138Path', v_docs->>'form_138'), ''),
      'form_137', NULLIF(COALESCE(p_payload->>'docForm137Path', v_docs->>'form_137'), ''),
      'good_moral', NULLIF(COALESCE(p_payload->>'docGoodMoralPath', v_docs->>'good_moral'), ''),
      'birth_certificate', NULLIF(COALESCE(p_payload->>'docBirthCertificatePath', v_docs->>'birth_certificate'), '')
    )),
    'pending'
  )
  RETURNING id INTO v_id;

  RETURN json_build_object(
    'success', TRUE,
    'applicationId', v_id,
    'applicationNumber', v_app_number
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_pending_admissions()
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
        a.id,
        a.application_number AS "applicationNumber",
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(LEFT(a.middle_name, 1) || '.', '')) AS student,
        a.email,
        a.contact_number AS "contactNumber",
        str.code AS strand,
        a.grade_level AS grade,
        a.payment_mode AS "paymentMode",
        a.gcash_reference AS "gcashReference",
        a.gcash_sender_name AS "gcashSenderName",
        a.gcash_proof_path AS "gcashProofPath",
        a.payment_amount AS "paymentAmount",
        a.status,
        TO_CHAR(a.created_at, 'Mon DD, YYYY HH12:MI AM') AS date,
        a.doc_form_138_path AS "docForm138Path",
        a.doc_form_137_path AS "docForm137Path",
        a.doc_good_moral_path AS "docGoodMoralPath",
        a.doc_birth_certificate_path AS "docBirthCertificatePath",
        COALESCE(
          NULLIF(a.documents, '{}'::jsonb),
          jsonb_strip_nulls(jsonb_build_object(
            'form_138', a.doc_form_138_path,
            'form_137', a.doc_form_137_path,
            'good_moral', a.doc_good_moral_path,
            'birth_certificate', a.doc_birth_certificate_path
          ))
        ) AS documents
      FROM admission_applications a
      LEFT JOIN strands str ON str.id = a.strand_id
      WHERE a.status = 'pending'
      ORDER BY a.created_at DESC
    ) t
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_admission_history()
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
        a.application_number AS id,
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(LEFT(a.middle_name, 1) || '.', '')) AS student,
        COALESCE(a.student_id_generated, '—') AS "studentId",
        str.code AS strand,
        a.grade_level AS grade,
        INITCAP(a.status) AS status,
        TO_CHAR(a.reviewed_at, 'Mon DD, YYYY') AS date,
        a.email
      FROM admission_applications a
      LEFT JOIN strands str ON str.id = a.strand_id
      WHERE a.status IN ('approved', 'rejected')
      ORDER BY a.reviewed_at DESC NULLS LAST
    ) t
  );
END;
$$;

CREATE OR REPLACE FUNCTION generate_student_id()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
  v_year TEXT;
  v_seq INT;
BEGIN
  v_year := TO_CHAR(NOW(), 'YYYY');
  SELECT COALESCE(MAX(
    NULLIF(SPLIT_PART(student_id, '-', 2), '')::INT
  ), 0) + 1
  INTO v_seq
  FROM students
  WHERE student_id LIKE v_year || '-%';

  RETURN v_year || '-' || LPAD(v_seq::TEXT, 5, '0') || '-SHS-0';
END;
$$;

CREATE OR REPLACE FUNCTION review_admission_application(
  p_application_id UUID,
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
  v_app admission_applications%ROWTYPE;
  v_new_status TEXT;
  v_student_id TEXT;
  v_temp_password TEXT;
  v_student_uuid UUID;
BEGIN
  SELECT id INTO v_faculty
  FROM faculty
  WHERE faculty_id = UPPER(TRIM(p_faculty_id))
  LIMIT 1;

  SELECT * INTO v_app
  FROM admission_applications
  WHERE id = p_application_id
  LIMIT 1;

  IF v_app.id IS NULL THEN
    RAISE EXCEPTION 'Application not found';
  END IF;

  IF v_app.status <> 'pending' THEN
    RAISE EXCEPTION 'Application already processed';
  END IF;

  v_new_status := CASE
    WHEN LOWER(p_action) = 'approve' THEN 'approved'
    WHEN LOWER(p_action) = 'reject' THEN 'rejected'
    ELSE NULL
  END;

  IF v_new_status IS NULL THEN
    RAISE EXCEPTION 'Invalid action';
  END IF;

  IF v_new_status = 'approved' THEN
    v_student_id := generate_student_id();
    v_temp_password := 'Shs' || LPAD(FLOOR(random() * 10000)::TEXT, 4, '0');

    INSERT INTO students (
      student_id,
      last_name,
      first_name,
      middle_name,
      birthdate,
      password,
      gender,
      address,
      contact_number,
      admission_type,
      admission_status,
      grade_level,
      strand_id,
      scholastic_status,
      track,
      is_active
    )
    VALUES (
      v_student_id,
      v_app.last_name,
      v_app.first_name,
      v_app.middle_name,
      v_app.birthdate,
      v_temp_password,
      v_app.gender,
      v_app.address,
      v_app.contact_number,
      v_app.admission_type,
      'approved',
      v_app.grade_level,
      v_app.strand_id,
      'Regular',
      'Academic',
      TRUE
    )
    RETURNING id INTO v_student_uuid;

    INSERT INTO notifications (student_id, title, message, type)
    VALUES (
      v_student_uuid,
      'Welcome to Enrollment Management System',
      'Your admission has been approved. Use your Student ID to sign in to the enrollment portal.',
      'announcement'
    );

    UPDATE admission_applications
    SET
      status = 'approved',
      student_id_generated = v_student_id,
      temp_password = v_temp_password,
      reviewed_by = v_faculty,
      reviewed_at = NOW(),
      updated_at = NOW()
    WHERE id = p_application_id;

    RETURN json_build_object(
      'success', TRUE,
      'status', 'approved',
      'studentId', v_student_id,
      'tempPassword', v_temp_password,
      'email', v_app.email,
      'firstName', v_app.first_name,
      'applicationNumber', v_app.application_number
    );
  END IF;

  UPDATE admission_applications
  SET
    status = 'rejected',
    rejection_reason = p_reason,
    reviewed_by = v_faculty,
    reviewed_at = NOW(),
    updated_at = NOW()
  WHERE id = p_application_id;

  RETURN json_build_object(
    'success', TRUE,
    'status', 'rejected',
    'email', v_app.email,
    'firstName', v_app.first_name,
    'applicationNumber', v_app.application_number
  );
END;
$$;

CREATE OR REPLACE FUNCTION get_admission_application(p_application_id UUID)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
BEGIN
  SELECT json_build_object(
    'id', a.id,
    'applicationNumber', a.application_number,
    'lastName', a.last_name,
    'firstName', a.first_name,
    'middleName', a.middle_name,
    'birthdate', a.birthdate,
    'gender', a.gender,
    'address', a.address,
    'contactNumber', a.contact_number,
    'email', a.email,
    'gradeLevel', a.grade_level,
    'strand', str.code,
    'admissionType', a.admission_type,
    'paymentMode', a.payment_mode,
    'gcashReference', a.gcash_reference,
    'documents', a.documents,
    'status', a.status,
    'createdAt', TO_CHAR(a.created_at, 'Mon DD, YYYY HH12:MI AM')
  )
  INTO result
  FROM admission_applications a
  LEFT JOIN strands str ON str.id = a.strand_id
  WHERE a.id = p_application_id
  LIMIT 1;

  RETURN result;
END;
$$;

GRANT EXECUTE ON FUNCTION submit_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_history TO anon, authenticated;
GRANT EXECUTE ON FUNCTION review_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_application TO anon, authenticated;
GRANT EXECUTE ON FUNCTION generate_student_id TO anon, authenticated;

-- Add ICT strand if not yet in database
INSERT INTO strands (code, name, track) VALUES
  ('ICT', 'Information and Communications Technology', 'TVL')
ON CONFLICT (code) DO NOTHING;

-- Include pending admission applications in faculty dashboard count
CREATE OR REPLACE FUNCTION get_faculty_dashboard()
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  result JSON;
  v_pending_admissions INT;
BEGIN
  SELECT COUNT(*) INTO v_pending_admissions
  FROM admission_applications
  WHERE status = 'pending';

  SELECT json_build_object(
    'totalStudents', (SELECT COUNT(*) FROM students WHERE is_active = TRUE),
    'totalStrands', (SELECT COUNT(*) FROM strands WHERE is_active = TRUE),
    'pendingEnrollments', (SELECT COUNT(*) FROM enrollments WHERE status = 'pending') + v_pending_admissions,
    'pendingAdmissions', v_pending_admissions,
    'totalAdmissions', (SELECT COUNT(*) FROM students WHERE admission_type = 'new'),
    'enrollmentStats', json_build_object(
      'approved', (SELECT COUNT(*) FROM enrollments WHERE status IN ('approved', 'enrolled')),
      'pending', (SELECT COUNT(*) FROM enrollments WHERE status = 'pending') + v_pending_admissions,
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

-- Remove deprecated entrance examination document from existing records
UPDATE admission_applications
SET documents = documents - 'entrance_exam'
WHERE documents ? 'entrance_exam';
