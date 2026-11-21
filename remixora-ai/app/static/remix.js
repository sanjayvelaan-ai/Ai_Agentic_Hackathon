'use strict';

let remixSelectedProject = localStorage.getItem('remixora-remix-project') || '';

function saveRemixLocation(){
  localStorage.setItem('remixora-remix-project', remixSelectedProject);
  localStorage.setItem('remixora-clip', clipId);
}

function remixStudio(){
  const projects = state.assets || [];
  
  // Step 1: Main Project Selection
  if (!remixSelectedProject) {
    return remixProjectPicker(projects);
  }

  const project = projects.find(p => p.id === remixSelectedProject);
  if (!project) {
    remixSelectedProject = '';
    saveRemixLocation();
    return remixProjectPicker(projects);
  }

  const projectClips = (state.clips || []).filter(c => c.asset_id === project.id || c.project_id === project.id);

  // Step 2: Sub-group / Moment Selection within the chosen Project
  if (!clipId || !projectClips.some(c => c.id === clipId)) {
    return remixClipPicker(project, projectClips);
  }

  // Step 3: Edit and Repurpose the Selected Clip
  const clip = projectClips.find(c => c.id === clipId);
  return remixEditorView(project, clip);
}

function remixProjectPicker(projects){
  return pageHead('Remix Studio · Step 1: Select Main Project', 'Choose the project you want to repurpose into multi-platform drafts and vertical video remixes.') + `
  <section class="panel section-gap">
    <div class="panel-head">
      <div>
        <h2>Select a Project to Remix</h2>
        <p>Each project contains discovered moments ready for copywriting and video rendering.</p>
      </div>
      <a href="#ingest" class="button primary small" data-action="new-workflow">${icon('upload')} Import New Source</a>
    </div>

    ${projects.length ? `
    <div class="projects-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(310px,1fr));gap:18px;">
      ${projects.map(p => {
        const pClips = (state.clips || []).filter(c => c.asset_id === p.id || c.project_id === p.id);
        const pVariants = (state.variants || []).filter(v => pClips.some(c => c.id === v.clip_id));
        return `
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
            <div style="display:flex;gap:8px;align-items:center;font-size:0.78rem;color:var(--muted);margin-bottom:4px;">
              ${badge(p.status)}
              <span>${esc((p.created_at||'').slice(0,10))}</span>
            </div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px;">
              <span class="pill subtle">${pClips.length} discovered moment${pClips.length===1?'':'s'}</span>
              <span class="pill green">${pVariants.length} remix export${pVariants.length===1?'':'s'}</span>
            </div>
          </div>
          ${pClips.length ? `
            <button class="button primary small" data-action="select-remix-project" data-id="${p.id}" style="margin-top:auto;">
              Select Project & View Moments (${pClips.length}) →
            </button>
          ` : `
            <div class="actions" style="margin-top:auto;">
              <button class="button ghost small" data-action="open-smart" data-id="${p.id}">
                Run Smart Cuts First
              </button>
            </div>
          `}
        </article>`;
      }).join('')}
    </div>
    ` : empty('No projects found', 'Upload a video or submit a YouTube link to get started.', '#ingest', 'Import a Source')}
  </section>
  `;
}

function remixClipPicker(project, clips){
  return pageHead('Remix Studio · Step 2: Select Moment', 'Choose a discovered clip moment to edit captions and render branded video exports.') + `
  <section class="panel section-gap" style="display:flex;align-items:center;justify-content:space-between;gap:16px;background:#181926;border:1px solid var(--line);border-radius:12px;padding:16px 20px;">
    <div style="display:flex;align-items:center;gap:16px;">
      <div style="width:72px;height:48px;border-radius:6px;overflow:hidden;background:#11121d;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
        <img src="/api/projects/${project.id}/thumbnail" alt="" style="width:100%;height:100%;object-fit:cover;" onerror="this.style.display='none'">
      </div>
      <div>
        <span class="eyebrow" style="margin-bottom:2px;">SELECTED MAIN PROJECT</span>
        <h2 style="font-size:1.15rem;margin:0 0 2px 0;">${esc(project.title || project.filename)}</h2>
        <small class="muted">${stamp(project.duration)} · ${project.media_kind || 'video'} · ${clips.length} moment(s) available</small>
      </div>
    </div>
    <div class="actions">
      <button class="button ghost small" data-action="switch-remix-project">⇄ Switch Project</button>
      <a class="button ghost small" href="#projects/${project.id}">Open Project Workspace</a>
    </div>
  </section>

  <section class="panel section-gap">
    <div class="panel-head">
      <div>
        <h2>Select a Discovered Moment to Edit</h2>
        <p>Pick a moment to create 9 platform drafts (Instagram, YouTube, LinkedIn) and render branded vertical video.</p>
      </div>
    </div>

    ${clips.length ? `
    <div class="grid-three">
      ${clips.map((c, i) => {
        const cVariants = (state.variants || []).filter(v => v.clip_id === c.id);
        const cCopies = (state.copies || []).filter(cp => cp.clip_id === c.id);
        return `
        <article class="panel clip-card" style="background:#151622;border:1px solid var(--line);border-radius:12px;display:flex;flex-direction:column;">
          <div class="clip-visual" style="height:90px;background:linear-gradient(135deg,#231c38,#161826);border-radius:8px;padding:12px;display:flex;flex-direction:column;justify-content:space-between;">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span class="pill">${esc(c.suggested_angle || 'Highlight')}</span>
              <span style="font-size:0.78rem;font-weight:600;color:#91d6c1;">Score ${(Number(c.score||0)).toFixed(1)}/5</span>
            </div>
            <span class="clip-time" style="font-size:0.8rem;color:#d1cfde;">${stamp(c.start)} – ${stamp(c.end)} · ${Math.round(c.end - c.start)}s</span>
          </div>
          <div class="clip-body" style="padding:14px 4px 4px;display:flex;flex-direction:column;flex:1;">
            <h3 style="font-size:1.02rem;line-height:1.3;margin-bottom:8px;">${esc(c.title)}</h3>
            <p style="font-size:0.84rem;color:var(--muted);line-height:1.5;margin-bottom:12px;">${esc(c.reason || '')}</p>
            ${c.quote ? `<blockquote style="font-size:0.8rem;margin:0 0 14px 0;padding-left:10px;border-left:2px solid var(--purple);color:#aaa4bc;line-height:1.5;">${esc(c.quote.slice(0, 110))}${c.quote.length>110?'…':''}</blockquote>` : ''}
            
            <div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;">
              <span class="pill subtle">${cCopies.length} copy draft${cCopies.length===1?'':'s'}</span>
              <span class="pill ${cVariants.some(v=>v.status==='rendered')?'green':'subtle'}">${cVariants.filter(v=>v.status==='rendered').length} render${cVariants.filter(v=>v.status==='rendered').length===1?'':'s'}</span>
            </div>

            <button class="button primary small" data-action="select-remix-clip" data-id="${c.id}" style="margin-top:auto;width:100%;">
              ${icon('remix')} Edit & Remix This Moment →
            </button>
          </div>
        </article>`;
      }).join('')}
    </div>
    ` : `
    <div class="empty">
      <div class="empty-icon">${icon('spark')}</div>
      <h3>No moments found in this project</h3>
      <p>Run Smart Cuts or AI Presets to discover high-impact highlights and talking clips first.</p>
      <button class="button primary small" data-action="open-smart" data-id="${project.id}">Run Smart Cuts on this Project</button>
    </div>
    `}
  </section>
  `;
}

function remixEditorView(project, clip){
  const copies = (state.copies || []).filter(c => c.clip_id === clip.id && c.angle === angle)
    .sort((a,b) => Object.keys(platforms).indexOf(a.platform) - Object.keys(platforms).indexOf(b.platform));
  const variants = (state.variants || []).filter(v => v.clip_id === clip.id);
  const totalDrafts = (state.copies || []).filter(c => c.clip_id === clip.id).length;

  return pageHead('Remix Studio', '') + `
  <section class="panel section-gap" style="display:flex;align-items:center;justify-content:space-between;gap:16px;background:#181926;border:1px solid var(--line);border-radius:12px;padding:14px 20px;">
    <div style="display:flex;align-items:center;gap:14px;">
      <button class="button ghost small" data-action="back-to-remix-clips" title="Back to project moments">← All Moments</button>
      <div style="border-left:1px solid var(--line);padding-left:14px;">
        <span class="eyebrow" style="margin-bottom:1px;">ACTIVE MOMENT</span>
        <h2 style="font-size:1.15rem;margin:0;">${esc(clip.title)}</h2>
        <small class="muted">${stamp(clip.start)} – ${stamp(clip.end)} · In project: <strong>${esc(project.title || project.filename)}</strong></small>
      </div>
    </div>
    <div class="actions">
      <button class="button ghost small" data-action="switch-remix-project">⇄ Switch Project</button>
    </div>
  </section>

  <div class="notice purple-notice section-gap">
    <strong>Source Excerpt:</strong> ${stamp(clip.start)}–${stamp(clip.end)}
    <details style="margin-top:6px;" open>
      <summary style="cursor:pointer;font-weight:550;">Read source transcript quote</summary>
      <blockquote style="margin-top:6px;">${esc(clip.quote || 'No transcript text available for this segment.')}</blockquote>
    </details>
  </div>

  <div class="panel-head section-gap">
    <div>
      <h2>Multi-Platform Copywriting Studio</h2>
      <p>Switch editorial angle to see tailored copy for Instagram, YouTube, and LinkedIn.</p>
    </div>
    <div class="tabs" role="tablist" aria-label="Editorial angle">
      ${angles.map(a => `<button role="tab" aria-selected="${a===angle}" class="tab ${a===angle?'active':''}" data-action="angle" data-angle="${a}">${a}</button>`).join('')}
    </div>
  </div>

  ${angle === 'Challenge It' ? '<p class="muted" style="margin-bottom:16px;">A reflective, thought-provoking hook when the source prompts debate.</p>' : ''}

  ${copies.length ? `
    <div class="grid-three">
      ${copies.map(copyCard).join('')}
    </div>
  ` : `
    <section class="panel section-gap" style="text-align:center;padding:36px 20px;">
      <div class="empty-icon">${icon('spark')}</div>
      <h3>Generate 9 Platform Drafts</h3>
      <p class="muted">Creates 3 editorial angles across Instagram Reel, YouTube Short, and LinkedIn.</p>
      <div class="actions" style="justify-content:center;margin-top:16px;">
        <button class="button primary" data-action="generate">
          ${icon('spark')} Create Nine Platform Drafts
        </button>
      </div>
    </section>
  `}

  <section class="panel section-gap">
    <div class="panel-head">
      <div>
        <h2>Put Your Angle on Screen</h2>
        <p>Render high-definition 720 × 1280 MP4 with opening hook headline and burned-in captions.</p>
      </div>
      ${icon('film')}
    </div>

    <form id="render-form">
      <div class="grid-two">
        <div class="form-row">
          <label for="headline">Opening Headline Overlay (Hook)</label>
          <input id="headline" name="headline" maxlength="120" required value="${esc(angle + ': ' + clip.title).slice(0, 120)}">
        </div>
        <div class="form-row">
          <label for="render-angle">Editorial Angle</label>
          <select id="render-angle" name="angle">
            ${angles.map(a => `<option ${a===angle?'selected':''}>${a}</option>`).join('')}
          </select>
        </div>
      </div>
      <div class="grid-two">
        <div class="form-row">
          <label for="render-aspect">Aspect Ratio</label>
          <select id="render-aspect" name="aspect_ratio">
            <option value="9:16" selected>9:16 Vertical (Shorts, Reels, TikTok)</option>
            <option value="1:1">1:1 Square (Feed, LinkedIn)</option>
            <option value="16:9">16:9 Landscape (YouTube, Desktop)</option>
          </select>
        </div>
        <div class="form-row" style="display:flex;align-items:flex-end;">
          <label class="check" style="margin-bottom:12px;">
            <input type="checkbox" name="subtitles" checked> Burn in source-aligned subtitles
          </label>
        </div>
      </div>
      <div class="actions" style="margin-top:10px;">
        <button class="button primary" type="submit">${icon('film')} Render This Video Remix</button>
        <small class="muted">One export at a time. FFmpeg rendering runs safely in the background.</small>
      </div>
    </form>

    <div class="section-gap" id="variant-list">
      ${variants.length ? `
        <div class="panel-head"><h2>Rendered Video Remixes</h2><span class="pill subtle">${variants.length} exports</span></div>
        ${variants.map(variantRow).join('')}
      ` : '<p class="muted section-gap">No video remixes rendered for this moment yet. Click "Render This Video Remix" above to create your first cut.</p>'}
    </div>
  </section>
  `;
}

async function handleRemixAction(action, el){
  switch(action){
    case 'select-remix-project':
      remixSelectedProject = el.dataset.id;
      clipId = '';
      saveRemixLocation();
      return route(false);
    case 'switch-remix-project':
      remixSelectedProject = '';
      clipId = '';
      saveRemixLocation();
      return route(false);
    case 'select-remix-clip':
      clipId = el.dataset.id;
      saveRemixLocation();
      return route(false);
    case 'back-to-remix-clips':
      clipId = '';
      saveRemixLocation();
      return route(false);
  }
}

if (typeof window !== 'undefined') {
  window.remixStudio = remixStudio;
  window.handleRemixAction = handleRemixAction;
}
