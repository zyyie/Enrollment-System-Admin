-- Fix Review Application page: include birthdate, gender, address in pending + detail APIs
-- Run this in Supabase SQL Editor

DROP FUNCTION IF EXISTS get_admission_detail(UUID);

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
        a.last_name AS "lastName",
        a.first_name AS "firstName",
        a.middle_name AS "middleName",
        CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(a.middle_name, '')) AS student,
        TO_CHAR(a.birthdate, 'YYYY-MM-DD') AS birthdate,
        a.gender,
        COALESCE(
          NULLIF(TRIM(a.address), ''),
          NULLIF(TRIM(CONCAT_WS(', ',
            NULLIF(a.addr_house_number, ''),
            NULLIF(a.addr_street, ''),
            NULLIF(a.addr_barangay, ''),
            NULLIF(a.addr_city, ''),
            NULLIF(a.addr_province, '')
          )), '')
        ) AS address,
        a.email,
        a.contact_number AS "contactNumber",
        str.code AS strand,
        a.grade_level AS grade,
        a.admission_type AS "admissionType",
        a.payment_mode AS "paymentMode",
        a.gcash_reference AS "gcashReference",
        a.gcash_sender_name AS "gcashSenderName",
        a.gcash_proof_path AS "gcashProofPath",
        a.payment_amount AS "paymentAmount",
        a.payment_status AS "paymentStatus",
        a.status,
        TO_CHAR(a.created_at, 'YYYY-MM-DD') AS date,
        a.doc_form_138_path AS "docForm138Path",
        a.doc_form_137_path AS "docForm137Path",
        a.doc_good_moral_path AS "docGoodMoralPath",
        a.doc_birth_certificate_path AS "docBirthCertificatePath",
        a.doc_high_school_diploma_path AS "docHighSchoolDiplomaPath",
        COALESCE(
          NULLIF(a.documents, '{}'::jsonb),
          jsonb_strip_nulls(jsonb_build_object(
            'form_138', a.doc_form_138_path,
            'form_137', a.doc_form_137_path,
            'good_moral', a.doc_good_moral_path,
            'birth_certificate', a.doc_birth_certificate_path,
            'high_school_diploma', a.doc_high_school_diploma_path
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

CREATE OR REPLACE FUNCTION get_admission_detail(p_application_id TEXT)
RETURNS JSON
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_result JSON;
BEGIN
  SELECT row_to_json(t) INTO v_result
  FROM (
    SELECT
      a.id,
      a.application_number AS "applicationNumber",
      a.last_name AS "lastName",
      a.first_name AS "firstName",
      a.middle_name AS "middleName",
      CONCAT(a.last_name, ', ', a.first_name, ' ', COALESCE(a.middle_name, '')) AS student,
      TO_CHAR(a.birthdate, 'YYYY-MM-DD') AS birthdate,
      a.gender,
      COALESCE(
        NULLIF(TRIM(a.address), ''),
        NULLIF(TRIM(CONCAT_WS(', ',
          NULLIF(a.addr_house_number, ''),
          NULLIF(a.addr_street, ''),
          NULLIF(a.addr_barangay, ''),
          NULLIF(a.addr_city, ''),
          NULLIF(a.addr_province, '')
        )), '')
      ) AS address,
      a.email,
      a.contact_number AS "contactNumber",
      str.code AS "strandCode",
      a.grade_level AS "gradeLevel",
      a.admission_type AS "admissionType",
      a.payment_mode AS "paymentMode",
      a.gcash_reference AS "gcashReference",
      a.gcash_sender_name AS "gcashSenderName",
      a.gcash_proof_path AS "gcashProofPath",
      a.payment_amount AS "paymentAmount",
      a.payment_status AS "paymentStatus",
      a.status,
      TO_CHAR(a.created_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS "submittedAt",
      TO_CHAR(a.created_at, 'YYYY-MM-DD') AS date,
      a.student_id_generated AS "studentId",
      a.rejection_reason AS "rejectionReason",
      TO_CHAR(a.reviewed_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS "reviewedAt",
      a.doc_form_138_path AS "docForm138Path",
      a.doc_form_137_path AS "docForm137Path",
      a.doc_good_moral_path AS "docGoodMoralPath",
      a.doc_birth_certificate_path AS "docBirthCertificatePath",
      a.doc_high_school_diploma_path AS "docHighSchoolDiplomaPath",
      COALESCE(
        NULLIF(a.documents, '{}'::jsonb),
        jsonb_strip_nulls(jsonb_build_object(
          'form_138', a.doc_form_138_path,
          'form_137', a.doc_form_137_path,
          'good_moral', a.doc_good_moral_path,
          'birth_certificate', a.doc_birth_certificate_path,
          'high_school_diploma', a.doc_high_school_diploma_path
        ))
      ) AS documents
    FROM admission_applications a
    LEFT JOIN strands str ON str.id = a.strand_id
    WHERE a.id::TEXT = p_application_id
       OR a.application_number = p_application_id
    LIMIT 1
  ) t;

  RETURN v_result;
END;
$$;

GRANT EXECUTE ON FUNCTION get_pending_admissions TO anon, authenticated;
GRANT EXECUTE ON FUNCTION get_admission_detail TO anon, authenticated;
