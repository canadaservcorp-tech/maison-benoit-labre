# MBL Frontend — Building Maintenance System

React SPA for the **Maison Benoît Labre Building Maintenance System**.

> ⚠️ **This repo currently contains only the production build artifacts**, not
> the React source code. The original React/Vite source was never recovered
> after the previous hosted instance was taken down. See
> [Recovering the source](#recovering-the-source) below.

## What's here

- `index.html` — Vite-built entry point
- `assets/index-B-irygFq.js` — minified bundled React app (the whole SPA)
- `assets/index-B0jiQx8Y.css` — Tailwind build
- `logo.png`, `vite.svg` — static assets

The bundle has been patched to call the backend at
`https://mbl-backend-mjaklkwn.fly.dev`. To point it at a different API URL,
run:

```bash
./scripts/rewrite-api-url.sh https://your-new-backend.example.com
```

This is a temporary arrangement. The long-term answer is to restore the React
source (see below) so the app can be edited, tested, and rebuilt normally.

## Deploying

This is static HTML/JS/CSS — deploy it anywhere that serves static files.

### Cloudflare Pages (recommended, free)

1. Sign in to https://dash.cloudflare.com → Workers & Pages → Create → Pages
2. Connect to this GitLab repo (`canada.servcorp-group/mbl-frontend`).
3. Build settings: **Framework preset: None**, **Build command:** *(leave
   blank)*, **Build output directory:** `/`.
4. Deploy. You'll get `<project>.pages.dev`.
5. (Optional) Add your own custom domain under "Custom domains".

### Netlify, Vercel, S3+CloudFront, GitLab Pages, etc.

Any static host works. Upload the four files/dirs listed above.

## Recovering the source

To make this app maintainable/sellable long-term, the React/Vite source code
needs to be located or reconstructed:

1. **Search old laptops/backups** for a `mbl-frontend` or similar directory
   that contains a `package.json` with `"name": "mbl-frontend"` — this was the
   original Vite project.
2. **Check previous Devin sessions** that built the frontend — the source
   would have been written to the VM's filesystem at that time.
3. **Last resort:** rebuild from scratch against the existing backend API
   contract (see `mbl-backend/app/main.py` and README). The API is stable so a
   rewrite is possible; estimate ~1–2 weeks for a single developer.

## API contract

See the backend repo: https://gitlab.com/canada.servcorp-group/mbl-backend

The frontend expects the backend at `apiUrl` which is hard-coded into the
bundle at build time. To point the bundle at a new URL without a rebuild, run
the rewrite script:

```bash
./scripts/rewrite-api-url.sh https://your-backend.example.com
```

It does an in-place string replacement in `assets/index-B-irygFq.js`. Commit
and redeploy afterward.

## Seeded users

For initial login (change passwords after first use):

| Email                                          | Password         | Role  |
| ---------------------------------------------- | ---------------- | ----- |
| `admin@mbl.com`                                | `Admin2025!`     | admin |
| `andreanedesilets@lamaisonbenoitlabre.org`     | `Andreanne2025!` | admin |
| `faycal@lamaisonbenoitlabre.org`               | `Faycal2025!`    | admin |
| `hicham@lamaisonbenoitlabre.org`               | `Hicham2025!`    | admin |
