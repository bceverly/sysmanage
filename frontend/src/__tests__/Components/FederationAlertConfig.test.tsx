import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

// `t` and the returned object MUST be stable across renders (the real
// react-i18next memoises them) — a fresh `t` per call breaks downstream
// useCallback/useEffect deps into an infinite render loop.
vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = fallback || key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(new RegExp(`{{${k}}}`, "g"), String(v));
      }
    }
    return s;
  };
  const value = { t, i18n: { language: "en" } };
  return { useTranslation: () => value };
});

vi.mock("../../Services/federation", () => ({
  doGetFederationAlertConfig: vi.fn(),
  doUpdateFederationAlertConfig: vi.fn(),
}));

import * as fed from "../../Services/federation";
import FederationAlertConfig from "../../Components/FederationAlertConfig";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => vi.clearAllMocks());

test("renders nothing when unlicensed", async () => {
  m(fed.doGetFederationAlertConfig).mockResolvedValue({ licensed: false });
  const { container } = render(<FederationAlertConfig />);
  await waitFor(() => expect(m(fed.doGetFederationAlertConfig)).toHaveBeenCalled());
  expect(container.querySelector('[data-testid="alert-config-card"]')).toBeNull();
});

test("loads effective values and existing overrides", async () => {
  m(fed.doGetFederationAlertConfig).mockResolvedValue({
    licensed: true,
    effective: {
      offline_multiplier: 4,
      min_offline_seconds: 900,
      compliance_threshold: 70,
      critical_cve_threshold: 0,
    },
    overrides: {
      offline_multiplier: 6,
      min_offline_seconds: null,
      compliance_threshold: null,
      critical_cve_threshold: null,
    },
  });
  render(<FederationAlertConfig />);
  const input = (await screen.findByTestId(
    "alert-config-offline_multiplier",
  )) as HTMLInputElement;
  expect(input.value).toBe("6"); // the override prefilled
  // an un-overridden field is blank
  const blank = screen.getByTestId(
    "alert-config-min_offline_seconds",
  ) as HTMLInputElement;
  expect(blank.value).toBe("");
});

test("saves parsed overrides; a blank field clears to null", async () => {
  m(fed.doGetFederationAlertConfig).mockResolvedValue({
    licensed: true,
    effective: {
      offline_multiplier: 4,
      min_offline_seconds: 900,
      compliance_threshold: 70,
      critical_cve_threshold: 0,
    },
    overrides: {
      offline_multiplier: null,
      min_offline_seconds: null,
      compliance_threshold: null,
      critical_cve_threshold: null,
    },
  });
  m(fed.doUpdateFederationAlertConfig).mockResolvedValue({
    licensed: true,
    effective: {
      offline_multiplier: 5,
      min_offline_seconds: 900,
      compliance_threshold: 85.5,
      critical_cve_threshold: 0,
    },
  });
  render(<FederationAlertConfig />);
  const mult = (await screen.findByTestId(
    "alert-config-offline_multiplier",
  )) as HTMLInputElement;
  fireEvent.change(mult, { target: { value: "5" } });
  const comp = screen.getByTestId(
    "alert-config-compliance_threshold",
  ) as HTMLInputElement;
  fireEvent.change(comp, { target: { value: "85.5" } });

  fireEvent.click(screen.getByTestId("alert-config-save"));
  await waitFor(() =>
    expect(m(fed.doUpdateFederationAlertConfig)).toHaveBeenCalledWith({
      offline_multiplier: 5,
      min_offline_seconds: null,
      compliance_threshold: 85.5,
      critical_cve_threshold: null,
    }),
  );
  expect(await screen.findByTestId("alert-config-msg")).toBeTruthy();
});
