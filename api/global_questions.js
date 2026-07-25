// Global question bank — questions banked from anywhere (not tied to a
// specific investigation), investigated as a fresh root topic rather than a
// turn appended to whatever tree happened to be open. Stored as one small
// JSON doc in the docs table (id "settings:global_questions"), same pattern
// as api/tutors.js. Whole-document last-write-wins: the doc is small and
// practically never edited concurrently.
//
//   GET  /api/global_questions        -> { doc: {saved_at, questions: [...]} | null }
//   POST /api/global_questions {doc}  -> { ok }

const { sql } = require("./_db");
const { authed } = require("./_auth");

const DOC_ID = "settings:global_questions";
const MAX_QUESTIONS = 300;
const MAX_TEXT = 500;

function validDoc(doc) {
  if (!doc || typeof doc !== "object" || !Array.isArray(doc.questions)) return false;
  if (doc.questions.length > MAX_QUESTIONS) return false;
  return doc.questions.every((q) =>
    q && typeof q === "object" &&
    /^[a-f0-9]{8,32}$/.test(String(q.id || "")) &&
    typeof q.text === "string" && q.text.trim() && q.text.length <= MAX_TEXT);
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
      if (!validDoc(doc)) return res.status(400).json({ error: "invalid global questions document" });
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
