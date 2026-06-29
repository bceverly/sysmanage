/**
 * Phase 12.7: client for the host-geolocation endpoint.
 *
 * Drives the world-map view (Pages/MapView.tsx).  Returns only hosts
 * with non-null geo coordinates — hosts whose public IP hasn't been
 * resolved yet (or whose public IP is internal-only / airgapped) are
 * filtered out server-side and simply don't appear on the map.
 */

import axiosInstance from "./api";

export interface HostGeolocation {
  host_id: string;
  fqdn: string;
  status: string | null;
  platform: string | null;
  country_code: string | null;
  subdivision_code: string | null;
  city: string | null;
  latitude: number;
  longitude: number;
}

export async function doGetHostGeolocations(): Promise<HostGeolocation[]> {
  const response = await axiosInstance.get<HostGeolocation[]>(
    "/api/v1/hosts/geolocations",
  );
  return response.data;
}
