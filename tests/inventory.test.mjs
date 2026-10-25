import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import ts from 'typescript';

// Isolated TypeScript modules plus deterministic HTTP fixtures. These tests never
// need a merchant credential, a local server, or access to the Square network.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function modules(overrides = {}) {
  const cache = new Map();
  function load(relative) {
    const filename = path.resolve(root, relative);
    if (cache.has(filename)) return cache.get(filename).exports;
    const entry = { exports: {} };
    cache.set(filename, entry);
    const source = readFileSync(filename, 'utf8');
    const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
    const externalRequire = createRequire(filename);
    function localRequire(id) {
      if (Object.hasOwn(overrides, id)) return overrides[id];
      if (id.startsWith('@/')) return load(`${id.slice(2)}.ts`);
      if (id.startsWith('.')) return load(path.resolve(path.dirname(filename), `${id}.ts`));
      return externalRequire(id);
    }
    new Function('module', 'exports', 'require', '__filename', '__dirname', compiled)(entry, entry.exports, localRequire, filename, path.dirname(filename));
    return entry.exports;
  }
  return load;
}

const env = (extra = {}) => ({ SQUARE_ACCESS_TOKEN: 'fixture-only-token', SQUARE_ENVIRONMENT: 'sandbox', ...extra });
const locations = [
  { id: 'L1', name: 'Main shop', status: 'ACTIVE' },
  { id: 'L2', name: 'Market stand', status: 'ACTIVE' },
  { id: 'OLD', name: 'Closed shop', status: 'INACTIVE' },
];
const variation = (id, itemId = 'I1', data = {}, object = {}) => ({
  type: 'ITEM_VARIATION', id, present_at_all_locations: true,
  item_variation_data: { item_id: itemId, name: id, sku: 'shared-sku', track_inventory: true, ...data }, ...object,
});
const item = (id, variants, object = {}) => ({
  type: 'ITEM', id, present_at_all_locations: true,
  item_data: { name: `Item ${id}`, variations: variants }, ...object,
});
const count = (id, quantity, extra = {}) => ({
  catalog_object_id: id, catalog_object_type: 'ITEM_VARIATION', location_id: 'L1', state: 'IN_STOCK', quantity,
  calculated_at: '2026-10-25T12:00:00Z', ...extra,
});
function squareFixture(t, options = {}) {
  const calls = [];
  const objects = options.objects ?? [item('I1', [variation('V1')])];
  const counts = options.counts ?? [count('V1', '8')];
  t.mock.method(globalThis, 'fetch', async (input, init = {}) => {
    const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
    const body = init.body ? JSON.parse(init.body) : null;
    calls.push({ url, init, body });
    if (options.handle) {
      const custom = await options.handle(url, init, body, calls);
      if (custom !== undefined) return custom;
    }
    if (url.pathname === '/v2/locations') return Response.json({ locations: options.locations ?? locations });
    if (url.pathname === '/v2/catalog/list') return Response.json({ objects });
    if (url.pathname === '/v2/inventory/counts/batch-retrieve') return Response.json({ counts });
    throw new Error(`Unexpected fixture endpoint: ${url.pathname}`);
  });
  return calls;
}

function stockItem(extra = {}) {
  return { variationId: 'V1', itemName: 'Bread', variationName: 'Large', sku: 'BREAD', quantity: '8', tracked: true, locationId: 'L1', updatedAt: '2026-10-25T12:00:00Z', ...extra };
}
function snapshot(items = [stockItem()], extra = {}) {
  return { source: 'square', environment: 'sandbox', location: { id: 'L1', name: 'Main shop' }, items, syncedAt: '2026-10-25T13:00:00Z', warnings: [], ...extra };
}

test('inventory status distinguishes missing counts, untracked items, and genuine zero stock', () => {
  const { inventoryStatus } = modules()('lib/inventory.ts');
  assert.equal(inventoryStatus(stockItem({ quantity: null }), 5), 'unknown');
  assert.equal(inventoryStatus(stockItem({ quantity: null, tracked: false }), 5), 'untracked');
  assert.equal(inventoryStatus(stockItem({ quantity: '0' }), 5), 'out');
  assert.equal(inventoryStatus(stockItem({ quantity: '-0.25' }), 5), 'out');
  assert.equal(inventoryStatus(stockItem({ quantity: '5' }), 5), 'low');
  assert.equal(inventoryStatus(stockItem({ quantity: '5.00001' }), 5), 'in-stock');
  assert.equal(inventoryStatus(stockItem({ quantity: '0.00001' }), 0), 'in-stock');
});

test('reorder thresholds cannot cross example, environment, location, or variation boundaries', () => {
  const { thresholdKey } = modules()('lib/inventory.ts');
  const original = thresholdKey(snapshot(), stockItem());
  const alternatives = [
    thresholdKey(snapshot(undefined, { source: 'example' }), stockItem()),
    thresholdKey(snapshot(undefined, { environment: 'production' }), stockItem()),
    thresholdKey(snapshot(undefined, { location: { id: 'L2', name: 'Market' } }), stockItem({ locationId: 'L2' })),
    thresholdKey(snapshot(), stockItem({ variationId: 'V2' })),
  ];
  assert.equal(new Set([original, ...alternatives]).size, 5);
});

test('CSV preserves decimal stock and escapes commas, quotes, multiline fields, and spreadsheet formulas', () => {
  const { inventoryCsv } = modules()('lib/inventory.ts');
  const csv = inventoryCsv(snapshot([
    stockItem({ itemName: 'Bread, "daily"\nlarge', variationName: '=SUM(1,2)', sku: '@TEST', quantity: '0.12500' }),
    stockItem({ variationId: 'V2', itemName: '  =HYPERLINK("https://example.com")', variationName: '+formula', sku: '-formula', quantity: null }),
  ]), { V1: 0.25, V2: 5 });
  assert.match(csv, /0\.12500/);
  assert.match(csv, /"Bread, ""daily""\nlarge"/);
  assert.match(csv, /'=SUM/);
  assert.match(csv, /'@TEST/);
  assert.match(csv, /'\s*=HYPERLINK/);
  assert.match(csv, /'\+formula/);
  assert.match(csv, /'-formula/);
  assert.ok(!csv.includes('[object Object]'));
});

test('Square defaults to sandbox, pins its API version, and never returns the access token', () => {
  const { getInventoryConnection, SQUARE_API_VERSION } = modules()('lib/square.ts');
  const connection = getInventoryConnection({ SQUARE_ACCESS_TOKEN: 'fixture-only-token' });
  assert.deepEqual(connection, { configured: true, environment: 'sandbox', apiVersion: SQUARE_API_VERSION });
  assert.equal(SQUARE_API_VERSION, '2026-09-16');
  assert.equal(getInventoryConnection(env({ SQUARE_ENVIRONMENT: 'production' })).environment, 'production');
  assert.ok(!JSON.stringify(connection).includes('fixture-only-token'));
});

test('an invalid environment fails closed rather than contacting production', async t => {
  const calls = squareFixture(t);
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env({ SQUARE_ENVIRONMENT: 'prodution' }), 'L1'), error => error.status === 503);
  assert.equal(calls.length, 0);
});

test('an unconfigured Square integration returns a disconnected state without HTTP calls', async t => {
  const calls = squareFixture(t);
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory({}, 'L1');
  assert.equal(result.connection.configured, false);
  assert.deepEqual(result.locations, []);
  assert.equal(result.snapshot, undefined);
  assert.equal(calls.length, 0);
});

test('location discovery returns active merchant locations without fetching inventory', async t => {
  const calls = squareFixture(t);
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env());
  assert.deepEqual(result.locations, [{ id: 'L1', name: 'Main shop' }, { id: 'L2', name: 'Market stand' }]);
  assert.equal(result.snapshot, undefined);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url.hostname, 'connect.squareupsandbox.com');
  assert.equal(new Headers(calls[0].init.headers).get('authorization'), 'Bearer fixture-only-token');
  assert.equal(new Headers(calls[0].init.headers).get('square-version'), '2026-09-16');
});

test('foreign or inactive location IDs are rejected before catalog or stock access', async t => {
  const calls = squareFixture(t);
  const { fetchSquareInventory } = modules()('lib/square.ts');
  for (const locationId of ['FOREIGN', 'OLD']) {
    await assert.rejects(fetchSquareInventory(env(), locationId), error => error.status === 404);
  }
  assert.ok(calls.every(call => call.url.pathname === '/v2/locations'));
});

test('location input cannot become an endpoint or arbitrary fetch target', async t => {
  const calls = squareFixture(t);
  const { fetchSquareInventory } = modules()('lib/square.ts');
  for (const locationId of ['https://attacker.example/', '../L1', 'L 1', 'L'.repeat(101)]) {
    await assert.rejects(fetchSquareInventory(env(), locationId), error => error.status === 400);
  }
  assert.ok(calls.every(call => call.url.hostname === 'connect.squareupsandbox.com'));
});

test('catalog and count cursors are followed with the original location and state filters', async t => {
  const calls = squareFixture(t, {
    handle(url, init, body) {
      if (url.pathname === '/v2/catalog/list') {
        return Response.json(url.searchParams.has('cursor')
          ? { objects: [item('I2', [variation('V2', 'I2')])] }
          : { objects: [item('I1', [variation('V1')])], cursor: 'catalog-next' });
      }
      if (url.pathname === '/v2/inventory/counts/batch-retrieve') {
        return Response.json(body.cursor
          ? { counts: [count('V2', '0.12500')] }
          : { counts: [count('V1', '8')], cursor: 'counts-next' });
      }
    },
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  assert.equal(result.snapshot.items.length, 2);
  assert.equal(result.snapshot.items.find(row => row.variationId === 'V2').quantity, '0.12500');
  const catalogs = calls.filter(call => call.url.pathname === '/v2/catalog/list');
  assert.equal(catalogs.length, 2);
  assert.equal(catalogs[1].url.searchParams.get('cursor'), 'catalog-next');
  assert.equal(catalogs[0].url.searchParams.get('types'), 'ITEM,ITEM_VARIATION');
  const counts = calls.filter(call => call.body);
  assert.equal(counts.length, 2);
  for (const call of counts) {
    assert.equal(call.init.method, 'POST');
    assert.deepEqual(call.body.location_ids, ['L1']);
    assert.deepEqual(call.body.states, ['IN_STOCK']);
    assert.equal(call.body.limit, 1000);
    assert.deepEqual(new Set(call.body.catalog_object_ids), new Set(['V1', 'V2']));
  }
  assert.equal(counts[1].body.cursor, 'counts-next');
  assert.equal(result.snapshot.source, 'square');
  assert.equal(result.snapshot.location.id, 'L1');
  assert.ok(Number.isFinite(Date.parse(result.snapshot.syncedAt)));
  assert.ok(!JSON.stringify(result).includes('fixture-only-token'));
});

test('more than one thousand tracked variations are fetched in bounded Square batches', async t => {
  const variants = Array.from({ length: 1001 }, (_, i) => variation(`V${i}`));
  const calls = squareFixture(t, {
    objects: [item('I1', variants)],
    handle(url, init, body) {
      if (url.pathname === '/v2/inventory/counts/batch-retrieve') return Response.json({ counts: body.catalog_object_ids.map(id => count(id, '1')) });
    },
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  const countCalls = calls.filter(call => call.body);
  assert.equal(countCalls.length, 2);
  assert.ok(countCalls.every(call => call.body.catalog_object_ids.length <= 1000));
  assert.equal(new Set(countCalls.flatMap(call => call.body.catalog_object_ids)).size, 1001);
  assert.equal(result.snapshot.items.length, 1001);
  assert.ok(result.snapshot.items.every(row => row.quantity === '1'));
});

test('effective tracking respects location overrides and never treats untracked items as zero', async t => {
  const variants = [
    variation('V1', 'I1', { location_overrides: [{ location_id: 'L1', track_inventory: false }] }),
    variation('V2', 'I1', { track_inventory: false, location_overrides: [{ location_id: 'L1', track_inventory: true }] }),
    variation('V3', 'I1', { track_inventory: undefined }),
  ];
  const calls = squareFixture(t, { objects: [item('I1', variants)], counts: [count('V1', '99'), count('V2', '2')] });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  const rows = Object.fromEntries(result.snapshot.items.map(row => [row.variationId, row]));
  assert.equal(rows.V1.tracked, false);
  assert.equal(rows.V1.quantity, null);
  assert.equal(rows.V2.tracked, true);
  assert.equal(rows.V2.quantity, '2');
  assert.equal(rows.V3.tracked, false);
  assert.equal(rows.V3.quantity, null);
  assert.deepEqual(calls.find(call => call.body).body.catalog_object_ids, ['V2']);
});

test('location availability applies to parent items and variations together', async t => {
  squareFixture(t, {
    objects: [
      item('I1', [
        variation('VISIBLE'),
        variation('ABSENT', 'I1', {}, { absent_at_location_ids: ['L1'] }),
        variation('OTHER', 'I1', {}, { present_at_all_locations: false, present_at_location_ids: ['L2'] }),
        variation('PRESENT', 'I1', {}, { present_at_all_locations: false, present_at_location_ids: ['L1'] }),
      ]),
      item('I2', [variation('PARENT_ABSENT', 'I2')], { absent_at_location_ids: ['L1'] }),
      item('I3', [variation('PARENT_OTHER', 'I3')], { present_at_all_locations: false, present_at_location_ids: ['L2'] }),
    ], counts: [],
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  assert.deepEqual(new Set(result.snapshot.items.map(row => row.variationId)), new Set(['VISIBLE', 'PRESENT']));
});

test('inventory counts join on variation and location, preserving absent, zero, decimal, and negative values', async t => {
  const variants = ['MISSING', 'ZERO', 'FRACTION', 'NEGATIVE', 'OTHER_LOCATION'].map(id => variation(id));
  squareFixture(t, {
    objects: [item('I1', variants)],
    counts: [count('ZERO', '0'), count('FRACTION', '0.25000'), count('NEGATIVE', '-2'), count('OTHER_LOCATION', '50', { location_id: 'L2' })],
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  const quantities = Object.fromEntries(result.snapshot.items.map(row => [row.variationId, row.quantity]));
  assert.deepEqual(quantities, { MISSING: null, ZERO: '0', FRACTION: '0.25000', NEGATIVE: '-2', OTHER_LOCATION: null });
  assert.ok(result.snapshot.items.every(row => row.sku === 'shared-sku'));
});

test('the newest matching count wins without using reserved stock as available inventory', async t => {
  squareFixture(t, { counts: [
    count('V1', '2', { calculated_at: '2026-10-25T12:00:00Z' }),
    count('V1', '9', { calculated_at: '2026-10-24T12:00:00Z' }),
    count('V1', '500', { state: 'RESERVED_FOR_SALE', calculated_at: '2026-10-25T13:00:00Z' }),
  ] });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  assert.equal(result.snapshot.items[0].quantity, '2');
  assert.equal(result.snapshot.items[0].updatedAt, '2026-10-25T12:00:00Z');
});

test('duplicate nested and top-level catalog variations produce one stock row', async t => {
  const variant = variation('V1');
  squareFixture(t, { objects: [item('I1', [variant]), variant] });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  const result = await fetchSquareInventory(env(), 'L1');
  assert.equal(result.snapshot.items.length, 1);
});

test('repeated catalog cursors fail explicitly instead of returning partial stock', async t => {
  const calls = squareFixture(t, { handle(url) {
    if (url.pathname === '/v2/catalog/list') return Response.json({ objects: [item('I1', [variation('V1')])], cursor: 'repeat' });
  } });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env(), 'L1'), error => error.status >= 400);
  assert.ok(calls.length < 10);
  assert.equal(calls.filter(call => call.body).length, 0);
});

test('repeated count cursors fail explicitly instead of declaring a complete snapshot', async t => {
  const calls = squareFixture(t, { handle(url) {
    if (url.pathname === '/v2/inventory/counts/batch-retrieve') return Response.json({ counts: [count('V1', '1')], cursor: 'repeat' });
  } });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env(), 'L1'), error => error.status >= 400);
  assert.ok(calls.length < 10);
});

test('catalog page limits reject oversized refreshes instead of silently dropping later pages', async t => {
  let page = 0;
  const calls = squareFixture(t, { handle(url) {
    if (url.pathname === '/v2/catalog/list') return Response.json({ objects: [], cursor: `next-${++page}` });
  } });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env(), 'L1'), error => error.status >= 400);
  assert.ok(calls.length <= 102);
  assert.equal(calls.filter(call => call.body).length, 0);
});

test('Square authentication and rate-limit failures are safe and actionable', async t => {
  for (const status of [401, 403, 429]) {
    squareFixture(t, { handle: () => Response.json({ errors: [{ detail: 'upstream-secret fixture-only-token', code: 'PRIVATE' }] }, { status }) });
    const { fetchSquareInventory } = modules()('lib/square.ts');
    await assert.rejects(fetchSquareInventory(env(), 'L1'), error => {
      assert.ok(error.status >= 400);
      assert.ok(!error.message.includes('fixture-only-token'));
      assert.ok(!error.message.includes('upstream-secret'));
      if (status === 429) assert.equal(error.status, 429);
      return true;
    });
    t.mock.restoreAll();
  }
});

test('inventory API reports disconnected state without allowing response caching', async () => {
  const { GET } = modules({ 'cloudflare:workers': { env: {} } })('app/api/inventory/square/route.ts');
  const response = await GET(new Request('https://nearby.example/api/inventory/square'));
  assert.equal(response.status, 200);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.equal((await response.json()).connection.configured, false);
});

test('inventory API rejects cross-origin requests before accessing Square and does not cache errors', async t => {
  const calls = squareFixture(t);
  const { GET } = modules({ 'cloudflare:workers': { env: env() } })('app/api/inventory/square/route.ts');
  const response = await GET(new Request('https://nearby.example/api/inventory/square?locationId=L1', { headers: { origin: 'https://other.example' } }));
  assert.equal(response.status, 403);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.equal(calls.length, 0);
});

test('inventory API returns safe upstream errors with no-store and no credential disclosure', async t => {
  squareFixture(t, { handle: () => Response.json({ errors: [{ detail: 'fixture-only-token private merchant details' }] }, { status: 401 }) });
  const { GET } = modules({ 'cloudflare:workers': { env: env() } })('app/api/inventory/square/route.ts');
  const response = await GET(new Request('https://nearby.example/api/inventory/square?locationId=L1', { headers: { origin: 'https://nearby.example' } }));
  assert.ok(response.status >= 400);
  assert.match(response.headers.get('cache-control'), /no-store/);
  const body = await response.text();
  assert.ok(!body.includes('fixture-only-token'));
  assert.ok(!body.includes('private merchant details'));
});

test('the aggregate Square deadline returns a safe timeout rather than making further requests', async t => {
  const calls = squareFixture(t);
  let duration;
  t.mock.method(AbortSignal, 'timeout', milliseconds => {
    duration = milliseconds;
    return AbortSignal.abort(new DOMException('Private transport timeout detail', 'TimeoutError'));
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env(), 'L1'), error => {
    assert.equal(error.status, 504);
    assert.match(error.message, /timed out|cancel/i);
    assert.ok(!error.message.includes('Private transport'));
    return true;
  });
  assert.equal(duration, 45000);
  assert.equal(calls.length, 0);
});

test('caller cancellation interrupts the current Square request', async t => {
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    controller.abort(new DOMException('Stop this refresh', 'AbortError'));
    init.signal.throwIfAborted();
    throw new Error('The canceled request unexpectedly continued');
  });
  const { fetchSquareInventory } = modules()('lib/square.ts');
  await assert.rejects(fetchSquareInventory(env(), 'L1', controller.signal), error => error.status === 504);
});

test('invalid or oversized upstream responses fail without a partial stock snapshot', async t => {
  for (const body of [
    () => new Response('not-json', { status: 200 }),
    () => Response.json({ counts: 'not-a-list' }),
    () => Response.json({ counts: [count('V1', 'NaN')] }),
    () => Response.json({ counts: [count('V1', '1.123456')] }),
    () => new Response('{}', { headers: { 'content-length': String(4 * 1024 * 1024 + 1) } }),
  ]) {
    squareFixture(t, { handle(url) {
      if (url.pathname === '/v2/inventory/counts/batch-retrieve') return body();
    } });
    const { fetchSquareInventory } = modules()('lib/square.ts');
    await assert.rejects(fetchSquareInventory(env(), 'L1'), error => error.status === 502);
    t.mock.restoreAll();
  }
});

test('duplicate location selectors are rejected without fetching merchant data', async t => {
  const calls = squareFixture(t);
  const { GET } = modules({ 'cloudflare:workers': { env: env() } })('app/api/inventory/square/route.ts');
  const response = await GET(new Request('https://nearby.example/api/inventory/square?locationId=L1&locationId=L2'));
  assert.equal(response.status, 400);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.equal(calls.length, 0);
});
