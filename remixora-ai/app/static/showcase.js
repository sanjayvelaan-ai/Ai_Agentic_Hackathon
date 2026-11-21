/**
 * REMIXORA AI — Design System Showcase View
 * Provides a live interactive gallery of tokens, colors, buttons, inputs, cards, and states.
 */
(function() {
  'use strict';

  function designSystemShowcase() {
    const esc = window.esc || (s => s);
    const icon = window.icon || (() => '');

    return `
      <div class="page-head">
        <div>
          <div class="eyebrow">DESIGN SYSTEM SPECIFICATION</div>
          <h1>Liquid Chrome × Obsidian × Pearl Lavender</h1>
          <p>Dual-theme design tokens, interactive components, typography scale, and responsive layout.</p>
        </div>
        <div class="actions">
          <a class="button primary" href="#projects">Back to Studio</a>
        </div>
      </div>

      <!-- Color Palette -->
      <section class="panel section-gap">
        <div class="panel-head">
          <div>
            <h2>Semantic Palette</h2>
            <p>Adaptive color tokens mapping Obsidian (dark) and Pearl Lavender (light).</p>
          </div>
        </div>
        <div class="grid-three">
          <div class="panel" style="background:var(--bg); border:2px solid var(--border-strong);">
            <div style="font-weight:600; margin-bottom:4px;">Background (--bg)</div>
            <div class="mono muted">Active theme background</div>
          </div>
          <div class="panel" style="background:var(--surface); border:2px solid var(--border-strong);">
            <div style="font-weight:600; margin-bottom:4px;">Surface (--surface)</div>
            <div class="mono muted">Base card & container background</div>
          </div>
          <div class="panel" style="background:var(--surface-raised); border:2px solid var(--border-strong);">
            <div style="font-weight:600; margin-bottom:4px;">Surface Raised (--surface-raised)</div>
            <div class="mono muted">Elevated cards & input fields</div>
          </div>
          <div class="panel" style="background:var(--purple-bg); border:1px solid var(--purple);">
            <div style="font-weight:600; color:var(--purple); margin-bottom:4px;">Primary Purple Accent</div>
            <div class="mono muted">--purple & --purple-bright</div>
          </div>
          <div class="panel" style="background:var(--teal-bg); border:1px solid var(--teal);">
            <div style="font-weight:600; color:var(--teal); margin-bottom:4px;">Teal Success Accent</div>
            <div class="mono muted">--teal (ready / complete)</div>
          </div>
          <div class="panel" style="background:var(--amber-bg); border:1px solid var(--amber);">
            <div style="font-weight:600; color:var(--amber); margin-bottom:4px;">Amber Warning Accent</div>
            <div class="mono muted">--amber (queued / pending)</div>
          </div>
        </div>
      </section>

      <!-- Buttons & Interactive Controls -->
      <section class="panel section-gap">
        <div class="panel-head">
          <div>
            <h2>Liquid Metal & Button Hierarchy</h2>
            <p>From primary CTA with liquid chrome reflection to ghost actions.</p>
          </div>
        </div>
        <div class="actions" style="margin-bottom:20px;">
          <button class="btn btn-primary btn-lg">Liquid Metal Large</button>
          <button class="btn btn-primary btn-md">Liquid Metal Medium</button>
          <button class="btn btn-primary btn-sm">Liquid Metal Small</button>
          <button class="btn btn-primary btn-xs">Extra Small</button>
        </div>
        <div class="actions" style="margin-bottom:20px;">
          <button class="btn btn-secondary btn-md">Secondary Raised</button>
          <button class="btn btn-ghost btn-md">Ghost Transparent</button>
          <button class="btn btn-teal btn-md">Teal Approved</button>
          <button class="btn btn-danger btn-md">Danger Action</button>
          <button class="btn btn-primary btn-md" disabled>Disabled State</button>
        </div>
        <div class="actions">
          <span class="pill">Default Pill</span>
          <span class="pill green">Approved / Ready</span>
          <span class="pill amber">Processing / Queued</span>
          <span class="pill red">Failed / Error</span>
          <span class="pill subtle">Subtle Metadata</span>
        </div>
      </section>

      <!-- Form Controls -->
      <section class="panel section-gap">
        <div class="panel-head">
          <div>
            <h2>Form & Input Components</h2>
            <p>Strict 4px vertical rhythm, high-contrast borders, and focus rings.</p>
          </div>
        </div>
        <div class="grid-two">
          <div class="form-row">
            <label for="demo-text">Standard Text Field</label>
            <input id="demo-text" type="text" placeholder="e.g. 5 AI Video Prompts That Actually Convert" value="5 AI Video Prompts That Actually Convert">
            <small>Helper text explaining the format requirements</small>
          </div>
          <div class="form-row">
            <label for="demo-select">Custom Styled Select</label>
            <select id="demo-select">
              <option>Instagram Reel (9:16 Vertical)</option>
              <option>YouTube Short (9:16 Vertical)</option>
              <option>LinkedIn Video (1:1 Square)</option>
            </select>
            <small>Uses SVG custom drop indicator and native accessibility</small>
          </div>
        </div>
        <div class="form-row">
          <label for="demo-file">File Selector with Styled Button</label>
          <input id="demo-file" type="file">
        </div>
      </section>

      <!-- Responsive Grid & Cards -->
      <section class="panel section-gap">
        <div class="panel-head">
          <div>
            <h2>Cards & Information Architecture</h2>
            <p>Responsive layout with overflow safety and subtle hover lift.</p>
          </div>
        </div>
        <div class="grid-three">
          <div class="panel">
            <h3>Standard Panel</h3>
            <p class="muted" style="margin:10px 0 16px;">Base card with semantic borders, padding, and subtle hover transition.</p>
            <button class="button small ghost">Explore</button>
          </div>
          <div class="panel panel-glass">
            <h3>Glass Elevation Panel</h3>
            <p class="muted" style="margin:10px 0 16px;">Backdrop filter with 20px blur and specular top-edge border.</p>
            <button class="button small primary">Action</button>
          </div>
          <div class="panel">
            <div class="stat-label">Discovered Moments</div>
            <div class="stat-value" style="color:var(--purple-bright);">42</div>
            <div class="stat-note">Grounded in verified transcripts</div>
          </div>
        </div>
      </section>
    `;
  }

  window.designSystemShowcase = designSystemShowcase;
})();
