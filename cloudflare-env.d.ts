declare module "cloudflare:workers" {
  const env: {
    DB?: D1Database;
    UPLOADS?: R2Bucket;
    [key: string]: unknown;
  };

  export { env };
}
