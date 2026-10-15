// Thin JSON client for the Flask API.

async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(url, opts);
  } catch {
    throw new Error("Can't reach the server. Check your connection.");
  }
  let data = null;
  try { data = await res.json(); } catch {}
  if (!res.ok) {
    const err = new Error((data && data.error) || `Server error (${res.status})`);
    err.status = res.status;
    throw err;
  }
  // e.g. an auth proxy's HTML login page: fail loudly instead of rendering nothing
  if (data === null) throw new Error("Unexpected response from the server.");
  return data;
}

const q = (params) => new URLSearchParams(params).toString();

export const api = {
  config: () => req("GET", "/api/config"),
  setLibrary: (books_dir) => req("POST", "/api/config", { books_dir }),
  settings: () => req("GET", "/api/settings"),
  saveSettings: (s) => req("POST", "/api/settings", s),
  browse: (path) => req("GET", "/api/browse" + (path ? "?" + q({ path }) : "")),
  fs: (path) => req("GET", "/api/fs?" + q({ path })),
  meta: (path) => req("GET", "/api/meta?" + q({ path })),
  book: (path) => req("GET", "/api/book?" + q({ path })),
  progress: () => req("GET", "/api/progress"),
  saveProgress: (p) => req("POST", "/api/progress", p),
  deleteProgress: (id) => req("DELETE", "/api/progress?" + q({ id })),
  stats: () => req("GET", "/api/stats"),
  coverUrl: (id) => "/api/cover?" + q({ id }),
  beacon: (p) => navigator.sendBeacon?.("/api/progress", JSON.stringify(p)),
};
