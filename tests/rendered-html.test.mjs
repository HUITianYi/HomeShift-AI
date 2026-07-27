import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import test from "node:test";

test("ships the complete bilingual HomeShift product shell", async () => {
  const [page, layout, app, i18n] = await Promise.all([
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(
      new URL("../app/components/HomeShiftApp.tsx", import.meta.url),
      "utf8",
    ),
    readFile(new URL("../lib/i18n.ts", import.meta.url), "utf8"),
  ]);

  assert.match(page, /HomeShift AI — Cut bills, not comfort/);
  assert.match(layout, /images: \["\/og\.png"\]/);
  assert.match(app, /Turn your energy data into a plan/);
  assert.match(app, /Run 7-agent diagnosis/);
  assert.match(app, /Synthetic demo/);
  assert.match(app, /Verify after-data/);
  assert.match(app, /data-testid="language-toggle"/);
  assert.match(app, /homeshift-locale/);
  assert.match(i18n, /家庭能源智能助手/);
  assert.match(i18n, /真正能执行的计划/);
  assert.doesNotMatch(`${page}${layout}${app}`, /codex-preview|Your site is taking shape/);
  await access(new URL("../public/og.png", import.meta.url));
});

test("keeps deterministic calculations and cloud bindings explicit", async () => {
  const [energy, hosting, packageJson] = await Promise.all([
    readFile(new URL("../lib/energy.ts", import.meta.url), "utf8"),
    readFile(new URL("../.openai/hosting.json", import.meta.url), "utf8"),
    readFile(new URL("../package.json", import.meta.url), "utf8"),
  ]);

  assert.match(energy, /TARIFF_SGD_PER_KWH = 0\.3478/);
  assert.match(energy, /GRID_EMISSION_KG_PER_KWH = 0\.402/);
  assert.match(energy, /compareActualToPlan/);
  const hostingConfig = JSON.parse(hosting);
  assert.equal(hostingConfig.d1, "DB");
  assert.equal(hostingConfig.r2, "UPLOADS");
  assert.match(hostingConfig.project_id, /^appgprj_/);
  assert.doesNotMatch(packageJson, /react-loading-skeleton/);
});
