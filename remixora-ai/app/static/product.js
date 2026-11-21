'use strict';

function libraryHome(){
  const exported = (state.variants||[]).filter(v=>v.status==='rendered').length + (state.clips||[]).filter(c=>c.render_status==='rendered').length;
  return pageHead('Library','',`<a class="button primary" href="#ingest" data-action="new-workflow">Import source</a>`) + `
  <div class="library-summary">
    <span><strong>${state.assets?.length||0}</strong> sources</span>
    <span><strong>${state.clips?.length||0}</strong> clips</span>
    <span><strong>${exported}</strong> exports</span>
  </div>
  ${(state.assets&&state.assets.length)?`
  <div class="library-grid">
    ${state.assets.map(a=>`
      <article class="panel library-card">
        <div class="library-preview">
          ${a.media_kind==='video'?`<video preload="metadata" muted src="/api/assets/${a.id}/media#t=0.1"></video>`:`<div class="audio-art">${icon('remix')}<span>Audio recording</span></div>`}
          <span class="duration">${stamp(a.duration)}</span>
        </div>
        <div class="library-card-body">
          <h2 title="${esc(a.title||a.filename)}">${esc(a.title||a.filename)}</h2>
          <div class="library-meta">${badge(a.status)}<small>${esc((a.created_at||'').slice(0,10))}</small></div>
          <div class="actions">
            <button class="button primary small" data-action="open-smart" data-id="${a.id}">Smart Cuts</button>
            <a class="button ghost small" href="#projects/${a.id}">Project</a>
          </div>
        </div>
      </article>
    `).join('')}
  </div>` : `
  <section class="panel empty">
    <h2>Your library is empty</h2>
    <a class="button primary" href="#ingest">Import your first recording</a>
  </section>`}
  ${typeof smartHistory === 'function' ? smartHistory() : ''}
  `;
}

window.createStudio = function(){
  const flow = (state.workflows||[]).find(f => f.id === workflowId);
  if (flow && !['complete','failed'].includes(flow.stage)) {
    return cleanWorkspace(flow);
  }
  return pageHead('Import Source', 'Upload video/audio recordings or paste YouTube links to create a new project.') + `
  <section class="panel import-panel section-gap">
    <div class="tabs" role="tablist" aria-label="Source type">
      <button class="tab ${inputMode==='youtube'?'active':''}" role="tab" aria-selected="${inputMode==='youtube'}" data-action="source-mode" data-mode="youtube">▷ YouTube link</button>
      <button class="tab ${inputMode==='upload'?'active':''}" role="tab" aria-selected="${inputMode==='upload'}" data-action="source-mode" data-mode="upload">${icon('upload')} Upload file</button>
    </div>
    <form id="source-import">
      ${inputMode==='youtube' ? `
        <div class="form-row">
          <label for="source-url">YouTube Video URL</label>
          <input id="source-url" name="url" type="text" inputmode="url" placeholder="https://www.youtube.com/watch?v=…" required autocomplete="off">
          <small class="muted">Single video, Shorts or youtu.be link. Automatic subtitles are imported when available.</small>
        </div>
      ` : `
        <div class="drop-zone section-gap" style="text-align:center;padding:28px 20px;">
          <div class="empty-icon">${icon('upload')}</div>
          <h2 style="font-size:1.15rem;margin-bottom:6px;">Select a Media Recording</h2>
          <p class="muted" style="margin-bottom:14px;">Supported formats: MP4, MOV, MKV, WebM, MP3, M4A, WAV (up to ${state.status?.max_upload_mb||150} MB)</p>
          <input name="media" type="file" accept=".mp4,.mov,.mkv,.webm,.mp3,.m4a,.wav" aria-label="Recording" required>
        </div>
        <div class="form-row">
          <label for="source-subtitles">Subtitles / Captions <span class="muted">(optional SRT or VTT)</span></label>
          <input id="source-subtitles" type="file" name="transcript" accept=".srt,.vtt">
          <small class="muted">Providing timestamped captions allows exact boundary alignment.</small>
        </div>
      `}
      <div style="margin:16px 0;">
        <label class="check">
          <input type="checkbox" name="rights" required checked> I own this media or have permission to download and repurpose it.
        </label>
      </div>
      <button class="button primary" type="submit">${icon('spark')} Import & Create Project</button>
      <progress id="import-progress" max="100" value="0" hidden style="width:100%;margin-top:14px;"></progress>
    </form>
  </section>
  ${typeof workflowHistory === 'function' ? workflowHistory() : ''}
  `;
};

function cleanWorkspace(flow){
  const asset = (state.assets||[]).find(a => a.id === flow.asset_id);
  const messages = {
    queued: 'Waiting to start',
    importing: 'Importing media & metadata',
    aligning: 'Preparing transcript & boundaries',
    scouting: 'Analyzing high-impact moments',
    drafting: 'Generating platform drafts',
    rendering: 'Rendering video exports',
    complete: 'Project ready',
    failed: 'Import needs attention',
    needs_transcript: 'Matching captions required'
  };

  return pageHead(flow.filename ? esc(flow.filename) : 'Source Ingestion', '', `<button class="button ghost" data-action="new-workflow">New Import</button>`) + `
  <section class="panel import-panel section-gap">
    <div class="panel-head">
      <div>
        <h2>${messages[flow.stage] || esc(flow.stage || 'Processing')}</h2>
        <p class="muted">Background durable workflow is running</p>
      </div>
      ${badge(flow.stage || 'queued')}
    </div>
    <progress value="${flow.progress || 0}" max="100" aria-label="Import progress" style="width:100%;height:10px;"></progress>
    ${flow.error ? `
      <p class="notice error section-gap">${esc(flow.error)}</p>
      <button class="button ghost section-gap" data-action="resume-workflow" data-id="${flow.id}">Retry Import</button>
    ` : ''}
    ${flow.stage === 'needs_transcript' ? `
      <form id="workflow-transcript" class="section-gap">
        <label for="workflow-subtitles">Upload Matching SRT / VTT</label>
        <input id="workflow-subtitles" name="transcript" type="file" accept=".srt,.vtt" required>
        <button class="button primary section-gap" type="submit">Save transcript & Continue</button>
      </form>
    ` : ''}
    ${asset ? `
      <div class="actions section-gap">
        <a class="button primary" href="#projects/${asset.id}">Open in Project Workspace</a>
        <button class="button ghost" data-action="open-smart" data-id="${asset.id}">Open Smart Cuts</button>
      </div>
    ` : ''}
  </section>
  ${typeof workflowHistory === 'function' ? workflowHistory() : ''}
  `;
}

function bindProductForms(){
  onForm('source-import', async (form, data) => {
    if (inputMode === 'youtube') {
      const r = await api('/youtube', 'POST', {
        url: data.get('url'),
        rights_confirmed: data.has('rights'),
        import_only: true,
        auto_render: false
      });
      selectWorkflow(r.id);
      toast('YouTube source import queued. Creating project…');
      await route();
    } else {
      const file = data.get('media');
      if (!file || !file.size) throw Error('Please select a media file to upload.');
      if (file.size > (state.status?.max_upload_mb || 150) * 1024 * 1024) {
        throw Error('This file exceeds the upload limit.');
      }
      const body = new FormData();
      body.set('media', file);
      if (data.get('transcript')?.size) body.set('transcript', data.get('transcript'));
      
      const prog = $('#import-progress');
      if (prog) prog.hidden = false;

      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/projects/import');
        xhr.upload.onprogress = e => {
          if (e.lengthComputable && prog) prog.value = (e.loaded / e.total) * 100;
        };
        xhr.onload = () => {
          try {
            const r = JSON.parse(xhr.responseText);
            xhr.status < 300 ? resolve(r) : reject(Error(r.detail || 'Upload failed'));
          } catch {
            reject(Error('Could not parse server response.'));
          }
        };
        xhr.onerror = () => reject(Error('Upload interrupted. Try again.'));
        xhr.send(body);
      });

      const pid = result.project_id || result.asset_id;
      toast(result.duplicate ? 'Existing project opened.' : 'Project created! Opening workspace…');
      location.hash = `projects/${pid}`;
      await route();
    }
  });
}

function studioSettings(){
  const s = state.status || {};
  const p = state.profile?.profile || {};

  return pageHead('Studio Settings', 'Manage workspace preferences, storage utilization, and processing engine status.',
    `<a href="/api/export" class="button ghost">${icon('download')} Export Studio Data</a>`
  ) + `
  <div class="grid-two">
    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Processing Engine</h2>
          <p>Local media rendering & analysis tools</p>
        </div>
        ${icon('health')}
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Media Engine (FFmpeg & FFprobe)</strong>
          <small>${s.ffmpeg && s.ffprobe ? 'Detected & Ready for high-definition rendering' : 'Required for video rendering'}</small>
        </div>
        ${badge(s.ffmpeg && s.ffprobe ? 'ready' : 'missing')}
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Background Job Processor</strong>
          <small>${s.worker_alive ? 'Active durable background queue' : 'Worker idle'}</small>
        </div>
        ${badge(s.worker_alive ? 'active' : 'idle')}
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Speech & Captioning Engine</strong>
          <small>${s.transcription_backend === 'none' ? 'Subtitle import mode (SRT / VTT)' : 'Local speech model detected'}</small>
        </div>
        ${badge(s.transcription_backend === 'none' ? 'srt_mode' : 'local_speech')}
      </div>
    </section>

    <section class="panel">
      <div class="panel-head">
        <div>
          <h2>Workspace & Storage</h2>
          <p>Local disk space and project assets</p>
        </div>
        ${icon('chart')}
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Disk Storage Used</strong>
          <small>${size(s.storage_bytes || 0)} used by media & renders</small>
        </div>
        <span class="pill subtle">${size(s.free_bytes || 0)} free</span>
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Studio Projects</strong>
          <small>${state.assets?.length || 0} active project source(s)</small>
        </div>
        <span class="pill subtle">${state.clips?.length || 0} moment(s)</span>
      </div>
      <div class="project-row">
        <div class="source-info">
          <strong>Workspace Mode</strong>
          <small>Local Single-Tenant Studio</small>
        </div>
        ${badge('secure')}
      </div>
    </section>
  </div>

  <section class="panel section-gap">
    <div class="panel-head">
      <div>
        <h2>Creative Preferences</h2>
        <p>Default editorial settings applied to newly discovered moments</p>
      </div>
      <a href="#brand" class="button ghost small">${icon('brand')} Edit Brand DNA</a>
    </div>
    <div class="grid-three">
      <div class="health-card">
        <h3>Target Audience</h3>
        <p class="purple">${esc(p.audience || 'General Video Audience')}</p>
        <p class="muted">Guides hook suggestions</p>
      </div>
      <div class="health-card">
        <h3>Tone of Voice</h3>
        <p class="purple">${esc(p.tone || 'Engaging & Authentic')}</p>
        <p class="muted">Applied to multi-platform caption drafts</p>
      </div>
      <div class="health-card">
        <h3>Default Video Aspect</h3>
        <p class="purple">9:16 Vertical (Shorts/Reels)</p>
        <p class="muted">Optimized for mobile platforms</p>
      </div>
    </div>
  </section>
  `;
}

window.libraryHome = libraryHome;
window.studioSettings = studioSettings;

if (typeof views !== 'undefined') {
  if (window.projectsDashboard) views.projects = window.projectsDashboard;
  if (window.projectsDashboard) views.home = window.projectsDashboard;
  if (window.smartCuts) views.smart = window.smartCuts;
  if (window.remixStudio) views.remix = window.remixStudio;
  views.health = studioSettings;
}

if (typeof route === 'function') {
  route();
}
