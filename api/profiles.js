// Profiles — the named interest areas ("computer-science", "history") that
// scope the whole app. Stored as one small JSON doc in the docs table
// (id "settings:profiles"), same pattern as api/tutors.js.
//
// Why a registry at all, when the filing already lives on each tree? Because
// a profile derived purely from the trees wearing its name cannot be created
// before its first conversation, and evaporates the moment its last tree is
// refiled or deleted. The registry makes a profile a record in its own right:
// created here, deleted here, and carrying the learning settings that
// interest is read with.
//
// `active` rides in the same doc on purpose. The profile you are in is the
// app's context, not a per-browser guess, so the server is the authority on
// it and every device agrees. Whole-document last-write-wins: the doc is
// tiny and a person is in one profile at a time.
//
//   GET  /api/profiles         -> { doc: {saved_at, active, profiles: [...]} | null }
//   POST /api/profiles {doc}   -> { ok }

const { sql } = require("./_db");
const { authed } = require("./_auth");

const DOC_ID = "settings:profiles";
const MAX_PROFILES = 60;
const MAX_NAME = 40;

// mirrors cleanProfileName() in public/index.html: names reach the client
// inside inline handlers, so quote-ish characters never enter the registry
const nameOk = (s) =>
  typeof s === "string" && s.trim() && s.length <= MAX_NAME && !/['"\\<>&]/.test(s);

function validDoc(doc) {
  if (!doc || typeof doc !== "object" || !Array.isArray(doc.profiles)) return false;
  if (doc.profiles.length > MAX_PROFILES) return false;
  if (doc.active !== undefined && doc.active !== "" && !nameOk(doc.active)) return false;
  return doc.profiles.every((p) =>
    p && typeof p === "object" && nameOk(p.name) &&
    (p.settings === undefined ||
     (p.settings && typeof p.settings === "object" && !Array.isArray(p.settings))));
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
      if (!validDoc(doc)) return res.status(400).json({ error: "invalid profiles document" });
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
