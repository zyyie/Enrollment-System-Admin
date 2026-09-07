const RoomsManageApp = (() => {
  let rooms = [];

  function esc(str) {
    return AdminApp.escHtml(String(str ?? ''));
  }

  function showMessage(message, type = 'error') {
    let box = document.getElementById('roomsPageMsg');
    if (!box) {
      box = document.createElement('div');
      box.id = 'roomsPageMsg';
      box.className = `admin-page-msg ${type}`;
      document.querySelector('.admin-card')?.prepend(box);
    }
    box.className = `admin-page-msg ${type}`;
    box.innerHTML = esc(message);
  }

  function clearMessage() {
    document.getElementById('roomsPageMsg')?.remove();
  }

  function renderTable() {
    const wrap = document.getElementById('roomsTable');
    if (!rooms.length) {
      wrap.innerHTML = '<div class="admin-empty">No rooms yet. Click <strong>+ Add Room</strong> to get started.</div>';
      return;
    }
    wrap.innerHTML = `
      <table class="admin-table">
        <thead>
          <tr><th>Room</th><th>Type</th><th>Capacity</th><th>Status</th><th></th></tr>
        </thead>
        <tbody>
          ${rooms.map(r => `
            <tr>
              <td><strong>${esc(r.name)}</strong></td>
              <td>${r.room_type === 'laboratory' ? 'Laboratory' : 'Classroom'}</td>
              <td>${esc(r.capacity || 40)}</td>
              <td>${AdminApp.statusBadge(r.is_active !== false ? 'Active' : 'Inactive')}</td>
              <td><button type="button" class="admin-btn secondary edit-room" data-id="${esc(r.id)}">Edit</button></td>
            </tr>
          `).join('')}
        </tbody>
      </table>`;

    wrap.querySelectorAll('.edit-room').forEach(btn => {
      btn.addEventListener('click', () => openForm(rooms.find(r => r.id === btn.dataset.id)));
    });
  }

  function openForm(room = null) {
    clearMessage();
    document.getElementById('roomFormWrap').hidden = false;
    document.getElementById('roomDbId').value = room?.id || '';
    document.getElementById('roomName').value = room?.name || '';
    document.getElementById('roomType').value = room?.room_type || 'classroom';
    document.getElementById('roomCapacity').value = room?.capacity || 40;
    document.getElementById('roomFormWrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function closeForm() {
    document.getElementById('roomFormWrap').hidden = true;
    document.getElementById('roomForm').reset();
    document.getElementById('roomDbId').value = '';
  }

  async function loadRooms() {
    const res = await AdminApp.fetchJson('/api/rooms');
    rooms = res.data || [];
    renderTable();
  }

  async function saveRoom(e) {
    e.preventDefault();
    clearMessage();
    const btn = e.target.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }
    try {
      const result = await AdminApp.postJson('/api/rooms', {
        id: document.getElementById('roomDbId').value || undefined,
        name: document.getElementById('roomName').value.trim(),
        roomType: document.getElementById('roomType').value,
        capacity: document.getElementById('roomCapacity').value,
      });
      closeForm();
      await loadRooms();
      showMessage(result.message || 'Room saved successfully.', 'success');
    } catch (err) {
      showMessage(err.message || 'Could not save room.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Save to Database';
      }
    }
  }

  function bindEvents() {
    document.getElementById('openRoomForm').addEventListener('click', () => openForm());
    document.getElementById('cancelRoomForm').addEventListener('click', closeForm);
    document.getElementById('roomForm').addEventListener('submit', saveRoom);
  }

  async function mount() {
    if (!AdminApp.requireAuth()) return;
    bindEvents();
    await AdminApp.refreshLayout('rooms', 'Classrooms');
    try {
      await loadRooms();
    } catch (err) {
      document.getElementById('roomsTable').innerHTML =
        `<div class="admin-empty">${esc(err.message)}</div>`;
    }
  }

  return { mount };
})();
