// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, within } from "@testing-library/react";
import { vi, describe, beforeEach, test, expect } from "vitest";

vi.mock("react-i18next", () => {
  const t = (key: string, fallback?: string, opts?: Record<string, unknown>) => {
    let s = typeof fallback === "string" ? fallback : key;
    if (opts) {
      for (const [k, v] of Object.entries(opts)) {
        s = s.replace(`{{${k}}}`, String(v));
      }
    }
    return s;
  };
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../../utils/locale", () => ({ appLocale: () => "en-US" }));

// Render every row/column through renderCell so the column renderers run
// under jsdom (the real grid virtualizes columns away without layout).
vi.mock("@mui/x-data-grid", () => ({
  DataGrid: ({
    rows,
    columns,
    onPaginationModelChange,
  }: {
    rows?: any[];
    columns?: any[];
    onPaginationModelChange?: (_m: { page: number; pageSize: number }) => void;
  }) => (
    <div data-testid="grid">
      <button onClick={() => onPaginationModelChange?.({ page: 1, pageSize: 25 })}>
        next-page
      </button>
      {(rows ?? []).map((row) => (
        <div key={row.id} data-testid="row">
          {(columns ?? []).map((c) => (
            <div key={c.field} data-testid={`cell-${c.field}`}>
              {c.renderCell({ value: row[c.field], row })}
            </div>
          ))}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("../../../Components/ColumnVisibilityButton", () => ({
  default: ({
    columns,
    onColumnsChange,
    onReset,
  }: {
    columns: Array<{ field: string }>;
    onColumnsChange: (_c: string[]) => void;
    onReset: () => void;
  }) => (
    <div>
      <span>{`columns:${columns.map((c) => c.field).join(",")}`}</span>
      <button onClick={() => onColumnsChange(["issuer"])}>hide-issuer</button>
      <button onClick={onReset}>reset-columns</button>
    </div>
  ),
}));

import HostCertificatesTab from "../../../Components/HostDetail/HostCertificatesTab";
import type { Certificate } from "../../../Components/HostDetail/hostDetailTypes";

const cert = (over: Partial<Certificate>): Certificate => ({
  id: "c1",
  certificate_name: "web.example.com",
  subject: "CN=web.example.com",
  issuer: "Let's Encrypt R3",
  not_before: null,
  not_after: "2027-01-15T00:00:00",
  serial_number: "ABC123",
  fingerprint_sha256: "ff",
  is_ca: false,
  key_usage: "Server",
  file_path: "/etc/ssl/web.pem",
  collected_at: null,
  is_expired: false,
  days_until_expiry: 100,
  common_name: null,
  ...over,
});

const CERTS = [
  cert({ id: "srv" }),
  cert({
    id: "cli",
    certificate_name: "client-auth",
    subject: "CN=client",
    issuer: "Internal CA",
    key_usage: "Client",
    days_until_expiry: 10,
    file_path: "/etc/ssl/client.pem",
  }),
  cert({
    id: "ca",
    certificate_name: "",
    common_name: "Root Authority",
    subject: "CN=Root Authority",
    issuer: "Root Authority",
    is_ca: true,
    key_usage: null,
    is_expired: true,
    days_until_expiry: -5,
    not_after: "2020-01-01T00:00:00Z",
    file_path: "/etc/ssl/ca.pem",
  }),
  cert({
    id: "anon",
    certificate_name: "",
    common_name: null,
    subject: "CN=anon",
    issuer: "Mystery",
    key_usage: "CA",
    not_after: null,
    days_until_expiry: null,
    file_path: "/etc/ssl/anon.pem",
  }),
  cert({
    id: "bad",
    certificate_name: "bad-date",
    issuer: "Somebody",
    not_after: "not a date",
    days_until_expiry: null,
    key_usage: "Other",
    file_path: "/etc/ssl/bad.pem",
  }),
];

const makeProps = (over: Record<string, unknown> = {}) => ({
  host: { id: "h1", active: true, is_agent_privileged: true } as any,
  licenseModules: ["secrets_engine"],
  certificates: CERTS,
  certificatesLoading: false,
  certificateFilter: "all" as const,
  setCertificateFilter: vi.fn(),
  certificateSearchTerm: "",
  setCertificateSearchTerm: vi.fn(),
  certificatePaginationModel: { page: 0, pageSize: 25 },
  setCertificatePaginationModel: vi.fn(),
  safePageSizeOptions: [25, 50],
  canDeployCertificate: true,
  setAddCertificateDialogOpen: vi.fn(),
  loadAvailableCertificates: vi.fn(),
  requestCertificatesCollection: vi.fn(),
  hiddenCertificatesColumns: [] as string[],
  setHiddenCertificatesColumns: vi.fn(),
  resetCertificatesPreferences: vi.fn(),
  getCertificatesColumnVisibilityModel: vi.fn(() => ({})),
  ...over,
});

const rowNames = () =>
  screen
    .getAllByTestId("cell-file_path")
    .map((c) => c.textContent);

describe("HostCertificatesTab", () => {
  beforeEach(() => vi.clearAllMocks());

  test("renders all certificates with names, chips and expiry details", () => {
    render(<HostCertificatesTab {...makeProps()} />);
    expect(screen.getByText("SSL Certificates (5)")).toBeInTheDocument();
    expect(screen.getAllByTestId("row")).toHaveLength(5);
    expect(
      screen.getByText("columns:certificate_name,issuer,not_after,file_path,serial_number"),
    ).toBeInTheDocument();

    const rows = screen.getAllByTestId("row");
    const srv = within(rows[0]);
    expect(srv.getByText("web.example.com")).toBeInTheDocument();
    expect(srv.getByText("100 days")).toBeInTheDocument();
    expect(
      srv.getByText(new Date("2027-01-15T00:00:00Z").toLocaleDateString("en-US")),
    ).toBeInTheDocument();

    const cli = within(rows[1]);
    expect(cli.getByText("Expiring Soon")).toBeInTheDocument();
    expect(cli.getByText("10 days")).toBeInTheDocument();

    const ca = within(rows[2]);
    expect(
      within(ca.getByTestId("cell-certificate_name")).getByText("Root Authority"),
    ).toBeInTheDocument();
    expect(ca.getAllByText("Expired")).toHaveLength(2);
    expect(ca.getByText("CA")).toBeInTheDocument();

    const anon = within(rows[3]);
    // Missing name and common name, and no expiry date.
    expect(anon.getAllByText("Unknown")).toHaveLength(2);

    const bad = within(rows[4]);
    expect(bad.getByText("Unknown")).toBeInTheDocument();
  });

  test.each([
    ["server", ["/etc/ssl/web.pem"]],
    ["client", ["/etc/ssl/client.pem"]],
    ["ca", ["/etc/ssl/ca.pem", "/etc/ssl/anon.pem"]],
  ])("filter %s narrows the rows", (filter, expected) => {
    render(<HostCertificatesTab {...makeProps({ certificateFilter: filter })} />);
    expect(rowNames()).toEqual(expected);
  });

  test("an unknown filter value shows everything", () => {
    render(<HostCertificatesTab {...makeProps({ certificateFilter: "bogus" })} />);
    expect(rowNames()).toHaveLength(5);
  });

  test("search matches name, subject or issuer case-insensitively", () => {
    const { rerender } = render(
      <HostCertificatesTab {...makeProps({ certificateSearchTerm: "CLIENT-AUTH" })} />,
    );
    expect(rowNames()).toEqual(["/etc/ssl/client.pem"]);
    rerender(<HostCertificatesTab {...makeProps({ certificateSearchTerm: "cn=anon" })} />);
    expect(rowNames()).toEqual(["/etc/ssl/anon.pem"]);
    rerender(<HostCertificatesTab {...makeProps({ certificateSearchTerm: "mystery" })} />);
    expect(rowNames()).toEqual(["/etc/ssl/anon.pem"]);
    rerender(<HostCertificatesTab {...makeProps({ certificateSearchTerm: "zzz" })} />);
    expect(screen.queryAllByTestId("row")).toHaveLength(0);
  });

  test("typing in search updates the term and resets to page 0", () => {
    const props = makeProps({ certificatePaginationModel: { page: 3, pageSize: 50 } });
    render(<HostCertificatesTab {...props} />);
    fireEvent.change(screen.getByPlaceholderText("Search certificates..."), {
      target: { value: "web" },
    });
    expect(props.setCertificateSearchTerm).toHaveBeenCalledWith("web");
    expect(props.setCertificatePaginationModel).toHaveBeenCalledWith({ page: 0, pageSize: 50 });
  });

  test("toggle buttons change the filter and ignore deselect", () => {
    const props = makeProps({ certificateFilter: "server" });
    render(<HostCertificatesTab {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Client" }));
    expect(props.setCertificateFilter).toHaveBeenCalledWith("client");
    expect(props.setCertificatePaginationModel).toHaveBeenCalledWith({ page: 0, pageSize: 25 });
    // Clicking the already-selected exclusive option yields null -> ignored.
    vi.mocked(props.setCertificateFilter).mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Server" }));
    expect(props.setCertificateFilter).not.toHaveBeenCalled();
  });

  test("add and collect buttons call their handlers", () => {
    const props = makeProps();
    render(<HostCertificatesTab {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(props.setAddCertificateDialogOpen).toHaveBeenCalledWith(true);
    expect(props.loadAvailableCertificates).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Collect" }));
    expect(props.requestCertificatesCollection).toHaveBeenCalled();
  });

  test("grid and column controls forward their callbacks", () => {
    const props = makeProps();
    render(<HostCertificatesTab {...props} />);
    fireEvent.click(screen.getByText("next-page"));
    expect(props.setCertificatePaginationModel).toHaveBeenCalledWith({ page: 1, pageSize: 25 });
    fireEvent.click(screen.getByText("hide-issuer"));
    expect(props.setHiddenCertificatesColumns).toHaveBeenCalledWith(["issuer"]);
    fireEvent.click(screen.getByText("reset-columns"));
    expect(props.resetCertificatesPreferences).toHaveBeenCalled();
    expect(props.getCertificatesColumnVisibilityModel).toHaveBeenCalled();
  });

  test("add is hidden without the secrets engine or permission", () => {
    const { rerender } = render(
      <HostCertificatesTab {...makeProps({ licenseModules: [] })} />,
    );
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
    rerender(<HostCertificatesTab {...makeProps({ canDeployCertificate: false })} />);
    expect(screen.queryByRole("button", { name: "Add" })).toBeNull();
  });

  test("buttons are disabled for an inactive or unprivileged host", () => {
    render(
      <HostCertificatesTab
        {...makeProps({ host: { id: "h1", active: false, is_agent_privileged: false } })}
      />,
    );
    expect(screen.getByRole("button", { name: "Add" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Collect" })).toBeDisabled();
  });

  test("loading shows spinners instead of the grid", () => {
    render(<HostCertificatesTab {...makeProps({ certificatesLoading: true })} />);
    expect(screen.queryByTestId("grid")).toBeNull();
    expect(screen.getAllByRole("progressbar").length).toBeGreaterThanOrEqual(2);
  });
});
