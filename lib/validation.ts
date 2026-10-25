import { z } from 'zod';

export class ResearchError extends Error {
  constructor(message: string, public status = 400) { super(message); }
}

export function normalizeWebsite(value: string): string {
  if (typeof value !== 'string' || value.trim().length > 250) throw new ResearchError('Enter a website address under 250 characters.');
  const raw = value.trim();
  let url: URL;
  try { url = new URL(raw.includes('://') ? raw : `https://${raw}`); }
  catch { throw new ResearchError('Enter a valid public business website, such as example.com.'); }
  const host = url.hostname.toLowerCase();
  if (url.protocol !== 'https:' || url.username || url.password || url.port || url.search || url.hash ||
    !/^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$/.test(host) ||
    /(?:^|\.)(?:localhost|local|internal|test|invalid|example|onion)$/.test(host) || /^(?:localhost|metadata|metadata\.google\.internal)$/.test(host)) {
    throw new ResearchError('Use a public HTTPS website without a login, port, query string, or fragment.');
  }
  return url.href;
}

export function domainOf(url: string) { return new URL(url).hostname.replace(/^www\./, '').toLowerCase(); }
export function belongsTo(url: string, website: string) {
  try { const host = domainOf(url); const root = domainOf(website); return host === root || host.endsWith(`.${root}`); } catch { return false; }
}

export const profileSchema = z.object({
  businessType: z.string().trim().max(100).optional(),
  location: z.string().trim().max(160).optional(),
  offerings: z.string().trim().max(600).optional(),
  customers: z.string().trim().max(400).optional(),
  currentApproach: z.string().trim().max(600).optional(),
  constraints: z.string().trim().max(600).optional(),
}).strict();

export const inputSchema = z.object({
  businessWebsite: z.string().min(1).max(250),
  competitors: z.array(z.string().min(1).max(250)).min(1).max(3),
  businessName: z.string().trim().max(100).optional().default(''),
  goal: z.string().trim().max(400).optional().default(''),
  profile: profileSchema.optional().default({}),
}).strict();
export function parseInput(raw: unknown) {
  const result = inputSchema.safeParse(raw);
  if (!result.success) {
    if (result.error.issues.some(issue => issue.path[0] === 'profile')) throw new ResearchError('Check your business questionnaire. Use text within each question’s character limit.');
    throw new ResearchError('Add your website and one to three competitor websites. Keep the goal under 400 characters.');
  }
  const profile = Object.fromEntries(Object.entries(result.data.profile).filter(([, value]) => Boolean(value)));
  const input = { ...result.data, profile, businessWebsite: normalizeWebsite(result.data.businessWebsite), competitors: result.data.competitors.map(normalizeWebsite) };
  const domains = [input.businessWebsite, ...input.competitors].map(domainOf);
  if (new Set(domains).size !== domains.length) throw new ResearchError('Use a different website for your business and each competitor.');
  if (domains.some((host, i) => domains.some((other, j) => i !== j && host.endsWith(`.${other}`)))) {
    throw new ResearchError('Use independent business domains. A business and its ordering subdomain cannot be compared as competitors.');
  }
  return input;
}

// Presentation limits are generous: the provider already bounds total output.
// Cosmetic verbosity must not discard otherwise valid, sourced recommendations.
const text = z.string().min(1).max(10000);
const ids = z.array(z.string().max(20)).min(1).max(8);
export const generatedSchema = z.object({
  businessName: z.string().min(1).max(500),
  summary: text,
  limitations: z.array(text).max(24),
  businesses: z.array(z.object({ name: z.string().max(500), url: z.string().max(250), summary: text, sourceIds: z.array(z.string().max(20)).max(8) })).min(2).max(4),
  recommendations: z.array(z.object({
    title: z.string().min(1).max(500), rationale: text, action: text, effort: z.string().max(500), metric: text,
    ownerChecks: z.array(text).min(1).max(16), sourceIds: ids,
    draft: z.object({ channel: z.string().max(500), title: z.string().max(500), body: z.string().min(1).max(12000) }),
  })).min(1).max(3),
  sourceNotes: z.array(z.object({ sourceId: z.string().max(20), excerpt: z.string().max(18000) })).max(24),
});

export function requireKnownSources(ids: string[], known: Set<string>) {
  if (ids.some(id => !known.has(id))) throw new ResearchError('The generated report included an unverified source. Please try again.', 502);
}
