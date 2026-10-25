declare namespace Cloudflare {
  interface Env {
    DB?: D1Database;
    BUCKET?: R2Bucket;
    ANTHROPIC_API_KEY?: string;
    SQUARE_ACCESS_TOKEN?: string;
    SQUARE_ENVIRONMENT?: 'sandbox' | 'production';
  }
}
