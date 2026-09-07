const FacultyManageApp = (() => {
  let strands = [];
  let teachers = [];
  let strandsWarning = '';
  let currentTeacher = null;
  let modalMode = 'view';

  function esc(str) {
    return AdminApp.escHtml(String(str ?? ''));
  }

  function showMessage(message, type = 'error') {
    let box = document.getElementById('facultyPageMsg');
    if (!box) {
      box = document.createElement('div');
      box.id = 'facultyPageMsg';
      box.className = `admin-page-msg ${type}`;
      document.querySelector('.admin-card')?.prepend(box);
    }
    box.className = `admin-page-msg ${type}`;
    box.innerHTML = esc(message);
  }

  function clearMessage() {
    document.getElementById('facultyPageMsg')?.remove();
  }

  function getInitials(teacher) {
    const first = (teacher?.first_name || teacher?.name || '?').charAt(0);
    const last = (teacher?.last_name || '').charAt(0);
    return (first + last).toUpperCase() || '?';
  }

  function formatTeacherName(teacher) {
    if (!teacher) return '—';
    const parts = [teacher.first_name, teacher.middle_name, teacher.last_name].filter(Boolean);
    return parts.join(' ').trim() || teacher.name || '—';
  }

  function renderStrandChips(selected = [], containerId = 'teacherStrandChips') {
    const wrap = document.getElementById(containerId);
    if (!wrap) return;
    if (!strands.length) {
      wrap.innerHTML = `
        <p class="admin-empty">
          ${strandsWarning || 'No strands loaded.'}
          <br><small>Run <strong>supabase/faculty-strands-rooms.sql</strong> in Supabase SQL Editor, restart server, then refresh.</small>
        </p>`;
      return;
    }
    wrap.innerHTML = strands.map(s => `
      <label class="auto-sched-chip">
        <input type="checkbox" name="teacherStrand" value="${esc(s.code)}" ${selected.includes(s.code) ? 'checked' : ''}>
        ${esc(s.code)}
      </label>
    `).join('');
  }

  function showTableLoading(message = 'Loading professors…') {
    const wrap = document.getElementById('teachersTable');
    if (!wrap) return;
    wrap.innerHTML = `
      <div class="faculty-table-loading">
        <div class="auto-sched-loading-spinner"></div>
        <p>${esc(message)}</p>
      </div>`;
  }

  function renderTable() {
    const wrap = document.getElementById('teachersTable');
    if (!teachers.length) {
      wrap.innerHTML = '<div class="admin-empty">No professors yet. Click <strong>+ Add Professor</strong> to get started.</div>';
      return;
    }
    wrap.innerHTML = `
      <table class="admin-table">
        <thead>
          <tr><th>Faculty ID</th><th>Name</th><th>Strands</th><th>Department</th><th>Max Load</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          ${teachers.map(t => `
            <tr>
              <td><strong>${esc(t.faculty_id)}</strong></td>
              <td>${esc(t.name)}</td>
              <td>${(t.strands || []).map(s => `<span class="strand-badge">${esc(s)}</span>`).join(' ') || '—'}</td>
              <td>${esc(t.department || '—')}</td>
              <td>${esc(t.max_load_units || 3)}</td>
              <td>${AdminApp.statusBadge(t.is_active ? 'Active' : 'Inactive')}</td>
              <td><button type="button" class="admin-btn secondary view-teacher" data-id="${esc(t.id)}">View</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    wrap.querySelectorAll('.view-teacher').forEach(btn => {
      btn.addEventListener('click', () => openView(btn.dataset.id));
    });
  }

  function closeViewModal() {
    const overlay = document.getElementById('teacherViewOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('admin-modal-open');
    currentTeacher = null;
    modalMode = 'view';
  }

  function renderViewActions() {
    const actions = document.getElementById('teacherViewActions');
    if (!actions) return;
    actions.innerHTML = `
      <button type="button" class="faculty-modal-btn-edit" id="editTeacherFromView">Edit Professor</button>
      <button type="button" class="faculty-modal-btn-close" id="closeTeacherView">Close</button>`;
    document.getElementById('editTeacherFromView')?.addEventListener('click', () => {
      if (currentTeacher) openEditModal(currentTeacher);
    });
    document.getElementById('closeTeacherView')?.addEventListener('click', closeViewModal);
  }

  function renderEditActions() {
    const actions = document.getElementById('teacherViewActions');
    if (!actions) return;
    actions.innerHTML = `
      <button type="submit" form="teacherModalForm" class="faculty-modal-btn-save" id="saveTeacherModalBtn">Save Changes</button>
      <button type="button" class="faculty-modal-btn-cancel" id="cancelTeacherEdit">Cancel</button>`;
    document.getElementById('cancelTeacherEdit')?.addEventListener('click', () => {
      if (currentTeacher) renderViewModal(currentTeacher);
    });
  }

  function renderViewModal(teacher) {
    currentTeacher = teacher;
    modalMode = 'view';
    const content = document.getElementById('teacherViewContent');
    if (!content || !teacher) return;

    const strandHtml = (teacher.strands || []).length
      ? teacher.strands.map(s => `<span class="strand-badge">${esc(s)}</span>`).join(' ')
      : '<span style="color:#94a3b8;">—</span>';

    content.innerHTML = `
      <div class="faculty-modal-header">
        <div class="faculty-modal-avatar">${esc(getInitials(teacher))}</div>
        <div class="faculty-modal-head-text">
          <h3 id="teacherViewTitle">${esc(formatTeacherName(teacher))}</h3>
          <p>${esc(teacher.department || 'No department assigned')}</p>
        </div>
        <div class="faculty-modal-head-meta">
          <span class="faculty-modal-id-badge">${esc(teacher.faculty_id)}</span>
        </div>
      </div>
      <div class="faculty-modal-body">
        <div class="faculty-credential-card">
          <div class="faculty-credential-item">
            <label>Faculty ID (Login)</label>
            <div class="value">${esc(teacher.faculty_id)}</div>
          </div>
          <div class="faculty-credential-item">
            <label>Password</label>
            <div class="value password">${esc(teacher.password || 'teacher123')}</div>
          </div>
        </div>
        <div class="faculty-detail-grid">
          <div class="faculty-detail-item"><label>Email</label><span>${esc(teacher.email || '—')}</span></div>
          <div class="faculty-detail-item"><label>Max Load</label><span>${esc(teacher.max_load_units || 3)} subjects / sem</span></div>
          <div class="faculty-detail-item"><label>Status</label><span>${teacher.is_active ? 'Active' : 'Inactive'}</span></div>
          <div class="faculty-detail-item"><label>Last Login</label><span>${esc(teacher.last_login || '—')}</span></div>
        </div>
        <div class="faculty-modal-strands">
          <label>Strands</label>
          <div>${strandHtml}</div>
        </div>
      </div>`;

    renderViewActions();
    openModalShell();
  }

  function openEditModal(teacher) {
    currentTeacher = teacher;
    modalMode = 'edit';
    const content = document.getElementById('teacherViewContent');
    if (!content || !teacher) return;

    content.innerHTML = `
      <div class="faculty-modal-header">
        <div class="faculty-modal-avatar">${esc(getInitials(teacher))}</div>
        <div class="faculty-modal-head-text">
          <h3>Edit Professor</h3>
          <p>${esc(teacher.faculty_id)} · ${esc(formatTeacherName(teacher))}</p>
        </div>
      </div>
      <div class="faculty-modal-body">
        <form id="teacherModalForm" class="admin-form faculty-modal-edit-form">
          <input type="hidden" id="teacherModalDbId" value="${esc(teacher.id)}">
          <div class="admin-form-row">
            <div class="admin-form-group">
              <label for="teacherModalLastName">Last Name</label>
              <input type="text" id="teacherModalLastName" class="admin-input" value="${esc(teacher.last_name || '')}" required>
            </div>
            <div class="admin-form-group">
              <label for="teacherModalFirstName">First Name</label>
              <input type="text" id="teacherModalFirstName" class="admin-input" value="${esc(teacher.first_name || '')}" required>
            </div>
          </div>
          <div class="admin-form-row">
            <div class="admin-form-group">
              <label for="teacherModalMiddleName">Middle Name</label>
              <input type="text" id="teacherModalMiddleName" class="admin-input" value="${esc(teacher.middle_name || '')}">
            </div>
            <div class="admin-form-group">
              <label for="teacherModalEmail">Email</label>
              <input type="email" id="teacherModalEmail" class="admin-input" value="${esc(teacher.email || '')}">
            </div>
          </div>
          <div class="admin-form-row">
            <div class="admin-form-group">
              <label for="teacherModalDepartment">Department</label>
              <input type="text" id="teacherModalDepartment" class="admin-input" value="${esc(teacher.department || '')}">
            </div>
            <div class="admin-form-group">
              <label for="teacherModalMaxLoad">Max Load (units)</label>
              <input type="number" id="teacherModalMaxLoad" class="admin-input" value="${esc(teacher.max_load_units || 3)}" min="1" max="6">
            </div>
          </div>
          <div class="admin-form-group">
            <label for="teacherModalPassword">New Password (optional)</label>
            <input type="text" id="teacherModalPassword" class="admin-input" placeholder="Leave blank to keep current password">
          </div>
          <div class="admin-form-group">
            <label>Strands this professor teaches</label>
            <div id="teacherModalStrandChips" class="auto-sched-strands"></div>
          </div>
        </form>
      </div>`;

    renderStrandChips(teacher.strands || [], 'teacherModalStrandChips');
    renderEditActions();

    document.getElementById('teacherModalForm')?.addEventListener('submit', saveTeacherFromModal, { once: true });
    openModalShell();
  }

  function openModalShell() {
    const overlay = document.getElementById('teacherViewOverlay');
    if (!overlay) return;
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('admin-modal-open');
  }

  async function openView(teacherId) {
    clearMessage();
    const content = document.getElementById('teacherViewContent');
    if (!content) return;

    content.innerHTML = '<div class="faculty-modal-body"><div class="admin-empty">Loading professor details...</div></div>';
    document.getElementById('teacherViewActions').innerHTML = '';
    openModalShell();

    try {
      const res = await AdminApp.fetchJson('/api/teachers/detail?id=' + encodeURIComponent(teacherId));
      renderViewModal(res.data);
    } catch (err) {
      const cached = teachers.find(t => t.id === teacherId);
      if (cached) {
        renderViewModal(cached);
        return;
      }
      closeViewModal();
      showMessage(err.message || 'Could not load professor details.');
    }
  }

  async function saveTeacherFromModal(e) {
    e.preventDefault();
    clearMessage();
    const btn = document.getElementById('saveTeacherModalBtn');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }

    try {
      const selectedStrands = [...document.querySelectorAll('#teacherModalStrandChips input[name="teacherStrand"]:checked')]
        .map(el => el.value);
      if (!selectedStrands.length) {
        showMessage('Select at least one strand this professor teaches.');
        return;
      }

      const payload = {
        id: document.getElementById('teacherModalDbId').value,
        lastName: document.getElementById('teacherModalLastName').value.trim(),
        firstName: document.getElementById('teacherModalFirstName').value.trim(),
        middleName: document.getElementById('teacherModalMiddleName').value.trim(),
        email: document.getElementById('teacherModalEmail').value.trim(),
        department: document.getElementById('teacherModalDepartment').value.trim(),
        maxLoadUnits: document.getElementById('teacherModalMaxLoad').value,
        strands: selectedStrands,
      };
      const password = document.getElementById('teacherModalPassword').value.trim();
      if (password) payload.password = password;

      await AdminApp.postJson('/api/teachers', payload);
      await loadAll();
      const updated = teachers.find(t => t.id === payload.id);
      if (updated) {
        try {
          const res = await AdminApp.fetchJson('/api/teachers/detail?id=' + encodeURIComponent(payload.id));
          renderViewModal(res.data);
        } catch (err) {
          renderViewModal(updated);
        }
        showMessage('Professor updated successfully.', 'success');
      } else {
        closeViewModal();
        showMessage('Professor updated successfully.', 'success');
      }
    } catch (err) {
      showMessage(err.message || 'Could not save professor.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Save Changes';
      }
    }
  }

  function openForm() {
    clearMessage();
    if (strandsWarning) showMessage(strandsWarning);
    document.getElementById('teacherFormWrap').hidden = false;
    document.getElementById('teacherDbId').value = '';
    document.getElementById('teacherForm').reset();
    document.getElementById('teacherMaxLoad').value = 3;
    document.getElementById('teacherPassword').placeholder = 'Default: teacher123';
    renderStrandChips([]);
    document.getElementById('teacherFormWrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function closeForm() {
    document.getElementById('teacherFormWrap').hidden = true;
    document.getElementById('teacherForm').reset();
    document.getElementById('teacherDbId').value = '';
  }

  async function loadStrands() {
    const strandRes = await AdminApp.fetchJson('/api/strands', 25000);
    strands = strandRes.data || [];
    strandsWarning = strandRes.warning || '';
    if (strandsWarning) showMessage(strandsWarning);
    renderStrandChips();
  }

  const REMOVED_STRANDS = ['GAS', 'CSS', 'HE', 'INDARTS', 'OTHER'];
  const LEGACY_FACULTY_IDS = new Set([
    'FAC-CK-01', 'FAC-CSS-01', 'FAC-GAS-01', 'FAC-HE-01', 'FAC-HUM-01', 'FAC-IA-01',
  ]);

  function isRemovedFaculty(teacher) {
    const id = (teacher.faculty_id || '').toUpperCase();
    if (LEGACY_FACULTY_IDS.has(id)) return true;
    const dept = (teacher.department || '').toUpperCase().trim();
    const strands = (teacher.strands || []).map(s => String(s).toUpperCase());
    return REMOVED_STRANDS.some(code =>
      strands.includes(code)
      || id.startsWith(`FAC-${code}-`)
      || id.includes(`-${code}-`)
      || dept.startsWith(`${code} DEPARTMENT`)
      || dept === code
    );
  }

  async function loadTeachers() {
    const teacherRes = await AdminApp.fetchJson('/api/teachers', 35000);
    teachers = (teacherRes.data || []).filter(t => t.is_active !== false && !isRemovedFaculty(t));
    renderTable();
  }

  async function loadAll() {
    showTableLoading();
    const [strandResult, teacherResult] = await Promise.allSettled([
      AdminApp.fetchJson('/api/strands', 25000),
      AdminApp.fetchJson('/api/teachers', 35000),
    ]);

    if (strandResult.status === 'fulfilled') {
      strands = strandResult.value.data || [];
      strandsWarning = strandResult.value.warning || '';
      if (strandsWarning) showMessage(strandsWarning);
      renderStrandChips();
    } else {
      strands = [];
      strandsWarning = strandResult.reason?.message || 'Could not load strands.';
      showMessage(strandsWarning);
      renderStrandChips();
    }

    if (teacherResult.status === 'fulfilled') {
      teachers = (teacherResult.value.data || []).filter(t => t.is_active !== false && !isRemovedFaculty(t));
      renderTable();
    } else {
      teachers = [];
      const msg = teacherResult.reason?.message || 'Could not load professors.';
      document.getElementById('teachersTable').innerHTML =
        `<div class="admin-empty">${esc(msg)}<br><small>Restart the admin server, then hard-refresh (Ctrl+Shift+R).</small></div>`;
    }
  }

  async function saveTeacher(e) {
    e.preventDefault();
    clearMessage();
    const btn = document.getElementById('saveTeacherBtn');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
      const selectedStrands = [...document.querySelectorAll('#teacherStrandChips input[name="teacherStrand"]:checked')].map(el => el.value);
      if (!selectedStrands.length) {
        showMessage('Select at least one strand this professor teaches.');
        return;
      }
      const payload = {
        lastName: document.getElementById('teacherLastName').value.trim(),
        firstName: document.getElementById('teacherFirstName').value.trim(),
        middleName: document.getElementById('teacherMiddleName').value.trim(),
        email: document.getElementById('teacherEmail').value.trim(),
        department: document.getElementById('teacherDepartment').value.trim(),
        maxLoadUnits: document.getElementById('teacherMaxLoad').value,
        strands: selectedStrands,
      };
      const password = document.getElementById('teacherPassword').value.trim();
      if (password) payload.password = password;

      const result = await AdminApp.postJson('/api/teachers', payload);
      closeForm();
      await loadAll();
      showMessage(result.message || 'Professor saved successfully.', 'success');
    } catch (err) {
      showMessage(err.message || 'Could not save professor.');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Save to Database';
    }
  }

  function bindEvents() {
    document.getElementById('openTeacherForm').addEventListener('click', () => openForm());
    document.getElementById('cancelTeacherForm').addEventListener('click', closeForm);
    document.getElementById('teacherForm').addEventListener('submit', saveTeacher);
    document.getElementById('teacherViewOverlay')?.addEventListener('click', (e) => {
      if (e.target.id === 'teacherViewOverlay') closeViewModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeViewModal();
    });
  }

  async function mount() {
    if (!AdminApp.requireAuth()) return;
    bindEvents();
    await AdminApp.refreshLayout('faculty', 'Faculty');
    try {
      await loadAll();
    } catch (err) {
      document.getElementById('teachersTable').innerHTML =
        `<div class="admin-empty">${esc(err.message)}<br><small>Run supabase/faculty-strands-rooms.sql in Supabase SQL Editor, then restart the server.</small></div>`;
    }
  }

  return { mount };
})();
