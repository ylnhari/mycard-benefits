# Accessibility

The public MyCard Benefits dashboard is designed against WCAG 2.1 AA success
criteria for its local, read-only surfaces. This is an engineering target and
test contract, not a certification or a substitute for testing with people who
use assistive technology.

## Keyboard and structure

- The first keyboard stop is a **Skip navigation and go to content** link.
- The dashboard has named navigation and main landmarks. Changing a dashboard
  view moves keyboard focus to that view's heading and announces its name.
- Controls use native links, buttons, fields, selects, and disclosure widgets.
  Result details expose their expanded state, and local card detail regions
  have names. Pressing Escape in an expanded local card detail returns focus to
  its control.
- Loading, result, and error text uses polite atomic status regions. Dynamic
  result collections identify additions and text changes without relying on
  colour alone.
- Links that open an admitted public source in a new tab state that behavior to
  assistive technology. Only validated HTTPS URLs render as links.

## Visual and motion behavior

- Interactive controls, navigation links, summaries, filter labels, and public
  source links have a 44px minimum target in the dashboard styles.
- Keyboard focus uses a visible three-pixel focus outline. Status badges also
  state their status as text; colour is never the only indicator.
- The checked dark and light text, muted text, accent, danger, and focus tokens
  meet the dashboard's deterministic 4.5:1 text and 3:1 focus-outline
  contrast contracts on their panel backgrounds.
- At 850px and below, navigation becomes horizontally scrollable and grids,
  filters, comparison, cards, and detail rows become a single column. The
  keyboard focus transition scrolls the selected view heading into view.
- With `prefers-reduced-motion: reduce`, smooth scrolling is disabled and any
  animation or transition is reduced to a single near-instant step. No content
  or focus treatment is removed.

## Verification scope

`tests/test_accessibility.py` checks DOM landmarks, view controls, live-region
contracts, focus-management hooks, safe external-link names, contrast tokens,
44px targets, mobile rules, and reduced-motion CSS without a browser, network,
or private vault. `tests/test_rendered_ui.py` supplies an opt-in synthetic
headless-browser check when Python Playwright and its matching Chromium driver
are already installed:

```powershell
$env:MYCARD_RENDERED_UI = "1"
uv run pytest tests/test_rendered_ui.py -m rendered_ui
```

The opt-in test is intentionally skipped when that pre-provisioned browser is
not available; it never downloads a browser. It uses only a temporary loopback
server, committed synthetic catalog data, and synthetic API responses. Do not
interpret a skipped browser check as a rendered-browser pass.
