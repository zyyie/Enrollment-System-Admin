// Enrollment Management System — Admin Portal
const AdminApp = (() => {
  const SESSION_KEY = 'shsFaculty';

  function escHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getUser() {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  function requireAuth() {
    const user = getUser();
    if (!user) {
      window.location.href = '../login.html';
      return false;
    }
    const role = (user.role || '').trim().toLowerCase();
    if (role === 'teacher') {
      sessionStorage.removeItem(SESSION_KEY);
      sessionStorage.removeItem('loginRole');
      window.location.href = 'http://localhost:8003/login.html';
      return false;
    }
    return true;
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem('loginRole');
    window.location.href = '../index.html';
  }

  function formatName(user) {
    if (!user) return 'Admin';
    return 'Admin';
  }

  function statusBadge(status) {
    const cls = (status || 'pending').toLowerCase();
    return `<span class="admin-badge ${cls}">${status || 'Pending'}</span>`;
  }

  async function fetchJson(url, timeoutMs = 8000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, { signal: controller.signal });
      const text = await res.text();
      if (text.trim().startsWith('<')) {
        throw new Error('Server API not found. Stop old servers and run: python server.py');
      }
      let data;
      try {
        data = JSON.parse(text);
      } catch (err) {
        throw new Error('Invalid server response. Restart with: python server.py');
      }
      if (!res.ok) {
        throw new Error(data.error || `Request failed (${res.status})`);
      }
      return data;
    } catch (err) {
      if (err && err.name === 'AbortError') {
        throw new Error('Request timed out. Check that the admin server is running on port 8001 and try again.');
      }
      if (err && err.message === 'Failed to fetch') {
        throw new Error('Cannot reach the admin server. Run python server.py in ENROLLSYSTEM-ADMIN (port 8001) and reload this page.');
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  async function postJson(url, body, timeoutMs = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const text = await res.text();
      if (text.trim().startsWith('<')) {
        throw new Error('Server API not found. Stop old servers and run: python server.py');
      }
      let data;
      try {
        data = JSON.parse(text);
      } catch (err) {
        throw new Error('Invalid server response.');
      }
      if (!res.ok) {
        throw new Error(data.error || data.hint || `Request failed (${res.status})`);
      }
      return data;
    } catch (err) {
      if (err && err.name === 'AbortError') {
        throw new Error('Request timed out. Check that the admin server is running on port 8001 and try again.');
      }
      if (err && err.message === 'Failed to fetch') {
        throw new Error('Cannot reach the admin server. Run python server.py in ENROLLSYSTEM-ADMIN (port 8001) and reload this page.');
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  function cachePendingAdmissions(list) {
    try {
      sessionStorage.setItem('pendingAdmissionsCache', JSON.stringify(list || []));
    } catch (e) {
      console.warn('Could not cache pending admissions', e);
    }
  }

  function getCachedAdmission(id) {
    try {
      const list = JSON.parse(sessionStorage.getItem('pendingAdmissionsCache') || '[]');
      return list.find(item => item.id === id || item.applicationNumber === id) || null;
    } catch (e) {
      return null;
    }
  }

  function resolveDocViewUrl(pathOrUrl) {
    if (!pathOrUrl) return null;
    const value = String(pathOrUrl).replace(/\\/g, '/').trim();
    if (/^https?:\/\//i.test(value)) return value;
    if (value.startsWith('/api/admission/file')) return value;
    const path = value.replace(/^\/+/, '');
    return `/api/admission/file?path=${encodeURIComponent(path)}`;
  }

  function normalizeReviewApp(app) {
    if (!app) return null;

    app.status = String(app.status || 'pending').toLowerCase();
    app.birthdate = app.birthdate || app.birth_date || '';
    app.gender = app.gender || '';
    app.address = app.address || [
      app.addr_house_number || app.houseNumber,
      app.addr_street || app.street,
      app.addr_barangay || app.barangay,
      app.addr_city || app.city,
      app.addr_province || app.province
    ].filter(Boolean).join(', ') || '';
    app.strandCode = app.strandCode || app.strand || '';
    app.gradeLevel = app.gradeLevel || app.grade || '';
    app.admissionType = app.admissionType || app.admission_type || 'new';
    app.previousSchool = app.previousSchool || app.previous_school || '';
    app.houseNumber = app.houseNumber || app.addr_house_number || '';
    app.street = app.street || app.addr_street || '';
    app.barangay = app.barangay || app.addr_barangay || '';
    app.city = app.city || app.addr_city || '';
    app.province = app.province || app.addr_province || '';
    app.paymentAmount = app.paymentAmount || app.payment_amount || '';
    app.paymentStatus = app.paymentStatus || app.payment_status || '';
    app.paymentMode = app.paymentMode || app.payment_mode || 'cashier';
    app.bankCode = app.bankCode || app.bank_code || '';
    app.bankReference = app.bankReference || app.bank_reference || '';
    app.bankSenderName = app.bankSenderName || app.bank_sender_name || '';
    app.gcashReference = app.gcashReference || app.gcash_reference || '';
    app.gcashSenderName = app.gcashSenderName || app.gcash_sender_name || '';

    if (!app.houseNumber && !app.street && !app.barangay && app.address) {
      const parts = String(app.address).split(',').map(part => part.trim()).filter(Boolean);
      if (parts.length >= 5) {
        app.houseNumber = app.houseNumber || parts[0];
        app.street = app.street || parts[1];
        app.barangay = app.barangay || parts[2];
        app.city = app.city || parts[3];
        app.province = app.province || parts[4];
      } else if (parts.length === 4) {
        app.street = app.street || parts[0];
        app.barangay = app.barangay || parts[1];
        app.city = app.city || parts[2];
        app.province = app.province || parts[3];
      }
    }

    if (!app.subjectScheduleDetails?.length) {
      const rawDocs = app.documents && !Array.isArray(app.documents) ? app.documents : {};
      let details = rawDocs.subject_schedule_details
        || app.preferredSubjectSchedules
        || app.preferred_subject_schedules
        || app.subjectSchedules;
      if (typeof details === 'string') {
        try { details = JSON.parse(details); } catch (e) { details = null; }
      }
      if (Array.isArray(details)) {
        app.subjectScheduleDetails = details;
      } else if (details && typeof details === 'object') {
        app.subjectScheduleDetails = Object.entries(details).map(([code, scheduleId]) => ({
          code,
          scheduleId: String(scheduleId || ''),
          description: code,
          section: '',
          dayTime: ''
        }));
      } else {
        app.subjectScheduleDetails = [];
      }
    }

    const inferProfilePathFromDocFolder = documents => {
      if (!Array.isArray(documents)) return null;
      const sample = documents.find(doc => doc.path && String(doc.path).includes('uploads/admissions/'));
      if (!sample?.path) return null;
      const folder = String(sample.path).replace(/\\/g, '/').replace(/\/[^/]+$/, '');
      return `${folder}/profile_upload_profile_upload.jpg`;
    };

    const resolveProfileUrls = () => {
      let profileUploadPath = app.profilePhotoUploadPath
        || app.profile_photo_upload_path
        || (typeof app.documents === 'object' && !Array.isArray(app.documents) ? app.documents.profile_upload : null);
      let profileCameraPath = app.profilePhotoCameraPath
        || app.profile_photo_camera_path
        || (typeof app.documents === 'object' && !Array.isArray(app.documents) ? app.documents.profile_camera : null);
      if (!profileUploadPath && Array.isArray(app.documents)) {
        profileUploadPath = inferProfilePathFromDocFolder(app.documents);
      }
      app.profilePhotoUploadUrl = resolveDocViewUrl(profileUploadPath);
      app.profilePhotoCameraUrl = resolveDocViewUrl(profileCameraPath);
      app.profilePhotoUrl = app.profilePhotoUrl || app.profilePhotoUploadUrl || app.profilePhotoCameraUrl;
    };

    if (Array.isArray(app.documents) && app.documents[0]?.label) {
      app.documents = app.documents.map(doc => ({
        ...doc,
        url: resolveDocViewUrl(doc.path || doc.url)
      }));
      resolveProfileUrls();
      return app;
    }

    const docs = app.documents && typeof app.documents === 'object' ? app.documents : {};
    const docPaths = {
      form_138: docs.form_138 || app.docForm138Path,
      form_137: docs.form_137 || app.docForm137Path,
      good_moral: docs.good_moral || app.docGoodMoralPath,
      birth_certificate: docs.birth_certificate || app.docBirthCertificatePath,
      high_school_diploma: docs.high_school_diploma || app.docHighSchoolDiplomaPath
    };
    const labels = {
      form_138: 'Original Copy of Form 138 (Report Card) signed by the Principal',
      form_137: 'Original Copy of Form 137',
      good_moral: 'Original Copy of Certificate of Good Moral Character',
      birth_certificate: 'Photocopy of Birth Certificate issued by PSA',
      high_school_diploma: 'High School Diploma'
    };
    app.documents = Object.keys(labels).map(key => {
      const clean = docPaths[key] ? String(docPaths[key]).replace(/\\/g, '/') : null;
      return {
        key,
        label: labels[key],
        path: clean,
        url: resolveDocViewUrl(clean),
        uploaded: Boolean(clean)
      };
    });

    const profileUploadPath = app.profilePhotoUploadPath
      || app.profile_photo_upload_path
      || docs.profile_upload;
    const profileCameraPath = app.profilePhotoCameraPath
      || app.profile_photo_camera_path
      || docs.profile_camera;
    app.profilePhotoUploadUrl = resolveDocViewUrl(profileUploadPath);
    app.profilePhotoCameraUrl = resolveDocViewUrl(profileCameraPath);
    app.profilePhotoUrl = app.profilePhotoUrl || app.profilePhotoUploadUrl || app.profilePhotoCameraUrl;

    return app;
  }

  async function loadAdmissionDetail(id) {
    try {
      const result = await fetchJson(`/api/admission/detail?id=${encodeURIComponent(id)}`, 8000);
      if (result.success && result.data) return normalizeReviewApp(result.data);
    } catch (err) {
      console.warn('Detail API unavailable, using fallback:', err.message);
    }

    const cached = getCachedAdmission(id);
    if (cached) return normalizeReviewApp({ ...cached });

    try {
      const full = await fetchJson('/api/admission/pending', 8000);
      const list = full.success && Array.isArray(full.data) ? full.data : [];
      cachePendingAdmissions(list);
      const found = list.find(item => item.id === id || item.applicationNumber === id);
      if (found) return normalizeReviewApp({ ...found });
    } catch (err) {
      console.warn('Full pending fallback failed:', err.message);
    }

    const pending = await loadPendingAdmissions();
    const found = pending.find(item => item.id === id || item.applicationNumber === id);
    if (found) return normalizeReviewApp({ ...found });

    throw new Error('Application not found. Go back and open Review again.');
  }

  async function loadDashboard() {
    const result = await fetchJson('/api/faculty/dashboard', 12000);
    if (result.success && result.data) {
      const d = result.data;
      d.pendingAdmissions = Array.isArray(d.pendingAdmissions) ? d.pendingAdmissions : [];
      return d;
    }
    throw new Error('Dashboard load failed');
  }

  async function loadPendingAdmissions() {
    const result = await fetchJson('/api/admission/pending', 10000);
    const list = result.success && Array.isArray(result.data) ? result.data : [];
    cachePendingAdmissions(list);
    return list;
  }

  async function loadAdmissionHistory() {
    const result = await fetchJson('/api/admission/history', 10000);
    return result.success && Array.isArray(result.data) ? result.data : [];
  }

  function ensureReviewModalRoot() {
    let root = document.getElementById('adminReviewModalRoot');
    if (root) return root;

    root = document.createElement('div');
    root.id = 'adminReviewModalRoot';
    root.innerHTML = `
      <div class="admin-modal-overlay" id="adminReviewModalOverlay" aria-hidden="true">
        <div class="admin-modal" role="dialog" aria-modal="true" aria-labelledby="adminReviewModalTitle">
          <div class="admin-modal-body" id="adminReviewModalBody"></div>
          <div class="admin-modal-actions" id="adminReviewModalActions"></div>
        </div>
      </div>`;
    document.body.appendChild(root);

    root.querySelector('#adminReviewModalOverlay').addEventListener('click', e => {
      if (e.target.id === 'adminReviewModalOverlay' && root._onCancel) {
        root._onCancel();
      }
    });

    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && root.querySelector('#adminReviewModalOverlay').classList.contains('open')) {
        root._onCancel?.();
      }
    });

    return root;
  }

  function closeReviewModal() {
    const overlay = document.getElementById('adminReviewModalOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('admin-modal-open');
    const root = document.getElementById('adminReviewModalRoot');
    if (root) {
      root._onConfirm = null;
      root._onCancel = null;
    }
  }

  function confirmReviewAction(action, applicantName) {
    return new Promise(resolve => {
      const root = ensureReviewModalRoot();
      const overlay = root.querySelector('#adminReviewModalOverlay');
      const body = root.querySelector('#adminReviewModalBody');
      const actions = root.querySelector('#adminReviewModalActions');
      const isApprove = action === 'approve';

      body.innerHTML = `
        <div class="admin-modal-icon ${isApprove ? 'approve' : 'reject'}">
          <i class="fas ${isApprove ? 'fa-check' : 'fa-times'}"></i>
        </div>
        <h3 id="adminReviewModalTitle">${isApprove ? 'Approve Application?' : 'Reject Application?'}</h3>
        ${applicantName ? `<div class="admin-modal-applicant">${escHtml(applicantName)}</div>` : ''}
        <p>${isApprove
          ? 'Student ID and temporary password will be emailed. Registration form is sent after payment approval.'
          : 'The applicant will be notified via email. You may optionally provide a reason below.'}</p>
        ${isApprove ? '' : `
          <div class="admin-modal-reason">
            <label for="adminRejectReason">Reason for rejection (optional)</label>
            <textarea id="adminRejectReason" placeholder="Enter reason..."></textarea>
          </div>`}`;

      actions.innerHTML = isApprove
        ? `
          <button type="button" class="admin-modal-btn-cancel" data-action="cancel">Cancel</button>
          <button type="button" class="admin-modal-btn-approve" data-action="confirm">
            <i class="fas fa-check"></i> Approve
          </button>`
        : `
          <button type="button" class="admin-modal-btn-cancel" data-action="cancel">Cancel</button>
          <button type="button" class="admin-modal-btn-reject" data-action="confirm">
            <i class="fas fa-times"></i> Reject
          </button>`;

      const finish = result => {
        closeReviewModal();
        resolve(result);
      };

      root._onCancel = () => finish({ confirmed: false });
      root._onConfirm = () => {
        const reasonEl = document.getElementById('adminRejectReason');
        const reason = reasonEl ? reasonEl.value.trim() : '';
        finish({ confirmed: true, reason: reason || null });
      };

      actions.querySelector('[data-action="cancel"]').addEventListener('click', root._onCancel);
      actions.querySelector('[data-action="confirm"]').addEventListener('click', root._onConfirm);

      overlay.classList.add('open');
      overlay.setAttribute('aria-hidden', 'false');
      document.body.classList.add('admin-modal-open');

      if (!isApprove) {
        setTimeout(() => document.getElementById('adminRejectReason')?.focus(), 100);
      }
    });
  }

  function confirmDialog(options = {}) {
    const {
      title = 'Are you sure?',
      message = '',
      detail = '',
      confirmLabel = 'Confirm',
      cancelLabel = 'Cancel',
      variant = 'approve',
      icon = null,
    } = options;

    const iconMap = {
      approve: 'fa-check',
      reject: 'fa-rotate-left',
      info: 'fa-calendar-check',
      warning: 'fa-triangle-exclamation',
    };
    const iconClass = variant === 'reject' ? 'reject' : variant === 'info' ? 'info' : variant === 'warning' ? 'warning' : 'approve';
    const confirmBtnClass = variant === 'reject'
      ? 'admin-modal-btn-reject'
      : variant === 'info'
        ? 'admin-modal-btn-primary'
        : 'admin-modal-btn-approve';

    return new Promise(resolve => {
      const root = ensureReviewModalRoot();
      const overlay = root.querySelector('#adminReviewModalOverlay');
      const body = root.querySelector('#adminReviewModalBody');
      const actions = root.querySelector('#adminReviewModalActions');

      body.innerHTML = `
        <div class="admin-modal-icon ${iconClass}">
          <i class="fas ${icon || iconMap[variant] || 'fa-check'}"></i>
        </div>
        <h3 id="adminReviewModalTitle">${escHtml(title)}</h3>
        ${detail ? `<div class="admin-modal-applicant">${escHtml(detail)}</div>` : ''}
        <p>${escHtml(message)}</p>`;

      actions.innerHTML = `
        <button type="button" class="admin-modal-btn-cancel" data-action="cancel">${escHtml(cancelLabel)}</button>
        <button type="button" class="${confirmBtnClass}" data-action="confirm">${escHtml(confirmLabel)}</button>`;

      const finish = confirmed => {
        closeReviewModal();
        resolve(confirmed);
      };

      root._onCancel = () => finish(false);
      root._onConfirm = () => finish(true);

      actions.querySelector('[data-action="cancel"]').addEventListener('click', root._onCancel);
      actions.querySelector('[data-action="confirm"]').addEventListener('click', root._onConfirm);

      overlay.classList.add('open');
      overlay.setAttribute('aria-hidden', 'false');
      document.body.classList.add('admin-modal-open');
    });
  }

  function alertDialog(options = {}) {
    return showReviewMessage({
      type: options.type || 'success',
      title: options.title || 'Done',
      message: options.message || '',
    });
  }

  function showReviewMessage({ type = 'success', title, message }) {
    return new Promise(resolve => {
      const root = ensureReviewModalRoot();
      const overlay = root.querySelector('#adminReviewModalOverlay');
      const body = root.querySelector('#adminReviewModalBody');
      const actions = root.querySelector('#adminReviewModalActions');
      const iconClass = type === 'error' ? 'error' : 'success';

      body.innerHTML = `
        <div class="admin-modal-icon ${iconClass}">
          <i class="fas ${type === 'error' ? 'fa-circle-exclamation' : 'fa-circle-check'}"></i>
        </div>
        <h3 id="adminReviewModalTitle">${title}</h3>
        <p>${message}</p>`;

      actions.innerHTML = `
        <button type="button" class="admin-modal-btn-ok" data-action="ok">OK</button>`;

      const close = () => {
        closeReviewModal();
        resolve();
      };

      root._onCancel = close;
      actions.querySelector('[data-action="ok"]').addEventListener('click', close);

      overlay.classList.add('open');
      overlay.setAttribute('aria-hidden', 'false');
      document.body.classList.add('admin-modal-open');
    });
  }

  async function reviewAdmission(applicationId, action, reason = null) {
    const user = getUser();
    if (!user) return { success: false, error: 'Not logged in.' };

    const res = await fetch('/api/admission/review', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        applicationId,
        action,
        facultyId: user.id,
        reason
      })
    });
    return res.json();
  }

  async function handleReviewDecision(reviewId, action, applicantName, container) {
    const confirmation = await confirmReviewAction(action, applicantName);
    if (!confirmation.confirmed) {
      return { cancelled: true };
    }

    const btn = document.getElementById(action === 'approve' ? 'btnApprove' : 'btnReject');
    const originalHtml = btn?.innerHTML;
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    }

    try {
      const result = await reviewAdmission(reviewId, action, confirmation.reason);

      if (!result.success) {
        await showReviewMessage({
          type: 'error',
          title: action === 'approve' ? 'Approval Failed' : 'Rejection Failed',
          message: [result.error, result.details, result.hint].filter(Boolean).join(' ') || 'Something went wrong. Please try again.',
        });
        return result;
      }

      if (action === 'approve') {
        let msg = `Student ID: <strong>${escHtml(result.studentId || '—')}</strong><br>Approval email queued for <strong>${escHtml(result.email || 'applicant')}</strong>. It should arrive within 1–2 minutes — check Spam if not in Primary. Registration form after payment approval.`;
        if (result.emailSent === false) msg += '<br><br><em>Warning: Email could not be sent.</em>';
        await showReviewMessage({ type: 'success', title: 'Application Approved', message: msg });
      } else {
        await showReviewMessage({
          type: 'success',
          title: 'Application Rejected',
          message: `The applicant has been notified via email.${confirmation.reason ? `<br><br>Reason: ${escHtml(confirmation.reason)}` : ''}`,
        });
      }

      await mountApplicationReview(container, reviewId);
      return result;
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
      }
    }
  }

  const FA_ICONS = {
    dashboard: 'fa-gauge-high',
    strands: 'fa-book',
    request: 'fa-clipboard-check',
    history: 'fa-clock-rotate-left',
    subjects: 'fa-book-open',
    faculty: 'fa-chalkboard-user',
    rooms: 'fa-door-open',
    'section-quota': 'fa-users-between-lines',
    students: 'fa-users',
    logout: 'fa-right-from-bracket'
  };

  function faIcon(type) {
    const cls = FA_ICONS[type];
    return cls ? `<i class="fas ${cls} admin-nav-fa"></i>` : '';
  }

  function renderSidebar(activePage, pendingCount = 0) {
    const nav = [
      { id: 'dashboard', label: 'Dashboard', href: 'dashboard.html', icon: 'dashboard' },
      { id: 'strands', label: 'Strands', href: 'strands.html', icon: 'strands' },
      { id: 'enrollment-request', label: 'Admission Applications', href: 'enrollment-request.html', icon: 'request', badge: pendingCount },
      { id: 'subject-enrollment', label: 'Subject Enrollment', href: 'subject-enrollment-request.html', icon: 'request' },
      { id: 'payment-approval', label: 'Payment Approval', href: 'payment-approval.html', icon: 'request' },
      { id: 'enrollment-history', label: 'Admission History', href: 'enrollment-history.html', icon: 'history' },
      { id: 'term-settings', label: 'Enrollment Period', href: 'term-settings.html', icon: 'history' },
      { id: 'subjects', label: 'Subjects', href: 'subjects.html', icon: 'subjects' },
      { id: 'auto-schedule', label: 'AI Auto-Schedule', href: 'auto-schedule.html', icon: 'subjects' }
    ];
    const manage = [
      { id: 'faculty', label: 'Faculty', href: 'faculty.html', icon: 'faculty' },
      { id: 'rooms', label: 'Classrooms', href: 'rooms.html', icon: 'rooms' },
      { id: 'section-quota', label: 'Section Quota', href: 'section-quota.html', icon: 'section-quota' },
      { id: 'students', label: 'Student List', href: 'students.html', icon: 'students' }
    ];

    const navHtml = nav.map(p => `
      <a href="${p.href}" class="admin-nav-link ${p.id === activePage ? 'active' : ''}">
        ${faIcon(p.icon)} ${p.label}
        ${p.badge > 0 ? `<span class="admin-nav-badge">${p.badge}</span>` : ''}
      </a>
    `).join('');

    const manageHtml = manage.map(p => `
      <a href="${p.href}" class="admin-nav-link sub ${p.id === activePage ? 'active' : ''}">
        ${faIcon(p.icon)} ${p.label}
      </a>
    `).join('');

    return `
      <aside class="admin-sidebar" id="adminSidebar">
        <div class="admin-brand">
          <span>Enrollment Management System</span>
        </div>
        <nav class="admin-nav">
          ${navHtml}
          <div class="admin-nav-section">Manage</div>
          ${manageHtml}
          <a href="#" class="admin-nav-link" onclick="AdminApp.logout(); return false;">${faIcon('logout')} Logout</a>
        </nav>
      </aside>`;
  }

  function icon(type) {
    return faIcon(type);
  }

  function renderDocList(documents) {
    if (!documents?.length) {
      return '<div class="admin-empty">No documents uploaded.</div>';
    }
    return `<div class="admin-doc-list">${documents.map(doc => `
      <div class="admin-doc-item ${doc.uploaded ? '' : 'missing'}">
        <div class="admin-doc-meta">
          <i class="fas ${doc.uploaded ? 'fa-file-pdf' : 'fa-file-circle-xmark'}"></i>
          <div>
            <strong>${doc.label}</strong>
            <small>${doc.uploaded ? 'Uploaded' : 'Missing'}</small>
          </div>
        </div>
        <div class="admin-doc-actions">
          ${doc.url ? `<a href="${doc.url}" target="_blank" rel="noopener"><i class="fas fa-eye"></i> View</a>` : '<span style="color:#94a3b8;font-size:12px;">Not available</span>'}
        </div>
      </div>
    `).join('')}</div>`;
  }

  function renderInfoItem(label, value) {
    const display = value === null || value === undefined || String(value).trim() === '' ? '—' : value;
    return `<div class="admin-info-item"><label>${label}</label><span>${display}</span></div>`;
  }

  function formatPaymentMode(app) {
    if (app.paymentMode === 'gcash') {
      return `GCash · Ref: ${app.gcashReference || '—'}`;
    }
    if (app.paymentMode === 'bank') {
      return `Bank Transfer · ${app.bankCode || '—'} · Ref: ${app.bankReference || '—'}`;
    }
    return 'Pay at Cashier';
  }

  function formatScheduleItem(item) {
    const section = item.section || '';
    const dayTime = String(item.dayTime || '')
      .replace(/:00/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    const slots = item.slots != null ? `[${item.slots}] ` : '';
    if (section || dayTime) return `${slots}${section}${section && dayTime ? ' · ' : ''}${dayTime}`.trim();
    return item.scheduleId ? `Schedule ID: ${item.scheduleId}` : '—';
  }

  function renderScheduleTable(schedules) {
    if (!schedules?.length) {
      return '<div class="admin-empty">No preferred schedules submitted.</div>';
    }
    return `
      <div class="admin-schedule-table-wrap">
        <table class="admin-schedule-table">
          <thead>
            <tr>
              <th>Code</th>
              <th>Subject</th>
              <th>Schedule</th>
            </tr>
          </thead>
          <tbody>
            ${schedules.map(item => `
              <tr>
                <td>${escHtml(item.code || '—')}</td>
                <td>${escHtml(item.description || '—')}</td>
                <td>${escHtml(formatScheduleItem(item))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>`;
  }

  function renderApplicationReview(app) {
    const paymentLabel = formatPaymentMode(app);

    return `
      <a href="enrollment-request.html" class="admin-review-back"><i class="fas fa-arrow-left"></i> Back to Review Applications</a>
      <div class="admin-card admin-review-resume" style="margin-bottom:16px;">
        <div class="admin-card-body padded">
          <div class="admin-review-resume-banner">
            <div class="admin-review-headline-top">
              <h2>${escHtml(app.student || 'Applicant')}</h2>
              ${statusBadge(app.status)}
            </div>
            <div class="admin-review-meta">
              <span><i class="fas fa-hashtag"></i> ${escHtml(app.applicationNumber || app.id || '—')}</span>
              <span><i class="fas fa-graduation-cap"></i> ${escHtml(app.gradeLevel || '—')} · ${escHtml(app.strandCode || '—')}</span>
              <span><i class="fas fa-calendar"></i> Submitted ${escHtml(app.date || app.submittedAt?.slice(0, 10) || '—')}</span>
            </div>
            <div class="admin-review-meta">
              <span><i class="fas fa-envelope"></i> ${escHtml(app.email || '—')}</span>
              <span><i class="fas fa-phone"></i> ${escHtml(app.contactNumber || '—')}</span>
            </div>
          </div>

          <div class="admin-review-resume-header">
            <div class="admin-review-photo">
              ${app.profilePhotoUrl
                ? `<img src="${app.profilePhotoUrl}" alt="Profile photo of ${escHtml(app.student || 'applicant')}" class="admin-profile-photo-img">`
                : `<div class="admin-profile-photo-placeholder"><i class="fas fa-user"></i><span>No photo</span></div>`}
            </div>
          </div>

          <div class="admin-review-grid">
            <div>
              <h3 class="admin-review-section-title"><i class="fas fa-user"></i> Personal Information</h3>
              <div class="admin-info-grid">
                ${renderInfoItem('Full Name', app.student)}
                ${renderInfoItem('Birthdate', app.birthdate)}
                ${renderInfoItem('Gender', app.gender)}
                ${renderInfoItem('Email', app.email)}
                ${renderInfoItem('Contact', app.contactNumber)}
                ${renderInfoItem('Admission Type', app.admissionType)}
              </div>
            </div>
            <div>
              <h3 class="admin-review-section-title"><i class="fas fa-map-marker-alt"></i> Address</h3>
              <div class="admin-info-grid">
                ${renderInfoItem('House / Unit No.', app.houseNumber)}
                ${renderInfoItem('Street', app.street)}
                ${renderInfoItem('Barangay', app.barangay)}
                ${renderInfoItem('City / Municipality', app.city)}
                ${renderInfoItem('Province', app.province)}
                ${renderInfoItem('Full Address', app.address)}
              </div>
            </div>
          </div>

          <div class="admin-review-grid">
            <div>
              <h3 class="admin-review-section-title"><i class="fas fa-school"></i> Academic Information</h3>
              <div class="admin-info-grid">
                ${renderInfoItem('Grade Level', app.gradeLevel)}
                ${renderInfoItem('Strand', app.strandCode)}
                ${renderInfoItem('Previous School', app.previousSchool)}
              </div>
            </div>
            <div>
              <h3 class="admin-review-section-title"><i class="fas fa-credit-card"></i> Payment Information</h3>
              <div class="admin-info-grid">
                ${renderInfoItem('Payment Mode', paymentLabel)}
                ${renderInfoItem('Amount', app.paymentAmount ? '₱' + app.paymentAmount : '—')}
                ${renderInfoItem('Payment Status', app.paymentStatus || '—')}
                ${renderInfoItem('GCash Sender', app.paymentMode === 'gcash' ? (app.gcashSenderName || '—') : '—')}
                ${renderInfoItem('Bank Sender', app.paymentMode === 'bank' ? (app.bankSenderName || '—') : '—')}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="admin-card" style="margin-bottom:16px;">
        <div class="admin-card-head"><i class="fas fa-calendar-alt"></i> Preferred Subject Schedules</div>
        <div class="admin-card-body padded">${renderScheduleTable(app.subjectScheduleDetails)}</div>
      </div>

      <div class="admin-card" style="margin-bottom:16px;">
        <div class="admin-card-head"><i class="fas fa-folder-open"></i> Uploaded Documents</div>
        <div class="admin-card-body padded">${renderDocList(app.documents)}</div>
      </div>
      ${app.status === 'pending' ? `
      <div class="admin-card">
        <div class="admin-card-head"><i class="fas fa-gavel"></i> Review Decision</div>
        <div class="admin-card-body padded">
          <p style="margin:0 0 14px;color:#64748b;font-size:14px;">Review the applicant information and documents above, then choose to approve or reject this application.</p>
          <div class="admin-review-actions">
            <button class="admin-btn approve" id="btnApprove"><i class="fas fa-check"></i> Approve Application</button>
            <button class="admin-btn reject" id="btnReject"><i class="fas fa-times"></i> Reject Application</button>
          </div>
        </div>
      </div>` : `
      <div class="admin-card">
        <div class="admin-card-body padded">
          <div class="admin-empty">This application has already been <strong>${app.status}</strong>.
          ${app.studentId ? `<br>Student ID: ${app.studentId}` : ''}
          ${app.rejectionReason ? `<br>Reason: ${app.rejectionReason}` : ''}</div>
        </div>
      </div>`}`;
  }

  async function mountApplicationReview(container, applicationId) {
    container.innerHTML = '<div class="admin-empty">Loading application...</div>';
    try {
      await refreshLayout('enrollment-request', 'Review Application');
      const app = await loadAdmissionDetail(applicationId);
      container.innerHTML = renderApplicationReview(app);

      if (app.status !== 'pending') return;

      document.getElementById('btnApprove')?.addEventListener('click', async () => {
        const reviewId = app.id || applicationId;
        if (!reviewId) {
          await showReviewMessage({
            type: 'error',
            title: 'Missing Application',
            message: 'Go back and open Review again.',
          });
          return;
        }
        await handleReviewDecision(reviewId, 'approve', app.student, container);
      });

      document.getElementById('btnReject')?.addEventListener('click', async () => {
        const reviewId = app.id || applicationId;
        if (!reviewId) {
          await showReviewMessage({
            type: 'error',
            title: 'Missing Application',
            message: 'Go back and open Review again.',
          });
          return;
        }
        await handleReviewDecision(reviewId, 'reject', app.student, container);
      });
    } catch (err) {
      await refreshLayout('enrollment-request', 'Review Application');
      container.innerHTML = `<div class="admin-empty">Could not load application.<br>${err.message || ''}<br><br><a href="enrollment-request.html" class="admin-review-back"><i class="fas fa-arrow-left"></i> Back to Review Applications</a></div>`;
    }
  }

  function renderHeader(user, pendingRequests = []) {
    const notifItems = pendingRequests.slice(0, 3).map(r => `
      <div class="notif-item">
        <strong>${r.student || r.applicant || 'Applicant'}</strong>
        <span>${r.studentId || r.applicationNumber || r.id || ''}</span>
      </div>
    `).join('') || '<div class="notif-item"><span>No pending requests</span></div>';

    return `
      <header class="admin-header">
        <button class="admin-menu-toggle" onclick="AdminApp.toggleSidebar()" aria-label="Menu">☰</button>
        <div class="admin-header-left">
          <h1 id="adminPageTitle">Dashboard</h1>
          <p id="adminPageGreet">Welcome back, ${formatName(user)}! Here's an overview of your system.</p>
        </div>
        <div class="admin-header-right">
          <div class="admin-notif-wrap">
            <button class="admin-notif-btn" onclick="AdminApp.toggleNotif(event)" aria-label="Notifications">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
              ${pendingRequests.length ? '<span class="admin-notif-dot"></span>' : ''}
            </button>
            <div class="admin-notif-panel" id="adminNotifPanel">
              <h4>Enrollment Requests (${pendingRequests.length})</h4>
              ${notifItems}
              <div class="notif-footer"><a href="enrollment-request.html">Review All Applications</a></div>
            </div>
          </div>
          <div class="admin-user-block">
            <div class="admin-user-name">${formatName(user)}</div>
            <div class="admin-user-meta">Last Login: ${user.lastLogin || '—'}</div>
          </div>
        </div>
      </header>`;
  }

  function initLayout(activePage, pageTitle, pendingCount = 0, pendingList = null) {
    if (!requireAuth()) return null;
    const user = getUser();
    const pendingRequests = Array.isArray(pendingList)
      ? pendingList
      : (pendingCount > 0 ? [{ student: `${pendingCount} pending`, id: '' }] : []);

    document.getElementById('adminSidebarWrap').innerHTML = renderSidebar(activePage, pendingCount);
    document.getElementById('adminHeader').innerHTML = renderHeader(user, pendingRequests);

    if (pageTitle) {
      const t = document.getElementById('adminPageTitle');
      if (t) t.textContent = pageTitle;
    }

    document.addEventListener('click', closeNotif);
    return user;
  }

  async function refreshLayout(activePage, pageTitle) {
    if (!requireAuth()) return [];
    let pending = [];
    try {
      pending = await loadPendingAdmissions();
    } catch (err) {
      console.warn('Could not load pending admissions:', err);
    }
    initLayout(activePage, pageTitle, pending.length, pending);
    return pending;
  }

  function toggleSidebar() {
    document.querySelector('.admin-sidebar')?.classList.toggle('open');
  }

  function toggleNotif(e) {
    e.stopPropagation();
    document.getElementById('adminNotifPanel')?.classList.toggle('open');
  }

  function closeNotif() {
    document.getElementById('adminNotifPanel')?.classList.remove('open');
  }

  function renderDashboardStats(d) {
    return `
      <div class="admin-stats">
        <div class="admin-stat-card">
          <div class="admin-stat-label">Total Students</div>
          <div class="admin-stat-value">${d.totalStudents ?? 0}</div>
          <a href="students.html" class="admin-stat-link">View →</a>
        </div>
        <div class="admin-stat-card green">
          <div class="admin-stat-label">Total Strands</div>
          <div class="admin-stat-value">${d.totalStrands ?? 0}</div>
          <a href="strands.html" class="admin-stat-link">Manage →</a>
        </div>
        <div class="admin-stat-card yellow">
          <div class="admin-stat-label">Pending Enrollments</div>
          <div class="admin-stat-value">${d.pendingEnrollments ?? 0}</div>
          <a href="enrollment-request.html" class="admin-stat-link">Review →</a>
        </div>
        <div class="admin-stat-card purple">
          <div class="admin-stat-label">Total Admissions</div>
          <div class="admin-stat-value">${d.totalAdmissions ?? 0}</div>
          <a href="enrollment-history.html" class="admin-stat-link">Manage →</a>
        </div>
      </div>`;
  }

  function renderQuickActions() {
    return `
      <h2 class="admin-section-title">Quick Actions</h2>
      <div class="admin-quick-actions">
        <div class="admin-quick-card">
          <p>Review new student applications with documents and payment proof.</p>
          <a href="enrollment-request.html" class="admin-qa-btn purple"><i class="fas fa-clipboard-check"></i> Review Applications</a>
        </div>
        <div class="admin-quick-card">
          <p>Create and manage all strands offered in the Enrollment Management System.</p>
          <a href="strands.html" class="admin-qa-btn blue">Go to Strands</a>
        </div>
        <div class="admin-quick-card">
          <p>Add and organize subjects for each strand in the curriculum.</p>
          <a href="subjects.html" class="admin-qa-btn green">Go to Subjects</a>
        </div>
      </div>`;
  }

  function renderActivityTable(items) {
    if (!items.length) {
      return '<div class="admin-empty">No enrollment activity yet.</div>';
    }
    return `
      <table class="admin-table">
        <thead><tr><th>Student</th><th>Application / Subject</th><th>Date</th><th>Status</th></tr></thead>
        <tbody>${items.map(a => `
          <tr>
            <td><div class="student-name">${a.student || '—'}</div><div class="student-sub">${a.strand || ''}</div></td>
            <td>${a.subject || '—'}</td>
            <td>${a.date || '—'}</td>
            <td>${statusBadge(a.status)}</td>
          </tr>`).join('')}</tbody>
      </table>`;
  }

  function renderEnrollmentStats(stats) {
    const s = stats || { approved: 0, pending: 0, rejected: 0 };
    const total = s.approved + s.pending + s.rejected || 1;
    const pct = n => Math.round((n / total) * 100);
    return `
      <div class="admin-stat-bar"><div class="bar-label"><span>Approved</span><span>${s.approved} (${pct(s.approved)}%)</span></div><div class="bar-track"><div class="bar-fill green" style="width:${pct(s.approved)}%"></div></div></div>
      <div class="admin-stat-bar"><div class="bar-label"><span>Pending</span><span>${s.pending} (${pct(s.pending)}%)</span></div><div class="bar-track"><div class="bar-fill yellow" style="width:${pct(s.pending)}%"></div></div></div>
      <div class="admin-stat-bar"><div class="bar-label"><span>Rejected</span><span>${s.rejected} (${pct(s.rejected)}%)</span></div><div class="bar-track"><div class="bar-fill red" style="width:${pct(s.rejected)}%"></div></div></div>`;
  }

  function renderStrandTable(strands) {
    if (!strands?.length) return '<div class="admin-empty">No strand data yet.</div>';
    return `
      <table class="admin-table">
        <thead><tr><th>Strand</th><th>Grade</th><th>Applicants</th></tr></thead>
        <tbody>${strands.map(s => `
          <tr><td><strong>${s.name}</strong></td><td>${s.grade || 'Grade 11 & 12'}</td><td>${s.applicants ?? s.subjects ?? 0}</td></tr>
        `).join('')}</tbody>
      </table>`;
  }

  async function mountDashboard(container) {
    container.innerHTML = '<div class="admin-empty">Loading dashboard...</div>';
    try {
      const d = await loadDashboard();
      container.innerHTML = `
        ${renderDashboardStats(d)}
        ${renderQuickActions()}
        <div class="admin-grid">
          <div class="admin-card">
            <div class="admin-card-head">Recent Enrollment Activity</div>
            <div class="admin-card-body" id="dashActivity">${renderActivityTable(d.recentActivity || [])}</div>
          </div>
          <div>
            <div class="admin-card" style="margin-bottom:16px">
              <div class="admin-card-head">Enrollment Statistics</div>
              <div class="admin-card-body padded" id="dashStats">${renderEnrollmentStats(d.enrollmentStats)}</div>
            </div>
            <div class="admin-card">
              <div class="admin-card-head">Strand Distribution</div>
              <div class="admin-card-body" id="dashStrands">${renderStrandTable(d.strandDistribution)}</div>
            </div>
          </div>
        </div>`;
      initLayout('dashboard', 'Dashboard', d.pendingEnrollments || 0);
      refreshLayout('dashboard', 'Dashboard');
    } catch (err) {
      container.innerHTML = `<div class="admin-empty">Could not load dashboard. Make sure <strong>python server.py</strong> is running.</div>`;
      console.error(err);
    }
  }

  return {
    getUser,
    requireAuth,
    logout,
    initLayout,
    refreshLayout,
    toggleSidebar,
    toggleNotif,
    loadDashboard,
    loadPendingAdmissions,
    loadAdmissionHistory,
    loadAdmissionDetail,
    reviewAdmission,
    mountDashboard,
    mountApplicationReview,
    statusBadge,
    formatName,
    fetchJson,
    postJson,
    escHtml,
    confirmDialog,
    alertDialog,
    showReviewMessage
  };
})();
