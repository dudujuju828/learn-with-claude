// Custom tutors — user-defined tutor styles, stored as one small JSON doc in
// the docs table (id "settings:tutors") so they follow the user across
// devices. Whole-document last-write-wins: the doc is tiny, edited rarely,
// and never edited concurrently in practice.
//
//   GET  /api/tutors           -> { doc: {saved_at, tutors: [{id,name,style}]} | null }
//   POST /api/tutors {doc}     -> { ok }

const { sql } = require("./_db");
const { authed } = require("./_auth");

const DOC_ID = "settings:tutors";
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
      const rows = await sql`
        SELECT doc FROM docs WHERE id = ${DOC_ID} AND NOT deleted`;
      return res.status(200).json({ doc: rows.length ? rows[0].doc : null });
    }

    if (req.method === "POST" || req.method === "PUT") {
      const doc = req.body && req.body.doc;
      if (!validDoc(doc)) return res.status(400).json({ error: "invalid tutors document" });
      await sql`
        INSERT INTO docs (id, doc) VALUES (${DOC_ID}, ${JSON.stringify(doc)}::jsonb)
        ON CONFLICT (id) DO UPDATE SET
          doc = EXCLUDED.doc, rev = docs.rev + 1, deleted = false, updated_at = now()`;
      return res.status(200).json({ ok: true });
    }

    return res.status(405).json({ error: "method not allowed" });
  } catch (err) {
    return res.status(500).json({ error: "server error: " + (err && err.message || err) });
  }
};
