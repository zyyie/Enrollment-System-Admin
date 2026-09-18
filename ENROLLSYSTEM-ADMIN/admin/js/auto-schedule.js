// Admin AI Auto-Scheduling UI — one strand at a time
const AutoScheduleApp = (() => {
  let config = null;
  let lastResult = null;
  let strandProgress = {};
  let progressLog = [];
  let wizardStep = 1;
  let selectedTrack = 'Academic';
  let schedulingContext = null;
  let wizardFormData = {};
  let contextLoading = false;
  let cooldownTimerId = null;
  let cooldownUntil = 0;
  let selectedViewStrand = null;
  let savedSchedules = [];
  let savedSchedulesLoading = false;
  let savedSchedulesError = '';
  let savedSchedulesSource = '';
  let savedSchedulesFilter = { gradeLevel: 'all', semesterCode: '1st' };
  let generationState = {
    strands: [],
    currentIndex: 0,
    accumulated: [],
    generatedStrands: [],
    savedStrands: [],
    notes: [],
    finalSource: 'ortools',
    started: false,
    allComplete: false,
  };

  const STRAND_CLASS = {
    STEM: 'stem', ABM: 'abm', HUMSS: 'humss',
    ICT: 'ict', COOKERY: 'cookery', EIM: 'eim',
  };

  const SECTION_NAMES_BY_GRADE = {
    'Grade 12': {
      STEM: ['Rizal', 'Bonifacio'],
      ABM: ['Aguinaldo', 'Mabini'],
      HUMSS: ['Luna', 'Jacinto'],
      ICT: ['Zamora', 'Gomez'],
      COOKERY: ['Del Pilar', 'Silang'],
      EIM: ['Aquino', 'Malvar'],
    },
    'Grade 11': {
      STEM: ['Hope', 'Fortitude'],
      ABM: ['Faith', 'Integrity'],
      HUMSS: ['Perseverance', 'Courage'],
      ICT: ['Humility', 'Kindness'],
      COOKERY: ['Wisdom', 'Compassion'],
      EIM: ['Resilience', 'Justice'],
    },
  };

  function sectionSlotName(strand, gradeLevel, slotKey) {
    const code = String(strand || 'STEM').toUpperCase();
    const slot = String(slotKey || 'A').toUpperCase();
    const slotIndex = slot === 'A' ? 0 : 1;
    const names = (SECTION_NAMES_BY_GRADE[gradeLevel] || {})[code];
    return names ? names[slotIndex] : slot;
  }

  function sectionDisplayLabel(strand, gradeLevel, slotKey) {
    const name = sectionSlotName(strand, gradeLevel, slotKey);
    return `Section ${name}`;
  }

  function sectionPairLabel(strand, gradeLevel) {
    return `${sectionSlotName(strand, gradeLevel, 'A')} & ${sectionSlotName(strand, gradeLevel, 'B')}`;
  }

  const WIZARD_STEPS = [
    'Select Track',
    'Select Strands',
    'Collect Data',
    'Generate Schedule',
  ];

  async function loadConfig() {
    const res = await AdminApp.fetchJson('/api/scheduling/config');
    config = res.data;
    return config;
  }

  function esc(str) {
    return AdminApp.escHtml ? AdminApp.escHtml(str) : String(str ?? '');
  }

  function formatSource(source) {
    const labels = {
      ortools: 'Google OR-Tools',
      groq_ai: 'Groq AI',
      openrouter_ai: 'OpenRouter AI',
      gemini_ai: 'Google Gemini',
      smart_ai_fallback: 'Rule-based Scheduler',
    };
    return labels[source] || source;
  }

  function strandClass(strand) {
    return STRAND_CLASS[String(strand || '').toUpperCase()] || 'stem';
  }

  const DAY_DISPLAY = {
    Monday: 'Mon',
    Tuesday: 'Tue',
    Wednesday: 'Wed',
    Thursday: 'Thu',
    Friday: 'Fri',
    Saturday: 'Sat',
  };

  function expandDayCode(code) {
    const parts = [];
    let i = 0;
    const text = String(code || '');
    while (i < text.length) {
      if (text.slice(i, i + 2) === 'Th') {
        parts.push('Thu');
        i += 2;
      } else if (text.slice(i, i + 2) === 'Sa') {
        parts.push('Sat');
        i += 2;
      } else if (text[i] === 'M') {
        parts.push('Mon');
        i += 1;
      } else if (text[i] === 'T') {
        parts.push('Tue');
        i += 1;
      } else if (text[i] === 'W') {
        parts.push('Wed');
        i += 1;
      } else if (text[i] === 'F') {
        parts.push('Fri');
        i += 1;
      } else {
        i += 1;
      }
    }
    if (!parts.length) return code || 'TBA';
    if (parts.length === 1) return parts[0];
    if (parts.length === 2) return `${parts[0]} & ${parts[1]}`;
    return `${parts.slice(0, -1).join(', ')} & ${parts[parts.length - 1]}`;
  }

  function formatReadableTime(value) {
    const text = String(value || '').trim();
    if (!text) return '';
    return text
      .replace(/(\d)(am|pm)\b/gi, '$1 $2')
      .replace(/\bam\b/gi, 'AM')
      .replace(/\bpm\b/gi, 'PM');
  }

  function formatScheduleDays(sessions, scheduleLabel) {
    const fromSessions = [...new Set(
      (sessions || []).map(session => DAY_DISPLAY[session.day] || session.day?.slice(0, 3) || session.day),
    )].filter(Boolean);
    if (fromSessions.length) {
      if (fromSessions.length === 1) return fromSessions[0];
      if (fromSessions.length === 2) return `${fromSessions[0]} & ${fromSessions[1]}`;
      return `${fromSessions.slice(0, -1).join(', ')} & ${fromSessions[fromSessions.length - 1]}`;
    }
    const match = String(scheduleLabel || '').match(/^(\S+)\s+/);
    return match ? expandDayCode(match[1]) : 'TBA';
  }

  function formatScheduleTimeRange(sessions, scheduleLabel) {
    if (sessions?.length) {
      const normalized = sessions.map((session) => ({
        day: DAY_DISPLAY[session.day] || session.day?.slice(0, 3) || '',
        start: formatReadableTime(session.start),
        end: formatReadableTime(session.end),
        rawStart: String(session.start || '').trim().toLowerCase(),
        rawEnd: String(session.end || '').trim().toLowerCase(),
      }));

      const allSameTime = normalized.every(
        (session) =>
          session.rawStart === normalized[0].rawStart &&
          session.rawEnd === normalized[0].rawEnd,
      );

      if (normalized.length === 1 || allSameTime) {
        return `${normalized[0].start} – ${normalized[0].end}`;
      }

      return normalized
        .map((session) => `${session.day} ${session.start} – ${session.end}`)
        .join(', ');
    }

    const label = String(scheduleLabel || '').trim();
    if (!label || label === 'TBA') return 'TBA';

    if (label.includes(',')) {
      return label
        .split(',')
        .map((part) => {
          const trimmed = part.trim();
          const match = trimmed.match(/^(\S+)\s+(.+)$/);
          if (!match) return trimmed;
          const day = expandDayCode(match[1]);
          const range = match[2].split('-');
          if (range.length === 2) {
            return `${day} ${formatReadableTime(range[0])} – ${formatReadableTime(range[1])}`;
          }
          return trimmed;
        })
        .join(', ');
    }

    const labelMatch = label.match(/^(\S+)\s+(.+)$/);
    if (labelMatch) {
      const range = labelMatch[2];
      const parts = range.split('-');
      if (parts.length === 2) {
        return `${formatReadableTime(parts[0].trim())} – ${formatReadableTime(parts[1].trim())}`;
      }
    }

    return label;
  }

  function getScheduleRooms(sessions) {
    const rooms = [...new Set((sessions || []).map(session => session.room).filter(Boolean))];
    if (!rooms.length) return 'TBA';
    if (rooms.length === 1) return rooms[0];
    return rooms.join(', ');
  }

  function renderScheduleCell(item) {
    const sessions = item.sessions || [];
    const days = formatScheduleDays(sessions, item.schedule_label);
    const time = formatScheduleTimeRange(sessions, item.schedule_label);
    const room = getScheduleRooms(sessions);

    return `
      <div class="schedule-card">
        <div class="schedule-card-top">
          <span class="schedule-card-days">${esc(days)}</span>
          <span class="schedule-card-time">${esc(time)}</span>
        </div>
        <div class="schedule-card-room">
          <span class="schedule-card-room-label">Room</span>
          <span class="schedule-card-room-value">${esc(room)}</span>
        </div>
      </div>
    `;
  }

  function renderAiStatus() {
    const mode = config?.scheduler_mode || 'ortools';
    if (mode === 'ortools' || config?.ai_provider === 'ortools') {
      return `
        <div class="auto-sched-status ok">
          ✓ Scheduler ready — ${esc(config.ai_provider_label || 'Google OR-Tools')} (${esc(config.ai_model || 'cp-sat')})
          <span class="auto-sched-status-sub">
            Local constraint solver — no API keys, no rate limits, generates in seconds.
          </span>
        </div>`;
    }
    if (config?.ai_model_ready) {
      const rate = config.rate_limit || {};
      const fallbacks = (config.fallback_providers || []).join(', ') || 'none';
      return `
        <div class="auto-sched-status ok">
          ✓ Cloud AI ready — ${esc(config.ai_provider_label)} (${esc(config.ai_model)})
          <span class="auto-sched-status-sub">
            Rate-limit safe: ${rate.subject_chunk_size || 3} subjects/chunk,
            ${rate.section_delay_sec || 8}s delay, ${rate.max_retries || 8} retries.
            Fallbacks: ${esc(fallbacks)}
          </span>
        </div>`;
    }
    return `
      <div class="auto-sched-status warn">
        ⚠ Scheduler not ready — restart the admin server (python server.py).
      </div>`;
  }

  const REMOVED_STRANDS = new Set(['GAS', 'CSS', 'HE', 'INDARTS', 'OTHER']);

  function strandsForTrack(track) {
    return (config?.tracks?.[track]?.strands || []).filter(
      code => !REMOVED_STRANDS.has(String(code || '').toUpperCase()),
    );
  }

  function gradeShortLabel(gradeLevel) {
    return String(gradeLevel || '').includes('11') ? 'G11' : 'G12';
  }

  function groupSavedSchedules(schedules) {
    const groups = {};
    (schedules || []).forEach(item => {
      const grade = item.gradeLevel || 'Grade 12';
      const strand = String(item.strand || 'OTHER').toUpperCase();
      const key = `${grade}|${strand}`;
      if (!groups[key]) groups[key] = { grade, strand, items: [] };
      groups[key].items.push(item);
    });
    return Object.values(groups).sort((a, b) => {
      if (a.grade !== b.grade) return a.grade.localeCompare(b.grade);
      return a.strand.localeCompare(b.strand);
    }).map(group => ({
      ...group,
      subjectCount: uniqueSubjectCodes(group.items).size,
    }));
  }

  function uniqueSubjectCodes(items) {
    const codes = new Set();
    (items || []).forEach(item => {
      const code = String(item.subject_code || item.subject_name || '').trim().toUpperCase();
      if (code) codes.add(code);
    });
    return codes;
  }

  /** G12 2nd sem is usually 6–9 subjects × sections A+B (12–18 rows). Fewer = incomplete save. */
  function savedScheduleLooksIncomplete(group, semesterCode) {
    if (semesterCode !== '2nd' || !String(group.grade || '').includes('12')) return false;
    const subjects = group.subjectCount ?? uniqueSubjectCodes(group.items).size;
    const rows = (group.items || []).length;
    return subjects <= 5 || rows <= 6;
  }

  function syncSavedSchedulesFilterFromWizard() {
    // Semester must match the wizard; grade stays on "all" so G11+G12 saves stay visible for delete.
    if (wizardFormData.semesterCode) savedSchedulesFilter.semesterCode = wizardFormData.semesterCode;
  }

  function savedScheduleCountsByGrade() {
    const counts = { 'Grade 11': 0, 'Grade 12': 0 };
    (savedSchedules || []).forEach(item => {
      const grade = item.gradeLevel || 'Grade 12';
      if (counts[grade] != null) counts[grade] += 1;
    });
    return counts;
  }

  async function refreshSavedSchedules() {
    savedSchedulesLoading = true;
    savedSchedulesError = '';
    savedSchedulesSource = '';
    updateSavedSchedulesSidebar();
    try {
      const params = new URLSearchParams({
        gradeLevel: savedSchedulesFilter.gradeLevel,
        semesterCode: savedSchedulesFilter.semesterCode,
      });
      const res = await AdminApp.fetchJson(`/api/scheduling/draft?${params}`, 30000);
      savedSchedules = dedupeScheduleEntries(res.schedules || []);
      savedSchedulesSource = res.source || '';
    } catch (err) {
      savedSchedules = [];
      savedSchedulesError = err.message || 'Could not load saved schedules.';
    } finally {
      savedSchedulesLoading = false;
      updateSavedSchedulesSidebar();
    }
  }

  function renderSavedSchedulesDetailTable(items, gradeLevel, strand) {
    const bySection = { A: [], B: [] };
    (items || []).forEach(item => {
      const sec = String(item.section || 'A').toUpperCase();
      if (bySection[sec]) bySection[sec].push(item);
      else bySection.A.push(item);
    });
    return ['A', 'B'].map(section => {
      const rows = bySection[section];
      if (!rows.length) return '';
      const label = sectionDisplayLabel(strand, gradeLevel, section);
      return `
        <div class="saved-sched-modal-section">
          <h4 class="saved-sched-modal-section-title">${esc(label)} <span>${rows.length} subject${rows.length === 1 ? '' : 's'}</span></h4>
          <div class="auto-sched-table-wrap">
            <table class="admin-table auto-sched-table saved-sched-modal-table">
              <thead>
                <tr><th>Code</th><th>Subject</th><th>Teacher</th><th>Schedule</th></tr>
              </thead>
              <tbody>
                ${rows.map(item => `
                  <tr>
                    <td><strong>${esc(item.subject_code)}</strong></td>
                    <td class="auto-sched-subject-name">${esc(item.subject_name || item.subject_code)}</td>
                    <td>${esc(item.faculty_name || item.faculty_id || '—')}</td>
                    <td class="auto-sched-schedule-cell">${renderScheduleCell(item)}</td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>`;
    }).join('');
  }

  function savedSchedulesForSidebar() {
    const { gradeLevel } = savedSchedulesFilter;
    if (!gradeLevel || gradeLevel === 'all') return savedSchedules || [];
    return (savedSchedules || []).filter(item => (item.gradeLevel || gradeLevel) === gradeLevel);
  }

  function revealAllSavedSchedulesForConflicts() {
    savedSchedulesFilter.gradeLevel = 'all';
    updateSavedSchedulesSidebar();
    return refreshSavedSchedules();
  }

  function renderSavedSchedulesSidebar() {
    const { gradeLevel, semesterCode } = savedSchedulesFilter;
    const semLabel = semesterCode === '2nd' ? '2nd Sem' : '1st Sem';
    const gShort = gradeShortLabel(gradeLevel);
    const visibleSchedules = savedSchedulesForSidebar();
    const groups = groupSavedSchedules(visibleSchedules);
    const total = visibleSchedules.length;
    const allTotal = (savedSchedules || []).length;
    const gradeCounts = savedScheduleCountsByGrade();
    const strandCount = groups.length;
    const incomplete2ndG12 = semesterCode === '2nd'
      && gradeLevel === 'Grade 12'
      && groups.length > 0
      && groups.every(g => savedScheduleLooksIncomplete(g, semesterCode));

    let body = '';
    if (savedSchedulesLoading) {
      body = `
        <div class="saved-aside-loading">
          <div class="auto-sched-loading-spinner"></div>
          <p>Loading saved schedules…</p>
        </div>`;
    } else if (savedSchedulesError) {
      body = `<div class="saved-aside-alert error">${esc(savedSchedulesError)}</div>`;
    } else if (!total) {
      body = `
        <div class="saved-aside-empty">
          <div class="saved-aside-empty-icon">📅</div>
          <p><strong>No schedules yet</strong></p>
          <p class="saved-aside-empty-sub">${esc(gShort)} · ${esc(semLabel)} — generate and save a schedule to see it here.</p>
        </div>`;
    } else {
      body = `
        <div class="saved-aside-stats">
          <span class="saved-aside-stat"><strong>${total}</strong> slots</span>
          <span class="saved-aside-stat"><strong>${strandCount}</strong> saved</span>
        </div>
        <div class="saved-aside-groups">
          ${groups.map(group => {
            const key = `${group.grade}|${group.strand}`;
            const gLabel = gradeShortLabel(group.grade);
            return `
              <article class="saved-aside-group ${strandClass(group.strand)}">
                <button type="button" class="saved-aside-group-head" data-sidebar-key="${esc(key)}" title="View schedule">
                  <span class="strand-badge ${strandClass(group.strand)}">${esc(group.strand)}</span>
                  <span class="saved-aside-group-meta">${esc(gLabel)} · ${esc(scheduleEntrySummary(group.items.length, group.subjectCount))}${savedScheduleLooksIncomplete(group, semesterCode) ? ' · incomplete' : ''}</span>
                  <span class="saved-aside-chevron" aria-hidden="true">↗</span>
                </button>
                <button type="button" class="saved-aside-delete" data-delete-key="${esc(key)}" title="Delete this schedule">Delete</button>
              </article>`;
          }).join('')}
        </div>`;
    }

    const gradeFilter = savedSchedulesFilter.gradeLevel;
    const subLine = gradeFilter === 'all'
      ? `${allTotal} entries · G11: ${gradeCounts['Grade 11']} · G12: ${gradeCounts['Grade 12']}`
      : `${total} ${gShort} entries`;

    const sourceNote = savedSchedulesSource === 'local'
      ? 'Showing last saved draft (database sync pending).'
      : incomplete2ndG12
        ? `${gShort} 2nd sem: counts are saved rows (subject × section). ~4 often means common subjects only — open a strand, then re-generate & save per strand (Virtue A/B).`
        : '';

    return `
      <div class="saved-aside-inner">
        <header class="saved-aside-hero">
          <div class="saved-aside-hero-top">
            <div>
              <h3>Saved Schedules</h3>
              <p class="saved-aside-sub">${total || allTotal ? esc(subLine) : `${gShort} · ${esc(semLabel)}`}</p>
            </div>
            <button type="button" class="saved-aside-refresh" id="savedSchedRefreshBtn" title="Refresh" ${savedSchedulesLoading ? 'disabled' : ''}>
              <span aria-hidden="true">↻</span>
            </button>
          </div>
          <div class="saved-aside-filters">
            <label>
              <span>Grade</span>
              <select id="savedSchedGrade" class="admin-input">
                <option value="all" ${gradeLevel === 'all' ? 'selected' : ''}>All</option>
                <option value="Grade 11" ${gradeLevel === 'Grade 11' ? 'selected' : ''}>G11</option>
                <option value="Grade 12" ${gradeLevel === 'Grade 12' ? 'selected' : ''}>G12</option>
              </select>
      </label>
            <label>
              <span>Sem</span>
              <select id="savedSchedSem" class="admin-input">
                <option value="1st" ${semesterCode === '1st' ? 'selected' : ''}>1st</option>
                <option value="2nd" ${semesterCode === '2nd' ? 'selected' : ''}>2nd</option>
              </select>
            </label>
          </div>
        </header>
        ${sourceNote ? `<p class="saved-aside-note">${esc(sourceNote)}</p>` : ''}
        <div class="saved-aside-body">${body}</div>
      </div>`;
  }

  function ensureSavedScheduleModalRoot() {
    let overlay = document.getElementById('savedSchedModalOverlay');
    if (overlay) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'savedSchedModalOverlay';
    overlay.className = 'admin-modal-overlay';
    overlay.setAttribute('aria-hidden', 'true');
    overlay.innerHTML = `
      <div class="admin-modal saved-sched-modal" role="dialog" aria-modal="true" aria-labelledby="savedSchedModalTitle">
        <div id="savedSchedModalContent"></div>
      </div>`;
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeSavedScheduleModal();
    });
    document.body.appendChild(overlay);
    return overlay;
  }

  function openSavedScheduleModal(key) {
    const group = groupSavedSchedules(savedSchedules).find(item => `${item.grade}|${item.strand}` === key);
    if (!group) return;

    const overlay = ensureSavedScheduleModalRoot();
    const content = document.getElementById('savedSchedModalContent');
    if (!content) return;

    const semLabel = savedSchedulesFilter.semesterCode === '2nd' ? '2nd Semester' : '1st Semester';
    const gLabel = gradeShortLabel(group.grade);

    content.innerHTML = `
      <div class="saved-sched-modal-head ${strandClass(group.strand)}">
        <div>
          <span class="strand-badge ${strandClass(group.strand)}">${esc(group.strand)}</span>
          <h3 id="savedSchedModalTitle">${esc(gLabel)} · ${esc(semLabel)}</h3>
          <p>${group.items.length} scheduled subject${group.items.length === 1 ? '' : 's'}</p>
        </div>
        <button type="button" class="saved-sched-modal-close" id="savedSchedModalClose" aria-label="Close">&times;</button>
      </div>
      <div class="saved-sched-modal-body">
        ${renderSavedSchedulesDetailTable(group.items, group.grade, group.strand)}
      </div>`;

    document.getElementById('savedSchedModalClose')?.addEventListener('click', closeSavedScheduleModal);
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    document.body.classList.add('admin-modal-open');
    content.querySelector('.saved-sched-modal-body')?.scrollTo(0, 0);
  }

  function closeSavedScheduleModal() {
    const overlay = document.getElementById('savedSchedModalOverlay');
    if (!overlay) return;
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('admin-modal-open');
  }

  function updateSavedSchedulesSidebar() {
    const el = document.getElementById('savedSchedSidebar');
    if (!el) return;
    el.innerHTML = renderSavedSchedulesSidebar();
    bindSavedSchedulesSidebar();
  }

  function bindSavedSchedulesSidebar() {
    const refreshBtn = document.getElementById('savedSchedRefreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => refreshSavedSchedules());

    const gradeSel = document.getElementById('savedSchedGrade');
    const semSel = document.getElementById('savedSchedSem');
    const onFilterChange = () => {
      savedSchedulesFilter.gradeLevel = gradeSel?.value || 'all';
      savedSchedulesFilter.semesterCode = semSel?.value || '1st';
      if (wizardStep >= 3 && savedSchedulesFilter.gradeLevel !== 'all') {
        wizardFormData.gradeLevel = savedSchedulesFilter.gradeLevel;
      }
      if (wizardStep >= 3) {
        wizardFormData.semesterCode = savedSchedulesFilter.semesterCode;
      }
      closeSavedScheduleModal();
      refreshSavedSchedules();
    };
    if (gradeSel) gradeSel.addEventListener('change', onFilterChange);
    if (semSel) semSel.addEventListener('change', onFilterChange);

    document.querySelectorAll('.saved-aside-group-head').forEach(btn => {
      btn.addEventListener('click', () => {
        openSavedScheduleModal(btn.dataset.sidebarKey);
      });
    });

    document.querySelectorAll('.saved-aside-delete').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (btn.disabled || btn.classList.contains('is-loading')) return;
        deleteSavedSchedule(btn.dataset.deleteKey, btn);
      });
    });
  }

  function setDeleteButtonLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      if (!btn.dataset.deleteLabel) {
        btn.dataset.deleteLabel = btn.textContent.trim() || 'Delete';
      }
      btn.classList.add('is-loading');
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.innerHTML = '<span class="saved-aside-delete-spinner" aria-hidden="true"></span>';
      return;
    }
    btn.classList.remove('is-loading');
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    btn.textContent = btn.dataset.deleteLabel || 'Delete';
  }

  function normalizeSectionLetter(item) {
    const section = String(item.section || '').trim().toUpperCase();
    if (section === 'A' || section === 'B') return section;
    const grade = item.gradeLevel || wizardFormData.gradeLevel || 'Grade 12';
    const strand = String(item.strand || '').toUpperCase();
    const names = config?.sectionNamesByGrade?.[grade]?.[strand];
    if (names) {
      if (names[0]?.toUpperCase() === section) return 'A';
      if (names[1]?.toUpperCase() === section) return 'B';
    }
    return null;
  }

  function dedupeScheduleEntries(schedules) {
    const seen = new Set();
    return (schedules || []).filter(item => {
      const section = normalizeSectionLetter(item);
      if (!section) return false;
      const key = [
        (item.gradeLevel || '').toUpperCase(),
        (item.strand || '').toUpperCase(),
        section,
        (item.subject_code || item.subject_name || '').toUpperCase(),
      ].join('|');
      if (!key.replace(/\|/g, '')) return false;
      if (seen.has(key)) return false;
      seen.add(key);
      item.section = section;
      return true;
    });
  }

  function removeStrandFromAccumulated(strand, gradeLevel) {
    const strandUpper = String(strand || '').toUpperCase();
    const grade = gradeLevel || 'Grade 12';
    generationState.accumulated = (generationState.accumulated || []).filter(item => !(
      (item.strand || '').toUpperCase() === strandUpper
      && (item.gradeLevel || grade) === grade
    ));
  }

  function mergeStrandSchedulesIntoAccumulated(strand, gradeLevel, newRows) {
    removeStrandFromAccumulated(strand, gradeLevel);
    const stamped = (newRows || []).map(item => ({
      ...item,
      gradeLevel: item.gradeLevel || gradeLevel || 'Grade 12',
    }));
    generationState.accumulated = dedupeScheduleEntries([
      ...(generationState.accumulated || []),
      ...stamped,
    ]);
  }

  function scheduleEntrySummary(count, subjectCount) {
    const entriesLabel = `${count} slot${count === 1 ? '' : 's'}`;
    if (!subjectCount || subjectCount === count) return entriesLabel;
    return `${entriesLabel} · ${subjectCount} subject${subjectCount === 1 ? '' : 's'}`;
  }

  async function deleteSavedScheduleForKey(key, { silent = false, semesterCode = null, button = null } = {}) {
    if (!key || !key.includes('|')) return { ok: false, error: 'Invalid schedule key.' };
    const [gradeLevel, strandCode] = key.split('|');
    const semCode = semesterCode || savedSchedulesFilter.semesterCode || '1st';
    const semLabel = semCode === '2nd' ? '2nd Semester' : '1st Semester';
    if (!silent) {
      const confirmed = await AdminApp.confirmDialog({
        title: 'Delete Saved Schedule?',
        detail: `${strandCode} · ${gradeShortLabel(gradeLevel)} · ${semLabel}`,
        message: 'This removes saved schedules from the database so you can regenerate. G11 and G12 are deleted separately.',
        confirmLabel: 'Delete',
        cancelLabel: 'Cancel',
        variant: 'reject',
        icon: 'fa-trash',
      });
      if (!confirmed) return { ok: false, error: 'Cancelled.' };
    }

    setDeleteButtonLoading(button, true);
    try {
      const res = await AdminApp.postJson('/api/scheduling/delete', {
        gradeLevel,
        semesterCode: semCode,
        strandCode,
      });
      if (!silent) {
        showBanner(res.message || 'Schedule deleted successfully.', 'success');
      }
      closeSavedScheduleModal();
      if (lastResult?.schedules?.length) {
        lastResult.schedules = lastResult.schedules.filter(item => !(
          (item.strand || '').toUpperCase() === strandCode.toUpperCase()
          && (item.gradeLevel || gradeLevel) === gradeLevel
        ));
      }
      removeStrandFromAccumulated(strandCode, gradeLevel);
      await refreshSavedSchedules();
      return { ok: true, res };
    } catch (err) {
      const msg = err.message || 'Could not delete schedule.';
      if (!silent) showBanner(msg);
      return { ok: false, error: msg };
    } finally {
      if (button?.isConnected) {
        setDeleteButtonLoading(button, false);
      }
    }
  }

  async function ensureSavedScheduleCleared(form, strand) {
    const data = new FormData(form);
    const gradeLevel = data.get('gradeLevel') || 'Grade 12';
    const semesterCode = data.get('semesterCode') || '1st';
    const strandUpper = (strand || '').toUpperCase();
    const params = new URLSearchParams({ gradeLevel, semesterCode });
    const res = await AdminApp.fetchJson(`/api/scheduling/draft?${params}`);
    const existing = dedupeScheduleEntries(res.schedules || []).filter(item => (
      (item.strand || '').toUpperCase() === strandUpper
      && (item.gradeLevel || gradeLevel) === gradeLevel
    ));
    if (!existing.length) return true;

    const semLabel = semesterCode === '2nd' ? '2nd Semester' : '1st Semester';
    const uniqueSubjects = new Set(
      existing.map(item => (item.subject_code || item.subject_name || '').toUpperCase()).filter(Boolean),
    );
    const summary = scheduleEntrySummary(existing.length, uniqueSubjects.size);
    const confirmed = await AdminApp.confirmDialog({
      title: 'Replace Saved Schedule?',
      detail: `${strandUpper} · ${gradeShortLabel(gradeLevel)} · ${semLabel}`,
      message: `You already saved ${summary} for this strand. Delete the old schedule before generating a new one?`,
      confirmLabel: 'Delete & Generate',
      cancelLabel: 'Cancel',
      variant: 'reject',
      icon: 'fa-trash',
    });
    if (!confirmed) return false;

    const outcome = await deleteSavedScheduleForKey(`${gradeLevel}|${strandUpper}`, {
      silent: true,
      semesterCode,
    });
    if (!outcome?.ok) {
      showBanner(outcome?.error || 'Could not delete the previous schedule.');
      return false;
    }

    const verify = await AdminApp.fetchJson(`/api/scheduling/draft?${params}`);
    const still = dedupeScheduleEntries(verify.schedules || []).filter(item => (
      (item.strand || '').toUpperCase() === strandUpper
      && (item.gradeLevel || gradeLevel) === gradeLevel
    ));
    if (still.length) {
      showBanner(
        `${still.length} saved row(s) still remain for ${strandUpper}. Use Delete in the sidebar, then try again.`,
        'warn',
      );
      return false;
    }

    showBanner(outcome.res?.message || `Previous ${strandUpper} schedule cleared.`, 'success');
    return true;
  }

  async function deleteSavedSchedule(key, button = null) {
    await deleteSavedScheduleForKey(key, { button });
  }

  function renderWizardNav() {
    return `
      <div class="auto-sched-wizard">
        ${WIZARD_STEPS.map((label, i) => {
          const num = i + 1;
          const cls = num === wizardStep ? 'active' : num < wizardStep ? 'done' : '';
          return `
            <div class="auto-sched-wizard-step ${cls}">
              <span class="wiz-num">${num < wizardStep ? '✓' : num}</span>
              <span class="wiz-label">${esc(label)}</span>
            </div>`;
        }).join('')}
      </div>`;
  }

  function getSelectedStrands(form) {
    if (wizardFormData.strands?.length) return [wizardFormData.strands[0]];
    const radio = form?.querySelector('input[name="strand"]:checked');
    if (radio?.value) return [radio.value];
    const checked = [...(form?.querySelectorAll('input[name="strand"]:checked') || [])].map(el => el.value);
    if (checked.length) return [checked[0]];
    return [];
  }

  function showBanner(message, type = 'error') {
    const existing = document.getElementById('autoSchedBanner');
    if (existing) existing.remove();
    const banner = document.createElement('div');
    banner.id = 'autoSchedBanner';
    banner.className = `auto-sched-banner ${type}`;
    banner.innerHTML = `
      <span>${esc(message)}</span>
      <button type="button" aria-label="Dismiss">&times;</button>
    `;
    banner.querySelector('button').addEventListener('click', () => banner.remove());
    const panel = document.querySelector('.auto-sched-panel');
    panel?.prepend(banner);
  }

  function renderStep4Summary() {
    const strands = wizardFormData.strands || [];
    const trackLabel = config?.tracks?.[selectedTrack]?.label || selectedTrack;
    return `
      <div class="auto-sched-review">
        <h4>Your selections</h4>
        <div class="auto-sched-review-grid">
          <div class="review-item">
            <span class="review-label">Track</span>
            <span class="review-value">${esc(trackLabel)}</span>
        </div>
          <div class="review-item">
            <span class="review-label">Strand</span>
            <span class="review-value review-strands">
              ${strands.slice(0, 1).map(s => `<span class="strand-badge ${strandClass(s)}">${esc(s)}</span>`).join('') || '—'}
            </span>
          </div>
          <div class="review-item">
            <span class="review-label">Grade / Sem</span>
            <span class="review-value">${esc(wizardFormData.gradeLevel || 'Grade 12')} · ${esc(wizardFormData.semesterCode || '1st')} sem</span>
          </div>
          <div class="review-item">
            <span class="review-label">Sections</span>
            <span class="review-value">${wizardFormData.sectionsPerStrand === '1' ? '1 section' : '2 sections per strand'}</span>
          </div>
        </div>
      </div>`;
  }

  function renderSchedulingDataPanel(compact = false) {
    if (contextLoading) {
      return `
        <div class="auto-sched-data-panel loading">
          <div class="auto-sched-loading-inline">
            <div class="auto-sched-loading-spinner"></div>
            <p>Collecting teacher, room, lab, and time data...</p>
          </div>
        </div>`;
    }

    if (!schedulingContext) {
      return `
        <div class="auto-sched-data-panel empty">
          <div class="auto-sched-data-checklist">
            <p class="auto-sched-data-lead">The system will gather:</p>
            <ul>
              <li>Teacher Availability</li>
              <li>Classroom Availability</li>
              <li>Laboratory Availability</li>
              <li>Time Constraints</li>
            </ul>
          </div>
          <button type="button" class="admin-btn secondary" id="loadContextBtn">Load Scheduling Data</button>
        </div>`;
    }

    const teachers = schedulingContext.teacher_availability || [];
    const classrooms = schedulingContext.classroom_availability || [];
    const labs = schedulingContext.laboratory_availability || [];
    const time = schedulingContext.time_constraints || {};

    return `
      <div class="auto-sched-data-panel ${compact ? 'compact' : ''}">
        <div class="auto-sched-data-header">
          <div>
            <h4>AI Collects Scheduling Data</h4>
            <p class="auto-sched-data-sub">Ready — data loaded from your database.</p>
          </div>
          ${!compact ? '<button type="button" class="admin-btn secondary" id="loadContextBtn">Refresh Data</button>' : ''}
        </div>
        <ul class="auto-sched-data-checklist done">
          <li>Teacher Availability</li>
          <li>Classroom Availability</li>
          <li>Laboratory Availability</li>
          <li>Time Constraints</li>
        </ul>
        <div class="auto-sched-data-grid">
          <article class="data-card">
            <span class="data-card-icon teachers">👩‍🏫</span>
            <h5>Teachers</h5>
            <p class="data-card-stat">${teachers.length} available</p>
            ${compact ? '' : `<ul class="data-card-list">${teachers.slice(0, 5).map(t =>
              `<li>${esc(t.name)} <span class="muted">${esc((t.strands || []).join(', ') || t.department || '')}</span></li>`,
            ).join('')}${teachers.length > 5 ? `<li class="muted">+${teachers.length - 5} more</li>` : ''}</ul>`}
          </article>
          <article class="data-card">
            <span class="data-card-icon rooms">🏫</span>
            <h5>Classrooms</h5>
            <p class="data-card-stat">${classrooms.length} rooms</p>
            <p class="data-card-detail">${esc(classrooms.join(', ') || 'None')}</p>
          </article>
          <article class="data-card">
            <span class="data-card-icon labs">🔬</span>
            <h5>Laboratories</h5>
            <p class="data-card-stat">${labs.length} labs</p>
            <p class="data-card-detail">${esc(labs.join(', ') || 'None')}</p>
          </article>
          <article class="data-card">
            <span class="data-card-icon time">🕐</span>
            <h5>Time Constraints</h5>
            <p class="data-card-stat">${esc(time.hours || '8am–5pm')}</p>
            <p class="data-card-detail">${esc((time.days || ['Mon–Fri']).join(', '))}</p>
          </article>
        </div>
      </div>`;
  }

  function renderContextPreview() {
    return renderSchedulingDataPanel(false);
  }

  async function refreshSchedulingContext(form) {
    if (contextLoading) return;
    contextLoading = true;
    schedulingContext = null;
    rerenderForm();
    try {
      const data = new FormData(form);
      wizardFormData = {
        ...wizardFormData,
        gradeLevel: data.get('gradeLevel') || wizardFormData.gradeLevel,
        semesterCode: data.get('semesterCode') || wizardFormData.semesterCode,
        sectionsPerStrand: data.get('sectionsPerStrand') || wizardFormData.sectionsPerStrand,
        rooms: data.get('rooms') || wizardFormData.rooms,
        strands: wizardFormData.strands?.length ? wizardFormData.strands : getSelectedStrands(form),
      };
      await loadSchedulingContext(form);
      const allRooms = [
        ...(schedulingContext?.classroom_availability || []),
        ...(schedulingContext?.laboratory_availability || []),
      ];
      if (allRooms.length) {
        wizardFormData.rooms = allRooms.join(', ');
      }
    } catch (err) {
      showBanner(err.message || 'Could not load scheduling data.');
    } finally {
      contextLoading = false;
      rerenderForm();
    }
  }

  async function loadSchedulingContext(form) {
    const data = new FormData(form);
    const strands = getSelectedStrands(form);
    const params = new URLSearchParams({
      gradeLevel: data.get('gradeLevel'),
      semesterCode: data.get('semesterCode'),
      strands: strands.join(','),
      rooms: data.get('rooms') || '',
    });
    const res = await AdminApp.fetchJson(`/api/scheduling/context?${params}`);
    schedulingContext = res.data;
    return schedulingContext;
  }

  function renderForm() {
    const rooms = (config?.rooms || []).join(', ');
    const trackStrands = strandsForTrack(selectedTrack);
    const pickedOne = wizardFormData.strands?.length ? wizardFormData.strands[0] : (trackStrands[0] || '');
    const strandChips = trackStrands.map(code => {
      const checked = code === pickedOne ? 'checked' : '';
    return `
      <label class="auto-sched-chip ${strandClass(code)}">
        <input type="radio" name="strand" value="${esc(code)}" ${checked}> ${esc(code)}
      </label>`;
    }).join('');

    let stepBody = '';
    if (wizardStep === 1) {
      stepBody = `
        <h3 class="auto-sched-panel-title">Step 1 — Select Track / Specialization</h3>
        <div class="auto-sched-track-grid">
          <label class="auto-sched-track-card ${selectedTrack === 'Academic' ? 'selected' : ''}">
            <input type="radio" name="track" value="Academic" ${selectedTrack === 'Academic' ? 'checked' : ''}>
            <strong>Academic</strong>
            <span>STEM, ABM, HUMSS</span>
          </label>
          <label class="auto-sched-track-card ${selectedTrack === 'TechPro' ? 'selected' : ''}">
            <input type="radio" name="track" value="TechPro" ${selectedTrack === 'TechPro' ? 'checked' : ''}>
            <strong>Technical-Professional (TechPro)</strong>
            <span>ICT, Cookery, EIM</span>
          </label>
        </div>`;
    } else if (wizardStep === 2) {
      stepBody = `
        <h3 class="auto-sched-panel-title">Step 2 — Select One Strand</h3>
        <p class="auto-sched-hint">${esc(config?.tracks?.[selectedTrack]?.label || selectedTrack)} — pick <strong>one strand only</strong> per run. Schedule other strands in a separate run after saving.</p>
        <div class="auto-sched-strands auto-sched-strands-single">${strandChips || '<p>No strands for this track.</p>'}</div>`;
    } else if (wizardStep === 3) {
      stepBody = `
        <h3 class="auto-sched-panel-title">Step 3 — AI Collects Scheduling Data</h3>
        <p class="auto-sched-hint">Set grade, semester, and rooms. Teacher, classroom, lab, and time data load automatically below.</p>
          <div class="auto-sched-grid">
            <label>Grade Level
              <select name="gradeLevel" class="admin-input">
              <option value="Grade 11" ${wizardFormData.gradeLevel === 'Grade 11' ? 'selected' : ''}>Grade 11</option>
              <option value="Grade 12" ${!wizardFormData.gradeLevel || wizardFormData.gradeLevel === 'Grade 12' ? 'selected' : ''}>Grade 12</option>
              </select>
            </label>
            <label>Semester
              <select name="semesterCode" class="admin-input">
              <option value="1st" ${!wizardFormData.semesterCode || wizardFormData.semesterCode === '1st' ? 'selected' : ''}>1st Semester</option>
              <option value="2nd" ${wizardFormData.semesterCode === '2nd' ? 'selected' : ''}>2nd Semester</option>
              </select>
            </label>
            <label>Sections per Strand
              <select name="sectionsPerStrand" class="admin-input">
              <option value="2" ${wizardFormData.sectionsPerStrand !== '1' ? 'selected' : ''}>2 sections per strand</option>
              <option value="1" ${wizardFormData.sectionsPerStrand === '1' ? 'selected' : ''}>1 section only</option>
              </select>
            </label>
          </div>
        <label class="auto-sched-block">Rooms (classrooms + labs, comma-separated)
          <input type="text" name="rooms" class="admin-input" value="${esc(wizardFormData.rooms || rooms)}">
          </label>
        ${renderContextPreview()}
        ${(wizardFormData.strands || []).slice(0, 1).map(s => `<input type="hidden" name="strand" value="${esc(s)}">`).join('')}`;
    } else {
      stepBody = `
        <h3 class="auto-sched-panel-title">Step 4 — Generate, Validate &amp; Publish</h3>
        ${renderStep4Summary()}
        ${renderSchedulingDataPanel(true)}
        <div class="auto-sched-options">
          <label class="auto-sched-check">
          <input type="checkbox" name="useAi" checked> Use Google OR-Tools (CP-SAT constraint solver)
          </label>
          <label class="auto-sched-check">
          <input type="checkbox" name="allowLocalFallback" checked>
          Fallback to rule-based scheduler if OR-Tools cannot find a solution.
          </label>
        </div>
        <p class="auto-sched-hint">One strand per run. Classes spread 8am–5pm across ${esc(String((config?.rooms || []).length || 15))} rooms to avoid conflicts with other strands.</p>`;
    }

    return `
      <div class="auto-sched-page">
        <div class="auto-sched-layout">
          <div class="auto-sched-main">
            <section class="auto-sched-hero">
              <h2>Auto-Scheduling</h2>
              <p>Google OR-Tools generates conflict-free schedules in seconds — Track → Strands → Collect Data → Generate → Save → Publish</p>
              ${renderAiStatus()}
            </section>
            <section class="auto-sched-panel">
              ${renderWizardNav()}
              <form id="autoSchedForm" class="auto-sched-form">
                ${wizardStep >= 2 ? `<input type="hidden" name="track" value="${esc(selectedTrack)}">` : ''}
                ${wizardStep === 4 ? `
                  <input type="hidden" name="gradeLevel" value="${esc(wizardFormData.gradeLevel || 'Grade 12')}">
                  <input type="hidden" name="semesterCode" value="${esc(wizardFormData.semesterCode || '1st')}">
                  <input type="hidden" name="sectionsPerStrand" value="${esc(wizardFormData.sectionsPerStrand || '2')}">
                  <input type="hidden" name="rooms" value="${esc(wizardFormData.rooms || rooms)}">
                  ${(wizardFormData.strands || []).map(s => `<input type="hidden" name="strand" value="${esc(s)}">`).join('')}
                ` : ''}
                ${stepBody}
          <div class="auto-sched-actions">
                  <div class="auto-sched-actions-left">
                    ${wizardStep > 1 ? '<button type="button" class="admin-btn secondary auto-sched-back-btn" id="wizardBackBtn">← Back</button>' : ''}
                  </div>
                  <div class="auto-sched-actions-right">
                  ${wizardStep < 4 ? '<button type="button" class="admin-btn primary" id="wizardNextBtn">Next →</button>' : `
                    <button type="submit" class="admin-btn primary" id="generateBtn">${esc(getGenerateButtonLabel())}</button>
                    <button type="button" class="admin-btn secondary" id="redoSchedBtn" style="display:none">Redo Schedule</button>
                    <button type="button" class="admin-btn success" id="savePublishBtn" style="display:none" disabled>Save &amp; Publish Schedule</button>
                  `}
                  </div>
          </div>
        </form>
            </section>
      </div>
          <aside class="auto-sched-saved-aside" id="savedSchedSidebar">
            ${renderSavedSchedulesSidebar()}
          </aside>
        </div>
      </div>`;
  }

  function renderNotes(notes) {
    if (!notes?.length) return '';
    return `
      <ul class="auto-sched-notes">
        ${notes.map(note => `<li>${esc(note)}</li>`).join('')}
      </ul>
    `;
  }

  function shortenNote(text) {
    if (!text) return '';
    if (text.includes('rate limit')) return 'Rate limit hit — retrying with backoff / next cloud provider';
    if (text.includes('local scheduler') || text.includes('rule-based')) return text.split(':').pop()?.trim() || text;
    return text.length > 80 ? `${text.slice(0, 77)}...` : text;
  }

  function appendProgress(entries) {
    if (!entries?.length) return;
    progressLog.push(...entries);
    if (progressLog.length > 80) progressLog = progressLog.slice(-80);
  }

  function renderProgressLog() {
    if (!progressLog.length) return '';
      return `
      <div class="auto-sched-log">
        <strong>Live progress</strong>
        <ul>
          ${progressLog.slice(-20).map(entry => `
            <li class="log-${esc(entry.level || 'info')}">${esc(entry.message)}</li>
          `).join('')}
        </ul>
        </div>
      `;
    }

  function renderProgressSteps(strands, currentIndex) {
      return `
      <div class="auto-sched-steps">
        ${strands.map((strand, index) => {
          const state = strandProgress[strand] || {};
          let statusClass = 'pending';
          let statusText = 'Waiting';
          if (state.status === 'processing') { statusClass = 'processing'; statusText = 'Generating...'; }
          if (state.status === 'done') { statusClass = 'done'; statusText = `Done (${state.count || 0})`; }
          if (state.status === 'failed') { statusClass = 'failed'; statusText = 'Failed'; }
          if (index === currentIndex && state.status === 'pending' && generationState.started) {
            statusClass = 'ready';
            statusText = 'Ready — press button';
          }
          if (index === currentIndex && state.status === 'processing') statusClass = 'processing';
      return `
            <div class="auto-sched-step ${statusClass} ${strandClass(strand)}">
              <div class="step-dot">${state.status === 'done' ? '✓' : index + 1}</div>
              <div class="step-label">${esc(strand)}</div>
              <div class="step-status">${esc(statusText)}</div>
            </div>
          `;
        }).join('')}
        </div>
      `;
    }

  function renderStrandRestPrompt(completedStrand, nextStrand, completedCount, cooldownRemaining) {
    if (!nextStrand) return '';
    const cooldownHtml = cooldownRemaining > 0
      ? `<p class="auto-sched-cooldown-inline">Cloud AI cooldown: <strong>${formatElapsed(cooldownRemaining)}</strong> remaining before next strand.</p>`
      : '<p>Cloud AI is ready — you can generate the next strand now.</p>';
      return `
      <div class="auto-sched-rest-card">
        <div class="auto-sched-rest-icon">✓</div>
        <div class="auto-sched-rest-body">
          <strong>${esc(completedStrand)} complete</strong> — ${completedCount} schedule entries added.
          ${cooldownHtml}
        </div>
      </div>
    `;
  }

  function viewKey(gradeLevel, strand) {
    const grade = gradeLevel || 'Grade 12';
    const code = String(strand || '').toUpperCase();
    return `${grade}|${code}`;
  }

  function parseViewKey(key) {
    const text = String(key || '').trim();
    if (!text) return { gradeLevel: null, strand: null };
    if (!text.includes('|')) {
      return {
        gradeLevel: wizardFormData.gradeLevel || 'Grade 12',
        strand: text.toUpperCase(),
      };
    }
    const [gradeLevel, strand] = text.split('|');
    return {
      gradeLevel: gradeLevel || 'Grade 12',
      strand: String(strand || '').toUpperCase(),
    };
  }

  function strandGradeGroupsFromSchedules(schedules) {
    const groups = {};
    (schedules || []).forEach(item => {
      const grade = item.gradeLevel || 'Grade 12';
      const strand = String(item.strand || '').toUpperCase();
      if (!strand) return;
      const key = viewKey(grade, strand);
      if (!groups[key]) {
        groups[key] = { key, gradeLevel: grade, strand, count: 0, subjects: new Set() };
      }
      groups[key].count += 1;
      const subjectCode = (item.subject_code || item.subject_name || '').toUpperCase();
      if (subjectCode) groups[key].subjects.add(subjectCode);
    });
    return Object.values(groups).sort((a, b) => {
      if (a.gradeLevel !== b.gradeLevel) {
        return a.gradeLevel.includes('11') ? -1 : 1;
      }
      return a.strand.localeCompare(b.strand);
    }).map(group => ({
      ...group,
      subjectCount: group.subjects.size,
    }));
  }

  function getViewSelection(highlightStrand) {
    if (selectedViewStrand) return parseViewKey(selectedViewStrand);
    if (highlightStrand) return parseViewKey(highlightStrand);
    const generated = generationState.generatedStrands || [];
    if (generated.length) {
      const strand = generated[generated.length - 1];
      return {
        gradeLevel: wizardFormData.gradeLevel || 'Grade 12',
        strand: String(strand).toUpperCase(),
      };
    }
    return { gradeLevel: null, strand: null };
  }

  function getViewStrand(highlightStrand) {
    return getViewSelection(highlightStrand).strand;
  }

  function getViewGradeLevel(highlightStrand) {
    return getViewSelection(highlightStrand).gradeLevel;
  }

  function strandCountsFromSchedules(schedules) {
    const counts = {};
    (schedules || []).forEach(item => {
      const key = (item.strand || '').toUpperCase();
      if (!key) return;
      counts[key] = (counts[key] || 0) + 1;
    });
    return counts;
  }

  function isSavedStrand(strand) {
    const generated = generationState.generatedStrands || [];
    return !generated.includes(String(strand || '').toUpperCase());
  }

  function isSavedStrandGrade(gradeLevel, strand) {
    const strandUpper = String(strand || '').toUpperCase();
    const generated = generationState.generatedStrands || [];
    if (!generated.includes(strandUpper)) return true;
    const activeGrade = wizardFormData.gradeLevel || 'Grade 12';
    return (gradeLevel || 'Grade 12') !== activeGrade;
  }

  function renderStrandSummary(schedules, { selectedKey = null } = {}) {
    const generated = new Set(generationState.generatedStrands || []);
    const groups = strandGradeGroupsFromSchedules(schedules);
    if (!groups.length) return '';

    const selection = selectedKey ? parseViewKey(selectedKey) : getViewSelection();
    const activeKey = selection.strand
      ? viewKey(selection.gradeLevel, selection.strand)
      : null;
    const semLabel = (wizardFormData.semesterCode || savedSchedulesFilter.semesterCode || '1st') === '2nd'
      ? '2nd sem'
      : '1st sem';

    return `
      <div class="auto-sched-summary auto-sched-summary-split">
        ${groups.map(group => {
          const saved = isSavedStrandGrade(group.gradeLevel, group.strand);
          const isActive = activeKey === group.key;
          return `
          <button type="button"
            class="auto-sched-summary-card ${strandClass(group.strand)}${isActive ? ' active' : ''}${saved ? ' is-saved' : ''}"
            data-view-key="${esc(group.key)}"
            aria-pressed="${isActive ? 'true' : 'false'}">
            <div class="auto-sched-summary-grade">${esc(gradeShortLabel(group.gradeLevel))}</div>
            <div class="count">${group.count}</div>
            <div class="label">${esc(group.strand)}</div>
            <div class="auto-sched-summary-sub">${esc(semLabel)} · ${esc(scheduleEntrySummary(group.count, group.subjectCount))}</div>
            <span class="auto-sched-summary-tag${saved ? '' : ' new'}">${saved ? 'Saved' : 'New'}</span>
          </button>`;
        }).join('')}
      </div>
    `;
  }

  function bindStrandSummaryClicks(container) {
    const root = container || document.getElementById('resultsWrap');
    if (!root) return;
    root.querySelectorAll('[data-view-key]').forEach(btn => {
      btn.addEventListener('click', () => {
        selectedViewStrand = btn.dataset.viewKey;
        refreshResultsView();
      });
    });
  }

  function refreshResultsView() {
    const wrap = document.getElementById('resultsWrap');
    if (!wrap || !lastResult) return;
    wrap.innerHTML = renderResults(
      lastResult,
      generationState.strands,
      generationState.currentIndex,
      selectedViewStrand,
    );
    bindStrandSummaryClicks(wrap);
  }

  function setResultsContent(html) {
    const wrap = document.getElementById('resultsWrap');
    if (!wrap) return;
    wrap.innerHTML = html;
    bindStrandSummaryClicks(wrap);
  }

  function renderTeacherLoads(loads) {
    if (!loads?.length) return '';
    const chips = loads.map(item => {
      const atMax = Number(item.load) >= Number(item.max_load || 3);
      return `<span class="auto-sched-load-chip${atMax ? ' at-max' : ''}">${esc(item.label || item.faculty_name || item.faculty_id)}</span>`;
    }).join('');
    return `
      <div class="auto-sched-teacher-loads">
        <strong>Teacher loads this semester</strong>
        <div class="auto-sched-load-chips">${chips}</div>
      </div>`;
  }

  function renderTableRows(schedules, highlightStrand, { showSection = true, showStrand = false } = {}) {
    return (schedules || []).map(item => {
      const highlight = highlightStrand && item.strand === highlightStrand ? ' auto-sched-row-new' : '';
      const facultyLabel = item.faculty_name || item.faculty_id || 'Unable to assign faculty';
      const facultyCell = item.faculty_id
        ? esc(facultyLabel)
        : `<span class="auto-sched-missing-faculty">${esc(facultyLabel)}</span>`;
      return `
        <tr class="${highlight}">
          ${showStrand ? `<td><span class="strand-badge ${strandClass(item.strand)}">${esc(item.strand)}</span></td>` : ''}
          ${showSection ? `<td><span class="section-badge">${esc(item.section)}</span></td>` : ''}
          <td><strong>${esc(item.subject_code)}</strong></td>
          <td class="auto-sched-subject-name">${esc(item.subject_name)}</td>
          <td>${facultyCell}</td>
          <td class="auto-sched-schedule-cell">${renderScheduleCell(item)}</td>
        </tr>
      `;
    }).join('');
  }

  function schedulesForSection(schedules, section) {
    return (schedules || []).filter(item => String(item.section || '').toUpperCase() === section);
  }

  function renderSectionTable(section, strand, gradeLevel, schedules, highlightStrand, { isGenerating = false } = {}) {
    const rows = schedulesForSection(schedules, section);
    const sectionLabel = sectionDisplayLabel(strand, gradeLevel, section);
    let body = '';
    if (rows.length) {
      body = `
          <div class="auto-sched-table-wrap">
            <table class="auto-sched-table">
              <thead>
                <tr>
                  <th>Code</th><th>Subject</th><th>Professor</th><th>Schedule</th>
        </tr>
              </thead>
              <tbody>${renderTableRows(rows, highlightStrand, { showSection: false })}</tbody>
            </table>
          </div>`;
    } else if (isGenerating) {
      body = `
          <div class="auto-sched-section-generating">
            <div class="auto-sched-loading-spinner"></div>
            <p>Building <strong>${esc(sectionLabel)}</strong> schedules…</p>
            <span class="auto-sched-section-generating-sub">Assigning rooms, teachers, and time slots…</span>
          </div>`;
    } else {
      body = `<p class="auto-sched-section-empty">No schedule entries for ${sectionLabel} yet.</p>`;
    }
    return `
      <div class="auto-sched-section-block">
        <h4 class="auto-sched-section-title">${sectionLabel} <span class="auto-sched-section-count">${rows.length} subject${rows.length === 1 ? '' : 's'}</span></h4>
        ${body}
      </div>
    `;
  }

  function schedulesForStrand(schedules, strandCode, gradeLevel = null) {
    if (!strandCode && !gradeLevel) return schedules || [];
    const code = String(strandCode || '').toUpperCase();
    return (schedules || []).filter(item => {
      const matchStrand = !code || String(item.strand || '').toUpperCase() === code;
      const matchGrade = !gradeLevel || (item.gradeLevel || 'Grade 12') === gradeLevel;
      return matchStrand && matchGrade;
    });
  }

  function renderSavedReferenceBlock(schedules, activeStrand) {
    const active = String(activeStrand || '').toUpperCase();
    const reference = (schedules || []).filter(item => String(item.strand || '').toUpperCase() !== active);
    if (!reference.length) return '';

    const byGroup = {};
    reference.forEach(item => {
      const grade = item.gradeLevel || 'Grade 12';
      const key = `${grade}|${(item.strand || 'OTHER').toUpperCase()}`;
      if (!byGroup[key]) byGroup[key] = { grade, strand: (item.strand || 'OTHER').toUpperCase(), items: [] };
      byGroup[key].items.push(item);
    });

    const groupKeys = Object.keys(byGroup).sort();
    const chips = groupKeys.map(key => {
      const group = byGroup[key];
      const gradeShort = String(group.grade).includes('11') ? 'G11' : 'G12';
      return `
      <span class="auto-sched-saved-chip ${strandClass(group.strand)}">
        <strong>${esc(group.strand)}</strong> · ${esc(gradeShort)} · ${group.items.length} saved
      </span>
      `;
    }).join('');

    return `
      <div class="auto-sched-saved-ref">
        <div class="auto-sched-saved-ref-icon" aria-hidden="true">📋</div>
        <div class="auto-sched-saved-ref-body">
          <strong>Saved schedules loaded for conflict check</strong>
          <p>Grade 11 and Grade 12 share the same school day — both grades are checked for the selected semester only (1st or 2nd, never mixed).</p>
          <div class="auto-sched-saved-chips">${chips}</div>
        </div>
      </div>
    `;
  }

  function strandsInSchedules(schedules) {
    const keys = new Set();
    (schedules || []).forEach(item => {
      keys.add(String(item.strand || 'UNKNOWN').toUpperCase());
    });
    return [...keys].sort();
  }

  function renderStrandBlock(strand, gradeLevel, strandSchedules, highlightStrand, { isGenerating = false } = {}) {
    const count = strandSchedules.length;
    const sectionsPresent = new Set(strandSchedules.map(item => String(item.section || '').toUpperCase()));
    const sectionNote = isGenerating
      ? sectionPairLabel(strand, gradeLevel)
      : sectionsPresent.has('A') && sectionsPresent.has('B')
      ? sectionPairLabel(strand, gradeLevel)
      : sectionsPresent.has('A')
        ? sectionSlotName(strand, gradeLevel, 'A')
        : sectionsPresent.has('B')
          ? sectionSlotName(strand, gradeLevel, 'B')
          : 'No sections';
    const countLabel = isGenerating && !count
      ? 'Building schedules…'
      : `${count} subject${count === 1 ? '' : 's'}`;

    return `
      <article class="auto-sched-strand-block ${strandClass(strand)}">
        <header class="auto-sched-strand-header">
          <span class="strand-badge ${strandClass(strand)}">${esc(strand)}</span>
          <div class="auto-sched-strand-meta">
            <strong>${esc(strand)} Strand</strong>
            <span>${countLabel} · ${sectionNote}</span>
          </div>
        </header>
        <div class="auto-sched-sections">
          ${renderSectionTable('A', strand, gradeLevel, strandSchedules, highlightStrand, { isGenerating })}
          ${renderSectionTable('B', strand, gradeLevel, strandSchedules, highlightStrand, { isGenerating })}
        </div>
      </article>
    `;
  }

  function renderScheduleTables(schedules, highlightStrand, { activeStrandOnly = false, isGenerating = false, gradeLevel = 'Grade 12', viewGradeLevel = null } = {}) {
    const view = parseViewKey(highlightStrand);
    const effectiveGrade = viewGradeLevel || view.gradeLevel || gradeLevel;
    const effectiveStrand = view.strand || (highlightStrand ? String(highlightStrand).toUpperCase() : null);
    const strandList = activeStrandOnly && effectiveStrand
      ? [effectiveStrand]
      : strandsInSchedules(schedules);

    if (!strandList.length) {
      return '<p class="auto-sched-section-empty">No schedule entries yet.</p>';
    }

    return `
      <div class="auto-sched-strand-groups">
        ${strandList.map(strand => renderStrandBlock(
          strand,
          effectiveGrade,
          schedulesForStrand(schedules, strand, activeStrandOnly ? effectiveGrade : null),
          effectiveStrand,
          {
            isGenerating: isGenerating
              && strand === String(effectiveStrand || '').toUpperCase(),
          },
        )).join('')}
      </div>
    `;
  }

  function renderResults(result, strands, currentIndex, highlightStrand, restPrompt) {
    if (!result && strands?.length) {
      return `
        <section class="auto-sched-panel">
          <h3 class="auto-sched-panel-title">Generation Progress</h3>
          ${renderProgressSteps(strands, currentIndex)}
          ${renderProgressLog()}
          <div class="auto-sched-loading-inline">
            <div class="auto-sched-loading-spinner"></div>
            <p>Processing <strong>${esc(strands[currentIndex] || '')}</strong>... please wait.</p>
          </div>
        </section>
      `;
    }

    if (!result?.success) {
      return `
        <section class="auto-sched-panel error-card">
          <h3>Generation Failed</h3>
          <p>${esc(result?.error || 'Unknown error')}</p>
          ${result?.ai_error ? `<p class="muted">${esc(result.ai_error)}</p>` : ''}
        </section>
      `;
    }

    const conflicts = result.validation?.conflicts || [];
    const activeStrand = highlightStrand || (strands && strands[currentIndex]) || null;
    const viewSelection = getViewSelection(activeStrand);
    const viewStrand = viewSelection.strand;
    const viewGradeLevel = viewSelection.gradeLevel || wizardFormData.gradeLevel || 'Grade 12';
    const viewKeyValue = viewStrand ? viewKey(viewGradeLevel, viewStrand) : null;
    const isGenerating = Boolean(viewStrand)
      && !generationState.allComplete
      && strandProgress[viewStrand]?.status === 'processing';
    const viewSchedules = viewStrand
      ? schedulesForStrand(result.schedules, viewStrand, viewGradeLevel)
      : (result.schedules || []);
    const viewCount = viewSchedules.length;
    const viewingSaved = Boolean(viewStrand) && isSavedStrandGrade(viewGradeLevel, viewStrand);
    const panelTitle = isGenerating
      ? `Generating ${esc(viewStrand)} · ${esc(gradeShortLabel(viewGradeLevel))}`
      : viewStrand
        ? `${esc(viewStrand)} · ${esc(gradeShortLabel(viewGradeLevel))} (${viewCount} ${viewCount === 1 ? 'entry' : 'entries'})${viewingSaved ? ' · Saved' : ''}`
        : `Generated Schedule (${result.count} entries)`;

    return `
      <section class="auto-sched-panel auto-sched-result-panel">
        <div class="auto-sched-result-head">
          <h3>${panelTitle}</h3>
          <span class="admin-badge ${result.validation?.valid ? 'approved' : 'rejected'}">
            ${result.validation?.valid ? 'Zero Conflicts' : 'Has Conflicts'}
          </span>
          <span class="admin-badge pending">Source: ${esc(formatSource(result.source))}</span>
        </div>

        ${strands?.length ? renderProgressSteps(strands, currentIndex) : ''}
        ${restPrompt || ''}
        ${renderProgressLog()}
        ${renderStrandSummary(result.schedules, { selectedKey: viewKeyValue })}
        ${result.ai_error ? renderNotes(
          String(result.ai_error).split(' | ').map(shortenNote).filter(Boolean),
        ) : ''}

        ${conflicts.length ? `
          <div class="auto-sched-conflicts">
            <strong>${conflicts.length} conflict(s)</strong>
            <ul>${conflicts.slice(0, 15).map(c => `<li>${esc(c.message)}</li>`).join('')}</ul>
            ${conflicts.length > 15 ? `<p class="muted">…and ${conflicts.length - 15} more</p>` : ''}
          </div>
        ` : ''}

        ${renderTeacherLoads(result.teacher_loads)}

        ${renderScheduleTables(result.schedules, viewKeyValue || viewStrand, {
          activeStrandOnly: Boolean(viewStrand),
          isGenerating,
          gradeLevel: wizardFormData.gradeLevel || 'Grade 12',
          viewGradeLevel: viewGradeLevel,
        })}
      </section>
    `;
  }

  function bindWizard(form) {
    form.querySelectorAll('input[name="strand"]').forEach(radio => {
      radio.addEventListener('change', () => {
        if (radio.checked) wizardFormData.strands = [radio.value];
      });
    });
    form.querySelectorAll('input[name="track"]').forEach(radio => {
      radio.addEventListener('change', () => {
        selectedTrack = radio.value;
        rerenderForm();
      });
    });
    const nextBtn = document.getElementById('wizardNextBtn');
    const backBtn = document.getElementById('wizardBackBtn');
    if (nextBtn) {
      nextBtn.addEventListener('click', async () => {
        if (wizardStep === 1) {
          const picked = form.querySelector('input[name="track"]:checked');
          const newTrack = picked?.value || 'Academic';
          if (newTrack !== selectedTrack) wizardFormData.strands = [];
          selectedTrack = newTrack;
        }
        if (wizardStep === 2) {
          const picked = getSelectedStrands(form);
          if (picked.length !== 1) { showBanner('Please select exactly one strand to continue.'); return; }
          wizardFormData.strands = picked;
        }
        if (wizardStep === 3) {
    const data = new FormData(form);
          const nextFormData = {
            ...wizardFormData,
      gradeLevel: data.get('gradeLevel'),
      semesterCode: data.get('semesterCode'),
            sectionsPerStrand: data.get('sectionsPerStrand'),
            rooms: data.get('rooms'),
            strands: wizardFormData.strands?.length ? wizardFormData.strands : getSelectedStrands(form),
          };
          const settingsChanged = nextFormData.gradeLevel !== wizardFormData.gradeLevel
            || nextFormData.semesterCode !== wizardFormData.semesterCode
            || nextFormData.rooms !== wizardFormData.rooms;
          wizardFormData = nextFormData;
          syncSavedSchedulesFilterFromWizard();
          refreshSavedSchedules();
          if (!wizardFormData.strands?.length) {
            showBanner('No strands selected. Go back to Step 2 and pick at least one.');
            return;
          }
          if (!schedulingContext || settingsChanged) {
            await refreshSchedulingContext(form);
            if (!schedulingContext) return;
          }
        }
        wizardStep += 1;
        if (wizardStep === 4) {
          const picked = wizardFormData.strands?.length
            ? wizardFormData.strands
            : getSelectedStrands(form);
          resetGenerationState(picked);
        }
        rerenderForm();
      });
    }
    if (backBtn) {
      backBtn.addEventListener('click', () => {
        if (wizardStep === 4) {
          resetGenerationState(getSelectedStrands(form) || []);
        }
        wizardStep = Math.max(1, wizardStep - 1);
        rerenderForm();
      });
    }
  }

  function rerenderForm() {
    const wrap = document.querySelector('.auto-sched-page')?.parentElement;
    if (!wrap) return;
    const results = document.getElementById('resultsWrap')?.innerHTML || '';
    wrap.innerHTML = `${renderForm()}<div id="resultsWrap">${results}</div>`;
    bindForm(document.getElementById('autoSchedForm'));
    bindSavedSchedulesSidebar();
  }

  function setSavePublishEnabled(enabled) {
    const btn = document.getElementById('savePublishBtn');
    if (!btn) return;
    btn.style.display = enabled ? '' : 'none';
    btn.disabled = !enabled;
    if (!enabled) {
      btn.textContent = 'Save & Publish Schedule';
    }
  }

  function shouldShowRedoButton() {
    if (!generationState.started) return false;
    if (generationState.strands.some(strand => strandProgress[strand]?.status === 'processing')) {
      return false;
    }
    if (generationState.allComplete) return true;
    return generationState.strands.some(strand => strandProgress[strand]?.status === 'failed');
  }

  async function redoSchedule(form) {
    const confirmed = await AdminApp.confirmDialog({
      title: 'Redo Schedule?',
      message: 'Clear this schedule and generate again? Unsaved results will be lost.',
      confirmLabel: 'Redo',
      cancelLabel: 'Keep',
      variant: 'reject',
      icon: 'fa-rotate-left',
    });
    if (!confirmed) return;
    clearCooldownTimer();
    const strands = getSelectedStrands(form);
    resetGenerationState(strands);
    lastResult = null;
    document.getElementById('resultsWrap').innerHTML = '';
    setSavePublishEnabled(false);
    updateGenerateControls(form);
    showBanner('Ready to generate a new schedule.', 'success');
  }

  function bindForm(form) {
    if (!form) return;
    bindWizard(form);
    form.addEventListener('submit', e => { e.preventDefault(); generate(form); });
    const loadBtn = document.getElementById('loadContextBtn');
    if (loadBtn) loadBtn.addEventListener('click', () => refreshSchedulingContext(form));
    const savePublishBtn = document.getElementById('savePublishBtn');
    const redoBtn = document.getElementById('redoSchedBtn');
    if (savePublishBtn) savePublishBtn.addEventListener('click', () => saveAndPublishSchedule(form));
    if (redoBtn) redoBtn.addEventListener('click', () => redoSchedule(form));

    if (wizardStep === 4) {
      updateGenerateControls(form);
      resumeCooldownTimer(form);
    }

    if (wizardStep === 3 && !schedulingContext && !contextLoading) {
      refreshSchedulingContext(form);
    }

    if (wizardStep === 3) {
      form.querySelectorAll('select[name="gradeLevel"], select[name="semesterCode"]').forEach(sel => {
        sel.addEventListener('change', () => {
          savedSchedulesFilter.semesterCode = form.querySelector('[name="semesterCode"]')?.value || '1st';
          refreshSavedSchedules();
        });
      });
    }
  }

  async function saveAndPublishSchedule(form) {
    if (!lastResult?.schedules?.length) return;

    const data = new FormData(form);
    const strand = (wizardFormData.strands || getSelectedStrands(form))[0];
    const gradeLevel = data.get('gradeLevel') || 'Grade 12';
    const semesterCode = data.get('semesterCode') || '1st';
    const semesterLabel = semesterCode === '2nd' ? '2nd Semester' : '1st Semester';
    const toSaveRaw = strand
      ? lastResult.schedules.filter(item =>
        (item.strand || '').toUpperCase() === strand.toUpperCase()
        && (item.gradeLevel || gradeLevel) === gradeLevel
      )
      : lastResult.schedules.filter(item => (item.gradeLevel || gradeLevel) === gradeLevel);
    const toSave = dedupeScheduleEntries(toSaveRaw);

    if (!toSave.length) {
      showBanner('No schedule entries to save for the selected strand.');
      return;
    }
    if (toSave.length !== toSaveRaw.length) {
      showBanner(
        `Removed ${toSaveRaw.length - toSave.length} invalid or duplicate row(s) before save.`,
        'success',
      );
    }

    const confirmed = await AdminApp.confirmDialog({
      title: 'Save & Publish Schedule?',
      detail: strand ? `${strand} · ${gradeLevel} · ${semesterLabel}` : `${gradeLevel} · ${semesterLabel}`,
      message: 'This saves the schedule to the database and publishes it so students, teachers, and the registrar can view it.',
      confirmLabel: 'Save & Publish',
      cancelLabel: 'Cancel',
      variant: 'info',
      icon: 'fa-cloud-arrow-up',
    });
    if (!confirmed) return;

    const btn = document.getElementById('savePublishBtn');
    const defaultLabel = 'Save & Publish Schedule';
    if (btn) {
    btn.disabled = true;
      btn.textContent = 'Saving...';
    }

    try {
      const applyRes = await fetch('/api/scheduling/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gradeLevel,
          semesterCode,
          schedules: toSave,
          source: lastResult.source,
        }),
      });
      const applyPayload = await applyRes.json();
      if (!applyPayload.success) {
        showBanner(applyPayload.error || applyPayload.hint || 'Save failed');
        await AdminApp.alertDialog({
          type: 'error',
          title: 'Save Failed',
          message: applyPayload.error || applyPayload.hint || 'Could not save schedule to the database.',
        });
        return;
      }

      if (btn) btn.textContent = 'Publishing...';

      let publishedCount = applyPayload.applied ?? applyPayload.count ?? toSave.length;
      const pubRes = await fetch('/api/scheduling/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gradeLevel, semesterCode }),
      });
      const pubPayload = await pubRes.json();
      if (pubPayload.success) {
        publishedCount = pubPayload.published ?? publishedCount;
      } else {
        console.warn('Publish step warning:', pubPayload.error || pubPayload.hint);
      }

      const savedCount = applyPayload.applied ?? applyPayload.count ?? toSave.length;
      const successMsg = `${strand || 'Schedule'} saved and published (${publishedCount} records). Students can view it in their portal.`;
      showBanner(successMsg, 'success');
      await AdminApp.alertDialog({
        type: 'success',
        title: 'Schedule Published',
        message: successMsg,
      });
      await refreshSavedSchedules();
    } catch (err) {
      showBanner(err.message || 'Save & publish failed');
      await AdminApp.alertDialog({
        type: 'error',
        title: 'Something Went Wrong',
        message: err.message || 'Could not complete save and publish.',
      });
    } finally {
      if (btn) {
      btn.disabled = false;
        btn.textContent = defaultLabel;
        if (lastResult?.success && lastResult?.schedules?.length) {
          btn.style.display = '';
        }
      }
    }
  }

  function buildPayload(form, strand, existingSchedules) {
    const data = new FormData(form);
    const useAiEl = form.querySelector('input[name="useAi"]');
    const fallbackEl = form.querySelector('input[name="allowLocalFallback"]');
    return {
      strand,
      gradeLevel: data.get('gradeLevel'),
      semesterCode: data.get('semesterCode'),
      sectionsPerStrand: parseInt(data.get('sectionsPerStrand'), 10) || 2,
      rooms: (data.get('rooms') || '').split(',').map(r => r.trim()).filter(Boolean),
      // Server loads saved drafts from DB — avoid sending duplicates from accumulated.
      existingSchedules: [],
      useAi: useAiEl ? useAiEl.checked : true,
      useCloudAi: useAiEl ? useAiEl.checked : true,
      allowLocalFallback: fallbackEl ? fallbackEl.checked : true,
    };
  }

  function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function strandsMatch(a, b) {
    if (!a?.length || !b?.length || a.length !== b.length) return false;
    return a.every((strand, index) => strand === b[index]);
  }

  function resetGenerationState(strands, { keepProgress = false } = {}) {
    selectedViewStrand = null;
    generationState = {
      strands: [...strands],
      currentIndex: 0,
      accumulated: [],
      generatedStrands: [],
      savedStrands: [],
      notes: [],
      finalSource: 'ortools',
      started: false,
      allComplete: false,
    };
    if (!keepProgress) {
      strandProgress = {};
      progressLog = [];
      lastResult = null;
    }
    strands.forEach(strand => {
      if (!strandProgress[strand]) {
        strandProgress[strand] = { status: 'pending', count: 0 };
      }
    });
  }

  function syncGenerationStrands(strands) {
    if (!generationState.started) {
      resetGenerationState(strands);
      return;
    }
    if (!strandsMatch(generationState.strands, strands)) {
      resetGenerationState(strands);
    }
  }

  function getCooldownRemainingSec() {
    if (!cooldownUntil) return 0;
    return Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
  }

  function isCooldownActive() {
    return getCooldownRemainingSec() > 0;
  }

  function clearCooldownTimer() {
    if (cooldownTimerId) {
      clearInterval(cooldownTimerId);
      cooldownTimerId = null;
    }
    cooldownUntil = 0;
    const btn = document.getElementById('generateBtn');
    if (btn) btn.classList.remove('cooldown');
  }

  function parseCooldownFromProgress(entries, source) {
    if (source === 'ortools' || source === 'smart_ai_fallback') return 0;
    let maxPause = 0;
    let hadRateLimit = false;
    let usedCloud = false;
    for (const entry of entries || []) {
      const msg = entry.message || '';
      const lower = msg.toLowerCase();
      if (/429|rate limit/.test(lower)) hadRateLimit = true;
      if (lower.includes('cloud ai') || lower.includes('via groq') || lower.includes('one ai call')) {
        usedCloud = true;
      }
      const match = lower.match(/pausing\s+(\d+)s/);
      if (match) maxPause = Math.max(maxPause, parseInt(match[1], 10));
    }
    if (hadRateLimit) return Math.max(30, maxPause + 15);
    if (usedCloud) return 10;
    return 0;
  }

  function resolveCooldownSec(data) {
    if (typeof data?.cooldown_sec === 'number') return data.cooldown_sec;
    return parseCooldownFromProgress(data?.progress || progressLog, data?.source);
  }

  function startCooldownTimer(form, seconds, targetLabel, { onReadyMessage } = {}) {
    clearCooldownTimer();
    if (!seconds || seconds <= 0) {
      updateGenerateControls(form);
      return;
    }

    cooldownUntil = Date.now() + seconds * 1000;

    const tick = () => {
      const remaining = getCooldownRemainingSec();
      const btn = document.getElementById('generateBtn');
      if (remaining <= 0) {
        clearCooldownTimer();
        updateGenerateControls(form);
        if (onReadyMessage) showBanner(onReadyMessage, 'success');
        return;
      }
      if (btn) {
        btn.disabled = true;
        btn.classList.add('cooldown');
        btn.textContent = `Wait ${formatElapsed(remaining)} — Generate ${targetLabel}`;
      }
    };

    tick();
    cooldownTimerId = setInterval(tick, 1000);
  }

  function resumeCooldownTimer(form) {
    if (!isCooldownActive() || cooldownTimerId) return;
    const index = generationState.currentIndex;
    const target = generationState.strands[index]
      ? `${generationState.strands[index]} (${index + 1} of ${generationState.strands.length})`
      : 'Next strand';

    const tick = () => {
      const remaining = getCooldownRemainingSec();
      const btn = document.getElementById('generateBtn');
      if (remaining <= 0) {
        clearCooldownTimer();
        updateGenerateControls(form);
        return;
      }
      if (btn) {
        btn.disabled = true;
        btn.classList.add('cooldown');
        btn.textContent = `Wait ${formatElapsed(remaining)} — Generate ${target}`;
      }
    };

    tick();
    cooldownTimerId = setInterval(tick, 1000);
  }

  function getGenerateButtonLabel() {
    if (generationState.allComplete) return 'Schedule Complete ✓';
    const strand = generationState.strands[0] || wizardFormData.strands?.[0];
    if (!strand) return 'Generate Schedule';
    const state = strandProgress[strand] || {};
    if (state.status === 'failed') return `Retry ${strand}`;
    return `Generate ${strand} Schedule`;
  }

  function updateGenerateControls(form) {
    const btn = document.getElementById('generateBtn');
    const redoBtn = document.getElementById('redoSchedBtn');
    if (!btn) return;
    const strands = getSelectedStrands(form);
    syncGenerationStrands(strands);

    const remaining = getCooldownRemainingSec();
    if (remaining > 0) {
      const index = generationState.currentIndex;
      const target = generationState.strands[index] || 'Next strand';
    btn.disabled = true;
      btn.classList.add('cooldown');
      btn.textContent = `Wait ${formatElapsed(remaining)} — Generate ${target}`;
      if (redoBtn) redoBtn.style.display = shouldShowRedoButton() ? '' : 'none';
      return;
    }

    btn.classList.remove('cooldown');
    btn.textContent = getGenerateButtonLabel();
    btn.disabled = generationState.allComplete;
    if (redoBtn) redoBtn.style.display = shouldShowRedoButton() ? '' : 'none';
  }

  function formatElapsed(seconds) {
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }

  function updateProgressLogDom() {
    const logList = document.querySelector('#resultsWrap .auto-sched-log ul');
    if (!logList) return;
    logList.innerHTML = progressLog.slice(-20).map(entry => `
      <li class="log-${esc(entry.level || 'info')}">${esc(entry.message)}</li>
    `).join('');
  }

  function startElapsedTimer(strand, strandIndex, totalStrands) {
    const startedAt = Date.now();
    const tick = () => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      const last = progressLog[progressLog.length - 1];
      const tickMessage = `Generating ${strand} (${strandIndex + 1}/${totalStrands}) — ${formatElapsed(elapsed)} elapsed...`;
      if (last && last.message && last.message.startsWith(`Generating ${strand}`)) {
        last.message = tickMessage;
      } else {
        progressLog.push({ level: 'info', message: tickMessage });
      }
      if (progressLog.length > 80) progressLog = progressLog.slice(-80);
      updateProgressLogDom();
    };
    tick();
    return setInterval(tick, 1000);
  }

  async function finalizeGeneration(form, strands) {
    const { accumulated, notes, finalSource } = generationState;
    const btn = document.getElementById('generateBtn');
    const formData = new FormData(form);

    if (!accumulated.length) {
      setResultsContent(renderResults(
        { success: false, error: 'No schedules were generated.', ai_error: notes.join(' | ') },
        strands,
        strands.length - 1,
      ));
      updateGenerateControls(form);
      setSavePublishEnabled(false);
      return;
    }

    try {
    const res = await fetch('/api/scheduling/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        schedules: accumulated,
        gradeLevel: formData.get('gradeLevel') || 'Grade 12',
        semesterCode: formData.get('semesterCode') || '1st',
        mergeWithSaved: true,
      }),
    });
    const data = await res.json();
      generationState.accumulated = dedupeScheduleEntries(accumulated);
      lastResult = {
        success: true,
        count: generationState.accumulated.length,
        schedules: [...generationState.accumulated],
        source: finalSource,
        ai_error: notes.length ? notes.join(' | ') : null,
        validation: data.validation,
      };
      generationState.allComplete = true;
      appendProgress([{ level: 'success', message: `${strands[0] || 'Strand'} schedule validated — ready to save.` }]);
      setResultsContent(renderResults(lastResult, strands, strands.length, selectedViewStrand));
      const canSave = Boolean(data.success && data.validation?.valid !== false && accumulated.length);
      setSavePublishEnabled(canSave);
      if (canSave) {
        showBanner(`${strands[0] || 'Strand'} schedule ready. Save & publish when done, then run again for other strands.`, 'success');
      } else {
        showBanner(`${strands[0] || 'Strand'} generated but has conflicts — fix before saving.`);
      }
    } catch (err) {
      document.getElementById('resultsWrap').innerHTML = `
        <section class="auto-sched-panel error-card"><p>${esc(err.message)}</p></section>`;
      setSavePublishEnabled(false);
    } finally {
      updateGenerateControls(form);
    }
  }

  async function loadDraftSchedules(form, strand) {
    const data = new FormData(form);
    const gradeLevel = data.get('gradeLevel') || 'Grade 12';
    try {
      const params = new URLSearchParams({
        gradeLevel,
        semesterCode: data.get('semesterCode') || '1st',
      });
      const res = await AdminApp.fetchJson(`/api/scheduling/draft?${params}`);
      const strandUpper = (strand || '').toUpperCase();
      const saved = dedupeScheduleEntries(res.schedules || []).filter(item => !(
        (item.strand || '').toUpperCase() === strandUpper
        && (item.gradeLevel || gradeLevel) === gradeLevel
      ));
      if (saved.length) {
        generationState.accumulated = saved;
        generationState.savedStrands = [...new Set(saved.map(item => (item.strand || '').toUpperCase()).filter(Boolean))];
        const grades = [...new Set(saved.map(item => item.gradeLevel || 'Grade 12'))];
        const semLabel = (data.get('semesterCode') || '1st') === '2nd' ? '2nd sem' : '1st sem';
        appendProgress([{
          level: 'info',
          message: `Loaded ${saved.length} saved entries (${grades.join(' + ')}, ${semLabel} only) for conflict check.`,
        }]);
      } else {
        generationState.accumulated = [];
        generationState.savedStrands = [];
      }
    } catch (_) {
      // No saved draft yet — fine for first strand
    }
  }

  async function generate(form) {
    const strands = getSelectedStrands(form);
    if (strands.length !== 1) {
      showBanner('Select exactly one strand in Step 2.');
      return;
    }
    if (generationState.allComplete) return;
    if (isCooldownActive()) {
      const remaining = getCooldownRemainingSec();
      const next = generationState.strands[generationState.currentIndex] || 'next strand';
      showBanner(`Please wait ${formatElapsed(remaining)} before retrying ${next}.`);
      return;
    }

    syncGenerationStrands(strands);
    const i = generationState.currentIndex;
    const strand = generationState.strands[i];
    if (!strand) return;

    const canGenerate = await ensureSavedScheduleCleared(form, strand);
    if (!canGenerate) {
      updateGenerateControls(form);
      return;
    }

    const btn = document.getElementById('generateBtn');
    btn.disabled = true;
    btn.textContent = `Generating ${strand}...`;
    setSavePublishEnabled(false);

    if (!generationState.started) {
      generationState.started = true;
      progressLog = [];
      await loadDraftSchedules(form, strand);
      document.getElementById('resultsWrap').innerHTML = renderResults(null, generationState.strands, i);
    }

    strandProgress[strand] = { status: 'processing', count: 0 };
    setResultsContent(renderResults(
      {
        success: true,
        count: generationState.accumulated.length,
        schedules: [...generationState.accumulated],
        validation: { valid: true, conflicts: [] },
      },
      generationState.strands,
      i,
      strand,
    ));

    const elapsedTimer = startElapsedTimer(
      strand,
      i,
      generationState.strands.length,
    );

    try {
      const res = await fetch('/api/scheduling/generate-strand', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(form, strand, generationState.accumulated)),
      });
      clearInterval(elapsedTimer);
      let data = {};
      try {
        data = await res.json();
      } catch (_) {
        throw new Error(
          res.ok
            ? 'Server returned an invalid response. Restart the admin server and try again.'
            : `Server error (${res.status}). Restart the admin server (python server.py) and try again.`,
        );
      }
      appendProgress(data.progress || []);

      if (!data.success) {
        strandProgress[strand] = { status: 'failed', count: 0, error: data.error };
        const failNote = data.hint
          ? `${shortenNote(data.error || 'failed')} — ${data.hint}`
          : shortenNote(data.error || 'failed');
        generationState.notes.push(`${strand}: ${failNote}`);
        setResultsContent(renderResults(
          {
            success: true,
            count: generationState.accumulated.length,
            schedules: [...generationState.accumulated],
            source: generationState.finalSource,
            ai_error: generationState.notes.join(' | '),
            validation: data.validation || { valid: false, conflicts: [] },
          },
          generationState.strands,
          i,
          strand,
        ));
        updateGenerateControls(form);
        setSavePublishEnabled(false);
        const retryCooldown = resolveCooldownSec({ progress: data.progress, source: data.source });
        if (retryCooldown > 0) {
          startCooldownTimer(form, retryCooldown, strand, {
            onReadyMessage: `Cloud AI ready — you can retry ${strand} now.`,
          });
        }
        const conflictMsg = String(data.error || '');
        if (/room\/time conflict/i.test(conflictMsg)) {
          await revealAllSavedSchedulesForConflicts();
          showBanner(
            `${strand} blocked — delete the conflicting saved schedule(s) on the right, then retry.`,
            'warn',
          );
        } else {
          showBanner(`${strand} failed — fix the issue or press Retry when ready.`);
        }
      return;
    }

      const gradeLevel = new FormData(form).get('gradeLevel') || 'Grade 12';
      mergeStrandSchedulesIntoAccumulated(strand, gradeLevel, data.schedules || []);
      const strandKey = String(strand).toUpperCase();
      if (!generationState.generatedStrands.includes(strandKey)) {
        generationState.generatedStrands.push(strandKey);
      }
      selectedViewStrand = viewKey(new FormData(form).get('gradeLevel') || 'Grade 12', strandKey);
      strandProgress[strand] = { status: 'done', count: data.count || 0, source: data.source };
      if (data.source === 'ortools') generationState.finalSource = 'ortools';
      else if (data.source === 'smart_ai_fallback') generationState.finalSource = 'smart_ai_fallback';
      else if (data.source === 'gemini_ai') generationState.finalSource = 'gemini_ai';
      else if (data.source === 'openrouter_ai') generationState.finalSource = 'openrouter_ai';
      if (data.ai_error) generationState.notes.push(`${strand}: ${shortenNote(data.ai_error)}`);

      lastResult = {
        success: true,
        count: generationState.accumulated.length,
        schedules: [...generationState.accumulated],
        source: generationState.finalSource,
        ai_error: generationState.notes.length ? generationState.notes.join(' | ') : null,
        validation: data.validation || { valid: data.combined_valid, conflicts: [] },
      };

      generationState.currentIndex += 1;

      appendProgress([{ level: 'success', message: `${strand} schedule complete.` }]);

      setResultsContent(renderResults(
        lastResult,
        generationState.strands,
        generationState.currentIndex,
        strandKey,
      ));

      await finalizeGeneration(form, generationState.strands);
    } catch (err) {
      clearInterval(elapsedTimer);
      strandProgress[strand] = { status: 'failed', count: 0, error: err.message };
      document.getElementById('resultsWrap').innerHTML = `
        <section class="auto-sched-panel error-card"><p>${esc(err.message)}</p></section>`;
      updateGenerateControls(form);
      setSavePublishEnabled(false);
    }
  }

  async function mount(container) {
    if (!AdminApp.requireAuth()) return;
    wizardStep = 1;
    selectedTrack = 'Academic';
    schedulingContext = null;
    wizardFormData = {};
    resetGenerationState([]);
    container.innerHTML = '<p>Loading scheduler config...</p>';
    try {
      await loadConfig();
    } catch (err) {
      container.innerHTML = `<section class="auto-sched-panel error-card"><p>${esc(err.message)}</p></section>`;
      return;
    }

    container.innerHTML = `${renderForm()}<div id="resultsWrap"></div>`;
    bindForm(document.getElementById('autoSchedForm'));
    bindSavedSchedulesSidebar();
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeSavedScheduleModal();
    });
    refreshSavedSchedules();
  }

  return { mount, loadConfig };
})();
