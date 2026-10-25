import { env } from 'cloudflare:workers';
import { research } from '@/lib/research';
import { parseInput, ResearchError } from '@/lib/validation';

export const dynamic = 'force-dynamic';
let active = false;
let lastStarted = 0;
const MAX_REQUEST_BYTES = 20000;

export async function POST(request: Request) {
  // This shared, owner-private prototype relies on Sites dispatch for browser and
  // service authentication. Preserve owner-private access when deploying it.
  const origin = request.headers.get('origin');
  if (origin && origin !== new URL(request.url).origin) return Response.json({ error: 'Open this app directly to run research.' }, { status: 403 });
  if (!request.headers.get('content-type')?.includes('application/json')) return Response.json({ error: 'Send a JSON research request.' }, { status: 415 });
  const key = env.ANTHROPIC_API_KEY;
  if (!key) return Response.json({ error: 'Live research is not connected yet. The site owner needs to configure the Claude API credential.' }, { status: 503 });
  if (Number(request.headers.get('content-length')) > MAX_REQUEST_BYTES) return Response.json({ error: 'The research request is too large.' }, { status: 413 });
  const raw = await request.text();
  if (new TextEncoder().encode(raw).byteLength > MAX_REQUEST_BYTES) return Response.json({ error: 'The research request is too large.' }, { status: 413 });
  let input: unknown;
  try { input = JSON.parse(raw); } catch { return Response.json({ error: 'The request could not be read. Please try again.' }, { status: 400 }); }
  try { input = parseInput(input); } catch (error) { return Response.json({ error: error instanceof ResearchError ? error.message : 'Check the website addresses and try again.' }, { status: 400 }); }
  if (active || Date.now() - lastStarted < 15000) return Response.json({ error: 'Research is already running or was just started. Please wait a moment before retrying.' }, { status: 429 });
  active = true;
  lastStarted = Date.now();
  try {
    const report = await research(input, key, request.signal);
    return Response.json({ report }, { headers: { 'Cache-Control': 'no-store' } });
  } catch (error) {
    if (error instanceof ResearchError) return Response.json({ error: error.message }, { status: error.status });
    return Response.json({ error: 'Research could not finish. Please try again. Your saved report and drafts are unchanged.' }, { status: 500 });
  } finally { active = false; }
}
