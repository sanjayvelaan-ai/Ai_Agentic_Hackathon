'use strict';
let smartRun=localStorage.getItem('remixora-preset-run')||'',
    smartPreset='best_highlights',
    smartSearch='',
    smartCategory='All',
    smartSelected=new Set(),
    smartData=[],
    smartBusy=false,
    smartSelectedProject=localStorage.getItem('remixora-smart-project')||'';

function saveSmartLocation(){
  localStorage.setItem('remixora-source', sourceId);
  localStorage.setItem('remixora-preset-run', smartRun);
  localStorage.setItem('remixora-smart-project', smartSelectedProject);
}

function presetIcon(p){
  const d={
    funny_moments:'M4 5h16v12H9l-5 4zM8 9h1m6 0h1M8 12q4 5 8 0',
    reactions:'M2 12h4l3-8 5 16 3-8h5',
    fail_moments:'M6 6l12 12M18 6 6 18M3 3h18v18H3z',
    clutch_moments:'M7 3h10v7a5 5 0 0 1-10 0zM7 5H3v4l5 3m9-7h4v4l-5 3m-4 3v5m-4 1h8',
    funny_clips:'M3 4h13v10H7l-4 4zM18 8h3v13l-4-4h-6',
    best_highlights:'M5 3h14v18l-7-5-7 5z',
    best_talking_moments:'M9 3h6v11H9zM5 10v3a7 7 0 0 0 14 0v-3m-7 10v3m-4 0h8',
    motivation:'M12 20 3 11a5 5 0 0 1 9-5 5 5 0 0 1 9 5z',
    key_takeaways:'M9 18h6m-6 3h6M8 15a7 7 0 1 1 8 0v1H8z',
    shorts_reels:'M7 2h10v20H7zM10 8l5 4-5 4z',
    cinematic:'M3 5h18v14H3zM8 5v14m8-14v14M3 9h5m8 0h5M3 15h5m8 0h5',
    remove_silence:'M8 8l12 12M8 16 20 4M3 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8m0 10a4 4 0 1 0 0 8 4 4 0 0 0 0-8'
  }[p];
  return `<span class="icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d||'M12 2v20'}"/></svg></span>`;
}

function smartProjectPicker(){
  const projects = state.assets || [];
  return pageHead('Smart Cuts · Select Project', 'Choose which video or recording you want to analyze with AI Presets.') + `
  <section class="panel section-gap">
    <div class="panel-head">
      <div>
        <h2>Step 1: Choose a Project to Analyze</h2>
        <p>Smart Cuts scans video and transcripts for highlights, viral hooks, takeaways, or silence removal.</p>
      </div>
      <a href="#ingest" class="button primary small" data-action="new-workflow">${icon('upload')} Import New Source</a>
    </div>

    ${projects.length ? `
    <div class="projects-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:18px;">
      ${projects.map(p => `
        <article class="panel project-card" style="padding:16px;display:flex;flex-direction:column;gap:12px;border:1px solid var(--line);border-radius:12px;background:#181926;transition:all .2s;">
          <div style="position:relative;width:100%;height:155px;border-radius:8px;overflow:hidden;background:#10111a;display:flex;align-items:center;justify-content:center;">
            <img src="/api/projects/${p.id}/thumbnail" alt="${esc(p.title || p.filename)}" style="width:100%;height:100%;object-fit:cover;" onerror="this.onerror=null;this.style.display='none';if(this.nextElementSibling)this.nextElementSibling.style.display='flex';">
            <div class="project-thumb-placeholder" style="display:none;width:100%;height:100%;align-items:center;justify-content:center;">
              ${icon(p.media_kind==='audio'?'brand':'film')}
            </div>
            <span style="position:absolute;bottom:8px;right:8px;background:rgba(0,0,0,0.78);color:#fff;padding:2px 7px;border-radius:4px;font-size:0.75rem;font-weight:600;">${stamp(p.duration)}</span>
          </div>
          <div>
            <h3 style="font-size:1.05rem;font-weight:600;margin-bottom:6px;line-height:1.3;" title="${esc(p.title || p.filename)}">${esc(p.title || p.filename)}</h3>
            <div style="display:flex;gap:8px;align-items:center;font-size:0.78rem;color:var(--muted);">${badge(p.status)}<span>${esc((p.created_at||'').slice(0,10))}</span></div>
          </div>
          <button class="button primary small" data-action="select-smart-project" data-id="${p.id}" style="margin-top:auto;">
            Select Project for Smart Cuts →
          </button>
        </article>
      `).join('')}
    </div>
    ` : empty('No projects in library', 'Upload a video or YouTube link to start using Smart Cuts.', '#ingest', 'Import a Source')}
  </section>
  `;
}

async function smartCuts(){
  const asset = state.assets?.find(a => a.id === smartSelectedProject);
  if (!smartSelectedProject || !asset) {
    return smartProjectPicker();
  }

  sourceId = smartSelectedProject;
  saveSmartLocation();

  const run = state['preset-runs']?.find(r => r.id === smartRun && (r.asset_id === sourceId || r.project_id === sourceId));
  if (run) {
    try {
      smartData = await api(`/preset-runs/${run.id}/candidates`);
    } catch {
      smartData = [];
    }
    return smartResults(run, asset);
  }

  return pageHead('Smart Cuts', 'Choose a preset to run algorithmic video analysis.') + `
  <section class="panel section-gap" style="display:flex;align-items:center;justify-content:space-between;gap:16px;background:#181926;border:1px solid var(--line);border-radius:12px;padding:16px 20px;">
    <div style="display:flex;align-items:center;gap:16px;">
      <div style="width:72px;height:48px;border-radius:6px;overflow:hidden;background:#11121d;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <img src="/api/projects/${asset.id}/thumbnail" alt="" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">
      </div>
      <div>
        <span class="eyebrow" style="margin-bottom:2px;">ACTIVE PROJECT</span>
        <h2 style="font-size:1.15rem;margin:0 0 2px 0;">${esc(asset.title || asset.filename)}</h2>
        <small class="muted">${stamp(asset.duration)} · ${asset.media_kind || 'video'} · ${badge(asset.status)}</small>
      </div>
    </div>
    <div class="actions">
      <button class="button ghost small" data-action="switch-smart-project">⇄ Switch Project</button>
      <a class="button ghost small" href="#projects/${asset.id}">Open in Project Workspace</a>
    </div>
  </section>

  <div class="smart-toolbar section-gap">
    <label class="search-box">${icon('scout')}<input id="preset-search" aria-label="Search presets" placeholder="Search presets…" value="${esc(smartSearch)}"></label>
    <select id="preset-category" aria-label="Preset category">
      ${['All','Entertainment / Gaming','Creator / Podcast / Learning','Visual / Utility'].map(v=>`<option ${v===smartCategory?'selected':''}>${v}</option>`).join('')}
    </select>
  </div>

  <div class="preset-grid">
    ${(state.presets||[]).map(p=>{
      const unavailable = p.video_only && asset.media_kind === 'audio';
      return `<button class="preset-card" data-action="preset-settings" data-id="${p.id}" data-category="${esc(p.category)}" data-search="${esc((p.name+' '+p.description).toLowerCase())}" ${unavailable?'disabled':''}>
        <div class="preset-icon">${presetIcon(p.id)}</div>
        <h2>${esc(p.name)}</h2>
        <p>${esc(p.description)}</p>
        <div class="preset-meta">
          <span>${unavailable?'Video required':p.video_only?'Video':p.id==='remove_silence'?'Audio / video':'Speech'}</span>
          <span>${esc(p.cost)}</span>
        </div>
      </button>`;
    }).join('')}
  </div>
  <p id="preset-no-results" hidden class="muted">No presets match your search.</p>
  ${smartHistory(asset)}
  `;
}

function smartHistory(asset){
  const runs = (state['preset-runs']||[]).filter(r => !asset || r.asset_id === asset.id || r.project_id === asset.id);
  return runs.length ? `
  <section class="panel section-gap">
    <div class="panel-head"><h2>Recent Analyses in this Project</h2></div>
    ${runs.slice(0,8).map(r=>`
      <div class="project-row">
        <div class="source-info">
          <strong>${esc((state.presets||[]).find(p=>p.id===r.preset_id)?.name || 'Preset Analysis')}</strong>
          <small>${esc(r.filename || '')} · ${esc((r.started_at||'').slice(0,16))}</small>
        </div>
        ${badge(r.status)}
        <button class="button ghost small" data-action="open-preset-run" data-id="${r.id}" data-asset="${r.asset_id || r.project_id}">Review Candidates</button>
      </div>
    `).join('')}
  </section>` : '';
}

function presetSettings(id){
  smartPreset = id;
  const p = (state.presets||[]).find(x=>x.id===id) || {name:'Preset Settings'};
  const silence = id === 'remove_silence';
  modal(p.name, `
  <form id="preset-settings">
    <div class="grid-two">
      ${silence ? `
      <div class="form-row"><label for="silence-db">Silence threshold (dB)</label><input id="silence-db" name="silence_db" type="number" min="-60" max="-15" value="-38"></div>
      <div class="form-row"><label for="silence-min">Minimum quiet gap (seconds)</label><input id="silence-min" name="silence_min" type="number" min=".3" max="5" step=".1" value=".8"></div>
      <div class="form-row"><label for="silence-pad">Keep padding (seconds)</label><input id="silence-pad" name="silence_padding" type="number" min="0" max="1" step=".1" value=".2"></div>
      ` : `
      <div class="form-row"><label for="preset-min">Minimum length (seconds)</label><input id="preset-min" name="min_seconds" type="number" min="8" max="90" value="15"></div>
      <div class="form-row"><label for="preset-max">Maximum length (seconds)</label><input id="preset-max" name="max_seconds" type="number" min="8" max="90" value="45"></div>
      <div class="form-row"><label for="preset-count">Clip count</label><select id="preset-count" name="count"><option value="3">Up to 3</option><option value="5">Up to 5</option><option value="10">Up to 10</option><option value="20">All eligible · max 20</option></select></div>
      <div class="form-row"><label for="preset-intensity">Selection</label><select id="preset-intensity" name="intensity"><option value="balanced">Balanced</option><option value="only_best">Only best</option><option value="find_more">Find more</option></select></div>
      <div class="form-row"><label for="context-before">Context before (seconds)</label><input id="context-before" name="context_before" type="number" min="0" max="5" value="1"></div>
      <div class="form-row"><label for="context-after">Context after (seconds)</label><input id="context-after" name="context_after" type="number" min="0" max="5" value="1"></div>
      `}
      <div class="form-row"><label for="preset-aspect">Aspect Frame</label><select id="preset-aspect" name="aspect_ratio"><option>9:16</option><option>1:1</option><option>16:9</option></select></div>
      <div class="form-row"><label for="preset-platform">Platform Hook</label><select id="preset-platform" name="platform"><option value="youtube">YouTube</option><option value="instagram">Instagram</option><option value="linkedin">LinkedIn</option></select></div>
      <div class="form-row"><label for="preset-language">Language</label><select id="preset-language" name="language"><option value="en">English</option><option value="ta">Tamil</option><option value="hi">Hindi</option><option value="es">Spanish</option></select></div>
    </div>
    <label class="check"><input type="checkbox" name="burn_subtitles" checked>Burn captions when transcript is available</label>
    ${!silence && id !== 'cinematic' ? `<label class="check"><input type="checkbox" name="use_ai" checked>AI-assisted scoring and ranking</label>` : ''}
    <div class="dialog-actions"><button class="button primary" type="submit">Analyze Source</button></div>
  </form>
  `);
  bindSmartForms();
}

function smartResults(run, asset){
  const config = JSON.parse(run.config_json || '{}'), report = JSON.parse(run.capability_report_json || '{}');
  const ready = run.status === 'ready';
  return pageHead((state.presets||[]).find(p=>p.id===run.preset_id)?.name || 'Analysis', asset?.title || asset?.filename || '', `<button class="button ghost" data-action="choose-presets">Change Preset</button>`) + `
  <div class="review-layout">
    <section class="panel source-preview">
      <video id="smart-player" controls preload="metadata" src="/api/assets/${run.asset_id || run.project_id}/media"></video>
      <div class="panel-head">
        <span>${stamp(asset?.duration||0)} · ${esc(config.aspect_ratio || '9:16')}</span>
        ${badge(run.status)}
      </div>
      ${!['ready','no_matches','unsupported','failed'].includes(run.status) ? `
        <progress value="${run.progress||0}" max="100" aria-label="Analysis progress"></progress>
        <p>${run.status==='queued'?'Waiting in queue…':'Analyzing moments with AI…'}</p>
      ` : ''}
      ${report.message && !ready ? `<p class="muted">${esc(report.message)}</p>` : ''}
      ${run.error ? `<div class="notice error">${esc(run.error)}</div><button class="button ghost section-gap" data-action="preset-settings" data-id="${run.preset_id}">Adjust & retry</button>` : ''}
      ${report.edl ? `
        <h3>Timeline edit</h3>
        <p>${Number(report.removed_seconds||0).toFixed(1)}s removed · ${Number(report.retained_seconds||0).toFixed(1)}s retained</p>
        <details><summary>${report.edl.length} retained ranges</summary><ol class="edl-list">${report.edl.map(x=>`<li>${stamp(x.start)} – ${stamp(x.end)}</li>`).join('')}</ol></details>
      ` : ''}
      <div class="actions section-gap">
        <button class="button ghost small" data-action="switch-smart-project">⇄ Switch Project</button>
      </div>
    </section>

    <section class="review-list">
      ${ready ? `
        <div class="selection-toolbar">
          <span>${smartData.length} candidates discovered</span>
          <button class="button ghost small" data-action="select-all-presets">Select all</button>
          <button class="button primary" data-action="render-preset-selection">Render selected</button>
        </div>
      ` : ''}
      ${smartData.map((c,i)=>{
        const evidence = JSON.parse(c.evidence_json || '{}');
        const scoreBreakdown = JSON.parse(c.score_breakdown_json || '{}');
        const edl = JSON.parse(c.edl_json || '[]');
        return `
        <article class="panel result-card ${c.status==='rejected'?'rejected':''}">
          <div class="result-title">
            <label class="candidate-check">
              <input type="checkbox" class="preset-select" data-id="${c.id}" ${c.status==='rejected'?'disabled':''} ${smartSelected.has(c.id)?'checked':''} aria-label="Select candidate ${i+1}">
              <span>${String(i+1).padStart(2,'0')}</span>
            </label>
            <div>
              <h2>${esc(c.title)}</h2>
              <small>${stamp(c.start)} – ${stamp(c.end)} · ${(c.end-c.start).toFixed(1)}s</small>
            </div>
            <span class="pill">${['gemini','ollama'].includes(c.source)?'AI-assisted':c.source==='manual'?'Edited':'Local analysis'}</span>
          </div>
          <p>${esc(c.reason)}</p>
          <details>
            <summary>Evidence & score · ${Math.round((c.score||0)*100)} / 100</summary>
            <div class="score-chips">
              ${Object.entries(scoreBreakdown).map(([k,v])=>`<span>${esc(k.replaceAll('_',' '))} <strong>${Number(v).toFixed(2)}</strong></span>`).join('')}
            </div>
            ${c.quote ? `<blockquote>${esc(c.quote)}</blockquote>` : ''}
            <p class="muted">${(evidence.limitations||[]).map(esc).join(' ')}</p>
          </details>
          ${edl.length ? '' : `
            <form class="bounds-form" data-clip="${c.clip_id}">
              <label>Start (s)<input name="start" type="number" min="0" step=".01" value="${Number(c.start||0).toFixed(2)}" required></label>
              <label>End (s)<input name="end" type="number" min="0" step=".01" value="${Number(c.end||0).toFixed(2)}" required></label>
              <button class="button ghost small" type="submit">Save range</button>
            </form>
          `}
          <div class="actions section-gap">
            <button class="button ghost small" data-action="review-preset" data-id="${c.id}" data-status="${c.status==='rejected'?'proposed':'rejected'}">
              ${c.status==='rejected'?'Restore':'Reject'}
            </button>
            <button class="button ghost small" data-action="preview-preset" data-time="${c.start}">Preview source</button>
            ${c.quote ? `<button class="button ghost small" data-action="open-remix" data-id="${c.clip_id}">Write captions</button>` : ''}
            ${c.render_status==='rendered' ? `
              <a class="button primary small" href="/api/clips/${c.clip_id}/download">Download</a>
              <button class="button ghost small" data-action="preview-preset-export" data-id="${c.clip_id}">Play export</button>
            ` : ['queued','rendering'].includes(c.render_status) ? badge(c.render_status) : ''}
          </div>
          ${c.error ? `<p class="notice error">${esc(c.error)}</p>` : ''}
        </article>`;
      }).join('')}
      ${!smartData.length && ['no_matches','unsupported'].includes(run.status) ? `
        <div class="panel empty">
          <h2>${run.status==='no_matches'?'No matching moments found':'Source format not supported'}</h2>
          <button class="button ghost section-gap" data-action="choose-presets">Choose another preset</button>
        </div>
      ` : ''}
    </section>
  </div>`;
}

function filterPresets(){
  if(!$('#preset-search') && !$('#preset-category')) return;
  let visible = 0;
  $$('.preset-grid .preset-card').forEach(el => {
    const s = (el.dataset.search || '').toLowerCase();
    const c = el.dataset.category || 'All';
    const match = s.includes((smartSearch||'').toLowerCase()) && (smartCategory === 'All' || c === smartCategory);
    el.hidden = !match;
    if(!el.hidden) visible++;
  });
  if($('#preset-no-results')) $('#preset-no-results').hidden = !!visible;
}

function bindSmartForms(){
  onForm('preset-settings', async(form, data) => {
    let config = {
      preset_id: smartPreset,
      burn_subtitles: data.has('burn_subtitles'),
      use_ai: data.has('use_ai')
    };
    for(const [k, v] of data.entries()){
      if(['burn_subtitles','use_ai'].includes(k)) continue;
      config[k] = ['min_seconds','max_seconds','count','context_before','context_after','silence_db','silence_min','silence_padding'].includes(k) ? Number(v) : v;
    }
    const r = await api(`/assets/${sourceId}/presets/analyze`, 'POST', config);
    smartRun = r.id;
    saveSmartLocation();
    smartSelected.clear();
    $('#dialog').close();
    await route();
  });

  $$('.bounds-form').forEach(form => {
    form.onsubmit = async e => {
      e.preventDefault();
      const b = form.querySelector('button');
      b.disabled = true;
      try {
        const d = new FormData(form);
        await api(`/clips/${form.dataset.clip}/bounds`, 'PATCH', {start: Number(d.get('start')), end: Number(d.get('end'))});
        toast('Range saved as a new clip revision.');
        await route();
      } catch(ex) {
        toast(ex.message, true);
      } finally {
        b.disabled = false;
      }
    };
  });

  $$('.preset-select').forEach(el => el.onchange = () => el.checked ? smartSelected.add(el.dataset.id) : smartSelected.delete(el.dataset.id));
  if($('#preset-search')) $('#preset-search').oninput = e => { smartSearch = e.target.value; filterPresets(); };
  if($('#preset-category')) $('#preset-category').onchange = e => { smartCategory = e.target.value; filterPresets(); };
  filterPresets();
}

async function smartAction(action, el){
  switch(action){
    case 'select-smart-project':
      smartSelectedProject = el.dataset.id;
      sourceId = el.dataset.id;
      smartRun = '';
      localStorage.setItem('remixora-smart-project', smartSelectedProject);
      saveSmartLocation();
      return route();
    case 'switch-smart-project':
      smartSelectedProject = '';
      localStorage.removeItem('remixora-smart-project');
      return route();
    case 'review-preset':
      await api(`/preset-candidates/${el.dataset.id}`, 'PATCH', {status: el.dataset.status});
      smartSelected.delete(el.dataset.id);
      return route();
    case 'open-smart':
      smartSelectedProject = el.dataset.id;
      sourceId = el.dataset.id;
      smartRun = '';
      localStorage.setItem('remixora-smart-project', smartSelectedProject);
      saveSmartLocation();
      location.hash = 'smart';
      return route();
    case 'preset-settings':
      return presetSettings(el.dataset.id);
    case 'open-preset-run':
      smartSelectedProject = el.dataset.asset;
      sourceId = el.dataset.asset;
      smartRun = el.dataset.id;
      localStorage.setItem('remixora-smart-project', smartSelectedProject);
      saveSmartLocation();
      smartSelected.clear();
      location.hash = 'smart';
      return route();
    case 'choose-presets':
      smartRun = '';
      saveSmartLocation();
      smartSelected.clear();
      return route();
    case 'select-all-presets':
      smartData.filter(c => c.status !== 'rejected').forEach(c => smartSelected.add(c.id));
      return route(false);
    case 'preview-preset':
      $('#smart-player').currentTime = Number(el.dataset.time);
      $('#smart-player').play();
      return;
    case 'preview-preset-export':
      return modal('Export preview', `<video class="media-player" controls autoplay src="/api/clips/${el.dataset.id}/download"></video>`);
    case 'render-preset-selection':
      if(!smartSelected.size) throw Error('Select at least one candidate.');
      await api(`/preset-runs/${smartRun}/render-selected`, 'POST', {candidate_ids: [...smartSelected]});
      toast('Selected clips added to the render queue.');
      return route();
  }
}

setInterval(async () => {
  if(location.hash !== '#smart' || smartBusy || busy || document.hidden || $('#dialog')?.open || ['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) return;
  const run = state['preset-runs']?.find(x => x.id === smartRun);
  if($$('video').some(v => !v.paused)) return;
  if(['queued','analyzing'].includes(run?.status) || state.jobs?.some(j => ['queued','running'].includes(j.status))){
    smartBusy = true;
    try { await route(); } catch {} finally { smartBusy = false; }
  }
}, 3000);

if (typeof window !== 'undefined') {
  window.smartCuts = smartCuts;
  window.smartAction = smartAction;
  window.bindSmartForms = bindSmartForms;
}
