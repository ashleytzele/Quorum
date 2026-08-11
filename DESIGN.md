---
name: Quorum
description: Composed, precise meeting software where the tool disappears into the task — one indigo accent, warm-gray OKLCH neutrals, two co-equal themes.
colors:
  indigo: "oklch(51% 0.20 267)"
  indigo-strong: "oklch(46% 0.185 267)"
  indigo-ink: "oklch(41% 0.165 267)"
  indigo-tint: "oklch(97% 0.02 267)"
  indigo-tint-2: "oklch(93% 0.05 267)"
  canvas: "oklch(98.4% 0.004 74)"
  surface: "oklch(100% 0 0)"
  surface-raised: "oklch(97.4% 0.005 74)"
  muted: "oklch(95.6% 0.007 74)"
  border: "oklch(92.6% 0.005 74)"
  border-strong: "oklch(88% 0.008 74)"
  ink: "oklch(24% 0.013 74)"
  ink-muted: "oklch(45% 0.013 74)"
  ink-faint: "oklch(51% 0.013 74)"
  success: "oklch(50% 0.13 158)"
  warning: "oklch(52% 0.13 72)"
  danger: "oklch(52% 0.19 25)"
typography:
  display:
    fontFamily: "'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "21px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: "'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "'Hanken Grotesk', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.4
    letterSpacing: "0.06em"
  document:
    fontFamily: "'Source Serif 4', Georgia, 'Times New Roman', serif"
    fontSize: "33px"
    fontWeight: 700
    lineHeight: 1.12
    letterSpacing: "-0.01em"
  mono:
    fontFamily: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.65
    letterSpacing: "normal"
rounded:
  sm: "10px"
  md: "14px"
  lg: "20px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "10px"
  md: "16px"
  lg: "22px"
  xl: "30px"
components:
  button-primary:
    backgroundColor: "{colors.indigo}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    height: "40px"
    padding: "0 16px"
  button-primary-hover:
    backgroundColor: "{colors.indigo-strong}"
  button-ghost:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "40px"
    padding: "0 16px"
  button-danger:
    backgroundColor: "{colors.danger}"
    textColor: "#ffffff"
    rounded: "{rounded.sm}"
    height: "40px"
    padding: "0 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    height: "44px"
    padding: "0 13px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "22px"
  pill:
    backgroundColor: "{colors.indigo-tint}"
    textColor: "{colors.indigo-ink}"
    rounded: "{rounded.pill}"
    padding: "3px 9px"
---

# Design System: Quorum

## 1. Overview

**Creative North Star: "The Well-Run Meeting"**

Quorum should feel the way a well-run meeting feels — calm, organized, never shouty. The interface is an instrument the fluent user trusts on sight and then stops noticing: chrome recedes, the task the user is acting on carries all the visual weight, and nothing asks for attention it hasn't earned. This is Linear/Stripe-grade *earned familiarity* — standard affordances executed impeccably — not novelty for its own sake. A person mid-meeting, sometimes projecting to a room, should never have to fight the tool to find where they'd expect something to be.

The system is built on a single restrained indigo accent over warm-gray neutrals, expressed entirely in an OKLCH token set that produces **two co-equal themes** — light and dark are first-class outputs of the same tokens, not a skin and its inversion. The neutral is deliberately *warm-gray at near-zero chroma* (hue 74) so it reads as considered gray, never as the cream-and-terracotta look that has become the default of AI-generated interfaces. Indigo appears only where meaning lives: the primary action, the current selection, and state. Everything else is quiet.

This system explicitly rejects the generic Bootstrap/Material admin template (flat gray, default components, no point of view), consumer-social exuberance (playful gradients, big emoji, bouncy motion), the 2023 SaaS-cream + serif-display + terracotta aesthetic, and dashboards drowning in decorative charts, badges, and color for its own sake.

**Key Characteristics:**
- One accent (indigo), used for action, selection, and state — never decoration.
- Warm-gray OKLCH neutrals; two themes from one token set.
- The task is the hero; navigation chrome is dimmed so content takes precedence.
- Fast, state-only motion (150–250ms) — no page-load choreography.
- WCAG AA is a floor, not a finish (body ≥4.5:1, both themes).

## 2. Colors

A single indigo accent held with discipline over a warm-gray neutral field, plus a small, muted semantic vocabulary for state.

### Primary
- **Signal Indigo** (`oklch(51% 0.20 267)`): The one chromatic voice. Fills the primary button, marks the current/selected item, drives focus rings, and carries live state (the readiness bar, the Present progress bar). **Signal Indigo darkens for depth** — `indigo-strong` `oklch(46% 0.185 267)` on hover, `indigo-ink` `oklch(41% 0.165 267)` for links and text-on-tint.
- **Indigo Tints** (`oklch(97% 0.02 267)` / `oklch(93% 0.05 267)`): Quiet indigo washes for pills, subtle buttons, dropzone-hover, and focus glows. The accent whispering, not shouting.

### Neutral
- **Warm-Gray Canvas** (`oklch(98.4% 0.004 74)`): The page ground. Warm at a chroma so low it reads as neutral gray with a trace of warmth — never cream.
- **Surface / Surface-Raised** (`oklch(100% 0 0)` / `oklch(97.4% 0.005 74)`): Pure white cards on the warm canvas; the raised tone lines footers and hover rows. The top bar sits on the *canvas* tone, one notch below white, so it recedes behind content.
- **Border / Border-Strong** (`oklch(92.6% 0.005 74)` / `oklch(88% 0.008 74)`): Hairline dividers and input strokes.
- **Ink ramp** (`oklch(24% 0.013 74)` → `ink-muted 45%` → `ink-faint 51%`): Primary text, secondary/meta text, and the faintest labels — the faint step is tuned to clear AA (≥4.5:1) on every surface in both themes.

### Tertiary — Semantic state (muted, never decorative)
- **Success** (`oklch(50% 0.13 158)`): "Submitted", saved status, 100%-ready. Also the readiness bar's completion state.
- **Warning** (`oklch(52% 0.13 72)`): Transient "Saving…".
- **Danger** (`oklch(52% 0.19 25)`): Destructive actions and errors.

**The One Voice Rule.** Indigo is the only chromatic accent. It marks action, selection, and live state — nothing else. If a color is doing decoration, it is wrong. Semantic state colors (success/warning/danger) are a separate, muted vocabulary and never stand in as a second brand accent.

**The Warm-Gray Rule.** Neutrals are warm at hue 74, chroma ≤0.008. The instant a neutral reads as cream, sand, or beige (chroma climbing toward 0.03+), it has become the AI-default and must be pulled back to gray.

## 3. Typography

**Display / Body / Label Font:** Hanken Grotesk (with `-apple-system, 'Segoe UI', sans-serif`)
**Document Font:** Source Serif 4 (with `Georgia, 'Times New Roman', serif`)
**Mono Font:** `ui-monospace, 'SF Mono', Menlo` (with `Consolas, monospace`)

**Character:** One well-tuned humanist grotesk carries the entire product UI — headings, buttons, labels, data. A single high-contrast serif is held in reserve for exactly one surface: the exported minutes, where it signals a finished document. The pairing is a deliberate contrast axis (grotesk workhorse vs. serif document), never two similar sans fighting each other.

### Hierarchy
- **Display** (700, 21px, 1.2, `-0.02em`): Page titles (`<h1>`) and the login heading. The largest UI type; fixed rem-independent px so it never shrinks awkwardly in a panel.
- **Title** (700, 15.5px, `-0.01em`): Card titles and section heads.
- **Body** (400, 15px, 1.5): Default text. Prose panes cap at ~65–75ch; dense data (tables) may run tighter.
- **Label** (700, 11px, `0.06em`, UPPERCASE): Column headers, pane labels, sub-heads. Functional micro-labels — a wayfinding device, not a marketing eyebrow.
- **Document** (Source Serif 4, up to 33px title / 16.5px body, 1.62): The minutes "paper" only.
- **Mono** (13px, 1.65): The markdown note editor and inline code.

**The One-Family Rule.** Product UI is one sans in multiple weights. Reach for the serif *only* for the minutes document; reach for mono *only* for the note editor and code. A serif or mono anywhere else in the chrome is a defect.

## 4. Elevation

A hybrid of hairline borders and soft, indigo-tinted shadows. Surfaces are defined first by a 1px border and a warm-gray tonal step; shadow is added sparingly to lift genuinely floating layers. Shadows are tinted with the brand hue (`oklch(28% ~0.05 267)`) in light and pure black at higher opacity in dark — never a flat gray drop shadow.

### Shadow Vocabulary
- **Resting** (`--shadow-sm`, `0 1px 2px / 0 1px 3px` indigo-tinted): Cards and chips at rest — barely there.
- **Raised** (`--shadow`, `0 2px 4px, 0 12px 28px -10px`): Dropdowns, the Present deck cards.
- **Floating** (`--shadow-lg`, `0 28px 64px -18px`): The team drawer, modal dialogs, the auth card.

**The Quiet-Depth Rule.** Depth is carried by borders and tonal layering first; shadow is a supporting actor for things that truly float (drawer, dialog, toast). If a flat panel has a shadow, remove it.

## 5. Components

### Buttons
- **Shape:** Gently rounded (10px, `--radius-sm`); large variants 11px. Height 40px (46px for `btn-lg`).
- **Primary:** Signal Indigo fill, white text, faint indigo shadow. Hover → `indigo-strong`; active → `indigo-ink`. Exactly one filled primary per view.
- **Ghost:** Surface fill, `border-strong` stroke, ink text; hover fills to `muted`. The default secondary.
- **Subtle:** Indigo-tint fill, indigo-ink text — a quiet accent action.
- **Danger:** Danger fill, white text — destructive confirms only. (In dark theme the fill deepens to `oklch(52% 0.19 25)` so white text stays AA-legible.)
- **Focus:** 4px indigo-tint focus ring (`:focus-visible`), visible on every control.

### Inputs / Fields
- **Style:** Surface fill, `border-strong` 1px stroke, 10px radius, 44px tall.
- **Focus:** Border shifts to indigo + a 4px indigo-tint glow. Placeholder text uses `ink-faint` (meets 4.5:1).

### Cards / Containers
- **Corner Style:** 14px (`--radius-md`).
- **Background:** Surface (white) on the warm canvas; footers use surface-raised.
- **Border:** 1px `border`, always. **Shadow:** Resting only.
- **Internal Padding:** 22px.

### Pills & Status
- **Pills:** Indigo-tint background, indigo-ink text, fully rounded — quiet metadata chips. A `pill-muted` uses the neutral `muted` fill.
- **Status:** A small dot + label; `.ok` turns success-green (with an `aria-live` region), `.saving` pulses warning-amber.

### Navigation (Top Bar)
- **Style:** Sticky, frosted (`backdrop-filter: blur`) on the *canvas* tone — deliberately dimmer than the white content below it, so the content column dominates. Brand mark + meeting context on the left, links + user chip on the right. Links are `ink-muted`, filling to a `surface` chip on hover.

### Dialogs & Toasts (signature)
A single in-app system replaces every native `prompt`/`confirm`/`alert`. Dialogs are the native `<dialog>` element (real focus trap + Esc for free), token-styled, `aria-labelledby` its title, with an indigo-blurred backdrop; danger confirms use the Danger button. Toasts are brief, non-blocking, bottom-center, dismissible; success/error carry `role="status"`/`role="alert"`. A `flashToast` survives a page reload for post-write feedback.

### Readiness Bar (signature)
The admin's at-a-glance answer to "is everyone in yet?": "N of M teams submitted" with an indigo progress fill that flips to success-green at 100%. The fill animates with `transform: scaleX` (never width), conveys state by text *and* color, and only appears once a meeting has teams.

### The Minutes Paper (signature)
The exported minutes are a self-contained light "vellum" document (`oklch(99.2% 0.004 80)`) set in Source Serif 4 — **always light, in both app themes**, so it reads and prints like paper on the desk. Its indigo section labels are fixed (not theme-flipping) so they stay legible on the vellum.

### The Present Deck (signature)
A deliberately single-look, always-dark projection stage (`#0e1018`) with large `vmin`-scaled type, an indigo progress bar, and keyboard navigation. Exempt from the two-theme rule by intent: a room projection is a committed visual world.

## 6. Do's and Don'ts

### Do:
- **Do** keep indigo to action, selection, and live state. One filled primary button per view.
- **Do** build every screen from the same tokens so light and dark are equally first-class; verify body text ≥4.5:1 in **both** themes before shipping.
- **Do** dim the navigation chrome so the content column takes precedence ("Don't compete for attention you haven't earned").
- **Do** keep motion fast (150–250ms) and state-only, with an ease-out curve; respect `prefers-reduced-motion`.
- **Do** use in-app dialogs and toasts (`ui.js`) for every confirm/prompt/error — never a native browser dialog.
- **Do** animate with `transform`/`opacity` (e.g. the readiness fill's `scaleX`), never layout properties.

### Don't:
- **Don't** ship the generic Bootstrap/Material admin look — flat gray, default components, no point of view.
- **Don't** reach for consumer-social exuberance — playful gradients, big emoji, bouncy/elastic motion.
- **Don't** drift into the 2023 SaaS-cream + serif-display + terracotta aesthetic; the neutral is warm-*gray*, never cream (chroma ≤0.008).
- **Don't** drown the UI in decorative charts, badges, or color for its own sake — color must mean something.
- **Don't** introduce a second accent, or use full-saturation state color on inactive elements.
- **Don't** put the serif or mono anywhere but the minutes document and the note editor, respectively.
- **Don't** nest cards, use `border-left`/`border-right` >1px as a colored accent stripe, gradient-clip text, or apply decorative glassmorphism.
- **Don't** treat dark mode as an afterthought skin — it is a first-class output of the token set.
