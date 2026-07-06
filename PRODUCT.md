# Product

## Register

product

## Users
Two roles inside a company that runs recurring team meetings:
- **Admins / meeting owners** — configure each meeting, review what every team submitted, then present live and export minutes. Power users, in a task, often mid-meeting.
- **Team members** — before a meeting, submit their pre-meeting note + files and capture meeting notes. Light-touch, in and out quickly.
Both are at a desk on a laptop, in focused work, sometimes projecting to a room (Present mode). Not a consumer audience; not mobile-first, but must not break on smaller screens.

## Product Purpose
MeeTeam turns scattered pre-meeting prep and note-taking into one shared, structured flow. Teams submit ahead of time; the admin reviews, presents a clean deck, and exports minutes — with a full History archive. Two operating modes: **Team** (each team self-submits) and **VIP** (the admin authors everything solo for high-stakes meetings). Success = the tool disappears into running the meeting: nothing to fight, everything where you'd expect it.

## Brand Personality
Composed, precise, quietly premium. Three words: **trustworthy, efficient, considered.** It should feel like a well-run meeting — calm, organized, never shouty. The voice is plain and active ("Add team", "Start presentation", "Submitted"), never clever or salesy.

## Anti-references
- Generic Bootstrap/Material admin templates — flat gray, default components, no point of view.
- Consumer-social exuberance — playful gradients, big emoji, bouncy motion.
- The 2023 SaaS-cream + serif-display + terracotta look.
- Dashboards drowning in decorative charts, badges, and color for its own sake.

## Design Principles
- **Earned familiarity.** Standard affordances done impeccably (Linear/Stripe-grade), so a fluent user trusts it on sight. Don't reinvent controls for flavor.
- **Restraint with one clear accent.** Indigo carries primary actions, current selection, and state — never decoration. Everything else is quiet, tinted neutrals.
- **The task is the hero.** Content and controls the user acts on get the visual weight; chrome recedes. Same concept → same visual weight everywhere.
- **State over motion.** Motion is fast (150–250ms) and only conveys state — save, selection, drawer, reveal. No orchestrated page-load choreography.
- **Two themes, one system.** Light and dark are equal first-class outputs of the same OKLCH token set; neither is an afterthought.

## Accessibility & Inclusion
- Target WCAG AA: body text ≥4.5:1, large/bold ≥3:1, in both themes. Placeholders meet 4.5:1.
- Visible keyboard focus on every interactive element; the theme toggle and all actions reachable by keyboard.
- `prefers-reduced-motion` respected (already global). `prefers-color-scheme` seeds the default theme; the user's explicit toggle persists and wins.
