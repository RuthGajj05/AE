import type { InventoryConnection, InventoryItem, InventoryLocation, InventoryResponse } from './inventory-types';

export const SQUARE_API_VERSION = '2026-09-16';
const MAX_PAGES = 100;
const MAX_VARIATIONS = 10000;
const MAX_OBJECTS = 20000;
const MAX_RESPONSE_BYTES = 4 * 1024 * 1024;
const REQUEST_DEADLINE_MS = 45000;
type SquareEnv = { SQUARE_ACCESS_TOKEN?: string; SQUARE_ENVIRONMENT?: string };
type JsonObject = Record<string, unknown>;
type CatalogObject = JsonObject & { id: string; type: string };

export class SquareError extends Error {
  constructor(message: string, public readonly status: number) { super(message); this.name = 'SquareError'; }
}

export function getInventoryConnection(env: SquareEnv): InventoryConnection {
  const setting = env.SQUARE_ENVIRONMENT?.trim() || 'sandbox';
  if (setting !== 'sandbox' && setting !== 'production') throw new SquareError('The Square environment setting needs attention. Use sandbox or production.', 503);
  return { configured: Boolean(env.SQUARE_ACCESS_TOKEN?.trim()), environment: setting, apiVersion: SQUARE_API_VERSION };
}

function object(value: unknown): value is JsonObject { return Boolean(value && typeof value === 'object' && !Array.isArray(value)); }
function incomplete(): never { throw new SquareError('Square returned incomplete inventory data. Please refresh again.', 502); }
function list(value: JsonObject, key: string): unknown[] {
  if (value[key] === undefined) return [];
  if (!Array.isArray(value[key])) return incomplete();
  return value[key];
}
function text(value: unknown, fallback: string): string { return typeof value === 'string' && value.trim() ? value : fallback; }
function nextCursor(value: JsonObject, seen: Set<string>): string | undefined {
  if (value.cursor === undefined || value.cursor === null || value.cursor === '') return undefined;
  if (typeof value.cursor !== 'string' || value.cursor.length > 10000 || seen.has(value.cursor)) throw new SquareError('Square pagination could not finish. Please refresh again.', 502);
  seen.add(value.cursor);
  return value.cursor;
}
function overLimit(): never { throw new SquareError('This Square catalog is larger than this prototype can load in one refresh. No partial inventory was returned.', 502); }

function upstreamError(status: number): SquareError {
  if (status === 401) return new SquareError('The Square credential is invalid or expired. Update the server connection and try again.', 401);
  if (status === 403) return new SquareError('Square has not granted the required inventory, item, and location read permissions.', 403);
  if (status === 429) return new SquareError('Square is receiving too many requests. Wait a moment, then refresh.', 429);
  if (status === 408 || status === 504) return new SquareError('Square took too long to respond. Please refresh again.', 504);
  return new SquareError('Square could not complete this inventory refresh. Please try again shortly.', 502);
}

async function readResponse(response: Response): Promise<JsonObject> {
  if (Number(response.headers.get('content-length')) > MAX_RESPONSE_BYTES) return overLimit();
  if (!response.body) return incomplete();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let bytes = 0;
  let raw = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_RESPONSE_BYTES) { await reader.cancel(); return overLimit(); }
      raw += decoder.decode(value, { stream: true });
    }
    raw += decoder.decode();
  } finally { reader.releaseLock(); }
  let parsed: unknown;
  try { parsed = JSON.parse(raw); } catch { return incomplete(); }
  if (!object(parsed)) return incomplete();
  const errors = list(parsed, 'errors');
  if (errors.length) {
    const codes = errors.filter(object).map(error => error.code);
    if (codes.includes('UNAUTHORIZED') || codes.includes('ACCESS_TOKEN_EXPIRED') || codes.includes('ACCESS_TOKEN_REVOKED')) throw upstreamError(401);
    if (codes.includes('FORBIDDEN') || codes.includes('INSUFFICIENT_SCOPES')) throw upstreamError(403);
    if (codes.includes('RATE_LIMITED')) throw upstreamError(429);
    throw upstreamError(502);
  }
  return parsed;
}

function presentAt(value: JsonObject, locationId: string): boolean {
  // Square defaults present_at_all_locations to true. ITEM and ITEM_VARIATION
  // settings both apply; a variation cannot enable a disabled parent location.
  if (value.present_at_all_locations === false) return Array.isArray(value.present_at_location_ids) && value.present_at_location_ids.includes(locationId);
  return !Array.isArray(value.absent_at_location_ids) || !value.absent_at_location_ids.includes(locationId);
}

function catalogObject(value: unknown): CatalogObject {
  if (!object(value) || typeof value.id !== 'string' || !value.id || typeof value.type !== 'string') return incomplete();
  return value as CatalogObject;
}

export async function fetchSquareInventory(env: SquareEnv, locationId?: string, requestSignal?: AbortSignal): Promise<InventoryResponse> {
  const connection = getInventoryConnection(env);
  if (locationId !== undefined && !/^[A-Za-z0-9_-]{1,100}$/.test(locationId)) throw new SquareError('Choose a valid Square location.', 400);
  if (!connection.configured) return { connection, locations: [] };
  const base = connection.environment === 'production' ? 'https://connect.squareup.com' : 'https://connect.squareupsandbox.com';
  const deadline = AbortSignal.timeout(REQUEST_DEADLINE_MS);
  const signal = requestSignal ? AbortSignal.any([deadline, requestSignal]) : deadline;
  const token = env.SQUARE_ACCESS_TOKEN!.trim();
  async function request(path: string, body?: object): Promise<JsonObject> {
    try {
      signal.throwIfAborted();
      const response = await fetch(`${base}${path}`, {
        method: body ? 'POST' : 'GET',
        headers: { Authorization: `Bearer ${token}`, 'Square-Version': SQUARE_API_VERSION, 'Content-Type': 'application/json', Accept: 'application/json' },
        ...(body ? { body: JSON.stringify(body) } : {}),
        redirect: 'error', cache: 'no-store', signal,
      });
      if (!response.ok) throw upstreamError(response.status);
      return await readResponse(response);
    } catch (error) {
      if (error instanceof SquareError) throw error;
      if (signal.aborted) throw new SquareError('The inventory refresh timed out or was canceled. Please try again.', 504);
      throw new SquareError('Square could not be reached. Please try again shortly.', 502);
    }
  }

  const locationsData = await request('/v2/locations');
  const locations: InventoryLocation[] = [];
  for (const entry of list(locationsData, 'locations')) {
    if (!object(entry) || typeof entry.id !== 'string' || !entry.id || typeof entry.status !== 'string') return incomplete();
    if (entry.status === 'ACTIVE') locations.push({ id: entry.id, name: text(entry.name, 'Unnamed location') });
  }
  if (locations.length > 1000) return overLimit();
  if (locationId === undefined) return { connection, locations };
  const location = locations.find(entry => entry.id === locationId);
  if (!location) throw new SquareError('This location is not active or does not belong to the connected Square account.', 404);

  const parents = new Map<string, CatalogObject>();
  const variations = new Map<string, CatalogObject>();
  const catalogCursors = new Set<string>();
  let cursor: string | undefined;
  let catalogPages = 0;
  let objectCount = 0;
  do {
    if (++catalogPages > MAX_PAGES) return overLimit();
    const query = new URLSearchParams({ types: 'ITEM,ITEM_VARIATION' });
    if (cursor) query.set('cursor', cursor);
    const page = await request(`/v2/catalog/list?${query}`);
    for (const value of list(page, 'objects')) {
      if (++objectCount > MAX_OBJECTS) return overLimit();
      const entry = catalogObject(value);
      if (entry.is_deleted === true) continue;
      if (entry.type === 'ITEM') {
        if (!object(entry.item_data)) return incomplete();
        parents.set(entry.id, entry);
        for (const nested of list(entry.item_data, 'variations')) {
          const variation = catalogObject(nested);
          if (variation.type !== 'ITEM_VARIATION') return incomplete();
          if (variation.is_deleted !== true) variations.set(variation.id, variation);
        }
      } else if (entry.type === 'ITEM_VARIATION') variations.set(entry.id, entry);
      if (variations.size > MAX_VARIATIONS) return overLimit();
    }
    cursor = nextCursor(page, catalogCursors);
  } while (cursor);

  const items: InventoryItem[] = [];
  for (const variation of variations.values()) {
    const data = variation.item_variation_data;
    if (!object(data) || typeof data.item_id !== 'string') return incomplete();
    const parent = parents.get(data.item_id);
    if (!parent || !object(parent.item_data)) throw new SquareError('Square item details changed during the refresh. Please try again.', 502);
    if (!presentAt(parent, locationId) || !presentAt(variation, locationId)) continue;
    const overrides = list(data, 'location_overrides');
    if (overrides.some(entry => !object(entry) || typeof entry.location_id !== 'string')) return incomplete();
    const override = overrides.find(entry => object(entry) && entry.location_id === locationId) as JsonObject | undefined;
    const tracking = override?.track_inventory ?? data.track_inventory ?? false;
    if (typeof tracking !== 'boolean') return incomplete();
    items.push({
      variationId: variation.id, itemName: text(parent.item_data.name, 'Unnamed item'), variationName: text(data.name, 'Regular'),
      sku: typeof data.sku === 'string' && data.sku ? data.sku : null,
      quantity: null, tracked: tracking, locationId, updatedAt: null,
    });
  }
  const trackedIds = items.filter(item => item.tracked).map(item => item.variationId);
  const counts = new Map<string, { quantity: string; updatedAt: string | null }>();
  let countPages = 0;
  let countRecords = 0;
  for (let offset = 0; offset < trackedIds.length; offset += 1000) {
    const ids = trackedIds.slice(offset, offset + 1000);
    const allowedIds = new Set(ids);
    const countCursors = new Set<string>();
    cursor = undefined;
    do {
      if (++countPages > MAX_PAGES) return overLimit();
      const page = await request('/v2/inventory/counts/batch-retrieve', {
        catalog_object_ids: ids, location_ids: [locationId], states: ['IN_STOCK'], limit: 1000,
        ...(cursor ? { cursor } : {}),
      });
      for (const value of list(page, 'counts')) {
        if (++countRecords > 50000) return overLimit();
        if (!object(value)) return incomplete();
        if (value.location_id !== locationId || value.state !== 'IN_STOCK' || typeof value.catalog_object_id !== 'string' || !allowedIds.has(value.catalog_object_id)) continue;
        if (typeof value.quantity !== 'string' || value.quantity.length > 26 || !/^-?\d+(?:\.\d{1,5})?$/.test(value.quantity)) return incomplete();
        const updatedAt = typeof value.calculated_at === 'string' && Number.isFinite(Date.parse(value.calculated_at)) ? value.calculated_at : null;
        const previous = counts.get(value.catalog_object_id);
        if (!previous || (updatedAt && (!previous.updatedAt || Date.parse(updatedAt) > Date.parse(previous.updatedAt)))) counts.set(value.catalog_object_id, { quantity: value.quantity, updatedAt });
      }
      cursor = nextCursor(page, countCursors);
    } while (cursor);
  }
  for (const item of items) {
    const count = counts.get(item.variationId);
    if (item.tracked && count) { item.quantity = count.quantity; item.updatedAt = count.updatedAt; }
  }
  items.sort((a, b) => a.itemName.localeCompare(b.itemName) || a.variationName.localeCompare(b.variationName) || a.variationId.localeCompare(b.variationId));
  return {
    connection, locations,
    snapshot: {
      source: 'square', environment: connection.environment, location, items, syncedAt: new Date().toISOString(),
      warnings: [
        'Counts are Square’s IN_STOCK estimates for this location. Refresh to retrieve changes; this prototype does not receive live updates.',
        'A missing count is unknown, not zero. Items with inventory tracking disabled do not show a count.',
        'Stock counts do not include manual sold-out availability or ingredient and recipe tracking.',
      ],
    },
  };
}
