// Server-side tree history, so every logged-in device sees the same past
// investigations. Each knowledge tree is stored as one blob at
// trees/<id>.json — the same portable .know.json document the CLI writes.
//
// Auth matches api/index.py: an HMAC-signed expiry timestamp in the lwc_auth
// cookie, keyed off APP_PASSWORD.
//
//   GET    /api/trees        -> { trees: [{id, size, uploadedAt}] }
//   GET    /api/trees?id=X   -> { tree }
//   POST   /api/trees {tree} -> { ok, id }   (overwrites; last write wins)
//   DELETE /api/trees?id=X   -> { ok }

const crypto = require("crypto");
const { list, put, del } = require("@vercel/blob");

const PREFIX = "trees/";
const FORMAT = "learn-with-claude/knowledge-tree";
const idOk = (id) => /^[a-z0-9][a-z0-9-]{0,63}$/.test(id);

function secretKey() {
  return crypto.createHash("sha256")
    .update("learn-with-claude-web:" + (process.env.APP_PASSWORD || ""))
    .digest();
}

function authed(req) {
  const cookie = (req.headers.cookie || "")
    .split(";").map((s) => s.trim())
    .find((s) => s.startsWith("lwc_auth="));
  if (!cookie) return false;
  const token = cookie.slice("lwc_auth=".length);
  const dot = token.indexOf(".");
  if (dot < 1) return false;
  const exp = token.slice(0, dot);
  const sig = Buffer.from(token.slice(dot + 1));
  const want = Buffer.from(
    crypto.createHmac("sha256", secretKey()).update(exp).digest("hex"));
  if (sig.length !== want.length || !crypto.timingSafeEqual(sig, want)) return false;
  return parseInt(exp, 10) > Date.now() / 1000;
}

async function findBlob(id) {
  const page = await list({ prefix: `${PREFIX}${id}.json`, limit: 10 });
  return page.blobs.find((b) => b.pathname === `${PREFIX}${id}.json`) || null;
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (!authed(req)) return res.status(401).json({ error: "not logged in" });
  const id = String(req.query.id || "");

  try {
    if (req.method === "GET" && !id) {
      const trees = [];
      let cursor;
      do {
        const page = await list({ prefix: PREFIX, cursor, limit: 1000 });
        for (const b of page.blobs) {
          trees.push({
            id: b.pathname.slice(PREFIX.length).replace(/\.json$/, ""),
            size: b.size,
            uploadedAt: b.uploadedAt,
          });
        }
        cursor = page.hasMore ? page.cursor : undefined;
      } while (cursor);
      return res.status(200).json({ trees });
    }

    if (req.method === "GET") {
      if (!idOk(id)) return res.status(400).json({ error: "bad id" });
      const blob = await findBlob(id);
      if (!blob) return res.status(404).json({ error: "no such tree" });
      // cache-buster: overwritten blobs can serve from the CDN for up to a
      // minute; a unique query string forces a fresh read
      const r = await fetch(blob.url + "?b=" + Date.now(), { cache: "no-store" });
      if (!r.ok) return res.status(502).json({ error: "blob fetch failed" });
      const tree = await r.json();
      return res.status(200).json({ tree });
    }

    if (req.method === "POST" || req.method === "PUT") {
      const tree = req.body && req.body.tree;
      if (!tree || tree.format !== FORMAT || !idOk(String(tree.id || ""))) {
        return res.status(400).json({ error: "body must be {tree} in knowledge-tree format" });
      }
      await put(`${PREFIX}${tree.id}.json`, JSON.stringify(tree), {
        access: "public",
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType: "application/json",
        cacheControlMaxAge: 60,
      });
      return res.status(200).json({ ok: true, id: tree.id });
    }

    if (req.method === "DELETE") {
      if (!idOk(id)) return res.status(400).json({ error: "bad id" });
      const blob = await findBlob(id);
      if (blob) await del(blob.url);
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (err) {
    return res.status(500).json({ error: "server error: " + (err && err.message || err) });
  }
};
