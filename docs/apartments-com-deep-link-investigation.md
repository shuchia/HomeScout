# apartments.com Deep-Link Investigation (task #28)

> Status: **closed**. Anchor IDs verified against live DOM, deep-links shipped 2026-06-18 (commit forthcoming).
> Last touched: 2026-06-18

## Verified anchor IDs

User inspected the Aera listing in Chrome DevTools. The relevant DOM:

```html
<div class="ctaContainer">
  <button id="checkAvailabilityTourBtn"
          class="requestTourBtn js-checkAvailabilityModified stickyContactRightRail btn btn-md btn-primary">
    Request Tour
  </button>
  <button id="sendMessageBtn"
          class="sendMessageBtn js-checkAvailability stickyContactRightRail btn btn-md btn-secondary">
    Send Message
  </button>
  <p class="phoneLabel">
    <button class="propertyPhone js-propertyPhoneNumber" data-phone="8573418466">
      <span class="phoneNumber">(857) 341-8466</span>
    </button>
  </p>
</div>
```

Confirmed mapping:

| CTA | Element ID |
|---|---|
| Send Message (contact form) | `#sendMessageBtn` |
| Request Tour / Schedule Tour | `#checkAvailabilityTourBtn` |

## Shipped behavior

In `frontend/app/tours/[id]/page.tsx` `openListing()`:

```ts
const anchor = intent === 'tour' ? '#checkAvailabilityTourBtn' : '#sendMessageBtn'
window.open(sourceUrl + anchor, '_blank', 'noopener,noreferrer')
```

## ⚠️ Mobile regression + fix (2026-06-18, same day)

The above shipped behavior **blanked the apartments.com page on mobile**. The
anchor IDs were only ever verified against the **desktop** DOM (note the
`stickyContactRightRail` class — a desktop-only element); on mobile those IDs
don't exist and the unresolved hash blanked the page. There were also two
latent issues in the same function that hurt mobile specifically:

1. `await navigator.clipboard.writeText(...)` ran **before** `window.open()`,
   consuming the tap's transient activation → mobile browsers blank/block the
   new tab.
2. The `'noopener,noreferrer'` windowFeatures string can degrade a new tab into
   a blank popup on mobile.

**Fix:** open the window **synchronously first** (preserve activation), drop the
windowFeatures string (use `win.opener = null` instead), and **gate the fragment
to desktop only** (`window.matchMedia('(min-width: 768px)')`). Mobile now opens
the bare `sourceUrl`. The clipboard write moved to fire-and-forget after the
open. apartments.com is Akamai-fenced and mobile-only-failing, so this was
fixed defensively rather than via headless repro (which isn't possible).

## What this gets us and what it doesn't

| | Result |
|---|---|
| Desktop | Buttons are in `stickyContactRightRail` — already above the fold. Fragment is a no-op visually but harmless. |
| Mobile | Buttons live below the page content. Fragment scrolls them into view. Net positive. |
| Auto-click the button | No. Fragments only control scroll position. User still taps "Send Message" / "Request Tour" to open the modal. |
| Auto-paste the message | No, but the clipboard already has the AI-drafted message from the same click action (existing UX) — user pastes when the modal opens. |

The class names hint at JS-handler hooks (`js-checkAvailability`, `js-checkAvailabilityModified`, `js-propertyPhoneNumber`). Programmatically triggering a click from our domain isn't possible (cross-origin), so the deep-link is purely a scroll affordance.

## What we wanted

On the Contact tab, the "Contact this property" and "Schedule a tour" buttons currently open `source_url` (the bare apartments.com listing). Goal: deep-link to the contact form / tour scheduler section so the user's eye lands on the right CTA immediately, rather than landing at the top of a long marketing page.

## What I tried (CLI-only)

| Approach | Result |
|---|---|
| `curl` with realistic Chrome User-Agent + Sec-Fetch headers against `apartments.com/aera/g5qm48y/` | HTTP 403 (Akamai/edgesuite block) |
| Same probe with various `#fragment` and `?query` candidates | All HTTP 403 (note: fragments are stripped before reaching the server anyway, so this test is unsound for fragment validation) |
| `apartments.com/sitemap.xml` | HTTP 403 |
| Alt routes: `m.apartments.com/...`, `/aera/g5qm48y/contact`, `/schedule-tour`, `/amp` | 301 redirect or 403 |
| WebFetch via Claude tool | HTTP 403 |

apartments.com is fully fenced off from automated agents. Even very realistic browser-header curls don't get past Akamai's edge.

## What I did learn

Two anchor IDs are confirmed to exist on apartments.com listing pages — extracted from `<a href="#...">` references embedded in **pro100chok's FAQ-answer HTML** (the FAQ answers occasionally link back to other sections of the same page):

- `#feesSection`
- `#matterport3dSection`

This proves apartments.com **does** use `<word>Section`-style anchor IDs for its on-page sections. The contact-form section and tour-scheduler section almost certainly follow the same pattern — but we don't know the exact IDs without inspecting the live DOM.

Also from pro100chok's `flags` field (15 booleans per listing):

- `hasRequestTour`, `hasOnlineScheduling`, `hasIntegratedTours`, `has3DTour` — confirm that tour-related CTAs render on the page.
- These flags vary per listing (Aera has `hasRequestTour: true`, Rivermark has `hasOnlineScheduling: true` and `hasIntegratedTours: true`), so the exact CTA on the page differs by property. The anchor target might therefore differ too.

## Future enhancements (not pursued for beta)

If the apartments.com sticky CTA opens a click-to-open modal (which it does), deep-linking via `#sendMessageBtn` only scrolls to the trigger, not into a ready-to-paste textarea. To go further you'd need one of:

- A query parameter that opens the modal on load — existence unknown, would need browser-side discovery.
- A Snugd-domain redirector page that runs JS before forwarding to apartments.com (`document.querySelector('#sendMessageBtn').click()` after navigation) — but the click would happen on the Snugd page, not the apartments.com page (cross-origin), so it doesn't actually work.

Neither is worth pursuing. The current UX (pre-loaded clipboard + scroll-to-button on mobile) is enough.
