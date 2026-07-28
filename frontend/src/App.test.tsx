import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import {
  datasetsFixture,
  profileFixture,
  providersFixture,
  statusFixture,
  workspaceFixture,
} from "./test/fixtures";

function jsonResponse(payload: unknown) {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  }));
}

describe("HomeShift SPA", () => {
  beforeEach(() => {
    localStorage.setItem("homeshift-locale", "zh");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/status")) return jsonResponse(statusFixture);
      if (url.endsWith("/providers")) return jsonResponse(providersFixture);
      if (url.endsWith("/datasets")) return jsonResponse(datasetsFixture);
      if (url.endsWith("/workspace")) return jsonResponse(workspaceFixture);
      if (url.endsWith("/profile")) return jsonResponse(profileFixture);
      return jsonResponse({});
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  function renderApp(path: string) {
    window.history.pushState({}, "", path);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>,
    );
  }

  it("renders the current France/EUR workspace without stale Singapore data", async () => {
    renderApp("/baseline");
    expect(await screen.findByText("Sceaux, France")).toBeInTheDocument();
    expect(screen.getByText("€117.45")).toBeInTheDocument();
    expect(screen.queryByText("Singapore")).not.toBeInTheDocument();
  });

  it("shows registered data sources and explicit reset-oriented import workspace", async () => {
    renderApp("/data");
    expect(await screen.findByText("HomeShift 合成家庭")).toBeInTheDocument();
    expect(screen.getByText("UCI France")).toBeInTheDocument();
    expect(screen.getByText("导入与列映射")).toBeInTheDocument();
  });
});
