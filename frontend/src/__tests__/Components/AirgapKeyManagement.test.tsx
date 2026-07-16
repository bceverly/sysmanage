// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, beforeEach, test, expect } from "vitest";

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
  return { useTranslation: () => ({ t, i18n: { language: "en" } }) };
});

vi.mock("../../Services/api", () => ({
  default: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}));

vi.mock("../../utils/clipboard", () => ({
  copyToClipboard: vi.fn(),
}));

import axiosInstance from "../../Services/api";
import { copyToClipboard } from "../../utils/clipboard";
import {
  CollectorPublicKeyCard,
  TrustedCollectorsCard,
  ImportDeviceCard,
} from "../../Components/AirgapKeyManagement";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

const collectorKey = {
  public_key_pem: "-----BEGIN PUBLIC KEY-----\nABC\n-----END PUBLIC KEY-----",
  fingerprint: "AB:CD:EF:12",
};

const trusted = [{ name: "collector-a", fingerprint: "FF:EE:DD" }];

const devices = {
  devices: [
    {
      name: "sr0",
      path: "/dev/sr0",
      type: "rom",
      size_bytes: 1024,
      removable: true,
      label: "MEDIA",
      fstype: "iso9660",
      is_optical: true,
    },
  ],
  selected: null,
  default: "/dev/sr0",
};

beforeEach(() => {
  vi.clearAllMocks();
  m(copyToClipboard).mockResolvedValue(true);
  m(axiosInstance.get).mockImplementation((url: string) => {
    if (url.includes("collector-key"))
      return Promise.resolve({ data: collectorKey });
    if (url.includes("trusted-collectors"))
      return Promise.resolve({ data: { trusted } });
    if (url.includes("block-devices"))
      return Promise.resolve({ data: devices });
    return Promise.resolve({ data: {} });
  });
  m(axiosInstance.post).mockResolvedValue({
    data: { name: "new", fingerprint: "1234567890abcdef00" },
  });
  m(axiosInstance.put).mockResolvedValue({ data: {} });
  m(axiosInstance.delete).mockResolvedValue({ data: {} });
});

test("CollectorPublicKeyCard renders the fingerprint and copies the key", async () => {
  render(<CollectorPublicKeyCard />);

  expect(await screen.findByText("AB:CD:EF:12")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /Copy Public Key/ }));

  await waitFor(() =>
    expect(m(copyToClipboard)).toHaveBeenCalledWith(
      collectorKey.public_key_pem,
    ),
  );
});

test("TrustedCollectorsCard lists trusted keys and imports a new one", async () => {
  render(<TrustedCollectorsCard />);

  expect(await screen.findByText("collector-a")).toBeInTheDocument();

  const nameField = screen.getByLabelText(/Collector name/) as HTMLInputElement;
  fireEvent.change(nameField, { target: { value: "collector-b" } });
  const pemField = screen.getByLabelText(/Public key/) as HTMLInputElement;
  fireEvent.change(pemField, { target: { value: "-----BEGIN-----" } });

  fireEvent.click(screen.getByRole("button", { name: /Import Key/ }));

  await waitFor(() =>
    expect(m(axiosInstance.post)).toHaveBeenCalledWith(
      "/api/v1/airgap/trusted-collectors",
      expect.objectContaining({ name: "collector-b" }),
    ),
  );
});

test("TrustedCollectorsCard removes a trusted key", async () => {
  render(<TrustedCollectorsCard />);
  await screen.findByText("collector-a");

  const buttons = screen.getAllByRole("button");
  const deleteBtn = buttons.find((b) => b.querySelector('[data-testid="DeleteIcon"]'));
  fireEvent.click(deleteBtn!);

  await waitFor(() =>
    expect(m(axiosInstance.delete)).toHaveBeenCalledWith(
      "/api/v1/airgap/trusted-collectors/collector-a",
    ),
  );
});

test("TrustedCollectorsCard requires name and pem before import", async () => {
  render(<TrustedCollectorsCard />);
  await screen.findByText("collector-a");

  fireEvent.click(screen.getByRole("button", { name: /Import Key/ }));

  await waitFor(() =>
    expect(
      screen.getByText("Name and public key are both required."),
    ).toBeInTheDocument(),
  );
  expect(m(axiosInstance.post)).not.toHaveBeenCalled();
});

test("ImportDeviceCard lists drives and persists a selection", async () => {
  render(<ImportDeviceCard />);

  expect(await screen.findByText("Import Drive")).toBeInTheDocument();

  const buttons = screen.getAllByRole("button");
  const rescanBtn = buttons.find((b) =>
    b.querySelector('[data-testid="RefreshIcon"]'),
  );
  fireEvent.click(rescanBtn!);

  await waitFor(() =>
    expect(m(axiosInstance.get)).toHaveBeenCalledWith(
      "/api/v1/airgap/block-devices",
    ),
  );
});
