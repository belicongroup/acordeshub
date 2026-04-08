const SONG_INDEX_URL = "../songs-index.json";
const MAX_RESULTS = 100;
const SPACE_REGEX = /\s+/g;

const queryInput = document.getElementById("queryInput");
const statusText = document.getElementById("statusText");
const resultsList = document.getElementById("resultsList");

let catalog = [];

function normalizeText(value) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[_-]/g, " ")
    .replace(SPACE_REGEX, " ")
    .trim();
}

function parseTokens(query) {
  const normalized = normalizeText(query);
  return normalized ? normalized.split(" ").filter(Boolean) : [];
}

function scoreSong(song, normalizedQuery, queryTokens) {
  let score = 0;
  if (song.titleNormalized === normalizedQuery) score += 100;
  if (song.titleNormalized.startsWith(normalizedQuery)) score += 65;
  if (song.titleNormalized.includes(normalizedQuery)) score += 40;
  if (song.artistNormalized.startsWith(normalizedQuery)) score += 36;
  if (song.artistNormalized.includes(normalizedQuery)) score += 24;
  if (queryTokens.every((token) => song.searchText.includes(token))) score += 18;
  return score;
}

function getResults(query) {
  const normalizedQuery = normalizeText(query);
  const queryTokens = parseTokens(query);
  if (!normalizedQuery) {
    return catalog.slice(0, MAX_RESULTS);
  }

  return catalog
    .map((song) => ({ song, score: scoreSong(song, normalizedQuery, queryTokens) }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score || a.song.title.localeCompare(b.song.title))
    .slice(0, MAX_RESULTS)
    .map((item) => item.song);
}

function openInViewer(song) {
  const targetUrl = `../lyrics-viewer/index.html#${encodeURIComponent(song.id)}`;
  window.location.href = targetUrl;
}

function renderResults(results, query) {
  resultsList.innerHTML = "";
  if (!query.trim()) {
    statusText.textContent = `Showing ${results.length} songs from ${catalog.length}.`;
  } else if (results.length === 0) {
    statusText.textContent = "No songs found.";
  } else {
    statusText.textContent = `${results.length} results.`;
  }

  results.forEach((song) => {
    const item = document.createElement("li");
    item.className = "result-item";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "result-btn";
    button.innerHTML = `<span class="result-main"><strong class="result-title">${song.title}</strong><span class="result-artist">${song.artist}</span></span><span class="result-arrow" aria-hidden="true">&gt;</span>`;
    button.addEventListener("click", () => openInViewer(song));
    item.append(button);
    resultsList.append(item);
  });
}

queryInput.addEventListener("input", () => {
  const results = getResults(queryInput.value);
  renderResults(results, queryInput.value);
});

async function init() {
  try {
    const response = await fetch(SONG_INDEX_URL);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    catalog = await response.json();
    renderResults(getResults(""), "");
  } catch (_error) {
    statusText.textContent = "Could not load songs-index.json. Run npm run build-index.";
  }
}

init();
