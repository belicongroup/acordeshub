import { cp, mkdir, rm, copyFile } from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const dist = path.join(root, "dist");

const copyPlans = [
  ["chords", "chords"],
  ["lyrics-viewer", "lyrics-viewer"],
  ["search", "search"],
];

await rm(dist, { recursive: true, force: true });
await mkdir(dist, { recursive: true });

for (const [from, to] of copyPlans) {
  const src = path.join(root, from);
  const dest = path.join(dist, to);
  await cp(src, dest, { recursive: true });
}

await copyFile(path.join(root, "songs-index.json"), path.join(dist, "songs-index.json"));

console.log("Wrote dist/ for Cloudflare Pages (site assets only).");
