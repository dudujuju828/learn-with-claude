// One-off migration: Vercel Blob (trees/<id>.json + settings/tutors.json)
// -> Neon Postgres docs table (see api/_db.js for the schema).
//
// Usage:
//   vercel env pull .env.migration --environment production
//   node --env-file=.env.migration scripts/migrate-blob-to-postgres.mjs
//
// Idempotent: rows that already exist are left alone (the app may have
// written newer revisions since), so it is safe to re-run.

import { list } from "@vercel/blob";
import { neon } from "@neondatabase/serverless";

const url = process.env.DATABASE_URL || process.env.POSTGRES_URL;
if (!url) { console.error("DATABASE_URL is not set"); process.exit(1); }
if (!process.env.BLOB_READ_WRITE_TOKEN) {
  console.error("BLOB_READ_WRITE_TOKEN is not set"); process.exit(1);
}
const sql = neon(url);

await sql`
  CREATE TABLE IF NOT EXISTS docs (
    id         text PRIMARY KEY,
    doc        jsonb,
    rev        integer NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now(),
    deleted    boolean NOT NULL DEFAULT false
  )`;

async function fetchJson(blob) {
  const r = await fetch(blob.url + "?b=" + Date.now(), { cache: "no-store" });
  if (!r.ok) throw new Error(`fetch ${blob.pathname}: HTTP ${r.status}`);
  return r.json();
}

async function upsert(id, doc) {
  const body = JSON.stringify(doc);
  const rows = await sql`
    INSERT INTO docs (id, doc, rev)
    VALUES (${id}, jsonb_set(${body}::jsonb, '{rev}', to_jsonb(1)), 1)
    ON CONFLICT (id) DO NOTHING
    RETURNING id`;
  return rows.length > 0;
}

let migrated = 0, skipped = 0, failed = 0;
let cursor;
do {
  const page = await list({ prefix: "trees/", cursor, limit: 1000 });
  for (const blob of page.blobs) {
    const id = blob.pathname.slice("trees/".length).replace(/\.json$/, "");
    try {
      const doc = await fetchJson(blob);
      if (!doc || doc.format !== "learn-with-claude/knowledge-tree" || String(doc.id) !== id) {
        console.warn(`  skip ${blob.pathname}: not a knowledge tree for id ${id}`);
        skipped++;
        continue;
      }
      if (await upsert(id, doc)) { console.log(`  migrated tree ${id}`); migrated++; }
      else { console.log(`  exists  tree ${id} (left alone)`); skipped++; }
    } catch (err) {
      console.error(`  FAILED ${blob.pathname}: ${err.message}`);
      failed++;
    }
  }
  cursor = page.hasMore ? page.cursor : undefined;
} while (cursor);

try {
  const page = await list({ prefix: "settings/tutors.json", limit: 5 });
  const blob = page.blobs.find((b) => b.pathname === "settings/tutors.json");
  if (blob) {
    const doc = await fetchJson(blob);
    if (await upsert("settings:tutors", doc)) { console.log("  migrated settings:tutors"); migrated++; }
    else { console.log("  exists  settings:tutors (left alone)"); skipped++; }
  }
} catch (err) {
  console.error(`  FAILED settings/tutors.json: ${err.message}`);
  failed++;
}

const [{ n }] = await sql`SELECT count(*)::int AS n FROM docs`;
console.log(`\ndone: ${migrated} migrated, ${skipped} already present/skipped, ` +
            `${failed} failed — ${n} docs now in Postgres`);
process.exit(failed ? 1 : 0);
