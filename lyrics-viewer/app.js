import { Chord, transpose } from "https://esm.sh/chord-transposer@3.0.9";

const SONG_INDEX_URL = "../songs-index.json";

const lyricsContent = document.getElementById("lyricsContent");
const songTitle = document.getElementById("songTitle");
const transposeUpBtn = document.getElementById("transposeUpBtn");
const transposeDownBtn = document.getElementById("transposeDownBtn");
const notationToggleBtn = document.getElementById("notationToggleBtn");

let originalSongText = "";
let currentTranspose = 0;
let notationMode = "english";
let songsCatalog = [];
let songsById = new Map();
const TOKEN_CANDIDATE_REGEX = /(^|[\s(])([^\s),.:;!?]+)(?=$|[\s),.:;!?])/g;
const SOLFEGE_TO_ENGLISH_BASE = {
  Do: "C",
  Re: "D",
  Mi: "E",
  Fa: "F",
  Sol: "G",
  La: "A",
  Si: "B",
};
const ENGLISH_TO_SOLFEGE_BASE = {
  C: "Do",
  D: "Re",
  E: "Mi",
  F: "Fa",
  G: "Sol",
  A: "La",
  B: "Si",
};

function safeParseChord(token) {
  try {
    return Chord.parse(token);
  } catch (_error) {
    return null;
  }
}

function parseSolfegeRoot(rawRoot) {
  const root = rawRoot.toLowerCase();
  if (root === "do") return "Do";
  if (root === "re") return "Re";
  if (root === "mi") return "Mi";
  if (root === "fa") return "Fa";
  if (root === "sol") return "Sol";
  if (root === "la") return "La";
  if (root === "si") return "Si";
  return null;
}

function parseEnglishChordParts(chordText) {
  const match = chordText.match(/^([A-G])([#b]?)([^/\s]*)(?:\/([A-G])([#b]?))?$/);
  if (!match) {
    return null;
  }

  return {
    root: `${match[1]}${match[2] || ""}`,
    suffix: match[3] || "",
    bass: match[4] ? `${match[4]}${match[5] || ""}` : "",
  };
}

function parseSolfegeChordParts(chordText) {
  const match = chordText.match(/^(Do|Re|Mi|Fa|Sol|La|Si)(#|b)?([^/\s]*)(?:\/(Do|Re|Mi|Fa|Sol|La|Si)(#|b)?)?$/i);
  if (!match) {
    return null;
  }

  const root = parseSolfegeRoot(match[1]);
  const bassRoot = match[4] ? parseSolfegeRoot(match[4]) : null;
  if (!root || (match[4] && !bassRoot)) {
    return null;
  }

  return {
    root: `${root}${match[2] || ""}`,
    suffix: match[3] || "",
    bass: bassRoot ? `${bassRoot}${match[5] || ""}` : "",
  };
}

function isEnglishChordCandidate(token) {
  return safeParseChord(token) !== null;
}

function isSolfegeChordCandidate(token) {
  return parseSolfegeChordParts(token) !== null;
}

function isTransposableChordCandidate(token) {
  return isEnglishChordCandidate(token) || isSolfegeChordCandidate(token);
}

function isStrongEnglishChordCandidate(token) {
  const parts = parseEnglishChordParts(token);
  if (!parts || !safeParseChord(token)) {
    return false;
  }

  return Boolean(parts.suffix || parts.bass || parts.root.includes("#") || parts.root.includes("b"));
}

function isStrongSolfegeChordCandidate(token) {
  const parts = parseSolfegeChordParts(token);
  if (!parts) {
    return false;
  }

  return Boolean(parts.suffix || parts.bass || parts.root.includes("#") || parts.root.includes("b"));
}

function isStrongTransposableChordCandidate(token) {
  return isStrongEnglishChordCandidate(token) || isStrongSolfegeChordCandidate(token);
}

function looksChordHeavyLine(line, isChordCandidate = isEnglishChordCandidate) {
  const tokens = line.split(/(\s+)/).filter((token) => token.trim());
  if (tokens.length === 0) {
    return false;
  }

  const chordCount = tokens.filter((token) => isChordCandidate(token)).length;
  if (chordCount === tokens.length) {
    return true;
  }

  // Also allow mixed lines when they are mostly chords.
  return chordCount >= 2 && chordCount / tokens.length >= 0.45;
}

function convertChordNotation(chordText, targetMode) {
  if (targetMode === "solfege") {
    const parts = parseEnglishChordParts(chordText);
    if (!parts) {
      return chordText;
    }

    const convertedRoot = ENGLISH_TO_SOLFEGE_BASE[parts.root[0]] + (parts.root[1] || "");
    const convertedBass = parts.bass
      ? `${ENGLISH_TO_SOLFEGE_BASE[parts.bass[0]]}${parts.bass[1] || ""}`
      : "";
    return `${convertedRoot}${parts.suffix}${convertedBass ? `/${convertedBass}` : ""}`;
  }

  if (targetMode === "english") {
    const parts = parseSolfegeChordParts(chordText);
    if (!parts) {
      return chordText;
    }

    const rootMatch = parts.root.match(/^(Do|Re|Mi|Fa|Sol|La|Si)(#|b)?$/);
    const bassMatch = parts.bass ? parts.bass.match(/^(Do|Re|Mi|Fa|Sol|La|Si)(#|b)?$/) : null;
    if (!rootMatch) {
      return chordText;
    }

    const convertedRoot = `${SOLFEGE_TO_ENGLISH_BASE[rootMatch[1]]}${rootMatch[2] || ""}`;
    const convertedBass = bassMatch ? `${SOLFEGE_TO_ENGLISH_BASE[bassMatch[1]]}${bassMatch[2] || ""}` : "";
    return `${convertedRoot}${parts.suffix}${convertedBass ? `/${convertedBass}` : ""}`;
  }

  return chordText;
}

function toEnglishChordIfPossible(chordText) {
  if (safeParseChord(chordText)) {
    return chordText;
  }

  if (isSolfegeChordCandidate(chordText)) {
    const english = convertChordNotation(chordText, "english");
    if (safeParseChord(english)) {
      return english;
    }
  }

  return chordText;
}

function transposeSingleChord(chordText, steps) {
  const normalizedChord = toEnglishChordIfPossible(chordText);

  try {
    if (steps > 0) {
      return transpose(normalizedChord).up(steps).toString();
    }
    if (steps < 0) {
      return transpose(normalizedChord).down(Math.abs(steps)).toString();
    }
    return normalizedChord;
  } catch (_error) {
    return chordText;
  }
}

function transformChordSymbols(songText, isChordCandidate, isStrongChordCandidate, transformChordText) {
  const lines = songText.split("\n");
  const transformedLines = lines.map((line) => {
    const withBracketChords = line.replace(/\[([^\]\n\r]+)\]/g, (match, inner) => {
      const trimmed = inner.trim();
      if (!isChordCandidate(trimmed)) {
        return match;
      }
      return `[${transformChordText(trimmed)}]`;
    });

    const lineLooksChordHeavy = looksChordHeavyLine(withBracketChords, isChordCandidate);
    if (!lineLooksChordHeavy) {
      // Inline chords on lyric lines still transpose if they have clear chord intent
      // (suffix/accidental/slash), e.g. "Am", "F#m", "FAm", "C/G".
      return withBracketChords.replace(TOKEN_CANDIDATE_REGEX, (full, prefix, candidate) => {
        if (!isChordCandidate(candidate) || !isStrongChordCandidate(candidate)) {
          return full;
        }
        return `${prefix}${transformChordText(candidate)}`;
      });
    }

    return withBracketChords.replace(
      TOKEN_CANDIDATE_REGEX,
      (full, prefix, candidate) => {
        if (!isChordCandidate(candidate)) {
          return full;
        }
        return `${prefix}${transformChordText(candidate)}`;
      }
    );
  });

  return transformedLines.join("\n");
}

function applyTranspose(songText, steps = 0) {
  return transformChordSymbols(
    songText,
    isTransposableChordCandidate,
    isStrongTransposableChordCandidate,
    (chordText) => transposeSingleChord(chordText, steps)
  );
}

function transposeUp(songText, steps = 1) {
  return applyTranspose(songText, Math.abs(steps));
}

function transposeDown(songText, steps = 1) {
  return applyTranspose(songText, -Math.abs(steps));
}

function applyNotation(songText, targetMode) {
  if (targetMode === "solfege") {
    return transformChordSymbols(songText, isEnglishChordCandidate, isStrongEnglishChordCandidate, (chordText) =>
      convertChordNotation(chordText, "solfege")
    );
  }

  if (targetMode === "english") {
    return transformChordSymbols(songText, isSolfegeChordCandidate, isStrongSolfegeChordCandidate, (chordText) =>
      convertChordNotation(chordText, "english")
    );
  }

  return songText;
}

function updateTransposeMeta() {
  notationToggleBtn.classList.toggle("is-active", notationMode === "solfege");
  notationToggleBtn.setAttribute("aria-pressed", String(notationMode === "solfege"));
}

function renderCurrentSong() {
  if (!originalSongText) {
    return;
  }

  lyricsContent.classList.add("is-transposing");
  const nextText =
    currentTranspose >= 0
      ? transposeUp(originalSongText, currentTranspose)
      : transposeDown(originalSongText, Math.abs(currentTranspose));
  const displayText = notationMode === "solfege" ? applyNotation(nextText, "solfege") : nextText;

  window.setTimeout(() => {
    lyricsContent.textContent = displayText;
    lyricsContent.classList.remove("is-transposing");
  }, 80);

  updateTransposeMeta();
}

async function loadSong(songId) {
  const selectedSong = songId ? songsById.get(songId) : null;
  if (!selectedSong) {
    songTitle.textContent = "Select a song";
    lyricsContent.textContent = "Open the search dashboard and choose a song.";
    originalSongText = "";
    currentTranspose = 0;
    updateTransposeMeta();
    return;
  }

  songTitle.textContent = `${selectedSong.title} - ${selectedSong.artist}`;
  lyricsContent.textContent = "Loading...";

  try {
    const response = await fetch(`../${selectedSong.path}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    originalSongText = await response.text();
    currentTranspose = 0;
    renderCurrentSong();
  } catch (error) {
    lyricsContent.textContent =
      "Could not load the file.\n\nRun this through a local server (not file://).\n\nExample:\npython3 -m http.server";
    originalSongText = "";
    currentTranspose = 0;
    updateTransposeMeta();
  }
}

function currentSongFromHash() {
  const value = window.location.hash.slice(1);
  return decodeURIComponent(value || "");
}

window.addEventListener("hashchange", () => {
  loadSong(currentSongFromHash());
});

transposeUpBtn.addEventListener("click", () => {
  if (!originalSongText) {
    return;
  }
  currentTranspose += 1;
  renderCurrentSong();
});

transposeDownBtn.addEventListener("click", () => {
  if (!originalSongText) {
    return;
  }
  currentTranspose -= 1;
  renderCurrentSong();
});

notationToggleBtn.addEventListener("click", () => {
  notationMode = notationMode === "english" ? "solfege" : "english";
  if (!originalSongText) {
    updateTransposeMeta();
    return;
  }
  renderCurrentSong();
});

// Expose requested API functions for external use/testing.
window.transposeUp = transposeUp;
window.transposeDown = transposeDown;

async function loadCatalog() {
  try {
    const response = await fetch(SONG_INDEX_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    songsCatalog = await response.json();
    songsById = new Map(songsCatalog.map((song) => [song.id, song]));
  } catch (_error) {
    lyricsContent.textContent = "Song index failed to load. Regenerate songs-index.json and retry.";
  }
}

updateTransposeMeta();
await loadCatalog();
loadSong(currentSongFromHash());
