#!/usr/bin/env node
/*
 * patch-showdown-loopback.cjs — idempotent postinstall patch for the vendored
 * pokemon-showdown package.
 *
 * WHY: IPTools.getHost() runs a port-80 probe to classify an IP. On a dev host
 * where something else is bound to :80, the probe mislabels loopback
 * (127.0.0.1 / ::1) as '?/proxy', which trips Showdown's #hostfilter and blocks
 * poke-env login — breaking the local arena2d demo and any local self-play.
 *
 * This treats loopback as residential ("localhost/res") BEFORE the probe runs.
 * It is a LOCAL-DEV convenience: in CI/prod, login traffic does not originate
 * from loopback, so the short-circuit is effectively a no-op there.
 *
 * Reversible: `npm ci` / reinstall restores the pristine file; this script
 * re-applies on the next install. Idempotent: re-running is a no-op once the
 * marker is present. Fail-safe: any unexpected state logs a warning and exits 0
 * so it never breaks `npm install`.
 */
const fs = require("fs");

const MARKER = "[adx-loopback-patch]";

const ANCHOR = [
  '      if (!ip) {',
  '        resolve("");',
  '        return;',
  '      }',
  '      const ipNumber = IPTools.ipToNumber(ip);',
].join("\n");

const PATCH_BLOCK = [
  '      if (!ip) {',
  '        resolve("");',
  '        return;',
  '      }',
  '      // adx local-dev patch (reversible; npm reinstall restores): treat loopback',
  '      // as residential before the port-80 probe. The probe mislabels 127.0.0.1',
  "      // as '?/proxy' when something else on the dev host is bound to :80, which",
  '      // triggers #hostfilter and blocks poke-env login.',
  '      if (ip === "127.0.0.1" || ip === "::1" || ip === "::ffff:127.0.0.1") {',
  '        console.log("' + MARKER + ' getHost(\'" + ip + "\') -> localhost/res"); resolve("localhost/res");',
  '        return;',
  '      }',
  '      const ipNumber = IPTools.ipToNumber(ip);',
].join("\n");

function resolveIpTools() {
  try {
    return require.resolve("pokemon-showdown/dist/server/ip-tools.js", {
      paths: [__dirname + "/.."],
    });
  } catch (_e) {
    return null;
  }
}

function main() {
  const target = resolveIpTools();
  if (!target || !fs.existsSync(target)) {
    console.warn("[adx-patch] pokemon-showdown ip-tools.js not found — skipping (ok).");
    return;
  }
  const src = fs.readFileSync(target, "utf8");
  if (src.includes(MARKER)) {
    console.log("[adx-patch] loopback patch already present — no-op.");
    return;
  }
  if (!src.includes(ANCHOR)) {
    console.warn(
      "[adx-patch] anchor not found in ip-tools.js (showdown version changed?) — skipping (ok)."
    );
    return;
  }
  fs.writeFileSync(target, src.replace(ANCHOR, PATCH_BLOCK), "utf8");
  console.log("[adx-patch] applied loopback patch to " + target);
}

main();
