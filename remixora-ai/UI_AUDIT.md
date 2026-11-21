# REMIXORA AI — UI/UX Audit & Design System Architecture

## 1. Executive Summary & Problem Analysis
Prior to this refactor, REMIXORA AI suffered from severe visual and architectural fragmentation:
- **Style Collisions:** `glass.css` was loaded after `style.css`, overriding design tokens with a pastel-green palette (`#e8ede3`), changing all typography to Georgia serif, and disabling essential visual indicators (waveforms, badges, stat cards).
- **No Unified Design System:** Dimensions, paddings, border radii, and button heights were hardcoded inconsistently across multiple CSS files and JS templates.
- **Missing Light/Dark Dual-Theme Support:** The app toggled between an unstyled dark theme in `style.css` and a fixed glass theme in `glass.css`.
- **Button Inconsistencies:** Multiple incompatible button styles existed (`.button`, `.icon-button`, `::file-selector-button`, `.btn`) with differing heights and colors.
- **Workflow & Route State Handling:** Navigation was losing context when hopping between screens, and some components were crashing on undefined fields.

## 2. Target Design Language: Liquid Chrome × Obsidian × Pearl Lavender
We establish a unified dual-theme design system using CSS Custom Properties (`--bg`, `--surface`, `--text-primary`, `--purple`, etc.):
- **Dark Theme (Obsidian):**
  - Background: `#090B10`
  - Sidebar: `#101319`
  - Surface: `#151922`
  - Surface Raised: `#1C2130`
  - Primary Accent: Liquid Chrome / Purple `#B8A5F5`
  - Border: `#252D3D`
- **Light Theme (Pearl Lavender):**
  - Background: `#FAF9FF`
  - Sidebar: `#F6F3FC`
  - Surface: `#FFFFFF`
  - Surface Raised: `#F0EDF9`
  - Primary Accent: Vibrant Lavender `#6B4EBF`
  - Border: `#DDD7EE`
- **Core Principle:** Layout dimensions, spacing, typography scales, and component structures remain 100% identical between both themes. Only semantic color tokens adapt.

## 3. Component Architecture
1. **Tokens (`tokens.css`):** 4px spacing scale (`--space-1` to `--space-16`), typography scale (`--text-xs` to `--text-4xl`), border radii (`--radius-xs` to `--radius-full`), and z-index layers (`--z-base` to `--z-toast`).
2. **Liquid Metal Button (`liquid-button.css` & `liquid-button.js`):** Multi-stop metallic gradient with animated light reflection, micro-interaction transitions, and accessible focus states.
3. **AppShell Redesign (`redesign.css`):**
   - 248px desktop sidebar with active route indicator, responsive mobile slide-out drawer.
   - 64px sticky glass topbar with breadcrumb navigation and 3-way Theme Switcher (Dark / Light / System).
   - Card grids with max 1440px content width, strict overflow guards (`min-width: 0`), and responsive breakpoints at 1500px, 1150px, 850px, and 560px.
4. **Showcase Route (`#showcase`):** Live documentation of colors, typography, buttons, cards, badges, and form components.
