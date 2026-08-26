// Copyright (c) 2024-2026 Bryan Everly
// Licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).
// See the LICENSE file in the project root for the full terms.

import { http, HttpResponse } from "msw";

// Declare process.env for TypeScript
declare const process: { env: { CI?: string } } | undefined;

// Simplified approach - use broad patterns and check URLs in the handler
export const handlers = [
  // Column preferences: an OBJECT, not the catch-all's empty array.  Declared
  // before the catch-all so it wins.
  http.get("*/api/v1/user-preferences/column-preferences/*", ({ request }) => {
    const path = new globalThis.URL(request.url).pathname;
    return HttpResponse.json({
      id: "00000000-0000-0000-0000-000000000000",
      user_id: "00000000-0000-0000-0000-000000000001",
      grid_identifier: path.split("/").pop() ?? "",
      hidden_columns: [],
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  }),

  // Catch all /api/ requests and handle them dynamically.
  //
  // ORIGIN IS A WILDCARD ON PURPOSE.  These were pinned to
  // `http://localhost:8080` while jsdom serves the app from `localhost:3000`,
  // so every relative-URL request the app makes missed all four handlers and
  // fell through unmocked -- silently, because onUnhandledRequest was 'warn'.
  // Match any origin so the mock covers both the configured API base and the
  // document origin.
  http.get("*/api/*", ({ request }) => {
    const url = new globalThis.URL(request.url);
    const path = url.pathname;

    const logPrefix =
      process !== undefined && process.env?.CI === "true" ? "MSW-CI:" : "MSW:";
    console.log(`${logPrefix} Handling GET ${path}`);

    // Host data - using pattern matching for UUID
    if (
      /^\/api\/hosts?\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
        path,
      ) ||
      path === "/api/v1/host/550e8400-e29b-41d4-a716-446655440000" ||
      path === "/api/hosts/550e8400-e29b-41d4-a716-446655440000"
    ) {
      return HttpResponse.json({
        id: "550e8400-e29b-41d4-a716-446655440000",
        fqdn: "test-host.example.com",
        ipv4: "192.168.1.100", // NOSONAR - test mock data
        ipv6: "::1",
        active: true,
        status: "up",
        approval_status: "approved",
        platform: "Linux",
        last_access: "2023-01-01T12:00:00Z",
        created_at: "2023-01-01T10:00:00Z",
        updated_at: "2023-01-01T12:00:00Z",
        hardware_updated_at: "2023-01-01T11:00:00Z",
        software_updated_at: "2023-01-01T11:30:00Z",
        user_access_updated_at: "2023-01-01T11:15:00Z",
        cpu_vendor: "Intel",
        cpu_model: "Intel Core i7-8700K",
        cpu_cores: 6,
        cpu_threads: 12,
        cpu_frequency_mhz: 3700,
        memory_total_mb: 16384,
        is_agent_privileged: true,
        diagnostics_request_status: "idle",
      });
    }

    // User data
    if (path === "/api/v1/user/me" || path === "/api/v1/users/me") {
      return HttpResponse.json({
        id: "550e8400-e29b-41d4-a716-446655440001",
        username: "current_user",
        email: "user@example.com",
        first_name: "Test",
        last_name: "User",
        is_active: true,
        is_superuser: false,
        created_at: "2023-01-01T10:00:00Z",
        updated_at: "2023-01-01T12:00:00Z",
      });
    }

    // Software packages - using pattern matching for UUID
    if (
      /^\/api\/hosts?\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/software$/.test(
        path,
      ) ||
      path === "/api/v1/host/550e8400-e29b-41d4-a716-446655440000/software" ||
      path === "/api/hosts/550e8400-e29b-41d4-a716-446655440000/software"
    ) {
      return HttpResponse.json([
        {
          id: "550e8400-e29b-41d4-a716-446655440002",
          package_name: "vim",
          version: "8.2",
          package_manager: "apt",
          description: "Vi IMproved - enhanced vi editor",
          status: "installed",
        },
        {
          id: "550e8400-e29b-41d4-a716-446655440003",
          package_name: "curl",
          version: "7.68.0",
          package_manager: "apt",
          description: "Command line tool for transferring data",
          status: "installed",
        },
      ]);
    }

    // Package search
    if (path === "/api/v1/packages/search") {
      const query = url.searchParams.get("query");
      if (!query || query.length < 2) {
        return HttpResponse.json([]);
      }

      const availablePackages = [
        {
          name: "htop",
          description: "Interactive process viewer",
          version: "3.0.5",
        },
        {
          name: "htop-dev",
          description: "Development files for htop",
          version: "3.0.5",
        },
        {
          name: "nginx",
          description: "HTTP and reverse proxy server",
          version: "1.18.0",
        },
        {
          name: "nodejs",
          description: "JavaScript runtime",
          version: "18.17.0",
        },
        {
          name: "python3",
          description: "Python 3 interpreter",
          version: "3.9.2",
        },
      ];

      const results = availablePackages.filter(
        (pkg) =>
          pkg.name.toLowerCase().includes(query.toLowerCase()) ||
          pkg.description.toLowerCase().includes(query.toLowerCase()),
      );

      return HttpResponse.json(results);
    }

    // Empty arrays for other endpoints
    if (
      path.includes("/storage") ||
      path.includes("/network") ||
      path.includes("/users") ||
      path.includes("/groups") ||
      path.includes("/diagnostics") ||
      path.includes("/tags") ||
      path.includes("/installation-history")
    ) {
      return HttpResponse.json([]);
    }

    // Ubuntu Pro (null response)
    if (path.includes("/ubuntu-pro")) {
      return HttpResponse.json(null);
    }

    // Dashboard card preferences
    if (path === "/api/v1/user-preferences/dashboard-cards") {
      return HttpResponse.json({
        preferences: [
          { card_identifier: "hosts", visible: true },
          { card_identifier: "updates", visible: true },
          { card_identifier: "security", visible: true },
          { card_identifier: "reboot", visible: true },
          { card_identifier: "antivirus", visible: true },
          { card_identifier: "opentelemetry", visible: true },
        ],
      });
    }

    // Antivirus coverage
    if (path === "/api/v1/antivirus-coverage") {
      return HttpResponse.json({
        total_hosts: 0,
        hosts_with_antivirus: 0,
        coverage_percentage: 0,
      });
    }

    // OpenTelemetry coverage
    if (path === "/api/v1/opentelemetry/opentelemetry-coverage") {
      return HttpResponse.json({
        total_hosts: 0,
        hosts_with_opentelemetry: 0,
        coverage_percentage: 0,
      });
    }

    // Default: return empty array for API endpoints
    console.log(`MSW: Unhandled API endpoint ${path}, returning empty array`);
    return HttpResponse.json([]);
  }),

  // Handle POST requests for package installation
  http.post("*/api/v1/packages/install/*", async ({ request }) => {
    const body = (await request.json()) as {
      package_names: string[];
      requested_by: string;
    };

    return HttpResponse.json({
      success: true,
      message: "Package installation has been queued",
      installation_ids: body.package_names.map(
        () => `uuid-${Math.random().toString(36).slice(2, 11)}`,
      ), // NOSONAR - test mock data, not used for security
    });
  }),

  // Handle POST requests for package uninstallation
  http.post("*/api/v1/packages/uninstall/*", async () => {
    return HttpResponse.json({
      success: true,
      message: "Package uninstallation has been queued",
      uninstallation_id: `uuid-${Math.random().toString(36).slice(2, 11)}`, // NOSONAR - test mock data, not used for security
    });
  }),

  // Handle PUT requests for dashboard preferences
  http.put("*/api/v1/user-preferences/dashboard-cards", async ({ request }) => {
    const body = (await request.json()) as {
      preferences: Array<{ card_identifier: string; visible: boolean }>;
    };
    return HttpResponse.json({
      preferences: body.preferences,
    });
  }),

  // Config-management prerequisite (Phase 20.1).  Defaults to satisfied so
  // the host-detail tests are not forced to care about a card they are not
  // exercising; tests that DO care override this per-test.
  http.get("*/api/v1/hosts/*/config-management/prerequisite", () => {
    return HttpResponse.json({
      host_id: "test-host",
      executor: "ansible-core",
      status: "satisfied",
      installed_version: "2.20.1",
      minimum_version: "2.20",
      can_install: false,
      detail: null,
      package_name: "ansible-core",
    });
  }),

  http.post("*/api/v1/hosts/*/config-management/prerequisite/install", () => {
    return HttpResponse.json({
      host_id: "test-host",
      queued: true,
      message:
        "Installation of the config-management prerequisite was requested",
    });
  }),

  // Config-management run history (Phase 20.1).
  http.get("*/api/v1/hosts/*/config-management/runs", () => {
    return HttpResponse.json([]);
  }),

  http.get("*/api/v1/config-management/runs/*", () => {
    return HttpResponse.json({
      id: "run-1",
      host_id: "test-host",
      profile_id: null,
      profile_name: "baseline",
      executor: "ansible-core",
      check_mode: false,
      success: true,
      changed: false,
      exit_code: 0,
      tasks_ok: 1,
      tasks_changed: 0,
      tasks_failed: 0,
      tasks_skipped: 0,
      tasks_unreachable: 0,
      reason: null,
      completed_at: "2026-08-26T12:00:00Z",
      tasks: [],
      error_output: null,
    });
  }),

  // Fallback for non-API requests
  http.all("*", ({ request }) => {
    const url = new globalThis.URL(request.url);
    if (!url.pathname.startsWith("/api/")) {
      return HttpResponse.json({}, { status: 200 });
    }

    console.warn(
      `MSW: Truly unhandled request: ${request.method} ${request.url}`,
    );
    return HttpResponse.json([], { status: 200 });
  }),
];
