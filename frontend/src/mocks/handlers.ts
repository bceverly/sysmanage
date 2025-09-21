import { http, HttpResponse } from 'msw';

const API_BASE_URL = 'http://localhost:8080/api';

export const handlers = [
  // Mock login endpoint
  http.post(`${API_BASE_URL}/login`, () => {
    return HttpResponse.json({
      token: 'mock-jwt-token',
      user: {
        id: 1,
        userid: 'test@example.com',
        active: true
      }
    });
  }),

  // Mock hosts endpoints
  http.get(`${API_BASE_URL}/hosts`, () => {
    return HttpResponse.json([
      {
        id: 1,
        fqdn: 'test-host.example.com',
        ipv4: '192.168.1.100',
        active: true,
        status: 'up'
      }
    ]);
  }),

  // Mock host detail endpoint
  http.get(`${API_BASE_URL}/hosts/:id`, ({ params }) => {
    const { id } = params;
    return HttpResponse.json({
      id: Number(id),
      fqdn: 'test-host.example.com',
      ipv4: '192.168.1.100',
      active: true,
      status: 'up'
    });
  }),

  // Mock packages search endpoint
  http.get(`${API_BASE_URL}/packages/search`, ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('query');

    if (!query || query.length < 2) {
      return HttpResponse.json([]);
    }

    return HttpResponse.json([
      {
        name: `${query}`,
        version: '1.0.0',
        description: `Mock package for ${query}`
      }
    ]);
  }),

  // Mock package installation endpoint
  http.post(`${API_BASE_URL}/packages/install/:hostId`, ({ request }) => {
    console.log('Package installation request:', request.url);
    return HttpResponse.json({
      success: true,
      message: 'Package installation queued',
      installation_ids: ['mock-uuid']
    });
  })
];