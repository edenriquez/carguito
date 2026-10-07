# Carguito landing

Standalone marketing site for Carguito. Next.js 14 + Tailwind 3, no backend, no
Supabase. Deployed on Vercel as its own project with **Root Directory =
`landing`**.

The design is "Señal oscura": a Night ground, a drifting cyan mesh in the
hero, and the product as six drawn readings in a bento grid. `/b` and `/d`
(the two drafts compared before choosing) redirect to `/`.

## Pages and sections

`/` (`src/app/page.tsx`), in the order of the argument — pain → how →
proof → objections → close:

| Section | Component | Anchor |
|---|---|---|
| Nav | `shared/Nav` | |
| Hero (one promise, one CTA, one number) | `landing/HeroB` + `MeshGradient` | |
| Cómo funciona (three steps) | `landing/StepsB` | `#como-funciona` |
| Seis lecturas (bento; mirrors the dashboard's nav) | `landing/BentoB` | `#lecturas` |
| Reconoce a quien te cobra (merchant marquee) | `shared/LogoMarquee` | |
| Custodia (three cells) | `landing/CustodyB` | |
| Bancos (what the backend reads, by tier) | `landing/BanksB` | `#bancos` |
| Preguntas (native `<details>` FAQ + FAQPage JSON-LD) | `landing/FaqB` | `#preguntas` |
| Closing band | `shared/CtaBand` | |
| Footer (links) | `shared/Footer` | |

`/privacidad` (`src/app/privacidad/page.tsx`): the custody promise written
against what the code does today (see `docs/custody-plan.md`). If the backend
changes what it keeps, change this page the same day.

Copy that makes a checkable claim lives in `src/lib/data.ts` (`FIGURES`,
`BANKS`) and `src/lib/site.ts` (`SITE`: the one headline used by the H1, the
`<title>`, the OG image and the meta description).

## CTAs

Every "Comenzar" goes to `appUrl(placement)` (`src/lib/site.ts`), which stamps
`NEXT_PUBLIC_APP_URL` with `utm_source=landing&utm_medium=cta&utm_content=<nav|hero|band|footer|faq>`
so the app can tell landing arrivals apart and see which button converts.

## Run

```bash
npm install
cp .env.local.example .env.local   # NEXT_PUBLIC_APP_URL = where "Comenzar" sends people
npm run dev                        # http://localhost:3001
npx tsc --noEmit && npm run lint
npm run build                      # not while a dev server is running in this folder
```

## Design tokens

`src/design/tokens.ts` is a verbatim copy of `frontend/src/design/tokens.ts`.
Refresh it with `npm run tokens:sync`. Dark-surface additions live in
`src/design/dark.ts` and are never merged back.

## Vercel

1. Add New → Project → repo `edenriquez/carguito`.
2. Root Directory: `landing`. Framework: Next.js (auto).
3. Environment variables: `NEXT_PUBLIC_APP_URL` (the deployed app). Optional
   `NEXT_PUBLIC_SITE_URL` for a custom domain; otherwise
   `VERCEL_PROJECT_PRODUCTION_URL` is used for `metadataBase`.
4. Deploy. `vercel.json` carries the ignore rule so commits that only touch
   `backend/` or `frontend/` do not rebuild the landing.
