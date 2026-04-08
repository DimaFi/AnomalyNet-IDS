import { render, screen } from "@testing-library/react";
import "../i18n";
import { App } from "./App";

vi.mock("../lib/api", () => ({
  api: {
    getHealth: () =>
      Promise.resolve({
        service: "traffic-analysis-local-api",
        status: "active",
        mode: "mock",
        active_model_id: "mock-default",
        retention_days: 14,
        contract_version: "feature-contract.v1"
      }),
    getSettings: () =>
      Promise.resolve({
        language: "ru",
        theme: "dark",
        run_mode: "mock",
        retention_days: 14,
        active_model_id: "mock-default",
        capture_enabled: true,
        stream_autostart: true
      }),
    getModels: () =>
      Promise.resolve({
        active_model_id: "mock-default",
        items: []
      })
  }
}));

vi.stubGlobal(
  "WebSocket",
  class {
    close() {}
  } as unknown as typeof WebSocket
);

test("renders application title", async () => {
  render(<App />);
  expect(await screen.findByText("Traffic Analysis Console")).toBeInTheDocument();
});
