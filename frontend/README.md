# Frontend — Employee Hub + HR Admin Center (06-frontend-impl)

Next.js (App Router) + Tailwind + TanStack Query + Zustand + native EventSource.

## Routes

| Route | Role | Contents |
|---|---|---|
| `/hub` | employee, hr_admin | Timeline + progress, optimistic checklist, buddy card, cited chat |
| `/admin` | hr_admin | Pipeline table (`?status=` filter parity) |
| `/admin/cases/[id]` | hr_admin | Plan / Trace / Execution tabs (HITL editor, SSE feed, halt) |
| `/login` | — | MVP SSO stub (role cookie); prod → OIDC httpOnly JWT |

Auth: `middleware.ts` gates `/hub` and `/admin` on the `ob_role` cookie.
No secrets in client; chat never sends region/dept (server resolves per spec 06 §2).

## Env

```bash
cp .env.example .env.local
npm install
npm run gen-api   # OpenAPI → lib/api.types.ts (CI fails build on drift)
NEXT_PUBLIC_USE_MSW=1 npm run dev   # mocked backend from tests/fixtures
npm run dev                       # real API at NEXT_PUBLIC_API_URL
```

## Tests

- `npm test` — Vitest unit (progress, diff, citations, rollback)
- `npm run test:e2e` — Playwright vs MSW mocks (HR + employee flows; system Chrome via `playwright.config.ts`)
- Lighthouse (prod build, system Chrome): `/login` perf 0.99 / a11y 100 / LCP 2.0s;
  `/hub` 1.0 / 100 / 1.8s; `/admin` 1.0 / 100 / 1.5s — all within LCP < 2.5s budget.
  (Best-practices 0.96 is console noise from the unreachable API in no-backend envs.)

## CI & drift

- `.github/workflows/frontend.yml` — `npm run gen-api` + drift check (fails build on
  `lib/api.types.ts` staleness), `tsc`, Vitest, `next build`, e2e.
- `ApiVersionBanner` — compares `OPENAPI_HASH` against live `/openapi.json`
  `info.version`; shows a redeploy banner on drift, stays silent when undiscoverable.

## A11y / perf budgets

WCAG AA: skip link, labelled controls, `role=alert/status/tab`, keyboard-operable tabs/modal,
responsive 360–1440px. Budgets: LCP < 2.5s, route < 200ms cached, SSE render < 100ms/event.
