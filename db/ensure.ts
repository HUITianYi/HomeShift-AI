import { env } from "cloudflare:workers";

let initialized = false;

export async function ensureSchema() {
  if (initialized) return;

  const binding = (env as unknown as { DB?: D1Database }).DB;
  if (!binding) {
    throw new Error("D1 binding DB is not available.");
  }

  await binding.batch([
    binding.prepare(`
      CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY NOT NULL,
        household_name TEXT NOT NULL,
        profile_json TEXT NOT NULL,
        baseline_json TEXT NOT NULL,
        plans_json TEXT NOT NULL,
        selected_plan TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `),
    binding.prepare(`
      CREATE TABLE IF NOT EXISTS checkins (
        id TEXT PRIMARY KEY NOT NULL,
        session_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        result_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      )
    `),
    binding.prepare(`
      CREATE TABLE IF NOT EXISTS uploads (
        id TEXT PRIMARY KEY NOT NULL,
        session_id TEXT NOT NULL,
        object_key TEXT NOT NULL,
        kind TEXT NOT NULL,
        file_name TEXT NOT NULL,
        content_type TEXT NOT NULL,
        size_bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL
      )
    `),
  ]);

  initialized = true;
}
