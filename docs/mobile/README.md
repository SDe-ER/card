# CARD Mobile

CARD Mobile is the phone interface of CARD, served by the CARD app at `/cdms`. It is a Progressive
Web App (PWA) built the same way as the Frappe HR mobile app (`/hrms`). CARD Desk stays the full
management system; CARD Mobile covers the few actions people need on site.

> **Status:** in development for v4.1.0. Not released. Installation on real iPhone and Android
> devices has not been tested yet (see [Device checklist](#device-checklist)).

## How it fits into CARD

| Part | Path | Role |
|---|---|---|
| Frontend sources | `frontend/` | Vue 3, TypeScript, [frappe-ui](https://github.com/frappe/frappe-ui), Tailwind CSS, Vite |
| Build scripts | `package.json` | `bench build` runs `build`, which builds `frontend/` (as Frappe HR) |
| Build output (not in git) | `card/public/frontend/`, `card/www/cdms.html` | Bundles, manifest, icons, service worker; the page template |
| Page | `card/www/cdms.py` | Boot data: CSRF token, language, direction, translations |
| Access | `card/mobile.py` | Who may open the app; `get_session_context` (GET) |
| Service worker route | `card/pwa.py` | Serves `/cdms/sw.js` so its scope is `/cdms/` |
| Routes and apps screen | `card/hooks.py` | `website_route_rules`, `page_renderer`, `add_to_apps_screen` |
| Business endpoints | `card/materials.py` | Existing operator endpoints; CARD Mobile adds no business logic |

Frappe HR registers its service worker at `/assets/hrms/frontend/sw.js`, so the worker's scope is
`/assets/hrms/frontend/` and it never controls `/hrms`. CARD serves the same kind of worker at
`/cdms/sw.js` through Frappe's `page_renderer` hook, so it controls `/cdms` and nothing wider.

## Access

- Sign-in happens inside the app with the user's ERPNext account (Frappe `login`), so sessions and
  CSRF protection are Frappe's own.
- The page opens for a signed-in user with a CARD portal role (Card Operator, Card Supervisor,
  Card Manager or System Manager). The app's screens also need an **Active Employee** linked to
  the user (`Employee.user_id`); otherwise the user sees a "not set up" screen.
- Every call is checked again on the server by the CARD endpoint it reaches.
- Apps screen: *Card* (Desk) is shown to users who can read Card Equipment and is hidden from
  Website Users; *Card Mobile* is shown to users who may open `/cdms`.

## Screens

| Screen | Operator | Supervisor / Manager | Status |
|---|---|---|---|
| Sign in | ✓ | ✓ | Done |
| Home: my machines, open requests | ✓ | ✓ (link to the review in Desk) | Done |
| New request (parts, consumables, tools) | ✓ | – | Done |
| My requests and their status | ✓ | – | Done |
| Profile, install hint, sign out | ✓ | ✓ | Done |
| Supervisor review, request on behalf, custody | – | ✓ | Planned (needs CARD G2) |
| Manager approvals | – | ✓ | Planned |
| My tools in custody | ✓ | – | Planned (needs CARD G3) |

## Layout rules

- Phone UI only. On a computer the same UI is shown in a centered column up to 480 px wide.
- Safe areas (`env(safe-area-inset-*)`) for the notch, Dynamic Island and home indicator.
- Touch targets at least 48 px; one main action per screen; bottom navigation with four items.
- Zoom is allowed (the viewport does not disable it).

## Languages

Translations come from Frappe's translation system in the page boot. Arabic and Urdu are
right-to-left; English, Bengali and Hindi left-to-right. Generic words (Home, Login, Quantity, …)
use the translation context **Card Mobile** (`msgctxt "Card Mobile"` in `card/locale/*.po`), so
CARD never overrides Frappe's or ERPNext's own translations. "Card" is never translated.

## Development

```bash
cd apps/card
yarn install          # installs frontend/ dependencies
yarn dev              # Vite dev server that proxies the bench (frappe-ui plugin)
```

Checks (also run by CI, job *CARD Mobile*):

```bash
cd apps/card/frontend
yarn type-check
yarn test
yarn build
```

App icons are rendered from the SVG sources in `frontend/icons/` (derived from
`card/public/images/card-logo.svg`) into `frontend/public/icons/`.

## Device checklist

To be completed on an HTTPS test site before iPhone or Android support is stated:

- [ ] Android (Chrome): install from the prompt or the browser menu; opens standalone; icon and
      name correct; maskable icon not cropped.
- [ ] iPhone (Safari): Share → Add to Home Screen; opens standalone; status bar and safe areas
      correct on a model with a notch or Dynamic Island.
- [ ] Sign in, new request, my requests, sign out — in Arabic (RTL) and English (LTR).
- [ ] Update: a new build is picked up after reopening the app.
- [ ] Desktop browser: same UI in the centered column.
