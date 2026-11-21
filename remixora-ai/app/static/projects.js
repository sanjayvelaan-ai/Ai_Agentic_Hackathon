'use strict';

let currentProjectId = localStorage.getItem('remixora-project') || '';
let currentProjectTab = 'overview';
let projectSearch = '';
let projectStatusFilter = 'all';
let projectSortOrder = 'newest';
let projectData = null;
let projectCandidates = [];
let projectRenders = [];
let projectPresetRuns = [];
let projectSegments = [];

function setProjectLocation(pid, tab = 'overview') {
  currentProjectId = pid;
  currentProjectTab = tab;
  localStorage.setItem('remixora-project', pid);
  localStorage.setItem('remixora-source', pid);
}

// -------------------------------------------------------------
// 1. PROJECTS DASHBOARD
// -------------------------------------------------------------
async function projectsDashboard() {
  const projects = await api('/projects');
  state.allProjects = projects;

  // Filter & Sort
  let list = projects.filter(p => {
    const matchesSearch = !projectSearch.trim() || p.title.toLowerCase().includes(projectSearch.toLowerCase().trim());
    const matchesStatus = projectStatusFilter === 'all' || p.status === projectStatusFilter;
    return matchesSearch && matchesStatus;
  });

  if (projectSortOrder === 'oldest') {
    list.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  } else if (projectSortOrder === 'updated') {
    list.sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));
  } else if (projectSortOrder === 'title') {
    list.sort((a, b) => a.title.localeCompare(b.title));
  } else {
    list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  }

  const totalCandidates = projects.reduce((acc, p) => acc + (p.candidates_count || 0), 0);
  const totalRenders = projects.reduce((acc, p) => acc + (p.renders_count || 0), 0);

  return pageHead(
    'My Projects',
    'Organized video workspaces with isolated storage, candidate clips, and verified renders.',
    `<a class="button primary" href="#ingest" data-action="new-workflow">${icon('upload')} New Project</a>`
  ) + `
  <div class="library-summary">
    <span><strong>${projects.length}</strong> Projects</span>
    <span><strong>${totalCandidates}</strong> Suggested Clips</span>
    <span><strong>${totalRenders}</strong> Rendered Outputs</span>
  </div>

  <div class="smart-toolbar" style="margin-bottom: 24px;">
    <label class="search-box">
      ${icon('scout')}
      <input id="proj-search" placeholder="Search projects by name..." value="${esc(projectSearch)}">
    </label>
    <select id="proj-status-filter" style="width: 190px;" aria-label="Filter status">
      <option value="all" ${projectStatusFilter === 'all' ? 'selected' : ''}>All Statuses</option>
      <option value="ready" ${projectStatusFilter === 'ready' ? 'selected' : ''}>Ready</option>
      <option value="queued" ${projectStatusFilter === 'queued' ? 'selected' : ''}>Processing</option>
      <option value="needs_transcript" ${projectStatusFilter === 'needs_transcript' ? 'selected' : ''}>Needs Transcript</option>
      <option value="failed" ${projectStatusFilter === 'failed' ? 'selected' : ''}>Failed</option>
    </select>
    <select id="proj-sort-order" style="width: 190px;" aria-label="Sort order">
      <option value="newest" ${projectSortOrder === 'newest' ? 'selected' : ''}>Newest First</option>
      <option value="oldest" ${projectSortOrder === 'oldest' ? 'selected' : ''}>Oldest First</option>
      <option value="updated" ${projectSortOrder === 'updated' ? 'selected' : ''}>Recently Updated</option>
      <option value="title" ${projectSortOrder === 'title' ? 'selected' : ''}>Title (A-Z)</option>
    </select>
  </div>

  ${list.length ? `
    <div class="library-grid">
      ${list.map(p => `
        <article class="panel library-card project-card" data-project-id="${p.id}">
          <div class="library-preview">
            <img src="/api/projects/${p.id}/thumbnail" alt="${esc(p.title)}" style="width:100%;height:100%;object-fit:cover;" onerror="this.onerror=null;this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';">
            <div class="audio-art" style="display:none;width:100%;height:100%;">
              ${icon(p.source_type === 'youtube' ? 'film' : 'remix')}
              <span>${esc(p.source_type === 'youtube' ? 'YouTube Video' : 'Original Recording')}</span>
            </div>
            <span class="duration">${stamp(p.duration)}</span>
          </div>
          <div class="library-card-body">
            <h2 title="${esc(p.title)}">${esc(p.title)}</h2>
            <div class="library-meta">
              <span class="pill subtle">${p.source_type === 'youtube' ? 'YouTube' : 'Upload'}</span>
              ${badge(p.status)}
              <small>${esc(p.created_at.slice(0, 10))}</small>
            </div>
            <div style="display:flex;gap:10px;margin-bottom:14px;font-size:13px;color:var(--muted);">
              <span><strong>${p.candidates_count || 0}</strong> candidates</span>
              <span>•</span>
              <span><strong class="teal">${p.renders_count || 0}</strong> renders</span>
            </div>
            <div class="actions" style="justify-content:space-between;">
              <button class="button primary small" data-action="open-project" data-id="${p.id}">Open Workspace</button>
              <div style="display:flex;gap:6px;">
                <button class="button ghost small" data-action="rename-project" data-id="${p.id}" title="Rename Project">Rename</button>
                <button class="button ghost small" data-action="delete-project" data-id="${p.id}" title="Delete Project" style="color:var(--danger);">Delete</button>
              </div>
            </div>
          </div>
        </article>
      `).join('')}
    </div>
  ` : empty(
    'No matching projects found',
    projectSearch ? 'Try a different search keyword or status filter.' : 'Upload a video or import a YouTube link to create your first project.',
    '#ingest',
    'Import New Source'
  )}
  `;
}

// -------------------------------------------------------------
// 2. DEDICATED PROJECT WORKSPACE (/projects/{id})
// -------------------------------------------------------------
async function projectWorkspaceView(projectId, tab = currentProjectTab) {
  setProjectLocation(projectId, tab);

  // Fetch full project data
  try {
    projectData = await api(`/projects/${projectId}`);
  } catch (err) {
    return pageHead('Project Not Found', '') + `
      <div class="panel empty">
        <h2>This project no longer exists.</h2>
        <a class="button primary section-gap" href="#projects">Back to Projects</a>
      </div>
    `;
  }

  // Fetch tab-specific data in parallel
  const [candidates, renders, runs, segments] = await Promise.all([
    api(`/projects/${projectId}/candidates`).catch(() => []),
    api(`/projects/${projectId}/renders`).catch(() => []),
    api(`/projects/${projectId}/preset-runs`).catch(() => []),
    api(`/projects/${projectId}/transcript`).catch(() => [])
  ]);

  projectCandidates = candidates;
  projectRenders = renders;
  projectPresetRuns = runs;
  projectSegments = segments;

  const tabs = [
    { id: 'overview', label: 'Overview', icon: 'home' },
    { id: 'media', label: 'Original Media', icon: 'film', count: segments.length ? `${segments.length} cues` : null },
    { id: 'presets', label: 'AI Presets', icon: 'spark', count: '12' },
    { id: 'candidates', label: 'Suggested Clips', icon: 'scout', count: candidates.length },
    { id: 'renders', label: 'Rendered Clips', icon: 'download', count: renders.length },
    { id: 'studio', label: 'Content Studio', icon: 'remix' },
    { id: 'calendar', label: 'Calendar', icon: 'calendar' },
    { id: 'analytics', label: 'Analytics', icon: 'chart' }
  ];

  return `
    <div class="project-header" style="margin-bottom:24px;">
      <div class="page-head" style="margin-bottom:14px;">
        <div>
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;">
            <a href="#projects" class="pill subtle" style="text-decoration:none;">‹ All Projects</a>
            <span class="pill ${projectData.source_type === 'youtube' ? 'amber' : 'subtle'}">${projectData.source_type === 'youtube' ? 'YouTube' : 'Local File'}</span>
            ${badge(projectData.status)}
          </div>
          <h1>${esc(projectData.title)}</h1>
          <p>${stamp(projectData.duration)} duration • Created on ${esc(projectData.created_at.slice(0, 10))} • Isolated Project Storage</p>
        </div>
        <div class="actions">
          <button class="button ghost small" data-action="rename-project" data-id="${projectData.id}">Rename</button>
          <button class="button ghost small" data-action="delete-project" data-id="${projectData.id}" style="color:var(--danger);">Delete Project</button>
        </div>
      </div>

      <div class="tabs" role="tablist" style="width:100%;overflow-x:auto;display:flex;gap:6px;padding:6px;border-radius:14px;">
        ${tabs.map(t => `
          <button role="tab"
                  class="tab ${tab === t.id ? 'active' : ''}"
                  data-action="project-tab"
                  data-tab="${t.id}"
                  style="display:flex;align-items:center;gap:8px;white-space:nowrap;">
            ${icon(t.icon)}
            ${t.label}
            ${t.count !== null ? `<span class="pill subtle" style="font-size:11px;padding:2px 6px;">${t.count}</span>` : ''}
          </button>
        `).join('')}
      </div>
    </div>

    <div class="project-tab-content">
      ${renderTabContent(tab)}
    </div>
  `;
}

function renderTabContent(tab) {
  switch (tab) {
    case 'overview':
      return renderOverviewTab();
    case 'media':
      return renderMediaTab();
    case 'presets':
      return renderPresetsTab();
    case 'candidates':
      return renderCandidatesTab();
    case 'renders':
      return renderRendersTab();
    case 'studio':
      return renderStudioTab();
    case 'calendar':
      return renderCalendarTab();
    case 'analytics':
      return renderAnalyticsTab();
    default:
      return renderOverviewTab();
  }
}

// -------------------------------------------------------------
// TAB 1: OVERVIEW
// -------------------------------------------------------------
function renderOverviewTab() {
  const p = projectData;
  return `
    <div class="grid-two" style="gap:24px;">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Source Media Overview</h2>
            <p>${esc(p.source?.original_name || p.title)}</p>
          </div>
          ${badge(p.status)}
        </div>
        <video controls preload="metadata" class="media-player" style="margin-bottom:18px;" src="/api/projects/${p.id}/media"></video>
        <div class="grid-two" style="gap:12px;font-size:14px;">
          <div><strong class="muted">Duration:</strong> ${stamp(p.duration)}</div>
          <div><strong class="muted">Type:</strong> ${p.source_type}</div>
          <div><strong class="muted">Storage:</strong> Isolated Project Directory</div>
          <div><strong class="muted">Status:</strong> ${esc(p.status)}</div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Repurposing Pipeline Status</h2>
            <p>Summary of generated project artifacts.</p>
          </div>
        </div>
        <div class="stats" style="grid-template-columns:repeat(2,1fr);margin-bottom:20px;">
          <div class="stat">
            <div>
              <div class="stat-label">Transcript Segments</div>
              <div class="stat-value">${projectSegments.length}</div>
              <div class="stat-note">${projectSegments.length ? 'Ready for AI scouting' : 'Needs transcript'}</div>
            </div>
            ${icon('scout')}
          </div>
          <div class="stat">
            <div>
              <div class="stat-label">Preset Runs</div>
              <div class="stat-value">${projectPresetRuns.length}</div>
              <div class="stat-note">Analyses executed</div>
            </div>
            ${icon('spark')}
          </div>
          <div class="stat">
            <div>
              <div class="stat-label">Suggested Clips</div>
              <div class="stat-value">${projectCandidates.length}</div>
              <div class="stat-note">Source candidate moments</div>
            </div>
            ${icon('film')}
          </div>
          <div class="stat">
            <div>
              <div class="stat-label">Rendered MP4s</div>
              <div class="stat-value teal">${projectRenders.length}</div>
              <div class="stat-note">Completed & downloadable</div>
            </div>
            ${icon('download')}
          </div>
        </div>

        <div class="actions">
          <button class="button primary" data-action="project-tab" data-tab="presets">${icon('spark')} Run AI Preset</button>
          <button class="button ghost" data-action="project-tab" data-tab="candidates">${icon('scout')} View Candidates (${projectCandidates.length})</button>
          <button class="button ghost" data-action="project-tab" data-tab="renders">${icon('download')} View Renders (${projectRenders.length})</button>
        </div>
      </section>
    </div>
  `;
}

// -------------------------------------------------------------
// TAB 2: ORIGINAL MEDIA & TRANSCRIPT
// -------------------------------------------------------------
function renderMediaTab() {
  const p = projectData;
  return `
    <div class="source-layout">
      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Original Media Player</h2>
            <p>Original source stream with timeline seeking support.</p>
          </div>
          ${badge(p.status)}
        </div>
        <video id="workspace-source-player" class="media-player" controls preload="metadata" src="/api/projects/${p.id}/media"></video>
        <div class="actions section-gap">
          <small>${stamp(p.duration)} total duration • ${p.source?.media_type || 'video'}</small>
        </div>
      </section>

      <section class="panel">
        <div class="panel-head">
          <div>
            <h2>Synchronized Transcript</h2>
            <p>${projectSegments.length} aligned transcript cues</p>
          </div>
        </div>

        ${projectSegments.length ? `
          <div class="transcript-list" style="max-height:380px;">
            ${projectSegments.map(s => `
              <div class="segment">
                <button class="timecode" data-action="seek-project-media" data-time="${s.start}">${stamp(s.start)}</button>
                <p>${esc(s.text)}</p>
              </div>
            `).join('')}
          </div>
        ` : `
          <div class="empty" style="padding:24px 10px;">
            <h3>No Transcript Available</h3>
            <p>Import a matching .srt or .vtt subtitle file to enable AI clip discovery.</p>
          </div>
        `}

        <form id="project-transcript-form" class="section-gap">
          <label for="attach-subtitles">Import SRT / VTT Subtitles</label>
          <input id="attach-subtitles" type="file" name="transcript" accept=".srt,.vtt" required>
          <button class="button primary small section-gap" type="submit">Align Subtitles</button>
        </form>
      </section>
    </div>
  `;
}

// -------------------------------------------------------------
// TAB 3: AI PRESETS
// -------------------------------------------------------------
function renderPresetsTab() {
  const p = projectData;
  return `
    <div class="panel-head">
      <div>
        <h2>AI Preset Library</h2>
        <p>12 specialized curation presets to discover highlights, moments, and vertical shorts.</p>
      </div>
      <span class="pill subtle">${projectPresetRuns.length} runs executed</span>
    </div>

    <div class="preset-grid">
      ${state.presets.map(preset => {
        const videoOnly = preset.video_only && p.source?.media_type === 'audio';
        return `
          <button class="preset-card"
                  data-action="launch-preset"
                  data-preset="${preset.id}"
                  data-search="${esc((preset.name + ' ' + preset.description).toLowerCase())}"
                  data-category="${esc(preset.category)}"
                  ${videoOnly ? 'disabled' : ''}>
            <div class="preset-icon">${presetIcon(preset.id)}</div>
            <h2>${esc(preset.name)}</h2>
            <p>${esc(preset.description)}</p>
            <div class="preset-meta">
              <span>${videoOnly ? 'Video required' : preset.category}</span>
              <span class="pill subtle">${esc(preset.cost)}</span>
            </div>
          </button>
        `;
      }).join('')}
    </div>

    ${projectPresetRuns.length ? `
      <section class="panel section-gap">
        <div class="panel-head">
          <h2>Recent Preset Analyses in This Project</h2>
        </div>
        ${projectPresetRuns.map(run => `
          <div class="project-row" style="display:flex;justify-content:space-between;align-items:center;">
            <div>
              <strong>${esc(run.preset_name || run.preset_id)}</strong>
              <br><small>Executed on ${esc(run.started_at?.slice(0, 16) || 'Recently')}</small>
            </div>
            <div style="display:flex;gap:10px;align-items:center;">
              ${badge(run.status)}
              <button class="button small ghost" data-action="filter-candidates-run" data-run="${run.id}">View Clips</button>
            </div>
          </div>
        `).join('')}
      </section>
    ` : ''}
  `;
}

// -------------------------------------------------------------
// TAB 4: SUGGESTED CLIPS (STRICT SOURCE PREVIEWS)
// -------------------------------------------------------------
function renderCandidatesTab() {
  return `
    <div class="panel-head">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
          <h2>Suggested Clip Candidates</h2>
          <span class="pill green">SOURCE PREVIEW ONLY</span>
        </div>
        <p>AI-discovered moments grounded in your transcript. Previews play original media within candidate boundaries.</p>
      </div>
      <button class="button primary small" data-action="project-tab" data-tab="presets">${icon('spark')} Run Another Preset</button>
    </div>

    ${projectCandidates.length ? `
      <div class="grid-three">
        ${projectCandidates.map((c, i) => `
          <article class="panel clip-card candidate-card ${c.status === 'rejected' ? 'rejected' : ''}">
            <div class="clip-visual" style="position:relative;background:linear-gradient(140deg,#2d2740,#1d2633);">
              <span class="pill amber" style="position:absolute;top:12px;left:12px;">SOURCE PREVIEW</span>
              <span class="clip-time">${stamp(c.start_time)} – ${stamp(c.end_time)} · ${Math.round(c.end_time - c.start_time)}s</span>
            </div>

            <div class="clip-body">
              <div class="score-row">
                <span class="pill subtle">${esc(c.preset_name || 'AI Scout')}</span>
                <span class="score"><strong>${(c.score * 5).toFixed(1)}</strong> / 5</span>
              </div>

              <h3>${esc(c.title)}</h3>
              <p>${esc(c.selection_reason)}</p>

              <details style="margin:12px 0;">
                <summary>Transcript Evidence</summary>
                <div style="font-size:13px;color:var(--muted);margin-top:6px;">
                  <code>Start: ${c.start_time.toFixed(2)}s | End: ${c.end_time.toFixed(2)}s</code>
                </div>
              </details>

              <div class="actions" style="margin-top:auto;padding-top:16px;">
                <button class="button ghost small" data-action="preview-source-clip" data-start="${c.start_time}" data-end="${c.end_time}">
                  ${icon('scout')} Preview Source
                </button>
                <button class="button primary small" data-action="trigger-render-modal" data-id="${c.id}" data-title="${esc(c.title)}">
                  ${icon('film')} Render Clip
                </button>
              </div>
            </div>
          </article>
        `).join('')}
      </div>
    ` : empty(
      'No clip candidates yet',
      'Run an AI Preset like "Best Highlights" or "Funny Moments" to discover clips from your transcript.',
      '',
      ''
    )}
  `;
}

// -------------------------------------------------------------
// TAB 5: RENDERED CLIPS (STRICT COMPLETED OUTPUTS)
// -------------------------------------------------------------
function renderRendersTab() {
  const completed = projectRenders.filter(r => r.is_rendered);
  const pending = projectRenders.filter(r => !r.is_rendered);

  return `
    <div class="panel-head">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px;">
          <h2>Rendered Videos Gallery</h2>
          <span class="pill teal">${completed.length} Completed MP4s</span>
        </div>
        <p>Verified, standalone rendered video files. Click Preview to stream the actual rendered MP4 file.</p>
      </div>
    </div>

    ${pending.length ? `
      <div class="notice section-gap" style="margin-bottom:20px;">
        <span class="spinner" style="margin-right:8px;"></span>
        ${pending.length} clip(s) currently rendering in the background queue. Results update automatically.
      </div>
    ` : ''}

    ${completed.length ? `
      <div class="grid-three">
        ${completed.map(r => `
          <article class="panel clip-card rendered-card" data-render-id="${r.id}">
            <div class="library-preview" style="aspect-ratio:9/16;max-height:260px;background:#0d0e17;position:relative;">
              ${r.thumbnail_url ? `
                <img src="${r.thumbnail_url}" alt="" style="width:100%;height:100%;object-fit:cover;">
              ` : `
                <div class="audio-art" style="height:100%;background:#131522;">
                  ${icon('film')}
                  <span>${esc(r.aspect_ratio || '9:16')} Render</span>
                </div>
              `}
              <span class="pill green" style="position:absolute;top:10px;left:10px;">RENDERED</span>
              <span class="duration" style="position:absolute;bottom:10px;right:10px;">${stamp(r.duration)}</span>
            </div>

            <div class="clip-body">
              <h3>${esc(r.title || 'Rendered Clip')}</h3>
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:14px;">
                <span class="pill subtle">${esc(r.aspect_ratio || '9:16')}</span>
                <span class="pill subtle">${stamp(r.duration)}</span>
                <small>${esc(r.created_at?.slice(0, 10) || '')}</small>
              </div>

              <div class="actions" style="margin-top:auto;gap:8px;">
                <button class="button primary small" data-action="play-rendered-modal" data-id="${r.id}">
                  ▶ Preview MP4
                </button>
                <a class="button ghost small" href="${r.download_url}" download>
                  ${icon('download')} Download
                </a>
                <button class="button ghost small" data-action="rename-render" data-id="${r.id}">
                  Rename
                </button>
                <button class="button ghost small" data-action="delete-render" data-id="${r.id}" style="color:var(--danger);">
                  ✕
                </button>
              </div>
            </div>
          </article>
        `).join('')}
      </div>
    ` : empty(
      'No rendered clips yet',
      'Select a candidate moment in the "Suggested Clips" tab and click "Render Clip" to produce a verified video.',
      '',
      ''
    )}
  `;
}

// -------------------------------------------------------------
// TAB 6: CONTENT STUDIO (PLATFORM DRAFTS & BRAND DNA)
// -------------------------------------------------------------
function renderStudioTab() {
  const p = projectData;
  const projectCopies = state.copies.filter(c => projectCandidates.some(cand => cand.clip_id === c.clip_id));
  const activeCopies = projectCopies.filter(c => c.angle === angle);

  return `
    <div class="panel-head">
      <div>
        <h2>Content Studio & Brand Memory</h2>
        <p>Platform-specific editorial drafts for Instagram Reel, YouTube Short, and LinkedIn.</p>
      </div>
      <div class="tabs" role="tablist">
        ${angles.map(a => `
          <button role="tab" class="tab ${a === angle ? 'active' : ''}" data-action="angle" data-angle="${a}">${a}</button>
        `).join('')}
      </div>
    </div>

    ${activeCopies.length ? `
      <div class="grid-three">
        ${activeCopies.map(copyCard).join('')}
      </div>
    ` : `
      <section class="panel">
        ${empty(
          'No drafts generated for this project yet',
          'Generate 9 platform drafts for your discovered clips.',
          '',
          ''
        )}
        <div class="actions" style="justify-content:center;">
          <button class="button primary" data-action="generate-project-copies" data-project-id="${p.id}">
            ${icon('spark')} Generate Platform Drafts
          </button>
        </div>
      </section>
    `}
  `;
}

// -------------------------------------------------------------
// TAB 7: CALENDAR
// -------------------------------------------------------------
function renderCalendarTab() {
  const p = projectData;
  const items = state.calendar.filter(cal => projectCandidates.some(cand => cand.clip_id === cal.copy_id));
  return `
    <div class="panel-head">
      <div>
        <h2>Project Content Calendar</h2>
        <p>Scheduled publication slots for this project.</p>
      </div>
      <button class="button primary small" data-action="schedule">${icon('calendar')} Plan a Post</button>
    </div>
    ${calendar()}
  `;
}

// -------------------------------------------------------------
// TAB 8: ANALYTICS
// -------------------------------------------------------------
function renderAnalyticsTab() {
  return `
    <div class="panel-head">
      <div>
        <h2>Performance & Engagement Attribution</h2>
        <p>Observed outcomes and recommendation feedback.</p>
      </div>
    </div>
    ${feedback()}
  `;
}

// -------------------------------------------------------------
// MODALS & EVENT HANDLERS
// -------------------------------------------------------------
function openRenderPreviewModal(renderId) {
  const r = projectRenders.find(x => x.id === renderId);
  if (!r) return;
  modal(
    esc(r.title || 'Rendered Clip Preview'),
    `
    <div style="text-align:center;">
      <video controls autoplay class="media-player" style="max-height:65vh;width:auto;margin:0 auto 18px;" src="${r.stream_url}"></video>
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <span class="pill subtle">${esc(r.aspect_ratio || '9:16')} • ${stamp(r.duration)}</span>
        <a class="button primary" href="${r.download_url}" download>${icon('download')} Download MP4</a>
      </div>
    </div>
    `
  );
}

function openRenderTriggerModal(candidateId, defaultTitle) {
  modal(
    'Render Clip',
    `
    <form id="trigger-render-form" data-candidate-id="${candidateId}">
      <div class="form-row">
        <label for="render-headline">Opening Headline / Title</label>
        <input id="render-headline" name="headline" value="${esc(defaultTitle)}" maxlength="120" required>
      </div>
      <div class="form-row">
        <label for="render-aspect">Aspect Ratio Frame</label>
        <select id="render-aspect" name="aspect_ratio">
          <option value="9:16" selected>9:16 Vertical (Shorts, Reels, TikTok)</option>
          <option value="1:1">1:1 Square (Instagram Post, LinkedIn)</option>
          <option value="16:9">16:9 Landscape (YouTube)</option>
        </select>
      </div>
      <label class="check">
        <input type="checkbox" name="burn_subtitles" checked> Burn in source-aligned subtitles
      </label>
      <div class="dialog-actions">
        <button class="button primary" type="submit">Queue Render</button>
      </div>
    </form>
    `
  );
  bindProjectForms();
}

function bindProjectForms() {
  onForm('trigger-render-form', async (form, data) => {
    const candidateId = form.dataset.candidateId;
    await api(`/projects/${currentProjectId}/renders`, 'POST', {
      candidate_id: candidateId,
      aspect_ratio: data.get('aspect_ratio'),
      headline: data.get('headline'),
      burn_subtitles: data.has('burn_subtitles')
    });
    $('#dialog').close();
    toast('Render job queued in background. Inspect progress in Rendered Clips.');
    currentProjectTab = 'renders';
    await route();
  });

  onForm('project-transcript-form', async (form, data) => {
    await api(`/assets/${currentProjectId}/transcript`, 'POST', data);
    toast('Transcript aligned and saved to project.');
    await route();
  });
}

// Global project actions interceptor
async function handleProjectAction(action, el) {
  const id = el.dataset.id;
  switch (action) {
    case 'open-project':
      setProjectLocation(id, 'overview');
      location.hash = `projects/${id}`;
      return route();

    case 'project-tab':
      currentProjectTab = el.dataset.tab;
      location.hash = `projects/${currentProjectId}/${currentProjectTab}`;
      return route(false);

    case 'rename-project':
      modal(
        'Rename Project',
        `
        <form id="rename-project-form" data-id="${id}">
          <div class="form-row">
            <label for="new-project-title">Project Title</label>
            <input id="new-project-title" name="title" required value="${esc(state.allProjects?.find(p => p.id === id)?.title || projectData?.title || '')}">
          </div>
          <div class="dialog-actions">
            <button class="button primary" type="submit">Save Title</button>
          </div>
        </form>
        `
      );
      onForm('rename-project-form', async (form, data) => {
        await api(`/projects/${id}`, 'PATCH', { title: data.get('title') });
        $('#dialog').close();
        toast('Project renamed.');
        await route();
      });
      return;

    case 'delete-project':
      if (confirm('Are you sure you want to delete this project and its isolated storage? This cannot be undone.')) {
        await api(`/projects/${id}`, 'DELETE');
        toast('Project deleted.');
        location.hash = 'projects';
        return route();
      }
      return;

    case 'seek-project-media':
      const pPlayer = $('#workspace-source-player');
      if (pPlayer) {
        pPlayer.currentTime = Number(el.dataset.time);
        pPlayer.play();
      }
      return;

    case 'launch-preset':
      presetSettings(el.dataset.preset);
      return;

    case 'filter-candidates-run':
      currentProjectTab = 'candidates';
      location.hash = `projects/${currentProjectId}/candidates`;
      return route(false);

    case 'preview-source-clip':
      const player = $('#workspace-source-player');
      const start = Number(el.dataset.start);
      if (player) {
        player.currentTime = start;
        player.play();
      } else {
        modal('Source Preview', `<video class="media-player" controls autoplay src="/api/projects/${currentProjectId}/media#t=${start}"></video>`);
      }
      return;

    case 'trigger-render-modal':
      openRenderTriggerModal(id, el.dataset.title);
      return;

    case 'play-rendered-modal':
      openRenderPreviewModal(id);
      return;

    case 'rename-render':
      modal(
        'Rename Rendered Clip',
        `
        <form id="rename-render-form" data-id="${id}">
          <div class="form-row">
            <label for="new-render-title">Clip Title</label>
            <input id="new-render-title" name="title" required value="${esc(projectRenders?.find(r => r.id === id)?.title || '')}">
          </div>
          <div class="dialog-actions">
            <button class="button primary" type="submit">Save Title</button>
          </div>
        </form>
        `
      );
      onForm('rename-render-form', async (form, data) => {
        await api(`/projects/${currentProjectId}/renders/${id}`, 'PATCH', { title: data.get('title') });
        $('#dialog').close();
        toast('Rendered clip renamed.');
        await route();
      });
      return;

    case 'delete-render':
      if (confirm('Delete this rendered output file?')) {
        await api(`/projects/${currentProjectId}/renders/${id}`, 'DELETE');
        toast('Rendered clip deleted.');
        await route();
      }
      return;

    case 'generate-project-copies':
      const cand = projectCandidates[0];
      if (cand) {
        await api(`/clips/${cand.clip_id || cand.id}/remix`, 'POST');
        toast('Platform drafts generated.');
        await route();
      }
      return;
  }
}

// Hook search & filter inputs
document.addEventListener('input', e => {
  if (e.target.id === 'proj-search') {
    projectSearch = e.target.value;
    route(false);
  }
});

document.addEventListener('change', e => {
  if (e.target.id === 'proj-status-filter') {
    projectStatusFilter = e.target.value;
    route(false);
  }
  if (e.target.id === 'proj-sort-order') {
    projectSortOrder = e.target.value;
    route(false);
  }
});

if (typeof window !== 'undefined') {
  window.projectsDashboard = projectsDashboard;
  window.projectWorkspaceView = projectWorkspaceView;
  window.bindProjectForms = bindProjectForms;
  window.handleProjectAction = handleProjectAction;
}
