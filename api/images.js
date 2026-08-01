// The bytes behind 🖼 illustrate. Figures live here and NOT on the tree:
// api/trees.js caps a knowledge tree at 2 MB and every tree shares one
// localStorage key in the browser, so a single generated image would crowd out
// the conversations it was meant to explain. The tree keeps the metadata
// (id, caption, alt, which turn it hangs from) and this keeps the pixels.
//
// One row per figure in its own table — bytea rather than jsonb, since base64
// in JSON would inflate an already-large blob by a third and make every
// SELECT on the docs table drag images along with it.
//
// Ids are content-free and immutable: an image is never edited, only made or
// deleted (a redraw is a new id). That is what lets GET answer with a
// year-long immutable cache header, so re-reading a conversation costs one
// request the first time and none after.
//
//   GET    /api/images?id=X   -> the raw image (image/webp, immutable)
//   POST   /api/images        {id, mime, data:<base64>} -> { ok }
//   DELETE /api/images?id=X   -> { ok }

const { sql, ensureImages } = require("./_db");
const { authed } = require("./_auth");

// generous: the client re-encodes to WebP well under this before it uploads,
// so anything near the cap means something went wrong upstream
const MAX_BYTES = 4_000_000;
const MIMES = new Set(["image/webp", "image/png", "image/jpeg"]);
const idOk = (id) => /^img_[a-z0-9]{6,32}$/.test(id);

module.exports = async (req, res) => {
  if (!authed(req)) {
    res.setHeader("Cache-Control", "no-store");
    return res.status(401).json({ error: "not logged in" });
  }
  const id = String(req.query.id || "");

  try {
    await ensureImages();

    if (req.method === "GET") {
      if (!idOk(id)) {
        res.setHeader("Cache-Control", "no-store");
        return res.status(400).json({ error: "bad id" });
      }
      const rows = await sql`SELECT mime, bytes FROM images WHERE id = ${id}`;
      if (!rows.length) {
        res.setHeader("Cache-Control", "no-store");
        return res.status(404).json({ error: "no such image" });
      }
      const buf = Buffer.from(rows[0].bytes);
      res.setHeader("Content-Type", rows[0].mime || "image/webp");
      res.setHeader("Content-Length", String(buf.length));
      res.setHeader("Cache-Control", "private, max-age=31536000, immutable");
      return res.status(200).send(buf);
    }

    res.setHeader("Cache-Control", "no-store");

    if (req.method === "POST" || req.method === "PUT") {
      const body = req.body || {};
      const imgId = String(body.id || "");
      const mime = String(body.mime || "image/webp");
      if (!idOk(imgId)) return res.status(400).json({ error: "bad id" });
      if (!MIMES.has(mime)) return res.status(400).json({ error: "unsupported image type" });
      if (typeof body.data !== "string" || !body.data) {
        return res.status(400).json({ error: "missing 'data'" });
      }
      const bytes = Buffer.from(body.data, "base64");
      if (!bytes.length) return res.status(400).json({ error: "unreadable image data" });
      if (bytes.length > MAX_BYTES) return res.status(413).json({ error: "image too large" });
      // DO NOTHING on conflict: an id is minted per figure and never reused,
      // so a repeat is a retry of the same upload, not a new picture
      await sql`
        INSERT INTO images (id, mime, bytes) VALUES (${imgId}, ${mime}, ${bytes})
        ON CONFLICT (id) DO NOTHING`;
      return res.status(200).json({ ok: true, id: imgId, size: bytes.length });
    }

    if (req.method === "DELETE") {
      if (!idOk(id)) return res.status(400).json({ error: "bad id" });
      await sql`DELETE FROM images WHERE id = ${id}`;
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (err) {
    res.setHeader("Cache-Control", "no-store");
    return res.status(500).json({ error: "server error: " + ((err && err.message) || err) });
  }
};
