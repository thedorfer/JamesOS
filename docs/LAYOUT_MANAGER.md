# Workspace Layout Manager

Last reviewed: 2026-07-18

The recovery branch implements a desktop divider with a 300 px minimum, 420 px default, and 55% maximum chat width. Mobile ignores the desktop width and uses the chat drawer.

Normal mode keeps inputs editable and panels fixed. Customize mode attaches dragging to panel title bars and permits registered, unlocked panels to move and resize on a twelve-column logical grid. Save persists atomically, Cancel restores the baseline, and Reset returns the deterministic default.

Layouts are validated server-side and stored outside Git beneath `~/JamesOSData/JamesOS/Layouts/` through `GET`, `PUT`, and `DELETE /app/layouts/{view_id}`. Layout, value, and action locks are enforced. Destination, publication, order, and external-confirmation panels remain visible and protected; Jade/system locks override users, saved values, and agent placement hints.

Themes contain approved tokens only. HTML, JavaScript, arbitrary selectors, remote URLs, and executable CSS are rejected. `jamesos-dark` is the initial theme.
