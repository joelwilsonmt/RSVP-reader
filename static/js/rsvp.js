// Pure RSVP logic: pivot position, pacing, timing estimates, sentence bounds.

export const BREAK = "¶";
const WORD_CHAR = /[\p{L}\p{N}]/u;

// Optimal recognition point: index of the letter the eye should fix on.
export function orp(word) {
  let start = 0, end = word.length - 1;
  while (start < word.length && !WORD_CHAR.test(word[start])) start++;
  while (end > start && !WORD_CHAR.test(word[end])) end--;
  if (start >= word.length) return { left: "", pivot: word, right: "" };
  const len = end - start + 1;
  const off = len <= 1 ? 0 : len <= 5 ? 1 : len <= 9 ? 2 : len <= 13 ? 3 : 4;
  const p = start + off;
  return { left: word.slice(0, p), pivot: word[p], right: word.slice(p + 1) };
}

// Delay multiplier relative to one beat (60000 / wpm).
export function multiplier(word) {
  if (word === BREAK) return 2.2;
  let m = 1;
  const last = word[word.length - 1];
  if (/[.!?]["'”’)\]]?$/.test(word)) m += 1.3;
  else if (/[,;:]["'”’)\]]?$/.test(word) || last === "—" || last === "–") m += 0.6;
  const n = word.length;
  if (n > 8) m += Math.min(0.9, (n - 8) * 0.08);
  if (/\d/.test(word)) m += 0.3;
  return m;
}

// Prefix sums of multipliers so time-left and chapter durations are O(1).
export function buildTimeline(words) {
  const cum = new Float64Array(words.length + 1);
  for (let i = 0; i < words.length; i++) cum[i + 1] = cum[i] + multiplier(words[i]);
  return cum;
}

export function spanMs(cum, from, to, wpm) {
  const a = Math.max(0, Math.min(from, cum.length - 1));
  const b = Math.max(a, Math.min(to, cum.length - 1));
  return (cum[b] - cum[a]) * (60000 / wpm);
}

const ENDS_SENTENCE = /[.!?]["'”’)\]]?$/;

export function sentenceStart(words, i) {
  let j = Math.max(0, i - 1);
  while (j > 0 && words[j] !== BREAK && !ENDS_SENTENCE.test(words[j])) j--;
  if (j === 0) return 0;
  j++;
  while (j < words.length && words[j] === BREAK) j++;
  return Math.min(j, i);
}

export function sentenceEnd(words, i, max = 60) {
  let j = i;
  const limit = Math.min(words.length - 1, i + max);
  while (j < limit && words[j] !== BREAK && !ENDS_SENTENCE.test(words[j])) j++;
  return words[j] === BREAK ? j - 1 : j;
}

export function nextSentence(words, i) {
  const end = sentenceEnd(words, i, 400);
  let j = end + 1;
  while (j < words.length && words[j] === BREAK) j++;
  return Math.min(j, words.length - 1);
}

export function prevSentence(words, i) {
  const s = sentenceStart(words, i);
  // If already near the start of a sentence, jump to the previous one.
  return i - s <= 1 ? sentenceStart(words, Math.max(0, s - 1)) : s;
}

export function chapterAt(chapters, i) {
  let lo = 0, hi = chapters.length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (chapters[mid].index <= i) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans;
}

// Average multiplier for prose, used when only word counts are known.
export const AVG_MULT = 1.32;
