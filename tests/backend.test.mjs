import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import ts from 'typescript';

// Compile only the modules under test in memory. No test packages, build output,
// API credentials, or real network requests are needed.
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
const load = modules();
const { normalizeWebsite, parseInput, belongsTo } = load('lib/validation.ts');
const { collectEvidence, assembleReport, research } = load('lib/research.ts');
const OWNER = 'https://ownerbakery.com/';
const RIVAL = 'https://rivalbakery.com/';
const OTHER = 'https://otherbakery.com/';
const checkedAt = '2026-10-25T18:00:00Z';
const pageText = 'Our bakery offers bread and pastries. Orders for pickup can be placed on our website. Please contact us for current availability and opening hours.';
const input = () => parseInput({ businessWebsite: OWNER, competitors: [RIVAL] });
function fetched(url = OWNER, text = pageText, extra = {}) {
  return { type: 'web_fetch_tool_result', content: { type: 'web_fetch_result', url, retrieved_at: checkedAt, content: { title: 'Bakery menu', source: { type: 'text', data: text } }, ...extra } };
}
function evidence() { return collectEvidence([fetched(), fetched(RIVAL)], [OWNER, RIVAL], checkedAt); }
function generated() {
  return {
    businessName: 'Owner Bakery', summary: 'Compare the public order information and test a clearer guide.', limitations: ['This uses public website evidence.'],
    businesses: [
      { name: 'Owner Bakery', url: OWNER, summary: 'The site describes bread, pastries, and pickup.', sourceIds: ['s1'] },
      { name: 'Rival Bakery', url: RIVAL, summary: 'The site describes online pickup ordering.', sourceIds: ['s2'] },
    ],
    recommendations: [{ title: 'Clarify pickup instructions', rationale: 'Both websites describe pickup ordering.', action: 'Check whether the buying steps need a clearer explanation.', effort: 'Estimated 1 hour', metric: 'Count pickup questions for two weeks.', ownerChecks: ['Confirm the actual cutoff.'], sourceIds: ['s1', 's2'], draft: { channel: 'Website FAQ', title: 'Ordering for pickup', body: 'Order by [confirmed cutoff] for pickup on [confirmed days].' } }],
    sourceNotes: [{ sourceId: 's1', excerpt: 'Our bakery offers bread and pastries.' }],
  };
}

// URL and ownership boundaries.
test('accepts normal public HTTPS URLs and normalizes a bare domain', () => {
  assert.equal(normalizeWebsite('  WWW.OwnerBakery.com/menu  '), 'https://www.ownerbakery.com/menu');
  assert.equal(normalizeWebsite('https://ownerbakery.com/menu'), 'https://ownerbakery.com/menu');
});
test('rejects private, alternate IP, credential, unsupported protocol, and query URLs', () => {
  for (const value of [
    '', 'localhost', 'localhost.localdomain:3000', 'shop.local', 'shop.internal', 'shop.test',
    '127.0.0.1', '127.1', '2130706433', '0x7f000001', '0177.0.0.1', '[::1]', '[::ffff:127.0.0.1]',
    'http://ownerbakery.com', 'ftp://ownerbakery.com', 'file:///etc/passwd',
    'https://user:pass@ownerbakery.com', 'https://ownerbakery.com:444',
    'https://ownerbakery.com/?secret=value', 'https://ownerbakery.com/#fragment',
    'https://metadata.google.internal', 'https://ownerbakery.com@127.0.0.1',
  ]) assert.throws(() => normalizeWebsite(value), undefined, value);
});
test('validates competitor count, goal length, and unexpected fields', () => {
  for (const invalid of [
    { businessWebsite: OWNER, competitors: [] },
    { businessWebsite: OWNER, competitors: [RIVAL, OTHER, 'four.com', 'five.com'] },
    { businessWebsite: OWNER, competitors: [RIVAL], goal: 'x'.repeat(401) },
    { businessWebsite: OWNER, competitors: [RIVAL], apiKey: 'should-not-be-client-input' },
  ]) assert.throws(() => parseInput(invalid));
});
test('rejects duplicate sites after www, case, and path normalization', () => {
  assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: ['https://www.OWNERBAKERY.com/menu'] }));
});
test('rejects overlapping owner and competitor domains', () => {
  assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: ['https://orders.ownerbakery.com/'] }));
  assert.throws(() => parseInput({ businessWebsite: 'https://orders.ownerbakery.com/', competitors: [OWNER] }));
});
test('domain attribution permits real subdomains and rejects lookalikes', () => {
  assert.equal(belongsTo('https://orders.ownerbakery.com/menu', OWNER), true);
  assert.equal(belongsTo('https://www.ownerbakery.com/menu', OWNER), true);
  assert.equal(belongsTo('https://notownerbakery.com/', OWNER), false);
  assert.equal(belongsTo('https://ownerbakery.com.attacker.com/', OWNER), false);
});

// Tool evidence, rather than model prose, is the source of truth.
test('accepts only successful, non-empty, allowed-domain fetched text', () => {
  const accepted = collectEvidence([
    { type: 'text', text: 'I read https://ownerbakery.com/' },
    { type: 'server_tool_use', name: 'web_fetch', input: { url: OWNER } },
    { type: 'web_fetch_tool_result', content: { type: 'web_fetch_tool_result_error', error_code: 'url_not_accessible' } },
    fetched('https://unrelated.com/'), fetched('http://ownerbakery.com/'), fetched('https://user:pass@ownerbakery.com/'),
    fetched('https://ownerbakery.com:444/'), fetched(OWNER, 'Too short'),
    fetched(OWNER, pageText, { content: { source: { type: 'base64', data: 'abcd' } } }),
    fetched(OWNER), fetched(OWNER), fetched(RIVAL),
  ], [OWNER, RIVAL], checkedAt);
  assert.deepEqual(accepted.map(s => s.url), [OWNER, RIVAL]);
  assert.deepEqual(accepted.map(s => s.id), ['s1', 's2']);
});
test('caps fetched pages and each page text, and replaces invalid retrieval times', () => {
  const pages = Array.from({ length: 12 }, (_, index) => fetched(`${OWNER}page-${index}`, 'Text. '.repeat(4000), { retrieved_at: 'not a date' }));
  const accepted = collectEvidence(pages, [OWNER], checkedAt);
  assert.equal(accepted.length, 8);
  assert.ok(accepted.every(s => s.text.length <= 18000 && s.retrievedAt === checkedAt));
});
test('uses only verified quotes and does not expose full page text', () => {
  const result = assembleReport(generated(), evidence(), input(), checkedAt);
  assert.equal(result.sources[0].excerpt, 'Our bakery offers bread and pastries.');
  assert.equal('text' in result.sources[0], false);
  const fabricated = generated();
  fabricated.sourceNotes[0].excerpt = 'We guarantee you will double revenue.';
  const fallback = assembleReport(fabricated, evidence(), input(), checkedAt);
  assert.equal(fallback.sources[0].excerpt, evidence()[0].excerpt);
});
test('rejects invented recommendation or business citation IDs', () => {
  const rec = generated(); rec.recommendations[0].sourceIds.push('fabricated');
  assert.throws(() => assembleReport(rec, evidence(), input()), /unverified source/);
  const business = generated(); business.businesses[0].sourceIds = ['fabricated'];
  assert.throws(() => assembleReport(business, evidence(), input()), /unverified source/);
});
test('rejects a comparison that cites another business as its own evidence', () => {
  const wrong = generated(); wrong.businesses[0].sourceIds = ['s2'];
  assert.throws(() => assembleReport(wrong, evidence(), input()), /mixed sources/);
});
test('rejects a malformed report or a read business missing its cited summary', () => {
  assert.throws(() => assembleReport({}, evidence(), input()), /incomplete/);
  const missing = generated(); missing.businesses[0].sourceIds = [];
  assert.throws(() => assembleReport(missing, evidence(), input()), /incomplete/);
});
test('preserves input business order and replaces inaccessible-site claims with unknown', () => {
  const partialInput = parseInput({ businessWebsite: OWNER, competitors: [RIVAL, OTHER] });
  const data = generated();
  data.businesses.reverse();
  data.businesses.push({ name: 'Other Bakery', url: OTHER, summary: 'An unsupported invented claim about a special offer.', sourceIds: [] });
  const result = assembleReport(data, evidence(), partialInput, checkedAt);
  assert.deepEqual(result.businesses.map(b => b.url), [OWNER, RIVAL, OTHER]);
  assert.deepEqual(result.businesses.map(b => b.role), ['owner', 'competitor', 'competitor']);
  assert.equal(result.businesses[2].status, 'unavailable');
  assert.doesNotMatch(result.businesses[2].summary, /special offer/);
  assert.ok(result.limitations.some(value => value.includes('partial comparison')));
});

// End-to-end orchestration with a mock transport, never real API requests.
function mockFetch(t, responses) {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options, body: JSON.parse(options.body) });
    const response = responses.shift();
    if (!response) throw new Error('Unexpected additional API call');
    return Response.json(response.body || {}, { status: response.status || 200 });
  };
  t.after(() => { globalThis.fetch = original; });
  return calls;
}
test('runs two bounded calls and assembles a live report using retrieved sources', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)], stop_reason: 'end_turn', usage: { input_tokens: 100, output_tokens: 10 } } },
    { body: { content: [{ type: 'text', text: JSON.stringify(generated()) }], usage: { input_tokens: 200, output_tokens: 20 } } },
  ]);
  const report = await research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder');
  assert.equal(calls.length, 2);
  assert.ok(calls.every(call => call.url === 'https://api.anthropic.com/v1/messages'));
  assert.equal(calls[0].body.tools[0].max_uses, 8);
  assert.equal(calls[1].body.tools, undefined);
  assert.equal(calls[1].body.tool_choice, undefined);
  assert.equal(calls[1].body.output_config.format.type, 'json_schema');
  const schema = calls[1].body.output_config.format.schema;
  assert.equal(schema.additionalProperties, false);
  assert.ok(schema.required.includes('recommendations'));
  assert.ok(schema.properties.recommendations.items.required.includes('sourceIds'));
  assert.ok(schema.properties.recommendations.items.required.includes('draft'));
  assert.equal(report.mode, 'live');
  assert.equal(report.recommendations.length, 1);
  assert.deepEqual(report.usage, { inputTokens: 300, outputTokens: 30 });
  assert.equal(JSON.stringify(calls[1].body).includes('test-placeholder'), false);
});
test('does not generate recommendations if the owner cannot be read', async t => {
  const calls = mockFetch(t, [{ body: { content: [fetched(RIVAL)] } }]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), /Your website could not be read/);
  assert.equal(calls.length, 1);
});
test('does not generate recommendations if all competitors are unavailable', async t => {
  const calls = mockFetch(t, [{ body: { content: [fetched()] } }]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), /None of the competitor websites/);
  assert.equal(calls.length, 1);
});
test('does not silently resume paused server-tool turns or expand the fetch budget', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)], stop_reason: 'pause_turn' } },
    { body: { content: [{ type: 'text', text: JSON.stringify(generated()) }] } },
  ]);
  const result = await research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder');
  assert.equal(calls.length, 2);
  assert.ok(result.limitations.some(value => value.includes('stopped at the research budget')));
});
test('surfaces authentication failures without returning provider payloads', async t => {
  const calls = mockFetch(t, [{ status: 401, body: { error: 'provider-internal-detail' } }]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), error => error.status === 503 && /connection needs attention/.test(error.message) && !error.message.includes('provider-internal-detail'));
  assert.equal(calls.length, 1);
});

test('API rejects cross-origin research and oversized bodies before invoking Claude', async () => {
  const route = modules({ 'cloudflare:workers': { env: { ANTHROPIC_API_KEY: 'test-placeholder' } } })('app/api/research/route.ts');
  const crossOrigin = await route.POST(new Request('https://nearby.site/api/research', { method: 'POST', headers: { origin: 'https://unrelated.com', 'content-type': 'application/json' }, body: '{}' }));
  assert.equal(crossOrigin.status, 403);
  const oversized = await route.POST(new Request('https://nearby.site/api/research', { method: 'POST', headers: { 'content-type': 'application/json' }, body: 'x'.repeat(20001) }));
  assert.equal(oversized.status, 413);
});
test('API clearly reports missing provider configuration', async () => {
  const route = modules({ 'cloudflare:workers': { env: {} } })('app/api/research/route.ts');
  const result = await route.POST(new Request('https://nearby.site/api/research', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' }));
  assert.equal(result.status, 503);
  assert.match((await result.json()).error, /not connected yet/);
});


test('surfaces provider rate limits as retryable failures', async t => {
  mockFetch(t, [{ status: 429, body: { error: 'provider-internal-detail' } }]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), error => error.status === 429 && /usage limit/.test(error.message));
});

test('concurrent API requests cannot both enter the paid research flow', async () => {
  let release;
  let calls = 0;
  const waiting = new Promise(resolve => { release = resolve; });
  const route = modules({
    'cloudflare:workers': { env: { ANTHROPIC_API_KEY: 'test-placeholder' } },
    '@/lib/research': { research: async () => { calls += 1; await waiting; return { id: 'test' }; } },
  })('app/api/research/route.ts');
  const request = () => new Request('https://nearby.site/api/research', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ businessWebsite: OWNER, competitors: [RIVAL] }),
  });
  const first = route.POST(request());
  const second = route.POST(request());
  await new Promise(resolve => setImmediate(resolve));
  release();
  const results = await Promise.all([first, second]);
  assert.equal(calls, 1, 'Only one request may invoke the provider while the first is pending.');
  assert.deepEqual(results.map(response => response.status).sort(), [200, 429]);
});


test('rejects malformed JSON analysis output without saving a report', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [{ type: 'text', text: '{"businessName": "Owner Bakery", "recommendations": [' }], stop_reason: 'end_turn' } },
  ]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), error => error.status === 502 && /report was incomplete/.test(error.message));
  assert.equal(calls.length, 2);
});
test('rejects syntactically valid JSON that does not meet the report contract', async t => {
  mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [{ type: 'text', text: '{"businessName":"Owner Bakery"}' }] } },
  ]);
  await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), error => error.status === 502 && /report was incomplete/.test(error.message));
});
test('parses JSON text blocks while ignoring other response content', async t => {
  const serialized = JSON.stringify(generated());
  const split = Math.floor(serialized.length / 2);
  mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [
      { type: 'thinking', thinking: 'This is not report output.' },
      { type: 'text', text: serialized.slice(0, split) },
      { type: 'text', text: serialized.slice(split) },
    ] } },
  ]);
  const result = await research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder');
  assert.equal(result.businessName, 'Owner Bakery');
  assert.equal(result.recommendations[0].title, 'Clarify pickup instructions');
});


test('reports generation-budget exhaustion explicitly and never saves truncated output', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [
      { type: 'thinking', thinking: 'Analysis consumed most of the generation budget.' },
      { type: 'text', text: '{"businessName":"Owner Bakery","recommendations":[' },
    ], stop_reason: 'max_tokens' } },
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [{ type: 'text', text: JSON.stringify(generated()) }], stop_reason: 'max_tokens' } },
  ]);
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await assert.rejects(() => research({ businessWebsite: OWNER, competitors: [RIVAL] }, 'test-placeholder'), error => {
      assert.equal(error.status, 502);
      assert.match(error.message, /exceeded its generation budget/);
      assert.match(error.message, /narrower goal or fewer competitors/);
      assert.doesNotMatch(error.message, /report was incomplete/);
      return true;
    });
  }
  assert.equal(calls.length, 4, 'Budget exhaustion must not trigger an unbounded retry.');
});

test('preserves a 107-character effort description without relaxing source validation', () => {
  const data = generated();
  const recommendation = data.recommendations[0];
  data.recommendations = [
    structuredClone(recommendation),
    { ...structuredClone(recommendation), title: 'Review the ordering guide' },
    { ...structuredClone(recommendation), title: 'Check pickup information', effort: 'Estimated 1–2 hours to review ordering details, update the website, and confirm the wording with your team.' },
  ];
  const effort = data.recommendations[2].effort;
  assert.equal(effort.length, 107);
  const result = assembleReport(data, evidence(), input(), checkedAt);
  assert.equal(result.recommendations.length, 3);
  assert.equal(result.recommendations[2].effort, effort, 'A valid explanation must be preserved, not truncated.');
  data.recommendations[2].sourceIds = ['invented-source'];
  assert.throws(() => assembleReport(data, evidence(), input(), checkedAt), /unverified source/);
});

test('accepts longer verified quotes and checklists while keeping displayed excerpts short', () => {
  const quote = 'Our pickup ordering guide explains how to choose bread and pastries, select an available collection day, and review the order before paying. Customers should check the current menu for available items and contact the bakery about any special requirements before placing an order. Product availability can vary by day, and the team can explain which options are currently available.';
  assert.ok(quote.length > 260);
  const sourceText = `Welcome to our bakery website. The following guide describes our public pickup process and the information customers should review before ordering. ${quote}`;
  const refs = collectEvidence([fetched(OWNER, sourceText), fetched(RIVAL)], [OWNER, RIVAL], checkedAt);
  const data = generated();
  data.sourceNotes = [{ sourceId: 's1', excerpt: quote }];
  data.recommendations[0].ownerChecks = [
    'Confirm the pickup deadline.', 'Confirm the available collection days.',
    'Check the current menu.', 'Confirm the payment process.',
    'Check the contact details.', 'Review the wording before publication.',
  ];
  data.limitations = Array.from({ length: 9 }, (_, index) => `Evidence limitation ${index + 1}: confirm the applicable detail with the owner.`);
  const result = assembleReport(data, refs, input(), checkedAt);
  assert.equal(result.recommendations[0].ownerChecks.length, 6);
  assert.ok(data.limitations.every(limitation => result.limitations.includes(limitation)));
  const excerpt = result.sources[0].excerpt;
  assert.ok(excerpt.split(/\s+/).length <= 24);
  assert.ok(excerpt.length <= 220);
  assert.ok(quote.includes(excerpt));
  assert.notEqual(excerpt, refs[0].excerpt, 'The verified quote should be selected instead of the generic page preview.');
  data.sourceNotes[0].excerpt = `${quote} We guarantee every customer will double their revenue.`;
  const forged = assembleReport(data, refs, input(), checkedAt);
  assert.equal(forged.sources[0].excerpt, refs[0].excerpt, 'A forged long quote must fall back to actual retrieved text.');
});

// Owner-provided business context is optional and never becomes fetched evidence.
test('accepts legacy website-only input and removes blank questionnaire answers', () => {
  const legacy = input();
  assert.equal(legacy.goal, '');
  assert.deepEqual(legacy.profile, {});
  const blank = parseInput({ businessWebsite: OWNER, competitors: [RIVAL], goal: '  ', profile: { businessType: ' ', location: '\n', offerings: '', customers: '  ', currentApproach: '', constraints: '\t' } });
  assert.equal(blank.goal, '');
  assert.deepEqual(blank.profile, {});
  assert.equal(parseInput({ businessWebsite: OWNER, competitors: [RIVAL], goal: `  ${'x'.repeat(400)}  ` }).goal.length, 400);
  assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: [RIVAL], goal: 'x'.repeat(401) }));
  const result = assembleReport(generated(), evidence(), blank, checkedAt);
  assert.equal(result.ownerContext, undefined, 'Empty answers must not be presented as owner-provided facts.');
});
test('validates questionnaire shape, known fields, and individual length limits', () => {
  const limits = { businessType: 100, location: 160, offerings: 600, customers: 400, currentApproach: 600, constraints: 600 };
  for (const [key, maximum] of Object.entries(limits)) {
    assert.equal(parseInput({ businessWebsite: OWNER, competitors: [RIVAL], profile: { [key]: 'x'.repeat(maximum) } }).profile[key].length, maximum);
    assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: [RIVAL], profile: { [key]: 'x'.repeat(maximum + 1) } }), undefined, key);
    assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: [RIVAL], profile: { [key]: 7 } }), undefined, key);
  }
  for (const profile of [null, [], 'not an object', { madeUpField: 'extra' }, { constraints: null }, { offerings: ['bread'] }]) {
    assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: [RIVAL], profile }));
  }
});
test('retains a normalized owner snapshot separately from sources and ignores model replacements', () => {
  const submitted = parseInput({ businessWebsite: OWNER, competitors: [RIVAL], goal: '  More weekday pickup orders  ', profile: { businessType: '  Bakery  ', location: '  Fremont, Seattle  ', offerings: '  Bread and pastry boxes  ', customers: '  Nearby office workers  ', currentApproach: '  We already send an email newsletter  ', constraints: '  No new products; two hours per week  ' } });
  const expected = { goal: 'More weekday pickup orders', profile: { businessType: 'Bakery', location: 'Fremont, Seattle', offerings: 'Bread and pastry boxes', customers: 'Nearby office workers', currentApproach: 'We already send an email newsletter', constraints: 'No new products; two hours per week' } };
  const model = generated();
  model.ownerContext = { goal: 'Fabricated goal', profile: { constraints: 'Unlimited budget' } };
  const report = assembleReport(model, evidence(), submitted, checkedAt);
  assert.deepEqual(report.ownerContext, expected);
  assert.deepEqual(report.sources.map(s => s.id), ['s1', 's2']);
  assert.ok(report.sources.every(source => !source.excerpt.includes('two hours per week')));
  assert.ok(report.limitations.some(value => /owner|provided|questionnaire/i.test(value)), 'The report should disclose that submitted context is not independent website evidence.');
  model.recommendations[0].sourceIds.push('owner-context');
  assert.throws(() => assembleReport(model, evidence(), submitted, checkedAt), /unverified source/);
});
test('keeps an explicit goal in the owner snapshot even when the questionnaire is skipped', () => {
  const submitted = parseInput({ businessWebsite: OWNER, competitors: [RIVAL], goal: 'More weekday customers' });
  const report = assembleReport(generated(), evidence(), submitted, checkedAt);
  assert.deepEqual(report.ownerContext, { goal: 'More weekday customers', profile: {} });
});
test('questionnaire answers cannot replace missing website evidence', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(RIVAL)] } },
    { body: { content: [fetched()] } },
  ]);
  const ownerInput = { businessWebsite: OWNER, competitors: [RIVAL], profile: { offerings: 'The owner says this bakery sells bread.', constraints: 'Two hours available per week.' } };
  await assert.rejects(() => research(ownerInput, 'test-placeholder'), /Your website could not be read/);
  await assert.rejects(() => research(ownerInput, 'test-placeholder'), /None of the competitor websites/);
  assert.equal(calls.length, 2, 'Neither missing-evidence case should reach the analysis phase.');
});
test('API accepts a valid multilingual questionnaire above the former 5 KB limit', async () => {
  let received;
  const route = modules({
    'cloudflare:workers': { env: { ANTHROPIC_API_KEY: 'test-placeholder' } },
    '@/lib/research': { research: async value => { received = value; return { id: 'multilingual-test' }; } },
  })('app/api/research/route.ts');
  const profile = { businessType: '店'.repeat(100), location: '街'.repeat(160), offerings: '物'.repeat(600), customers: '客'.repeat(400), currentApproach: '做'.repeat(600), constraints: '限'.repeat(600) };
  const body = JSON.stringify({ businessWebsite: OWNER, competitors: [RIVAL], businessName: '店'.repeat(100), goal: '目'.repeat(400), profile });
  assert.ok(Buffer.byteLength(body, 'utf8') > 5000 && Buffer.byteLength(body, 'utf8') < 20000);
  const response = await route.POST(new Request('https://nearby.site/api/research', { method: 'POST', headers: { 'content-type': 'application/json' }, body }));
  assert.equal(response.status, 200);
  assert.deepEqual(received.profile, profile);
});
test('API caps actual UTF-8 request bytes before research even without a length header', async () => {
  let calls = 0;
  const route = modules({
    'cloudflare:workers': { env: { ANTHROPIC_API_KEY: 'test-placeholder' } },
    '@/lib/research': { research: async () => { calls += 1; return { id: 'should-not-run' }; } },
  })('app/api/research/route.ts');
  const body = '界'.repeat(7000);
  assert.ok(body.length < 20000 && Buffer.byteLength(body, 'utf8') > 20000);
  const response = await route.POST(new Request('https://nearby.site/api/research', { method: 'POST', headers: { 'content-type': 'application/json' }, body }));
  assert.equal(response.status, 413);
  assert.equal(calls, 0);
});


test('sends normalized questionnaire answers only to analysis and keeps them out of fetched evidence', async t => {
  const model = generated();
  model.ownerContext = { goal: 'Model replacement', profile: { constraints: 'Unlimited resources' } };
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [{ type: 'text', text: JSON.stringify(model) }] } },
  ]);
  const ownerInput = { businessWebsite: OWNER, competitors: [RIVAL], goal: '  More weekday orders  ', profile: { offerings: '  Seasonal pastry boxes  ', currentApproach: '  Already have online ordering  ', constraints: '  Two staff-hours available, no new equipment.  ' } };
  const expectedProfile = { offerings: 'Seasonal pastry boxes', currentApproach: 'Already have online ordering', constraints: 'Two staff-hours available, no new equipment.' };
  const report = await research(ownerInput, 'test-placeholder');
  assert.equal(calls.length, 2);
  const fetchRequest = JSON.stringify(calls[0].body);
  for (const value of [ownerInput.goal.trim(), ...Object.values(expectedProfile)]) {
    assert.ok(!fetchRequest.includes(value), 'Private questionnaire answers must not be sent during website fetching.');
  }
  const analysis = JSON.parse(calls[1].body.messages[0].content);
  assert.equal(analysis.ownerGoal, ownerInput.goal.trim());
  assert.deepEqual(analysis.ownerProvidedProfile, expectedProfile);
  assert.deepEqual(analysis.evidence.map(({ id, url, text }) => ({ id, url, text })), [
    { id: 's1', url: OWNER, text: pageText },
    { id: 's2', url: RIVAL, text: pageText },
  ]);
  assert.deepEqual(report.ownerContext, { goal: ownerInput.goal.trim(), profile: expectedProfile });
});

test('questionnaire does not make the owner website or competitor list optional', () => {
  const profile = { businessType: 'Bakery', location: 'Seattle', offerings: 'Bread' };
  assert.throws(() => parseInput({ competitors: [RIVAL], profile }));
  assert.throws(() => parseInput({ businessWebsite: OWNER, profile }));
  assert.throws(() => parseInput({ businessWebsite: OWNER, competitors: [], profile }));
});


test('does not save the default analysis goal as an answer from the owner', async t => {
  const calls = mockFetch(t, [
    { body: { content: [fetched(), fetched(RIVAL)] } },
    { body: { content: [{ type: 'text', text: JSON.stringify(generated()) }] } },
  ]);
  const profile = { constraints: 'One hour available each week' };
  const report = await research({ businessWebsite: OWNER, competitors: [RIVAL], profile }, 'test-placeholder');
  const analysis = JSON.parse(calls[1].body.messages[0].content);
  assert.ok(analysis.ownerGoal.length > 0, 'The model may receive a fallback goal for an unanswered question.');
  assert.deepEqual(report.ownerContext, { goal: '', profile }, 'The saved snapshot must contain only actual submitted answers.');
});
