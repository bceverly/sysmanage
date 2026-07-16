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

import HypervisorStatusCard from "../../Components/HypervisorStatusCard";

const m = (fn: unknown) => fn as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

test("renders a ready bhyve hypervisor with indicators", async () => {
  render(
    <HypervisorStatusCard
      type="bhyve"
      capabilities={{
        available: true,
        installed: true,
        enabled: true,
        running: true,
        kernel_supported: true,
        uefi_available: true,
      }}
      canCreate
      canEnable
      isAgentPrivileged
      onCreate={() => {}}
    />,
  );

  expect(await screen.findByText("bhyve")).toBeInTheDocument();
  expect(screen.getByText("Ready")).toBeInTheDocument();
  expect(screen.getByText("Available")).toBeInTheDocument();
  expect(screen.getByText("UEFI Firmware")).toBeInTheDocument();
});

test("fires onCreate when the Create VM button is clicked", async () => {
  const onCreate = vi.fn();
  render(
    <HypervisorStatusCard
      type="bhyve"
      capabilities={{
        available: true,
        installed: true,
        enabled: true,
        running: true,
        kernel_supported: true,
      }}
      canCreate
      canEnable
      isAgentPrivileged
      onCreate={onCreate}
    />,
  );

  fireEvent.click(await screen.findByText("Create VM"));
  await waitFor(() => expect(m(onCreate)).toHaveBeenCalled());
});

test("fires onEnable for a not-enabled bhyve hypervisor", async () => {
  const onEnable = vi.fn();
  render(
    <HypervisorStatusCard
      type="bhyve"
      capabilities={{
        available: true,
        installed: true,
        enabled: false,
        running: false,
        kernel_supported: true,
        needs_enable: true,
      }}
      canEnable
      isAgentPrivileged
      onEnable={onEnable}
    />,
  );

  expect(await screen.findByText("Not Enabled")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Enable bhyve"));
  await waitFor(() => expect(m(onEnable)).toHaveBeenCalled());
});

test("fires onEnableModules for KVM when modules are available but not loaded", async () => {
  const onEnableModules = vi.fn();
  render(
    <HypervisorStatusCard
      type="kvm"
      capabilities={{
        available: true,
        installed: true,
        enabled: true,
        running: true,
        initialized: false,
        modules_available: true,
        modules_loaded: false,
      }}
      canEnable
      isAgentPrivileged
      onEnableModules={onEnableModules}
    />,
  );

  expect(await screen.findByText("KVM/QEMU")).toBeInTheDocument();
  fireEvent.click(screen.getByText("Load Modules"));
  await waitFor(() => expect(m(onEnableModules)).toHaveBeenCalled());
});

test("shows a not-available message for an unavailable hypervisor", async () => {
  render(
    <HypervisorStatusCard type="wsl" capabilities={{ available: false }} />,
  );

  expect(await screen.findByText("Not Available")).toBeInTheDocument();
  expect(
    screen.getByText("Not available on this platform"),
  ).toBeInTheDocument();
});
