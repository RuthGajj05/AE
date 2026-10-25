import { env } from 'cloudflare:workers';
import { fetchSquareInventory, SquareError } from '@/lib/square';

export const dynamic = 'force-dynamic';
const headers = { 'Cache-Control': 'no-store' };

export async function GET(request: Request) {
  // Single-merchant, owner-private prototype: Sites dispatch authenticates users
  // and service calls. Keep this deployment private until merchant isolation is added.
  const url = new URL(request.url);
  const origin = request.headers.get('origin');
  if (origin && origin !== url.origin) return Response.json({ error: 'Open Nearby directly to view inventory.' }, { status: 403, headers });
  if (url.searchParams.getAll('locationId').length > 1) return Response.json({ error: 'Choose one Square location.' }, { status: 400, headers });
  const locationId = url.searchParams.get('locationId') ?? undefined;
  try {
    const result = await fetchSquareInventory(env, locationId, request.signal);
    return Response.json(result, { headers });
  } catch (error) {
    if (error instanceof SquareError) return Response.json({ error: error.message }, { status: error.status, headers });
    return Response.json({ error: 'Inventory could not be loaded. Please try again.' }, { status: 502, headers });
  }
}
