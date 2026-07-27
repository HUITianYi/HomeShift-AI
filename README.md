# HomeShift AI

**Cut bills, not comfort.**

HomeShift AI is a bilingual, real-data household energy demo. It combines
deterministic energy calculations with six OpenAI specialist agents and one
orchestrator. The model recommends a plan, but it cannot rewrite energy, cost
or carbon figures produced by the calculation engine.

## Demo flow

1. Enter a household profile, bill totals, comfort constraints and major
   appliance details.
2. Import 7–30 days of half-hour energy data.
3. Review the measured load shape and data-quality report.
4. Run the live seven-agent diagnosis.
5. Compare Maximum Savings, Balanced and Low Carbon pathways.
6. Select a plan and present its traceable household actions.

Use **Reload synthetic case** to restore a complete rehearsal dataset.

## CSV contract

The CSV must represent energy used in each half-hour interval, in kWh. It must
cover 7–30 calendar days with at least 80% interval coverage. Common timestamp
headers (`timestamp`, `datetime`, `date_time`, `time`) and energy headers
(`kwh`, `consumption`, `usage`, `energy`) are accepted with comma, semicolon or
tab delimiters.

```csv
timestamp,kwh
2026-07-01 00:00,0.182
2026-07-01 00:30,0.176
```

The app includes a downloadable seven-day template. Bill and appliance-label
images are optional local evidence only; values are entered manually and no
OCR is performed.

## Local development

Requires Node.js `>=22.13.0`.

```bash
npm install
copy .env.example .env.local
npm run dev
```

`OPENAI_API_KEY` is required for the live diagnosis. The app deliberately
blocks progression when the key is absent or the live agent run fails.

Useful checks:

```bash
npm test
npm run lint
npx tsc --noEmit
```

## Runtime configuration

- `OPENAI_API_KEY`: required for live multi-agent orchestration.
- `OPENAI_MODEL`: optional; defaults to `gpt-5.6-terra`.
- D1 binding `DB` and R2 binding `UPLOADS` remain available in the project but
  are not used by the single-household demo flow.

## Technology

Next.js-compatible vinext, TypeScript, React, Recharts, OpenAI Agents SDK,
Zod, Cloudflare Workers and OpenAI Sites.
