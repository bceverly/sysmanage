import { http, HttpResponse } from 'msw';

// Simplified approach - use broad patterns and check URLs in the handler
export const handlers = [
  // Catch all /api/ requests and handle them dynamically
  http.get('http://localhost:8080/api/*', ({ request }) => {
    const url = new globalThis.URL(request.url);
    const path = url.pathname;

    const logPrefix = process.env.CI === 'true' ? '🔄 MSW-CI:' : 'MSW:';
    console.log(`${logPrefix} Handling GET ${path}`);

    // Host data - using pattern matching for UUID
    if (path.match(/^\/api\/hosts?\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/) || path === '/api/host/550e8400-e29b-41d4-a716-446655440000' || path === '/api/hosts/550e8400-e29b-41d4-a716-446655440000') {
      return HttpResponse.json({
        id: '550e8400-e29b-41d4-a716-446655440000',
        fqdn: 'test-host.example.com',
        ipv4: '192.168.1.100',
        ipv6: '::1',
        active: true,
        status: 'up',
        approval_status: 'approved',
        platform: 'Linux',
        last_access: '2023-01-01T12:00:00Z',
        created_at: '2023-01-01T10:00:00Z',
        updated_at: '2023-01-01T12:00:00Z',
        hardware_updated_at: '2023-01-01T11:00:00Z',
        software_updated_at: '2023-01-01T11:30:00Z',
        user_access_updated_at: '2023-01-01T11:15:00Z',
        cpu_vendor: 'Intel',
        cpu_model: 'Intel Core i7-8700K',
        cpu_cores: 6,
        cpu_threads: 12,
        cpu_frequency_mhz: 3700,
        memory_total_mb: 16384,
        is_agent_privileged: true,
        diagnostics_request_status: 'idle',
      });
    }

    // User data
    if (path === '/api/user/me' || path === '/api/users/me') {
      return HttpResponse.json({
        id: '550e8400-e29b-41d4-a716-446655440001',
        username: 'current_user',
        email: 'user@example.com',
        first_name: 'Test',
        last_name: 'User',
        is_active: true,
        is_superuser: false,
        created_at: '2023-01-01T10:00:00Z',
        updated_at: '2023-01-01T12:00:00Z',
      });
    }

    // Software packages - using pattern matching for UUID
    if (path.match(/^\/api\/hosts?\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/software$/) || path === '/api/host/550e8400-e29b-41d4-a716-446655440000/software' || path === '/api/hosts/550e8400-e29b-41d4-a716-446655440000/software') {
      return HttpResponse.json([
        {
          id: '550e8400-e29b-41d4-a716-446655440002',
          package_name: 'vim',
          version: '8.2',
          package_manager: 'apt',
          description: 'Vi IMproved - enhanced vi editor',
          status: 'installed'
        },
        {
          id: '550e8400-e29b-41d4-a716-446655440003',
          package_name: 'curl',
          version: '7.68.0',
          package_manager: 'apt',
          description: 'Command line tool for transferring data',
          status: 'installed'
        }
      ]);
    }

    // Package search
    if (path === '/api/packages/search') {
      const query = url.searchParams.get('query');
      if (!query || query.length < 2) {
        return HttpResponse.json([]);
      }

      const availablePackages = [
        { name: 'htop', description: 'Interactive process viewer', version: '3.0.5' },
        { name: 'htop-dev', description: 'Development files for htop', version: '3.0.5' },
        { name: 'nginx', description: 'HTTP and reverse proxy server', version: '1.18.0' },
        { name: 'nodejs', description: 'JavaScript runtime', version: '18.17.0' },
        { name: 'python3', description: 'Python 3 interpreter', version: '3.9.2' },
      ];

      const results = availablePackages.filter(pkg =>
        pkg.name.toLowerCase().includes(query.toLowerCase()) ||
        pkg.description.toLowerCase().includes(query.toLowerCase())
      );

      return HttpResponse.json(results);
    }

    // Empty arrays for other endpoints
    if (path.includes('/storage') ||
        path.includes('/network') ||
        path.includes('/users') ||
        path.includes('/groups') ||
        path.includes('/diagnostics') ||
        path.includes('/tags') ||
        path.includes('/installation-history')) {
      return HttpResponse.json([]);
    }

    // Ubuntu Pro (null response)
    if (path.includes('/ubuntu-pro')) {
      return HttpResponse.json(null);
    }

    // Default: return empty array for API endpoints
    console.log(`MSW: Unhandled API endpoint ${path}, returning empty array`);
    return HttpResponse.json([]);
  }),

  // Handle POST requests for package installation
  http.post('http://localhost:8080/api/packages/install/*', async ({ request }) => {
    const body = await request.json() as { package_names: string[]; requested_by: string };

    return HttpResponse.json({
      success: true,
      message: 'Package installation has been queued',
      installation_ids: body.package_names.map(() => `uuid-${Math.random().toString(36).substr(2, 9)}`)
    });
  }),

  // Handle POST requests for package uninstallation
  http.post('http://localhost:8080/api/packages/uninstall/*', async () => {
    return HttpResponse.json({
      success: true,
      message: 'Package uninstallation has been queued',
      uninstallation_id: `uuid-${Math.random().toString(36).substr(2, 9)}`
    });
  }),

  // Fallback for non-API requests
  http.all('*', ({ request }) => {
    const url = new globalThis.URL(request.url);
    if (!url.pathname.startsWith('/api/')) {
      return HttpResponse.json({}, { status: 200 });
    }

    console.warn(`MSW: Truly unhandled request: ${request.method} ${request.url}`);
    return HttpResponse.json([], { status: 200 });
  }),
];