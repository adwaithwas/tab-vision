---
name: "Thesis Quarterly"
description: "An academic journal that lives well online. Cream-paper surfaces, Source Serif 4 for body running text, IBM Plex Mono for footnote numerals and citations, a single deep cobalt accent reserved for the active citation link. Built for research publications, scientific journals, and long-form scholarly content."
tags: [academic, editorial, minimal, premium, warm]
colors:
  primary:   "#1a1814"
  secondary: "#6e6960"
  tertiary:  "#1a1814"
  neutral:   "#ebe5d4"
  surface:   "#f4eedb"
typography:
  display: "Source Serif 4"
  body:    "Source Serif 4"
  mono:    "IBM Plex Mono"
  scale:
    hero: "4.5rem / 1.04 / 600 / -0.025em"
    h1:   "2.75rem / 1.12 / 600 / -0.02em"
    h2:   "1.625rem / 1.3 / 600 / -0.012em"
    body: "1.125rem / 1.7 / 400 / -0.005em"
radius:
  sm: 2px
  md: 3px
  lg: 5px
  pill: 9999px
shadows:
  card:   "rgba(26,24,20,0.04) 0 1px 2px"
  button: none
borders:
  card:    "1px solid rgba(26,24,20,0.10)"
  divider: rgba(26,24,20,0.14)
buttons:
  primary:
    background: #1a1814
    color: #f4eedb
    border: none
    shape: rounded
    padding: 11px 22px
    font: 600 / 0.875rem
  secondary:
    background: #ebe5d4
    color: #1a1814
    border: 1px solid rgba(26,24,20,0.14)
    shape: rounded
    padding: 11px 22px
    font: 600 / 0.875rem
  outline:
    background: transparent
    color: #1a1814
    border: 1px solid rgba(26,24,20,0.20)
    shape: rounded
    padding: 11px 22px
    font: 600 / 0.875rem
  ghost:
    background: transparent
    color: #6e6960
    border: none
    shape: rounded
    padding: 11px 16px
    font: 600 / 0.875rem
charts:
  variant: "thin-bars"
  stroke_width: 1.25
  fill_opacity: 0.06
  gridlines: true
  bar_gap: 12px
  highlight: single
  dot_marker: false
fonts_url: "https://fonts.googleapis.com/css2?family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,500;0,8..60,600;0,8..60,700;1,8..60,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
dependencies: ["lucide-react"]
---

# Thesis Quarterly

## AI Build Instructions

> **Read this section before writing any code.** The rules below
> are non-negotiable. Every value used in the UI must come from this
> file's frontmatter — never substitute, approximate, or invent new
> colors, fonts, radii, or shadows. If a value is missing, ask the
> user before adding one.

### 1 · Your role

You are building UI for a project that has adopted **Thesis Quarterly** as its
design system. Treat `DESIGN.md` as the single source of truth.
Your job is to translate the user's product requirements into
components and pages that look like they were designed by the same
person who authored this file.

### 2 · Token compliance

- Pull every color, font family, radius, shadow, and spacing value
  from the frontmatter at the top of this file.
- Use semantic roles (e.g. `primary`, `accent`, `muted`) — never
  hard-code hex values that bypass the system.
- When a token can be expressed as a CSS variable, declare it once
  in your global stylesheet and reference it everywhere downstream.
- The Google Fonts `<link>` is provided in the Typography section.
  Add it to `<head>` before any component renders.

### 3 · Component recipes

Use these recipes verbatim when building the corresponding component.

#### Buttons

Four variants are defined. Pick one — never blend variants or invent a fifth.

- **Primary** — rounded shape, bg `#1a1814`, text `#f4eedb`, padding `11px 22px`, weight `600`.
- **Secondary** — rounded shape, bg `#ebe5d4`, text `#1a1814`, border `1px solid rgba(26,24,20,0.14)`, padding `11px 22px`, weight `600`.
- **Outline** — rounded shape, text `#1a1814`, border `1px solid rgba(26,24,20,0.20)`, padding `11px 22px`, weight `600`.
- **Ghost** — rounded shape, text `#6e6960`, padding `11px 16px`, weight `600`.

Reach for **primary** as the single dominant CTA per screen.
**Secondary** for the supporting action. **Outline** for tertiary
actions in toolbars. **Ghost** for inline links and table actions.

#### Cards

- Background: `#f4eedb`
- Border: `1px solid rgba(26,24,20,0.10)`
- Shadow: `rgba(26,24,20,0.04) 0 1px 2px`
- Radius: `radius.lg` (`5px`)
- Internal padding: `20px` for compact cards, `24–28px` for content cards.

#### Tabs

Variant: `underline`. Flat row of labels. Active tab gets a 2px underline in the accent color — no fill.

#### Charts

- Bar/line variant: `thin-bars`
- Highlight strategy: `single` — emphasize a single bar/point per chart.

#### Typography pairings

- **Display (`Source Serif 4`)** — h1, h2, hero headlines, brand wordmarks.
- **Body (`Source Serif 4`)** — paragraphs, labels, button text, form inputs.
- **Mono (`IBM Plex Mono`)** — code, eyebrows, metadata, numerals in tables.

### 4 · Hard constraints

Never do any of the following without explicit instruction from the user:

- Introduce a new color, font, radius, or shadow that isn't declared above.
- Mix this system with another (e.g. don't paste in Material or Bootstrap defaults).
- Use generic gradient defaults (purple→blue, peach→pink) — they break the system's voice.
- Reach for emoji icons. Use a consistent icon library and size icons in line with body type.
- Add motion that exceeds the system's restraint — keep transitions short (≤200ms) and subtle.

### 5 · Before you finish — verify

Run through this checklist for every screen you produce:

- [ ] Every color used appears in the Colors table above.
- [ ] Headlines use the display font; body copy uses the body font.
- [ ] Buttons match one of the declared variants exactly (shape, padding, weight).
- [ ] Border-radius values come from `radius.sm` / `radius.md` / `radius.lg` / `radius.pill`.
- [ ] Cards and dividers use the declared border + shadow tokens.
- [ ] No values were invented; if you needed something missing, you stopped and asked.

---

## 1. Atmosphere

Thesis Quarterly is an academic journal that lives well on the web. The page surface is cream paper `#f4eedb` — closer to uncoated journal stock than to white. Body runs in Source Serif 4 at 18px on a 1.7 leading — large enough to be read for an hour, with optical sizing that opens the glyphs at body size and tightens them in display. Footnote numerals, DOIs, citation references, and figure numbers all switch to IBM Plex Mono. The single accent is deep cobalt `#1d3f8a` that appears only on active citation links — the rest of the document is ink on cream.

The discipline is in the reading rhythm: serif body at generous size and leading, mono-numbered footnotes in the margin, and one cobalt link colour that earns its meaning by being the only colour.

**Signature moves**
- Source Serif 4 at 18px / 1.7 leading for body — designed for hour-long reading
- IBM Plex Mono for every footnote numeral, DOI, citation reference
- Cobalt `#1d3f8a` only on active citation links — the only colour in the system
- Marginalia in mono at 11px uppercase — page numbers, footnote refs, dateline
- Soft 3-5px corners — the journal-card voice, never sharp, never pill

## 2. Palette

### Surfaces
- **Cream** `#f4eedb` — page background (warm uncoated journal stock)
- **Cream Lift** `#ebe5d4` — secondary surfaces, table headers, footnote bands
- **Hairline** `rgba(26,24,20,0.10)` — every divider

### Ink
- **Ink** `#1a1814` — text, headings, primary CTA fill
- **Ink 50** `#6e6960` — secondary text, mono marginalia

### Accent
- **Cobalt** `#1d3f8a` — active citation link, chart highlight
- **Cobalt Soft** `rgba(29,63,138,0.10)` — hovered citation background

## 3. Typography

| Role | Font | Size | Weight | Leading | Tracking |
|------|------|------|--------|---------|----------|
| Hero | Source Serif 4 | 72px | 600 | 1.04 | -0.025em |
| H1 | Source Serif 4 | 44px | 600 | 1.12 | -0.02em |
| H2 | Source Serif 4 | 26px | 600 | 1.3 | -0.012em |
| Body | Source Serif 4 | 18px | 400 | 1.7 | -0.005em |
| Pull Quote | Source Serif 4 (italic) | 22px | 400 | 1.4 | -0.01em |
| UI / Button | IBM Plex Mono | 13px | 600 | 1.4 | 0 |
| Footnote Numeral | IBM Plex Mono | 11px | 600 | 1.0 | 0 tabular-nums superscript |
| Marginalia | IBM Plex Mono | 11px | 500 | 1.0 | 0.08em uppercase |
| DOI / Citation | IBM Plex Mono | 12px | 500 | 1.0 | 0 tabular-nums |

Source Serif 4 uses optical sizing — at 72px the strokes gain weight, at 18px body they open up for legibility. IBM Plex Mono carries every numbered or technical string. Buttons run in mono — that's the academic-press voice carried into UI.

## 4. Buttons

### Primary (Ink with Mono Label)
```css
background: #1a1814;
color: #f4eedb;
padding: 11px 22px;
border-radius: 3px;
font-family: "IBM Plex Mono";
font-weight: 600;
```

Mono on the button label is the entire signature — buttons read as filing-card actions ("Read Full Paper", "Cite This Article").

### Secondary (Cream Lift)
- `#ebe5d4` background, 1px hairline at 14% ink, ink text in mono — same shape, same padding

### Outline & Ghost
- Outline: transparent, 1px hairline at 20% ink
- Ghost: no border, ink-50 mono, hover underlines

## 5. Cards

```css
background: #f4eedb;
border: 1px solid rgba(26,24,20,0.10);
border-radius: 5px;
box-shadow: rgba(26,24,20,0.04) 0 1px 2px;
```

The single 1px shadow is the maximum lift. Featured papers (the issue's lead article) lift to cream-lift surface with a 2px ink top border — the lead-article rule.

## 6. Charts

Thin precise bars (3px wide, 12px gap) with dashed gridlines at 8% ink. One bar in cobalt, others in 22% ink. Line charts at 1.25px ink with a 6% cobalt fill. Y-axis labels in IBM Plex Mono uppercase 11px set in the left margin. Figure captions in italic Source Serif 4 14px below.

## 7. Tabs

Underline 1.5px in cobalt for the active state. Inactive tabs are ink-50 in IBM Plex Mono 500. Hover = cobalt-soft background wash. Tabs sit on a 1px hairline baseline.

## 8. Spacing

- Base 4px (column-aware)
- Scale: `4, 8, 12, 16, 24, 32, 48, 64, 96, 128`
- Section padding: 128px desktop, 64px mobile
- Body column max-width: 680px — the optimal reading measure for 18px serif

## 9. Do's & don'ts

✅ **Do**
- Use Source Serif 4 at 18px / 1.7 leading for body — that's the hour-long-reading measure
- Put every footnote numeral, DOI, figure number in IBM Plex Mono
- Reserve cobalt for active citation links + chart highlight only
- Hold body column to ~680px — wider columns break the reading rhythm

❌ **Don't**
- Use sans-serif body — the entire system is serif body, mono numerals
- Use a second accent — cobalt alone, on links and the chart
- Use card shadows beyond the 1px lift — paper, not cards
- Use sharp 0px corners — soft 3-5px is the journal-card voice

---

## Tokens

> Generated from the same source the live preview renders from.
> Treat the values below as the contract — never substitute approximations.

### Colors

| Role      | Value |
|-----------|-------|
| primary   | `#1a1814` |
| secondary | `#6e6960` |
| tertiary  | `#1a1814` |
| neutral   | `#ebe5d4` |
| surface   | `#f4eedb` |

### Typography

- **Display:** Source Serif 4
- **Body:** Source Serif 4
- **Mono:** IBM Plex Mono

| Role | size / leading / weight / tracking |
|------|------------------------------------|
| Hero | 4.5rem / 1.04 / 600 / -0.025em |
| H1   | 2.75rem / 1.12 / 600 / -0.02em |
| H2   | 1.625rem / 1.3 / 600 / -0.012em |
| Body | 1.125rem / 1.7 / 400 / -0.005em |

### Radius

- sm: `2px`
- md: `3px`
- lg: `5px`
- pill: `9999px`

### Shadows

- **card:** `rgba(26,24,20,0.04) 0 1px 2px`
- **button:** `none`

### Borders

- **card:** `1px solid rgba(26,24,20,0.10)`
- **divider:** `rgba(26,24,20,0.14)`

### Buttons

Four variants, each fully tokenized. The preview renders from these exact values.

#### Primary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `#1a1814` |
| color | `#f4eedb` |
| border | `none` |
| padding | `11px 22px` |
| fontWeight | `600` |
| fontSize | `0.875rem` |

#### Secondary

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `#ebe5d4` |
| color | `#1a1814` |
| border | `1px solid rgba(26,24,20,0.14)` |
| padding | `11px 22px` |
| fontWeight | `600` |
| fontSize | `0.875rem` |

#### Outline

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `transparent` |
| color | `#1a1814` |
| border | `1px solid rgba(26,24,20,0.20)` |
| padding | `11px 22px` |
| fontWeight | `600` |
| fontSize | `0.875rem` |

#### Ghost

| Property | Value |
|----------|-------|
| shape | `rounded` |
| background | `transparent` |
| color | `#6e6960` |
| border | `none` |
| padding | `11px 16px` |
| fontWeight | `600` |
| fontSize | `0.875rem` |

### Charts

| Property | Value |
|----------|-------|
| variant | `thin-bars` |
| strokeWidth | `1.25` |
| fillOpacity | `0.06` |
| gridlines | `true` |
| barGap | `12px` |
| highlight | `single` |
| dotMarker | `false` |

---

## Pro tokens

> Production-fidelity tokens. States, density, motion, elevation,
> content rules and a measured WCAG contract — derived from the
> resting tokens unless explicitly authored.

### States

#### Button

- **hover** — bg: `rgba(26, 24, 20, 0.92)`, shadow: `0 4px 20px -8px rgba(26, 24, 20, 0.4)`
- **focus** — outline: `1.5px solid #1a1814`, outline-offset: `4px`
- **active** — transform: `translateY(1px)`, filter: `brightness(0.95)`
- **disabled** — opacity: `0.45`
- **loading** — opacity: `0.7`
- **selected** — bg: `#1a1814`, color: `#f4eedb`

#### Input

- **hover** — border: `1px solid #1a1814`
- **focus** — border: `1px solid #1a1814`, shadow: `0 1px 0 0 #1a1814`
- **disabled** — opacity: `0.45`
- **error** — border: `1px solid #991B1B`, shadow: `0 1px 0 0 #991B1B`

#### Card

- **hover** — shadow: `0 8px 24px -12px rgba(15,23,42,0.14)`, transform: `translateY(-1px)`
- **selected** — border: `1px solid #1a1814`

#### Tab

- **hover** — color: `#1a1814`
- **focus** — outline: `1.5px solid #1a1814`, outline-offset: `3px`
- **selected** — color: `#1a1814`, border: `0 0 2px 0 solid #1a1814`

### Density

| Mode | padding × | row × | body | radius × | Use for |
|------|-----------|-------|------|----------|---------|
| compact | 0.72 | 0.78 | 0.8125rem | 0.85 | Information-dense — tables, IDEs, dashboards |
| comfortable | 1 | 1 | 0.9375rem | — | Default — most product UI |
| spacious | 1.35 | 1.3 | 1rem | 1.15 | Editorial — marketing, long-form, settings |

### Motion

**Signature — Page turn.** Deliberate, measured motion — like turning a magazine page. Never jerky, never overdone.

```css
transition: all 320ms cubic-bezier(0.25, 0.46, 0.45, 0.94);
```

| Token | Value |
|-------|-------|
| duration.instant | `80ms` |
| duration.fast | `180ms` |
| duration.base | `320ms` |
| duration.slow | `500ms` |
| easing.standard | `cubic-bezier(0.25, 0.46, 0.45, 0.94)` |
| easing.decelerate | `cubic-bezier(0.0, 0, 0.2, 1)` |
| easing.accelerate | `cubic-bezier(0.4, 0, 1, 1)` |
| easing.spring | `cubic-bezier(0.5, 1.2, 0.6, 1)` |

### Elevation

Five-level scale, system-specific recipe.

| Level | Shadow | Recipe |
|-------|--------|--------|
| level0 | `none` | Hairline only — typical editorial resting state. |
| level1 | `0 1px 2px rgba(15,23,42,0.04)` | Barely visible — list rows, dividers. |
| level2 | `0 8px 24px -12px rgba(15,23,42,0.12)` | Pull-quote, sidebar — soft lift. |
| level3 | `0 16px 40px -16px rgba(15,23,42,0.18)` | Cover story card — clear lift. |
| level4 | `0 32px 80px -24px rgba(15,23,42,0.28)` | Modal — overlays the layout, with scrim. |

### Content

- **measure:** `60ch` (max line length for body prose)
- **paragraph spacing:** `1.5em`
- **list indent:** `1.75em`
- **list gap:** `0.55em`
- **link:** color `#1a1814`, underline `always`
- **blockquote:** border `4px solid #1a1814`, padding `0.4em 0 0.4em 1.5em`
- **code:** background `rgba(26, 24, 20, 0.06)`, color `#1a1814`

### Accessibility (WCAG 2.1)

**Overall:** AA

| Pair | Ratio | Required | Grade | Suggested fix |
|------|-------|----------|-------|---------------|
| Body text on surface | 15.28:1 | AA | AAA | — |
| Body text on canvas | 14.09:1 | AA | AAA | — |
| Muted text on surface | 4.7:1 | AA | AA | — |
| Accent on surface | 15.28:1 | AA-Large | AAA | — |
| Accent on canvas | 14.09:1 | AA-Large | AAA | — |
