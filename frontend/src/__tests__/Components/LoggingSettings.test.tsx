import { render, screen, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

// Stable `t`/return object across renders (see FederationAlertConfig.test.tsx):
// a fresh `t` per call would loop the component's useCallback/useEffect deps.
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

vi.mock("../../Services/loggingSettings", () => ({
  doGetLoggingSettings: vi.fn(),
  doUpdateLoggingSettings: vi.fn(),
}));

import * as svc from "../../Services/loggingSettings";
import LoggingSettings from "../../Components/LoggingSettings";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

// A response whose server config already uses the remote-syslog target, so the
// remote-fields block renders without having to drive the target <Select>.
const remoteResponse = (licensed: boolean) => ({
  server: {
    native_enabled: true,
    native_target: "syslog_remote",
    native_identifier: "sysmanage",
    log_level: null,
    verbosity: null,
    syslog_host: "loghost.example",
    syslog_port: 6514,
    syslog_facility: "local0",
    syslog_protocol: "tcp",
  },
  server_os_family: "linux",
  server_valid_targets: ["auto", "journald", "syslog", "syslog_remote", "none"],
  agents: { linux: null, windows: null, macos: null, bsd: null },
  agent_valid_targets: {
    linux: ["auto", "journald", "syslog", "syslog_remote", "none"],
    windows: ["auto", "eventlog", "syslog_remote", "none"],
    macos: ["auto", "syslog", "syslog_remote", "none"],
    bsd: ["auto", "syslog", "syslog_remote", "none"],
  },
  log_routing_licensed: licensed,
});

beforeEach(() => vi.clearAllMocks());

test("licensed: remote-syslog fields render prefilled and enabled", async () => {
  m(svc.doGetLoggingSettings).mockResolvedValue(remoteResponse(true));
  render(<LoggingSettings />);

  const host = (await screen.findByLabelText(/Syslog host/)) as HTMLInputElement;
  expect(host.value).toBe("loghost.example");
  expect(host.disabled).toBe(false);
  // No "requires Professional" lock alert when licensed.
  expect(screen.queryByText(/requires a SysManage Professional license/)).toBeNull();
});

test("unlicensed: remote fields are disabled and the lock hint shows", async () => {
  m(svc.doGetLoggingSettings).mockResolvedValue(remoteResponse(false));
  render(<LoggingSettings />);

  await waitFor(() =>
    expect(m(svc.doGetLoggingSettings)).toHaveBeenCalled(),
  );
  expect(
    screen.getByText(/requires a SysManage Professional license/),
  ).toBeInTheDocument();
  const host = screen.getByLabelText(/Syslog host/) as HTMLInputElement;
  expect(host.disabled).toBe(true);
});
