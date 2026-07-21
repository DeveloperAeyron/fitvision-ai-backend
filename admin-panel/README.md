# FitVision Admin Panel

Internal Next.js control surface for models, meals, label mapping, meal plans, prediction review, analytics, and access management.

## Run locally

```bash
npm install
cp .env.example .env.local
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The current dashboard uses typed mock data. Set `NEXT_PUBLIC_API_URL` and replace the exports in `lib/data.ts` with protected admin API requests when those endpoints are ready.
