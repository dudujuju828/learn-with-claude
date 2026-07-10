// Shared cookie auth for the Node endpoints — matches api/index.py: an
// HMAC-signed expiry timestamp in the lwc_auth cookie, keyed off APP_PASSWORD.
// (Files starting with "_" in /api are not exposed as functions.)

const crypto = require("crypto");

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

module.exports = { authed };
