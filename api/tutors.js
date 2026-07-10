// Custom tutors — user-defined tutor styles, stored as one small JSON doc in
// Vercel Blob (settings/tutors.json) so they follow the user across devices.
//
//   GET  /api/tutors           -> { doc: {saved_at, tutors: [{id,name,style}]} | null }
//   POST /api/tutors {doc}     -> { ok }   (whole-document last-write-wins)

const { list, put } = require("@vercel/blob");
const { authed } = require("./_auth");

const PATH = "settings/tutors.json";
const MAX_TUTORS = 20;
const MAX_NAME = 40;
const MAX_STYLE = 4000;

function validDoc(doc) {
  if (!doc || typeof doc !== "object" || !Array.isArray(doc.tutors)) return false;
  if (doc.tutors.length > MAX_TUTORS) return false;
  return doc.tutors.every((t) =>
    t && typeof t === "object" &&
    /^[a-z0-9-]{1,32}$/.test(String(t.id || "")) &&
    typeof t.name === "string" && t.name.trim() && t.name.length <= MAX_NAME &&
    typeof t.style === "string" && t.style.trim() && t.style.length <= MAX_STYLE);
}

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (!authed(req)) return res.status(401).json({ error: "not logged in" });

  try {
    if (req.method === "GET") {
      const page = await list({ prefix: PATH, limit: 5 });
      const blob = page.blobs.find((b) => b.pathname === PATH);
      if (!blob) return res.status(200).json({ doc: null });
      const r = await fetch(blob.url + "?b=" + Date.now(), { cache: "no-store" });
      if (!r.ok) return res.status(502).json({ error: "blob fetch failed" });
      return res.status(200).json({ doc: await r.json() });
    }

    if (req.method === "POST" || req.method === "PUT") {
      const doc = req.body && req.body.doc;
      if (!validDoc(doc)) return res.status(400).json({ error: "invalid tutors document" });
      await put(PATH, JSON.stringify(doc), {
        access: "public",
        addRandomSuffix: false,
        allowOverwrite: true,
        contentType: "application/json",
        cacheControlMaxAge: 60,
      });
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (err) {
    return res.status(500).json({ error: "server error: " + (err && err.message || err) });
  }
};
