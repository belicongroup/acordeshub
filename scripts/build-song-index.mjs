import { readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const ROOT_DIR = process.cwd();
const CHORDS_DIR = path.join(ROOT_DIR, "chords");
const OUTPUT_FILE = path.join(ROOT_DIR, "songs-index.json");

const SPACE_REGEX = /\s+/g;

function titleCaseFromSlug(value) {
  return value
    .replace(/\.chords\.txt$/i, "")
    .replace(/[_-]+/g, " ")
    .trim()
    .split(" ")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function normalizeText(value) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]/g, " ")
    .replace(SPACE_REGEX, " ")
    .trim();
}

async function walk(dirPath) {
  const entries = await readdir(dirPath, { withFileTypes: true });
  const results = [];
  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      const nested = await walk(fullPath);
      results.push(...nested);
      continue;
    }
    if (entry.isFile() && entry.name.endsWith(".chords.txt")) {
      results.push(fullPath);
    }
  }
  return results;
}

function toSong(relativePath) {
  const webPath = relativePath.split(path.sep).join("/");
  const parts = webPath.split("/");
  const filename = parts.at(-1) || "";
  const artistFolder = parts.length >= 2 ? parts[parts.length - 2] : "Unknown";
  const title = titleCaseFromSlug(filename);
  const artist = titleCaseFromSlug(artistFolder);
  const id = webPath.replace(/\.chords\.txt$/i, "");
  const titleNormalized = normalizeText(title);
  const artistNormalized = normalizeText(artist);
  const searchText = `${titleNormalized} ${artistNormalized} ${normalizeText(filename)}`;
  return {
    id,
    title,
    artist,
    path: webPath,
    titleNormalized,
    artistNormalized,
    searchText,
  };
}

async function main() {
  const files = await walk(CHORDS_DIR);
  const songs = files
    .map((fullPath) => path.relative(ROOT_DIR, fullPath))
    .sort((a, b) => a.localeCompare(b))
    .map((relativePath) => toSong(relativePath));

  await writeFile(OUTPUT_FILE, `${JSON.stringify(songs, null, 2)}\n`, "utf8");
  console.log(`Indexed ${songs.length} songs -> songs-index.json`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
