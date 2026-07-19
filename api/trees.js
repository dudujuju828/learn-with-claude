// Server-side tree history, so every logged-in device sees the same past
// investigations. Each knowledge tree is one row in Neon Postgres (see
// api/_db.js) — the document is the same portable .know.json the CLI writes,
// with a server-stamped `rev` so devices can sync without clock comparisons.
//
// Auth matches api/index.py: an HMAC-signed expiry timestamp in the lwc_auth
// cookie, keyed off APP_PASSWORD.
//
//   GET    /api/trees        -> { trees: [{id, rev, size, updated_at, deleted}] }
//                               (uploadedAt kept as an alias for older clients)
//   GET    /api/trees?id=X   -> { tree } | { deleted: true, rev }
//   POST   /api/trees {tree, base_rev}
//                            -> { ok, rev }
//                               409 { error, rev, tree? , deleted? } when
//                               base_rev is stale — the current server copy
//                               rides along so the client can merge and retry.
//                               base_rev 0 creates (and resurrects tombstones);
//                               a missing base_rev is a legacy client: last
//                               write wins, as before the restructure.
//   DELETE /api/trees?id=X   -> { ok }   (leaves a tombstone)

const { sql } = require("./_db");
const { authed } = require("./_auth");

const FORMAT = "learn-with-claude/knowledge-tree";
const MAX_BYTES = 2_000_000;
const idOk = (id) => /^[a-z0-9][a-z0-9-]{0,63}$/.test(id);

async function current(id) {
  const rows = await sql`SELECT doc, rev, deleted FROM docs WHERE id = ${id}`;
  return rows[0] || null;
}

function conflict(res, row) {
  if (row && row.deleted) {
    return res.status(409).json({ error: "conflict: deleted elsewhere", rev: row.rev, deleted: true });
  }
  return res.status(409).json({ error: "conflict: newer revision on server",
                                rev: row ? row.rev : 0, tree: row ? row.doc : null });
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (!authed(req)) return res.status(401).json({ error: "not logged in" });
  const id = String(req.query.id || "");

  try {
    if (req.method === "GET" && !id) {
      const rows = await sql`
        SELECT id, rev, deleted, updated_at,
               coalesce(octet_length(doc::text), 0) AS size
        FROM docs WHERE id NOT LIKE 'settings:%'`;
      return res.status(200).json({
        trees: rows.map((r) => ({
          id: r.id, rev: r.rev, deleted: r.deleted, size: r.size,
          updated_at: r.updated_at, uploadedAt: r.updated_at,
        })),
      });
    }

    if (req.method === "GET") {
      if (!idOk(id)) return res.status(400).json({ error: "bad id" });
      const row = await current(id);
      if (!row) return res.status(404).json({ error: "no such tree" });
      if (row.deleted) return res.status(200).json({ deleted: true, rev: row.rev });
      return res.status(200).json({ tree: row.doc });
    }

    if (req.method === "POST" || req.method === "PUT") {
      const tree = req.body && req.body.tree;
      if (!tree || tree.format !== FORMAT || !idOk(String(tree.id || ""))) {
        return res.status(400).json({ error: "body must be {tree} in knowledge-tree format" });
      }
      const body = JSON.stringify(tree);
      if (body.length > MAX_BYTES) return res.status(413).json({ error: "tree too large" });
      const baseRev = req.body.base_rev;

      if (baseRev === undefined || baseRev === null) {
        // legacy client (pre-rev deploy, or an old tab's unload beacon)
        const rows = await sql`
          INSERT INTO docs (id, doc, rev)
          VALUES (${tree.id}, jsonb_set(${body}::jsonb, '{rev}', to_jsonb(1)), 1)
          ON CONFLICT (id) DO UPDATE SET
            doc = jsonb_set(EXCLUDED.doc, '{rev}', to_jsonb(docs.rev + 1)),
            rev = docs.rev + 1, deleted = false, updated_at = now()
          RETURNING rev`;
        return res.status(200).json({ ok: true, id: tree.id, rev: rows[0].rev });
      }

      const base = parseInt(baseRev, 10) || 0;
      if (base > 0) {
        const rows = await sql`
          UPDATE docs SET
            doc = jsonb_set(${body}::jsonb, '{rev}', to_jsonb(docs.rev + 1)),
            rev = docs.rev + 1, updated_at = now()
          WHERE id = ${tree.id} AND rev = ${base} AND deleted = false
          RETURNING rev`;
        if (rows.length) return res.status(200).json({ ok: true, id: tree.id, rev: rows[0].rev });
        const row = await current(tree.id);
        if (row) return conflict(res, row);
        // row vanished (should not happen — tombstones persist); fall through
        // to the create path below rather than erroring the push away
      }
      const ins = await sql`
        INSERT INTO docs (id, doc, rev)
        VALUES (${tree.id}, jsonb_set(${body}::jsonb, '{rev}', to_jsonb(1)), 1)
        ON CONFLICT (id) DO NOTHING
        RETURNING rev`;
      if (ins.length) return res.status(200).json({ ok: true, id: tree.id, rev: ins[0].rev });
      // exists already — a tombstone is resurrected (an explicit create wins
      // over an old deletion); a live row is a genuine conflict
      const rez = await sql`
        UPDATE docs SET
          doc = jsonb_set(${body}::jsonb, '{rev}', to_jsonb(docs.rev + 1)),
          rev = docs.rev + 1, deleted = false, updated_at = now()
        WHERE id = ${tree.id} AND deleted = true
        RETURNING rev`;
      if (rez.length) return res.status(200).json({ ok: true, id: tree.id, rev: rez[0].rev });
      return conflict(res, await current(tree.id));
    }

    if (req.method === "DELETE") {
      if (!idOk(id)) return res.status(400).json({ error: "bad id" });
      await sql`
        INSERT INTO docs (id, doc, rev, deleted) VALUES (${id}, NULL, 1, true)
        ON CONFLICT (id) DO UPDATE SET
          doc = NULL, deleted = true, rev = docs.rev + 1, updated_at = now()`;
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (err) {
    return res.status(500).json({ error: "server error: " + (err && err.message || err) });
  }
};
