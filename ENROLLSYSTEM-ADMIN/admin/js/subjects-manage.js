const SubjectsManageApp = (() => {
  let strands = [];
  let subjects = [];
  let activeFilter = 'all';

  const OFFICIAL_STRANDS = ['STEM', 'ABM', 'HUMSS', 'ICT', 'COOKERY', 'EIM'];
  const REMOVED_STRANDS = new Set(['CSS', 'GAS', 'HE', 'INDARTS', 'OTHER']);
  const STRAND_ORDER = ['All Strands', ...OFFICIAL_STRANDS];

  const STRAND_BADGE_CLASS = {
    'All Strands': 'core',
    STEM: 'stem',
    ABM: 'abm',
    HUMSS: 'humss',
    ICT: 'ict',
    COOKERY: 'cookery',
    EIM: 'eim',
  };

  const STRAND_CODE_PATTERNS = [
    ['STEM', /^(G1[12]-STEM-|STEM-)/i],
    ['ABM', /^(G1[12]-ABM-|ABM-)/i],
    ['HUMSS', /^(G1[12]-HUM-|HUMSS-)/i],
    ['ICT', /^(G1[12]-ICT-|ICT-)/i],
    ['COOKERY', /^(G1[12]-CK-|COOKERY-|CK-)/i],
    ['EIM', /^(G1[12]-EIM-|EIM-)/i],
  ];

  const REMOVED_CODE_PATTERN = /^(G1[12]-(CSS|GAS|HE|IA)-|(CSS|GAS|HE|IA|INDARTS)-)/i;

  function esc(str) {
    return AdminApp.escHtml(String(str ?? ''));
  }

  function inferStrandFromCode(code) {
    const text = String(code || '');
    if (REMOVED_CODE_PATTERN.test(text)) return null;
    for (const [strand, pattern] of STRAND_CODE_PATTERNS) {
      if (pattern.test(text)) return strand;
    }
    return null;
  }

  function isRemovedSubject(subject) {
    const strand = (subject?.strand || '').toUpperCase();
    if (REMOVED_STRANDS.has(strand)) return true;
    return REMOVED_CODE_PATTERN.test(String(subject?.code || ''));
  }

  function isSharedSubject(subject) {
    const code = String(subject?.code || '').toUpperCase();
    if (code.startsWith('CORE-')) return true;
    if (/^G1[12]-C\d/.test(code)) return true;
    if (/^G1[12]-A\d/.test(code)) return true;
    if (code.startsWith('APPL-')) return true;
    if (/^G1[12]-PE/.test(code) || code.startsWith('PE-')) return true;
    return strandLabel(subject) === 'All Strands';
  }

  function strandLabel(subject) {
    const fromDb = subject?.strand;
    if (fromDb && fromDb !== 'All Strands' && !REMOVED_STRANDS.has(fromDb)) return fromDb;
    return inferStrandFromCode(subject?.code) || 'All Strands';
  }

  function strandBadgeClass(label) {
    return STRAND_BADGE_CLASS[label] || 'core';
  }

  function semesterCode(subject) {
    return subject?.semesterCode || '';
  }

  function semesterLabel(code) {
    if (code === '1st') return '1st Semester';
    if (code === '2nd') return '2nd Semester';
    return 'Unassigned';
  }

  function visibleSubjects() {
    return subjects.filter((subject) => !isRemovedSubject(subject));
  }

  function groupSubjectsByStrand(list) {
    const groups = new Map();
    for (const subject of list) {
      const key = strandLabel(subject);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(subject);
    }

    const keys = [...groups.keys()].sort((a, b) => {
      const ai = STRAND_ORDER.indexOf(a);
      const bi = STRAND_ORDER.indexOf(b);
      if (ai !== -1 && bi !== -1) return ai - bi;
      if (ai !== -1) return -1;
      if (bi !== -1) return 1;
      return a.localeCompare(b);
    });

    return keys.map((strand) => ({
      strand,
      items: groups.get(strand).sort(sortSubjects),
    }));
  }

  function groupBySemester(items) {
    const buckets = { '1st': [], '2nd': [], other: [] };
    for (const item of items) {
      const sem = semesterCode(item);
      if (sem === '1st') buckets['1st'].push(item);
      else if (sem === '2nd') buckets['2nd'].push(item);
      else buckets.other.push(item);
    }
    const groups = [];
    if (buckets['1st'].length) groups.push({ label: '1st Semester', items: buckets['1st'] });
    if (buckets['2nd'].length) groups.push({ label: '2nd Semester', items: buckets['2nd'] });
    if (buckets.other.length) groups.push({ label: 'Unassigned', items: buckets.other });
    return groups;
  }

  function groupByGrade(items) {
    const grade11 = items.filter((s) => s.gradeLevel === 'Grade 11').sort(sortSubjectsByCode);
    const grade12 = items.filter((s) => s.gradeLevel === 'Grade 12').sort(sortSubjectsByCode);
    const groups = [];
    if (grade11.length) groups.push({ label: 'Grade 11', items: grade11 });
    if (grade12.length) groups.push({ label: 'Grade 12', items: grade12 });
    const other = items.filter((s) => s.gradeLevel !== 'Grade 11' && s.gradeLevel !== 'Grade 12');
    if (other.length) groups.push({ label: 'Other', items: other.sort(sortSubjectsByCode) });
    return groups;
  }

  function sortSubjectsByCode(a, b) {
    return String(a.code || '').localeCompare(String(b.code || ''));
  }

  function sortSubjects(a, b) {
    const grade = String(a.gradeLevel || '').localeCompare(String(b.gradeLevel || ''));
    if (grade !== 0) return grade;
    const sem = semesterCode(a).localeCompare(semesterCode(b));
    if (sem !== 0) return sem;
    return String(a.code || '').localeCompare(String(b.code || ''));
  }

  function sharedSubjects() {
    return visibleSubjects().filter(isSharedSubject).sort(sortSubjects);
  }

  function subjectsForStrand(strand) {
    return visibleSubjects()
      .filter((subject) => strandLabel(subject) === strand)
      .sort(sortSubjects);
  }

  function combineStrandSubjects(strand) {
    const shared = sharedSubjects();
    const specialized = subjectsForStrand(strand);
    const seen = new Set();
    const combined = [];
    for (const subject of [...shared, ...specialized]) {
      if (seen.has(subject.id)) continue;
      seen.add(subject.id);
      combined.push(subject);
    }
    return combined.sort(sortSubjects);
  }

  function strandSubjectCount(strand) {
    return combineStrandSubjects(strand).length;
  }

  function renderSubjectRows(items) {
    if (!items.length) {
      return '<tr><td colspan="5" class="admin-empty-cell">No subjects in this group.</td></tr>';
    }
    return items.map((s) => `
      <tr>
        <td><strong>${esc(s.code)}</strong></td>
        <td>${esc(s.name)}</td>
        <td>${esc(s.semesterLabel || semesterLabel(semesterCode(s)))}</td>
        <td>${esc(s.units)}</td>
        <td><button type="button" class="admin-btn secondary edit-subject" data-id="${esc(s.id)}">Edit</button></td>
      </tr>
    `).join('');
  }

  function renderGradeBlock(gradeGroup) {
    return `
      <div class="subjects-grade-block">
        <h5 class="subjects-grade-title">${esc(gradeGroup.label)} <span class="subjects-grade-count">${gradeGroup.items.length}</span></h5>
        <table class="admin-table">
          <thead>
            <tr><th>Code</th><th>Subject</th><th>Sem</th><th>Units</th><th></th></tr>
          </thead>
          <tbody>${renderSubjectRows(gradeGroup.items)}</tbody>
        </table>
      </div>`;
  }

  function renderSemesterBlock(semGroup) {
    const gradeGroups = groupByGrade(semGroup.items);
    return `
      <div class="subjects-sem-block">
        <h4 class="subjects-sem-title">${esc(semGroup.label)} <span class="subjects-sem-count">${semGroup.items.length}</span></h4>
        ${gradeGroups.map(renderGradeBlock).join('')}
      </div>`;
  }

  function renderStrandTable(title, items, badgeClass) {
    const semGroups = groupBySemester(items);
    return `
      <section class="subjects-strand-section">
        <div class="subjects-strand-head">
          <h3 class="admin-section-title">${esc(title)}</h3>
          <span class="strand-badge ${badgeClass}">${items.length} subject(s)</span>
        </div>
        ${semGroups.map(renderSemesterBlock).join('')}
      </section>`;
  }

  function renderFilterTabs(groups) {
    const tabs = [{ id: 'all', label: 'Show All' }];
    for (const strand of OFFICIAL_STRANDS) {
      tabs.push({ id: strand, label: strand, count: strandSubjectCount(strand) });
    }

    return `
      <div class="subjects-strand-tabs" role="tablist" aria-label="Filter by strand">
        ${tabs.map((tab) => `
          <button type="button"
            class="subjects-strand-tab${activeFilter === tab.id ? ' active' : ''}"
            data-filter="${esc(tab.id)}"
            role="tab"
            aria-selected="${activeFilter === tab.id ? 'true' : 'false'}">
            ${esc(tab.label)}${tab.count != null ? ` <span class="subjects-tab-count">${tab.count}</span>` : ''}
          </button>
        `).join('')}
      </div>`;
  }

  function renderFilteredSections(groups) {
    if (activeFilter === 'all') {
      return groups.map(({ strand, items }) =>
        renderStrandTable(
          strand === 'All Strands' ? 'Core & Applied (All Strands)' : strand,
          items,
          strandBadgeClass(strand),
        ),
      ).join('');
    }

    return renderStrandTable(
      activeFilter,
      combineStrandSubjects(activeFilter),
      strandBadgeClass(activeFilter),
    );
  }

  function showMessage(message, type = 'error') {
    let box = document.getElementById('subjectsPageMsg');
    if (!box) {
      box = document.createElement('div');
      box.id = 'subjectsPageMsg';
      box.className = `admin-page-msg ${type}`;
      document.querySelector('.admin-card')?.prepend(box);
    }
    box.className = `admin-page-msg ${type}`;
    box.innerHTML = esc(message);
  }

  function clearMessage() {
    document.getElementById('subjectsPageMsg')?.remove();
  }

  function renderStrandOptions(selected = '') {
    const select = document.getElementById('subjectStrand');
    if (!select) return;
    const sel = (selected || '').toUpperCase();
    select.innerHTML = `<option value="">All Strands (Core)</option>${strands.map(s => `
      <option value="${esc(s.code)}" ${sel === s.code ? 'selected' : ''}>${esc(s.code)} — ${esc(s.name || s.code)}</option>
    `).join('')}`;
  }

  function renderTable() {
    const wrap = document.getElementById('subjectsTable');
    const list = visibleSubjects();
    if (!list.length) {
      wrap.innerHTML = '<div class="admin-empty">No subjects yet. Click <strong>+ Add Subject</strong> to get started.</div>';
      return;
    }

    const groups = groupSubjectsByStrand(list);
    wrap.innerHTML = `
      ${renderFilterTabs(groups)}
      <div class="subjects-strand-groups">
        ${renderFilteredSections(groups)}
      </div>
      <p class="admin-table-foot">${list.length} subject(s) · grouped by semester and grade level</p>`;

    wrap.querySelectorAll('.subjects-strand-tab').forEach((btn) => {
      btn.addEventListener('click', () => {
        activeFilter = btn.dataset.filter || 'all';
        renderTable();
      });
    });

    wrap.querySelectorAll('.edit-subject').forEach((btn) => {
      btn.addEventListener('click', () => openForm(subjects.find((s) => s.id === btn.dataset.id)));
    });
  }

  function openForm(subject = null) {
    clearMessage();
    document.getElementById('subjectFormWrap').hidden = false;
    document.getElementById('subjectDbId').value = subject?.id || '';
    document.getElementById('subjectCode').value = subject?.code || '';
    document.getElementById('subjectName').value = subject?.name || '';
    document.getElementById('subjectGrade').value = subject?.gradeLevel || 'Grade 12';
    document.getElementById('subjectSemester').value = subject?.semesterCode || '1st';
    document.getElementById('subjectUnits').value = subject?.units || 3;
    document.getElementById('subjectLec').value = subject?.lecHours ?? subject?.units ?? 3;
    document.getElementById('subjectLab').value = subject?.labHours || 0;
    renderStrandOptions(subject?.strandCode || (subject?.strand === 'All Strands' ? '' : subject?.strand));
    document.getElementById('subjectFormWrap').scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  function closeForm() {
    document.getElementById('subjectFormWrap').hidden = true;
    document.getElementById('subjectForm').reset();
    document.getElementById('subjectDbId').value = '';
  }

  async function loadStrands() {
    const res = await AdminApp.fetchJson('/api/strands');
    strands = (res.data || []).filter((s) => !REMOVED_STRANDS.has((s.code || '').toUpperCase()));
    if (res.warning) showMessage(res.warning);
    renderStrandOptions();
  }

  async function loadSubjects() {
    const res = await AdminApp.fetchJson('/api/subjects');
    subjects = res.data || [];
    renderTable();
  }

  async function loadAll() {
    await loadStrands();
    await loadSubjects();
  }

  async function saveSubject(e) {
    e.preventDefault();
    clearMessage();
    const btn = e.target.querySelector('button[type="submit"]');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }
    try {
      const result = await AdminApp.postJson('/api/subjects', {
        id: document.getElementById('subjectDbId').value || undefined,
        code: document.getElementById('subjectCode').value.trim(),
        name: document.getElementById('subjectName').value.trim(),
        strandCode: document.getElementById('subjectStrand').value,
        gradeLevel: document.getElementById('subjectGrade').value,
        semesterCode: document.getElementById('subjectSemester').value,
        units: document.getElementById('subjectUnits').value,
        lecHours: document.getElementById('subjectLec').value,
        labHours: document.getElementById('subjectLab').value,
      });
      closeForm();
      await loadSubjects();
      showMessage(result.message || 'Subject saved successfully.', 'success');
    } catch (err) {
      showMessage(err.message || 'Could not save subject.');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Save to Database';
      }
    }
  }

  function bindEvents() {
    document.getElementById('openSubjectForm').addEventListener('click', () => openForm());
    document.getElementById('cancelSubjectForm').addEventListener('click', closeForm);
    document.getElementById('subjectForm').addEventListener('submit', saveSubject);
  }

  async function mount() {
    if (!AdminApp.requireAuth()) return;
    bindEvents();
    await AdminApp.refreshLayout('subjects', 'Subjects');
    try {
      await loadAll();
    } catch (err) {
      document.getElementById('subjectsTable').innerHTML =
        `<div class="admin-empty">${esc(err.message)}<br><small>Run supabase/faculty-strands-rooms.sql in Supabase SQL Editor, then restart the server.</small></div>`;
    }
  }

  return { mount };
})();
