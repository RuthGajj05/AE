import { env } from 'cloudflare:workers';
export const dynamic = 'force-dynamic';
export async function GET() {
  return Response.json({ configured: Boolean(env.ANTHROPIC_API_KEY), provider: 'Claude', storage: 'browser' }, { headers: { 'Cache-Control': 'no-store' } });
}
