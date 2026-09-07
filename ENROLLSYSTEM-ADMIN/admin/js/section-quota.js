const SectionQuotaApp = (() => {
  let rows = [];

  function esc(str) {
    return AdminApp.escHtml(String(str ?? ''));
  }

  function showMessage(message, type = 'error') {
    let box = document.getElementById('sectionQuotaPageMsg');
    if (!box) {
      box = document.createElement('div');
      box.id = 'sectionQuotaPageMsg';
      box.className = `admin-page-msg ${type}`;
      document.querySelector('.admin-card')?.prepend(box);
    }
    box.className = `admin-page-msg ${type}`;
    box.innerHTML = esc(message);
  }

  function clearMessage() {
    document.getElementById('sectionQuotaPageMsg')?.remove();
  }

  function statusBadge(status) {
    return AdminApp.statusBadge(status);
  }

  function renderTable() {
    const wrap = document.getElementById('sectionQuotaTable');
    if (!rows.length) {
      wrap.innerHTML = '<div class="admin-empty">No sections found. Publish schedules first in AI Auto-Schedule.</div>';
      return;
    }

    wrap.innerHTML = `
      <table class="admin-table">
        <thead>
          <tr>
            <th>Strand</th>
            <th>Grade</th>
            <th>Section</th>
            <th>Quota</th>
            <th>Scheduled Students</th>
            <th>Remaining</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          ${rows.map(row => `
            <tr data-id="${esc(row.id)}">
              <td><strong>${esc(row.strand)}</strong></td>
              <td>${esc(row.gradeLevel)}</td>
              <td>${esc(row.section)}</td>
              <td>
                <input type="number" class="admin-input quota-input" min="1" max="200"
                  value="${esc(row.quota || 40)}" data-id="${esc(row.id)}" style="width:80px;">
              </td>
              <td>${esc(row.scheduledStudents ?? 0)}</td>
              <td>${esc(row.remaining ?? 0)}</td>
              <td>${statusBadge(row.status)}</td>
              <td>
                <button type="button" class="admin-btn secondary save-quota" data-id="${esc(row.id)}">Save</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    wrap.querySelectorAll('.save-quota').forEach(btn => {
      btn.addEventListener('click', () => saveQuota(btn.dataset.id));
    });
  }

  async function loadRows() {
    const res = await AdminApp.fetchJson('/api/section-quotas');
    rows = res.data || [];
    renderTable();
  }

  async function saveQuota(sectionId) {
    clearMessage();
    const input = document.querySelector(`.quota-input[data-id="${sectionId}"]`);
    const btn = document.querySelector(`.save-quota[data-id="${sectionId}"]`);
    const maxStudents = Number(input?.value || 40);

    if (!Number.isFinite(maxStudents) || maxStudents < 1) {
      showMessage('Quota must be at least 1.');
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }

    try {
      const result = await AdminApp.postJson('/api/section-quotas', {
        id: sectionId,
        maxStudents,
      });
      await loadRows();
      showMessage(result.message || 'Section quota updated.', 'success');
    } catch (err) {
      showMessage(err.message || 'Could not update section quota.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Save';
      }
    }
  }

  function bindEvents() {
    document.getElementById('refreshSectionQuotas')?.addEventListener('click', async () => {
      clearMessage();
      try {
        await loadRows();
        showMessage('Section quotas refreshed.', 'success');
      } catch (err) {
        showMessage(err.message || 'Could not refresh section quotas.');
      }
    });
  }

  async function mount() {
    if (!AdminApp.requireAuth()) return;
    bindEvents();
    await AdminApp.refreshLayout('section-quota', 'Section Quota');
    try {
      await loadRows();
    } catch (err) {
      document.getElementById('sectionQuotaTable').innerHTML =
        `<div class="admin-empty">${esc(err.message)}</div>`;
    }
  }

  return { mount };
})();
