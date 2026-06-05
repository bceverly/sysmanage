import {
  configure,
  render,
  screen,
  fireEvent,
  waitFor,
} from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

// This card loads through two chained async hops (role fetch → identity-key +
// enrollment-status fetch).  The default 1s findBy timeout gets starved when
// the full vitest suite runs everything in parallel (the component passes
// fine in isolation), so give the async utilities more headroom here.
configure({ asyncUtilTimeout: 5000 });

// Stable `t` — FederationRoleCard puts `t` in useCallback/useEffect deps, so a
// fresh `t` per render would infinite-loop (see project memory).
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

vi.mock("../../Services/api", () => ({
  default: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import api from "../../Services/api";
import FederationRoleCard from "../../Components/FederationRoleCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

function primeGet(role: string, peers: unknown[] = []) {
  m(api.get).mockImplementation((url: string) => {
    if (url.endsWith("/federation-role")) return Promise.resolve({ data: { role } });
    if (url.endsWith("/identity-key"))
      return Promise.resolve({
        data: {
          public_key_pem: "-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n",
          fingerprint: "a".repeat(64),
        },
      });
    if (url.endsWith("/trusted-peers")) return Promise.resolve({ data: { trusted: peers } });
    return Promise.resolve({ data: {} });
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom clipboard
  Object.assign(globalThis.navigator, {
    clipboard: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

test("defaults to 'not federated' and hides the key section", async () => {
  primeGet("none");
  render(<FederationRoleCard />);
  expect(await screen.findByText(/Not federated/i)).toBeTruthy();
  // Key/peer section only appears once federated.
  expect(screen.queryByTestId("federation-copy-key")).toBeNull();
});

test("shows the identity key + peer section when the server is a site", async () => {
  primeGet("site");
  render(<FederationRoleCard />);
  expect(await screen.findByTestId("federation-copy-key")).toBeTruthy();
  expect(screen.getByTestId("federation-peer-import")).toBeTruthy();
  // Empty-state for peers.
  expect(screen.getByText(/No trusted peer keys yet/i)).toBeTruthy();
});

test("saving the role PUTs the selected value", async () => {
  primeGet("none");
  m(api.put).mockResolvedValue({ data: { role: "coordinator" } });
  render(<FederationRoleCard />);
  await screen.findByText(/Not federated/i);
  // Select coordinator.
  fireEvent.click(screen.getByRole("radio", { name: /Federation Coordinator/i }));
  fireEvent.click(screen.getByTestId("federation-role-save"));
  await waitFor(() =>
    expect(m(api.put)).toHaveBeenCalledWith("/api/v1/federation-role", {
      role: "coordinator",
    }),
  );
});

test("copying the public key writes it to the clipboard", async () => {
  primeGet("coordinator");
  render(<FederationRoleCard />);
  fireEvent.click(await screen.findByTestId("federation-copy-key"));
  await waitFor(() =>
    expect(globalThis.navigator.clipboard.writeText).toHaveBeenCalledWith(
      expect.stringContaining("PUBLIC KEY"),
    ),
  );
});

test("a site can enroll with a coordinator (POSTs url + token)", async () => {
  primeGet("site");
  m(api.post).mockResolvedValue({ data: { licensed: true, status: "enrolled" } });
  render(<FederationRoleCard />);
  const url = (await screen.findByTestId(
    "federation-enroll-url",
  )) as HTMLInputElement;
  const token = screen.getByTestId("federation-enroll-token") as HTMLInputElement;
  fireEvent.change(url, { target: { value: "http://10.70.0.1:8080" } });
  fireEvent.change(token, { target: { value: "TOK123" } });
  fireEvent.click(screen.getByTestId("federation-enroll-submit"));
  await waitFor(() =>
    expect(m(api.post)).toHaveBeenCalledWith("/api/v1/federation/site/enroll", {
      coordinator_url: "http://10.70.0.1:8080",
      enrollment_token: "TOK123",
    }),
  );
});

test("the enroll section is hidden on a coordinator", async () => {
  primeGet("coordinator");
  render(<FederationRoleCard />);
  // Identity-key section renders for a coordinator...
  await screen.findByTestId("federation-copy-key");
  // ...but the site-only enroll handshake does not.
  expect(screen.queryByTestId("federation-enroll-submit")).toBeNull();
});

test("importing a peer POSTs name + pem", async () => {
  primeGet("site");
  m(api.post).mockResolvedValue({ data: { name: "coord", fingerprint: "b".repeat(64) } });
  render(<FederationRoleCard />);
  const name = (await screen.findByTestId("federation-peer-name")) as HTMLInputElement;
  const pem = screen.getByTestId("federation-peer-pem") as HTMLInputElement;
  fireEvent.change(name, { target: { value: "coord" } });
  fireEvent.change(pem, { target: { value: "-----BEGIN PUBLIC KEY-----\nx\n-----END PUBLIC KEY-----\n" } });
  fireEvent.click(screen.getByTestId("federation-peer-import"));
  await waitFor(() =>
    expect(m(api.post)).toHaveBeenCalledWith(
      "/api/v1/federation/trusted-peers",
      expect.objectContaining({ name: "coord" }),
    ),
  );
});
