import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("ships the bilingual real-data HomeShift flow", async () => {
  const [page, layout, app, i18n] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../app/components/HomeShiftApp.tsx", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../lib/i18n.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /HomeShift AI/);
  assert.match(layout, /images: \["\/og-real-data\.png"\]/);
  assert.match(i18n, /Run live 7-agent diagnosis/);
  assert.match(i18n, /Household setup/);
  assert.match(i18n, /Download CSV template/);
  assert.match(app, /specialistNames/);
  assert.match(app, /data-testid="language-toggle"/);
  assert.match(app, /homeshift-locale/);
  assert.match(i18n, /真实数据Demo/);
  assert.match(i18n, /家庭资料设置/);
  assert.doesNotMatch(app, /383\.5|Verify after-data|stage === "track"/);
  assert.doesNotMatch(
    `${page}${layout}${app}`,
    /codex-preview|Your site is taking shape/,
  );
  await access(new URL("../public/og.png", import.meta.url));
});

test("keeps deterministic formulas and live agent output explicit", async () => {
  const [energy, agent, hosting, packageJson] = await Promise.all([
    readFile(new URL("../lib/energy.ts", import.meta.url), "utf8"),
    readFile(new URL("../app/api/agent/route.ts", import.meta.url), "utf8"),
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(energy, /airConditionerDutyFactor|0\.65/);
  assert.match(energy, /overnightTarget/);
  assert.match(energy, /bill\.totalKwh \* 0\.3/);
  assert.match(agent, /outputType: agentDecisionSchema/);
  assert.match(agent, /configuration_missing/);
  assert.doesNotMatch(agent, /mode: "demo"/);
  const hostingConfig = JSON.parse(hosting);
  assert.equal(hostingConfig.d1, "DB");
  assert.equal(hostingConfig.r2, "UPLOADS");
  assert.match(hostingConfig.project_id, /^appgprj_/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
