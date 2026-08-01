// Shared Neon Postgres access for the Node endpoints. One table holds every
// synced document: knowledge trees (id = the tree id) and the custom-tutors
// doc (id = "settings:tutors"). `rev` is a server-owned monotonic version —
// writes say which rev they were based on and lose (409) when it is stale,
// so a stale device can never silently overwrite a newer tree. Deletions
// keep a tombstone row (doc NULL, deleted true) so they propagate to every
// device instead of resurrecting from one that still holds a copy.

const { neon } = require("@neondatabase/serverless");

let client = null;
let schemaReady = null;
let imagesReady = null;

function db() {
  if (!client) {
    const url = process.env.DATABASE_URL || process.env.POSTGRES_URL;
    if (!url) {
      throw new Error("DATABASE_URL is not set — create a Neon database in " +
                      "the Vercel dashboard and connect it to this project");
    }
    client = neon(url);
  }
  return client;
}

function ensureSchema() {
  if (!schemaReady) {
    schemaReady = db()`
      CREATE TABLE IF NOT EXISTS docs (
        id         text PRIMARY KEY,
        doc        jsonb,
        rev        integer NOT NULL DEFAULT 1,
        updated_at timestamptz NOT NULL DEFAULT now(),
        deleted    boolean NOT NULL DEFAULT false
      )`.catch((err) => { schemaReady = null; throw err; });
  }
  return schemaReady;
}

// Generated figures (api/images.js). Its own table, not a docs row: these are
// binary and large, and keeping them out of `docs` means the tree listing
// never has to read past them. Bootstrapped separately so the endpoints that
// never touch images don't pay for the DDL check.
function ensureImages() {
  if (!imagesReady) {
    imagesReady = db()`
      CREATE TABLE IF NOT EXISTS images (
        id         text PRIMARY KEY,
        mime       text NOT NULL DEFAULT 'image/webp',
        bytes      bytea NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
      )`.catch((err) => { imagesReady = null; throw err; });
  }
  return imagesReady;
}

// tagged-template query that lazily bootstraps the schema on a cold start
async function sql(strings, ...values) {
  await ensureSchema();
  return db()(strings, ...values);
}

module.exports = { sql, ensureImages };
