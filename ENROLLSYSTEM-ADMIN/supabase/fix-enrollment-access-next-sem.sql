-- Fix: allow next-semester enrollment after previous term is complete
-- Run in Supabase SQL Editor after fix-enrollment-lifecycle.sql

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
  v_lifecycle JSON;
  v_next_stage TEXT;
  v_is_completed BOOLEAN;
  v_blocked TEXT;
  v_stage_grade TEXT;
  v_stage_sem TEXT;
BEGIN
  SELECT s.id, s.grade_level, s.account_status, s.progression_status
  INTO v_student, v_grade_level, v_account_status, v_progression
  FROM students s
  WHERE s.student_id = UPPER(TRIM(p_student_id))
  LIMIT 1;

  IF v_student IS NULL THEN
    RETURN json_build_object('canEnroll', FALSE, 'reason', 'Student not found.');
  END IF;

  v_lifecycle := get_student_lifecycle_state(p_student_id);
  v_next_stage := v_lifecycle->>'nextStage';
  v_is_completed := COALESCE((v_lifecycle->>'isCompleted')::BOOLEAN, FALSE);
  v_blocked := v_lifecycle->>'blockedReason';

  SELECT sem.enrollment_open, sem.target_grade_level, sem.name, sem.code
  INTO v_enrollment_open, v_target_grade, v_semester_name, v_semester_code
  FROM semesters sem
  WHERE sem.is_current = TRUE
  LIMIT 1;

  v_next_semester := CASE
    WHEN COALESCE(v_semester_code, '1st') = '1st' THEN '2nd Semester'
    ELSE 'the next school year (1st Semester)'
  END;

  SELECT e.status, sem.name, sem.code
  INTO v_current_status, v_semester_name, v_semester_code
  FROM enrollments e
  JOIN semesters sem ON sem.id = e.semester_id
  WHERE e.student_id = v_student
    AND e.status IN ('pending', 'approved', 'enrolled')
  ORDER BY e.created_at DESC
  LIMIT 1;

  v_stage_grade := CASE
    WHEN v_next_stage IN ('g11_1st', 'g11_2nd') THEN 'Grade 11'
    WHEN v_next_stage IN ('g12_1st', 'g12_2nd') THEN 'Grade 12'
    ELSE v_grade_level
  END;
  v_stage_sem := CASE
    WHEN v_next_stage IN ('g11_1st', 'g12_1st') THEN '1st'
    WHEN v_next_stage IN ('g11_2nd', 'g12_2nd') THEN '2nd'
    ELSE v_semester_code
  END;

  IF v_is_completed OR v_progression = 'graduated' THEN
    v_reason := 'You have completed the supported enrollment lifecycle (Grade 12 — 2nd Semester). No further enrollment is available.';
  ELSIF v_account_status = 'frozen' THEN
    v_reason := 'Your account has been frozen due to non-enrollment during the official registration period. Please contact the registrar''s office.';
  ELSIF v_account_status = 'inactive' THEN
    v_reason := 'Your account is inactive. Please contact the registrar''s office.';
  ELSIF NOT COALESCE(v_enrollment_open, FALSE) THEN
    v_reason := format(
      'Enrollment is currently closed for %s. Please wait for the registrar to open the registration period.',
      COALESCE(v_semester_name, 'this term')
    );
  ELSIF v_current_status = 'rejected' THEN
    v_current_status := NULL;
  END IF;

  IF v_reason = '' THEN
    IF v_current_status IN ('pending', 'approved') THEN
      IF v_next_stage IS NOT NULL
         AND lifecycle_stage_matches_term(v_next_stage, v_grade_level, v_semester_code) THEN
        v_reason := format(
          'Your %s enrollment is pending approval. Please wait for the administrator.',
          COALESCE(v_lifecycle->>'nextStageLabel', COALESCE(v_semester_name, 'this term'))
        );
      ELSE
        v_reason := format(
          'You have an enrollment submission for %s (%s) that must be resolved first. Please contact the registrar.',
          COALESCE(v_semester_name, 'this term'),
          COALESCE(v_grade_level, 'your grade level')
        );
      END IF;
    ELSIF v_current_status = 'enrolled' THEN
      IF is_stage_complete(v_student, v_grade_level, v_semester_code) THEN
        v_reason := format(
          'You have completed %s (%s). Enrollment for %s will open when the registrar enables it.',
          COALESCE(v_semester_name, 'this term'),
          COALESCE(v_grade_level, ''),
          v_next_semester
        );
      ELSIF v_blocked IS NOT NULL AND btrim(v_blocked) <> '' THEN
        v_reason := v_blocked;
      ELSE
        v_reason := format(
          'You are already enrolled for %s (%s).',
          COALESCE(v_semester_name, 'this term'),
          COALESCE(v_grade_level, '')
        );
      END IF;
    ELSIF v_blocked IS NOT NULL AND btrim(v_blocked) <> '' THEN
      v_reason := v_blocked;
    ELSIF v_next_stage IS NULL THEN
      v_reason := 'Enrollment is not available for your current academic stage. Please contact the registrar.';
    ELSIF NOT lifecycle_stage_matches_term(v_next_stage, v_stage_grade, v_stage_sem) THEN
      v_reason := format(
        'Your next enrollment stage is %s. The registrar must open that term before you can enroll.',
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF v_target_grade IS NOT NULL AND v_target_grade <> v_stage_grade THEN
      v_reason := format(
        'Enrollment is open for %s only. Your next required stage is %s.',
        v_target_grade,
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF COALESCE(v_semester_code, '1st') <> v_stage_sem THEN
      v_reason := format(
        'Enrollment is open for %s. Your next required stage is %s.',
        COALESCE(v_semester_name, 'this term'),
        v_lifecycle->>'nextStageLabel'
      );
    ELSIF v_progression = 'retained_g11' AND v_next_stage LIKE 'g12_%' THEN
      v_reason := 'You have unresolved failing grades in Grade 11. Grade 12 enrollment is not available until requirements are fulfilled. Please contact the registrar.';
    ELSIF v_target_grade IS NOT NULL
      AND v_target_grade <> v_stage_grade
      AND NOT (v_progression = 'eligible_g12' AND v_next_stage LIKE 'g12_%') THEN
      v_reason := format('Enrollment is open for %s only. Your next stage is %s.', v_target_grade, v_lifecycle->>'nextStageLabel');
    ELSE
      v_can_enroll := TRUE;
      v_reason := format('You may enroll for %s.', v_lifecycle->>'nextStageLabel');
    END IF;
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
    'nextSemesterLabel', v_next_semester,
    'lifecycleStage', v_lifecycle->>'lifecycleStage',
    'nextStage', v_lifecycle->>'nextStage',
    'nextStageLabel', v_lifecycle->>'nextStageLabel',
    'completedStages', v_lifecycle->'completedStages',
    'isLifecycleCompleted', v_is_completed
  );
END;
$$;

GRANT EXECUTE ON FUNCTION get_student_enrollment_access(TEXT) TO anon, authenticated, service_role;
