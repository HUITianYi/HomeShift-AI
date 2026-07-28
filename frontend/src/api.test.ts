import { describe, expect, it } from "vitest";
import { workspaceSchema } from "./api";
import { workspaceFixture } from "./test/fixtures";

describe("workspace API contract", () => {
  it("accepts the live Python workspace shape with dynamic EUR currency", () => {
    const parsed = workspaceSchema.parse(workspaceFixture);
    expect(parsed.meta.currency.code).toBe("EUR");
    expect(parsed.agents.count).toBe(7);
  });

  it("rejects a payload that omits the seven-role audit section", () => {
    const invalid: Record<string, unknown> = { ...workspaceFixture };
    delete invalid.agents;
    expect(() => workspaceSchema.parse(invalid)).toThrow();
  });
});
