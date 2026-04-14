#!/usr/bin/env node
/**
 * Dedupe chord files in chords-sc where the same song appears as both
 * underscore and hyphen slugs (e.g. 300_noches vs 300-noches).
 *
 * - Keeps the file with more lines as canonical (unchanged path).
 * - Tie on line count: prefer basename without "-" (underscore-style).
 * - Further tie: localeCompare on basename.
 * - Other files in the group rename to {normalized_stem}-2.chords.txt, -3, etc.
 * - If a target name exists, increments the numeric suffix until free.
 *
 * Default: dry-run. Pass --write to apply renames.
 *
 * Usage:
 *   node scripts/dedupe-chords-sc.mjs
 *   node scripts/dedupe-chords-sc.mjs --write
 *   node scripts/dedupe-chords-sc.mjs --root chords-sc --write
 */

import { readdir, readFile, rename } from "node:fs/promises";
import path from "node:path";

const ROOT_DIR = process.cwd();

function parseArgs(argv) {
  let rootRel = "chords-sc";
  let write = false;
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--write") write = true;
    else if (a === "--root" && argv[i + 1]) {
      rootRel = argv[++i];
    } else if (a === "--help" || a === "-h") {
      console.log(`Usage: node scripts/dedupe-chords-sc.mjs [--root <dir>] [--write]`);
      process.exit(0);
    }
  }
  return { rootRel, write };
}

function normalizeStem(basename) {
  const stem = basename.replace(/\.chords\.txt$/i, "");
  return stem
    .toLowerCase()
    .split(/[_-]+/)
    .filter(Boolean)
    .join("_");
}

async function lineCount(filePath) {
  const text = await readFile(filePath, "utf8");
  return text.split(/\r?\n/).length;
}

function compareCandidates(a, b) {
  if (b.lines !== a.lines) return b.lines - a.lines;
  const ah = a.base.includes("-") ? 1 : 0;
  const bh = b.base.includes("-") ? 1 : 0;
  if (ah !== bh) return ah - bh;
  return a.base.localeCompare(b.base);
}

/**
 * @param {string} artistDir
 * @returns {Promise<{ from: string, to: string }[]>}
 */
async function planArtistDir(artistDir) {
  const entries = await readdir(artistDir, { withFileTypes: true });
  const chordFiles = entries
    .filter((e) => e.isFile() && e.name.toLowerCase().endsWith(".chords.txt"))
    .map((e) => path.join(artistDir, e.name));

  if (chordFiles.length < 2) return [];

  /** @type {Map<string, string[]>} */
  const groups = new Map();
  for (const fp of chordFiles) {
    const base = path.basename(fp);
    const key = normalizeStem(base);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(fp);
  }

  const occupied = new Set(chordFiles.map((fp) => path.basename(fp)));
  /** @type { { from: string, to: string }[] } */
  const ops = [];

  for (const [groupStem, paths] of groups) {
    if (paths.length < 2) continue;

    const withMeta = await Promise.all(
      paths.map(async (fp) => {
        const base = path.basename(fp);
        const lines = await lineCount(fp);
        return { fp, base, lines };
      }),
    );

    withMeta.sort(compareCandidates);

    for (let i = 1; i < withMeta.length; i++) {
      const { fp: srcPath, base: srcBase } = withMeta[i];
      let num = i + 1;
      let candidateBase;
      for (;;) {
        candidateBase = `${groupStem}-${num}.chords.txt`;
        if (!occupied.has(candidateBase) || candidateBase === srcBase) {
          break;
        }
        num += 1;
      }

      if (candidateBase === srcBase) {
        continue;
      }

      const destPath = path.join(artistDir, candidateBase);
      ops.push({ from: srcPath, to: destPath });
      occupied.delete(srcBase);
      occupied.add(candidateBase);
    }
  }

  return ops;
}

async function main() {
  const { rootRel, write } = parseArgs(process.argv);
  const chordsRoot = path.resolve(ROOT_DIR, rootRel);

  const top = await readdir(chordsRoot, { withFileTypes: true });
  const artistDirs = top
    .filter((e) => e.isDirectory())
    .map((e) => path.join(chordsRoot, e.name));

  /** @type { { from: string, to: string }[] } */
  let allOps = [];
  for (const dir of artistDirs) {
    const part = await planArtistDir(dir);
    allOps.push(...part);
  }

  if (allOps.length === 0) {
    console.log(`No duplicate slug groups to resolve under ${chordsRoot}`);
    return;
  }

  console.log(
    write
      ? `Applying ${allOps.length} rename(s) under ${chordsRoot}:`
      : `Dry-run: would apply ${allOps.length} rename(s) under ${chordsRoot} (pass --write to apply):`,
  );

  for (const { from, to } of allOps) {
    const relFrom = path.relative(ROOT_DIR, from);
    const relTo = path.relative(ROOT_DIR, to);
    console.log(`  ${relFrom}  ->  ${relTo}`);
  }

  if (!write) {
    console.log("\nDry-run only; no files changed.");
    return;
  }

  for (const { from, to } of allOps) {
    await rename(from, to);
  }
  console.log(`\nDone. Renamed ${allOps.length} file(s).`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
