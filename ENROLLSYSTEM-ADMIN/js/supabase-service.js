// Supabase data and auth service
const SupabaseService = (() => {
  function getClient() {
    return SupabaseClient.getClient();
  }

  function isEnabled() {
    return SupabaseClient.isEnabled();
  }

  async function callRpc(name, params = {}) {
    const client = getClient();
    if (!client) return { data: null, error: { message: 'Supabase is not configured' } };

    try {
      const { data, error } = await client.rpc(name, params);
      return { data, error };
    } catch (err) {
      console.warn(`Supabase RPC failed (${name}):`, err);
      return { data: null, error: { message: err.message || 'Network error' } };
    }
  }

  async function loginStudent(studentId, birthMonth, birthDay, birthYear, password) {
    const { data, error } = await callRpc('authenticate_student', {
      p_student_id: studentId,
      p_birth_month: parseInt(birthMonth, 10),
      p_birth_day: parseInt(birthDay, 10),
      p_birth_year: parseInt(birthYear, 10),
      p_password: password
    });

    if (error || !data) return null;
    return data;
  }

  async function loginFaculty(facultyId, password) {
    const { data, error } = await callRpc('authenticate_faculty', {
      p_faculty_id: facultyId,
      p_password: password
    });

    if (error || data == null) return null;

    if (typeof data === 'string') {
      try {
        const parsed = JSON.parse(data);
        return parsed && parsed.id ? parsed : null;
      } catch (err) {
        return null;
      }
    }

    return data && data.id ? data : null;
  }

  async function getEnrollmentOfferings(studentId) {
    const { data, error } = await callRpc('get_enrollment_offerings', {
      p_student_id: studentId
    });

    if (error) {
      console.error('Failed to load enrollment offerings:', error.message);
      return null;
    }

    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data.subjects)) return data.subjects;
    return [];
  }

  async function getStudentEnrollment(studentId) {
    const { data, error } = await callRpc('get_student_enrollment', {
      p_student_id: studentId
    });

    if (error) {
      console.error('Failed to load enrollment record:', error.message);
      return null;
    }

    return data;
  }

  async function submitEnrollment(studentId, subjects) {
    const payload = subjects.map(item => ({
      code: item.code,
      units: item.units,
      scheduleId: item.schedule.id,
      scheduleLabel: `[${item.schedule.slots}] ${item.schedule.section} | ${item.schedule.dayTime}`
    }));

    const { data, error } = await callRpc('submit_student_enrollment', {
      p_student_id: studentId,
      p_subjects: payload
    });

    if (error) {
      const msg = error.message || error.details || 'Enrollment validation failed';
      console.error('Failed to submit enrollment:', msg);
      return { success: false, error: msg };
    }

    return { success: true, data };
  }

  async function getFacultyDashboard() {
    const { data, error } = await callRpc('get_faculty_dashboard');
    if (error) {
      console.error('Failed to load faculty dashboard:', error.message);
      return null;
    }
    return data;
  }

  function parseRpcArray(data) {
    if (data == null) return [];
    if (Array.isArray(data)) return data;
    if (typeof data === 'string') {
      try {
        const parsed = JSON.parse(data);
        return Array.isArray(parsed) ? parsed : [];
      } catch (err) {
        return [];
      }
    }
    return [];
  }

  async function getPendingEnrollments() {
    const { data, error } = await callRpc('get_pending_enrollments');
    if (error) {
      console.error('Failed to load pending enrollments:', error.message);
      return null;
    }
    return parseRpcArray(data);
  }

  async function getEnrollmentHistory() {
    const { data, error } = await callRpc('get_enrollment_history');
    if (error) {
      console.error('Failed to load enrollment history:', error.message);
      return null;
    }
    return parseRpcArray(data);
  }

  async function reviewEnrollment(enrollmentId, facultyId, action, reason = null) {
    const { data, error } = await callRpc('review_enrollment', {
      p_enrollment_id: enrollmentId,
      p_faculty_id: facultyId,
      p_action: action,
      p_reason: reason
    });

    if (error) {
      console.error('Failed to review enrollment:', error.message);
      return { success: false, error: error.message };
    }

    return { success: true, data };
  }

  async function getStudentNotifications(studentId) {
    const { data, error } = await callRpc('get_student_notifications', {
      p_student_id: studentId
    });

    if (error) {
      console.error('Failed to load notifications:', error.message);
      return null;
    }

    return Array.isArray(data) ? data : [];
  }

  async function getEnrollmentDetail(enrollmentId) {
    const { data, error } = await callRpc('get_enrollment_detail', {
      p_enrollment_id: enrollmentId
    });
    if (error) {
      console.error('Failed to load enrollment detail:', error.message);
      return null;
    }
    return data;
  }

  async function getEnrollmentPeriod() {
    const { data, error } = await callRpc('get_enrollment_period');
    if (error) {
      console.error('Failed to load enrollment period:', error.message);
      return null;
    }
    return data;
  }

  async function setEnrollmentPeriod(enrollmentOpen, targetGradeLevel = null, semesterCode = null) {
    const { data, error } = await callRpc('set_enrollment_period', {
      p_enrollment_open: enrollmentOpen,
      p_target_grade_level: targetGradeLevel,
      p_semester_code: semesterCode,
    });
    if (error) {
      return { success: false, error: error.message };
    }
    return { success: true, data };
  }

  async function switchEnrollmentSemester(semesterCode) {
    const { data, error } = await callRpc('switch_enrollment_semester', {
      p_semester_code: semesterCode,
    });
    if (error) {
      return { success: false, error: error.message };
    }
    return { success: true, data };
  }

  async function getStudentsForGrading(gradeLevel = null, strand = null) {
    const { data, error } = await callRpc('get_students_for_grading', {
      p_grade_level: gradeLevel,
      p_strand_code: strand
    });
    if (error) return [];
    return Array.isArray(data) ? data : [];
  }

  async function getGradesSheet(enrollmentId) {
    const { data, error } = await callRpc('get_enrollment_grades_sheet', {
      p_enrollment_id: enrollmentId
    });
    if (error) return [];
    return Array.isArray(data) ? data : [];
  }

  async function saveGrades(enrollmentId, facultyId, grades) {
    const { data, error } = await callRpc('save_student_grades', {
      p_enrollment_id: enrollmentId,
      p_faculty_id: facultyId,
      p_grades: grades
    });
    if (error) {
      return { success: false, error: error.message };
    }
    return { success: true, data };
  }

  async function getEnrollmentPhotos(studentId) {
    const { data, error } = await callRpc('get_student_enrollment_photos', {
      p_student_id: studentId
    });
    if (error) {
      console.error('Failed to load enrollment photos:', error.message);
      return null;
    }
    return data;
  }

  return {
    isEnabled,
    loginStudent,
    loginFaculty,
    getEnrollmentOfferings,
    getStudentEnrollment,
    getEnrollmentPhotos,
    submitEnrollment,
    getFacultyDashboard,
    getPendingEnrollments,
    getEnrollmentHistory,
    getEnrollmentDetail,
    reviewEnrollment,
    getEnrollmentPeriod,
    setEnrollmentPeriod,
    switchEnrollmentSemester,
    getStudentsForGrading,
    getGradesSheet,
    saveGrades,
    getStudentNotifications
  };
})();
