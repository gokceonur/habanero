---
name: explore-app
description: Systematically crawl a running iOS app to map screens, discover blind spots, and recommend adapter config.
---

# Explore App

Systematically crawl the running iOS app under Habanero to build a screen map,
surface elements the accessibility tree misses, and recommend an adapter
configuration that makes the app fully drivable.

If a `screen` argument is supplied, focus the crawl on that screen instead of
walking the whole app.

## Goal

Produce, for the connected app:

1. A **screen map** — every reachable screen, how you got there (the tap/nav
   path), and the key interactive elements on each.
2. A **blind-spot list** — controls that are visible but not exposed in the
   structured tree (missing labels/identifiers, custom-drawn views, canvases),
   so they can be made testable.
3. An **adapter recommendation** — which adapter to run and any per-app tuning
   needed for reliable observation and input.

## Procedure

1. **Orient.** Call `look` for a compact summary of the current screen — what is
   visible and tappable. Use `screen` to confirm the current screen identity.
   Only escalate to `tree` when you need the full hierarchy that `look` omits.
2. **Inventory.** Use `snapshot` / `find` to enumerate interactive elements with
   their frames and traits. Note any element with an empty label or identifier —
   it is a blind-spot candidate.
3. **Traverse.** Drive the app with `tap`, `scroll`, `swipe`, and `navigate`
   (deep links). After each transition re-`look` and record: source screen →
   action → destination screen. Prefer breadth first; track visited screens so
   you do not loop.
4. **Recover.** Use `back` / `dismiss` to unwind modals and return to a known
   screen before exploring the next branch. Re-orient with `look` after each.
5. **Probe blind spots.** For visible-but-unmapped controls, cross-check with a
   `screenshot` only when the structured tools cannot explain what is on screen.
   Record what is missing (label, identifier, trait) so the app or adapter can
   expose it.

## Output

Report back, not as files:

- The screen map (screen → reachable-via path → notable elements).
- The blind-spot list (element, screen, what metadata is missing).
- The recommended adapter and any per-app configuration, with the reasoning.

Be exhaustive about coverage but concise in prose. Prefer the structured
observation tools (`look`, `snapshot`, `find`) over screenshots; reach for
vision only for what the accessibility tree cannot show.
