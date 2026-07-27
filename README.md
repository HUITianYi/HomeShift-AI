# HomeShift AI

**Cut bills, not comfort.**

HomeShift AI is a presentation-ready prototype for **Agentic AI in
Sustainability**. It turns household bills, half-hour usage data and appliance
labels into three explainable energy plans, a seven-day action board and a
verified before/after report.

The public demo supports instant English/Chinese switching, remembers the
device preference and provides a touch-friendly single-column mobile flow so a
class can try the prototype from individual phones.

## Demo flow

1. Review or replace the clearly labelled synthetic bill, CSV and appliance
   label.
2. Run the diagnosis and watch six specialist agents report to the orchestrator.
3. Compare Maximum Savings, Balanced and Low Carbon pathways.
4. Choose Balanced and work through the seven-day action board.
5. Verify the preloaded after-data to close the measurement loop.

No API key is needed for this deterministic demo. When `OPENAI_API_KEY` is
configured, `/api/agent` uses the OpenAI Agents SDK; all financial and emissions
figures still come from calculation tools.

## Local development

Requires Node.js `>=22.13.0`.

```bash
npm install
copy .env.example .env.local
npm run dev
```

Open the URL printed by vinext. Useful commands:

```bash
npm test
npm run lint
npm run db:generate
```

## Runtime configuration

- `OPENAI_API_KEY`: optional, enables live agent orchestration.
- `OPENAI_MODEL`: optional, defaults to `gpt-5.6-terra`.
- D1 binding `DB`: stores sessions, plans and check-ins.
- R2 binding `UPLOADS`: stores user-supplied evidence.

The deployed demo is safe without the OpenAI key: it explicitly displays
“Transparent demo engine” and continues with precomputed synthetic evidence.

## Technology

Next.js-compatible vinext, TypeScript, Tailwind CSS, Recharts, OpenAI Agents SDK,
Drizzle ORM, Cloudflare D1/R2 and OpenAI Sites.
