"""Live tower (ATC) radio: list of sources and the LiveATC feed-list scan.

SkyTrack plays nothing itself. The mini window shows the official LiveATC listening page
(or a page the user added), exactly as a browser would, and a click on its title opens the
same page in the browser. The list of towers ships in data/stations.json; "Check for new
towers" opens LiveATC's own feed list in a visible window — the person passes LiveATC's
"are you human" check themselves if it appears — and reads the feeds shown there.
Nothing is scanned in the background.
"""
import json
import os
from datetime import date

from . import db

LIVEATC = "https://www.liveatc.net"
INDEX_URL = LIVEATC + "/feedindex.php?type=international-eu"
HOME_PREFIX = "EP"  # Poland


def bundled_path():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "stations.json")


def user_path():
    return os.path.join(db.data_dir(), "stations.json")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data.get("stations"), list) else None
    except (OSError, ValueError, AttributeError):
        return None


def load():
    """The newer of the bundled list and the list saved by the last check."""
    a, b = _read(bundled_path()) or {"stations": [], "checked": ""}, _read(user_path())
    if b and b.get("checked", "") >= a.get("checked", ""):
        # a newer package may know mounts the saved list doesn't — keep them
        known = {s["name"]: s for s in a["stations"]}
        for s in b["stations"]:
            if not s.get("mount") and known.get(s["name"], {}).get("mount"):
                s["mount"] = known[s["name"]]["mount"]
        return b
    return a


def listen_url(st):
    if st.get("url"):
        return st["url"]
    if st.get("mount"):
        return f"{LIVEATC}/hlisten.php?mount={st['mount']}&icao={st['icao'].lower()}"
    return f"{LIVEATC}/search/?icao={st['icao']}"


def key(st):
    return st.get("url") or "liveatc:" + st["name"]


def merge_scan(old, found):
    """Apply a fresh scan. Returns (new list dict, names of new feeds)."""
    clean = []
    for f in found:
        name = " ".join(str(f.get("name", "")).split())[:80]
        icao = str(f.get("icao", "")).upper()[:4]
        if not name or len(icao) != 4 or not icao.isalpha():
            continue
        st = {"icao": icao, "name": name,
              "status": "UP" if str(f.get("status", "")).upper() == "UP" else "DOWN"}
        mount = str(f.get("mount") or "")
        if mount and mount.replace("_", "").replace("-", "").isalnum():
            st["mount"] = mount
        clean.append(st)
    if not clean:
        return old, []
    before = {s["name"] for s in old["stations"]}
    prev = {s["name"]: s for s in old["stations"]}
    for st in clean:
        if not st.get("mount") and prev.get(st["name"], {}).get("mount"):
            st["mount"] = prev[st["name"]]["mount"]
    seen = {s["name"] for s in clean}
    # feeds that vanished from the list are kept, marked as down
    for s in old["stations"]:
        if s["name"] not in seen:
            clean.append(dict(s, status="DOWN"))
    clean.sort(key=lambda s: (not s["icao"].startswith(HOME_PREFIX), s["icao"], s["name"]))
    data = {"source": old.get("source", "LiveATC.net"), "checked": date.today().isoformat(),
            "stations": clean}
    return data, [s["name"] for s in clean if s["name"] not in before]


def save(data):
    os.makedirs(db.data_dir(), exist_ok=True)
    tmp = user_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
    os.replace(tmp, user_path())


# Reads LiveATC feed blocks (feed list and airport pages). Every feed block holds exactly
# one "Feed Status:"; name, status and the player link are read from inside it.
FEEDS_FN = r"""
function __stFeeds() {
  const leaves = [];
  for (const el of document.body.querySelectorAll("*")) {
    if (!/Feed Status/i.test(el.textContent)) continue;
    let deeper = false;
    for (const c of el.children) if (/Feed Status/i.test(c.textContent)) { deeper = true; break; }
    if (!deeper) leaves.push(el);
  }
  const count = (el) => (el.textContent.match(/Feed Status/gi) || []).length;
  const feeds = [], done = new Set();
  for (const leaf of leaves) {
    let block = leaf;
    while (block.parentElement && count(block.parentElement) === 1) block = block.parentElement;
    if (done.has(block)) continue;
    done.add(block);
    const text = block.innerText || block.textContent;
    const st = (text.match(/Feed Status:\s*([A-Z]+)/i) || [])[1] || "";
    let mount = "", icao = "", href = "";
    for (const a of block.querySelectorAll("a, [onclick]")) {
      const h = (a.getAttribute("href") || "") + " " + (a.getAttribute("onclick") || "");
      let m = h.match(/[?&]mount=([A-Za-z0-9_-]+)/) ||
              h.match(/\(\s*['"]([A-Za-z0-9_-]+)['"]\s*,\s*['"]([A-Za-z]{4})['"]/);
      if (m && !mount) {
        mount = m[1];
        if (m[2]) icao = m[2].toUpperCase();
        const raw = a.getAttribute("href") || "";
        if (/hlisten|listen/i.test(raw) && !/^javascript/i.test(raw)) href = a.href;
      }
      const i = h.match(/[?&]icao=([A-Za-z]{4})/);
      if (i && !icao) icao = i[1].toUpperCase();
    }
    const strong = block.querySelector("strong, b, th");
    let name = strong ? strong.textContent : text.split("\n")[0];
    name = name.replace(/\(Archives\)/i, "").replace(/\s+/g, " ").trim();
    if (!icao) icao = ((name.match(/^([A-Z]{4})\b/) || [])[1] || "");
    if (name) feeds.push({name, icao, status: st, mount, href});
  }
  return feeds;
}
"""

SCAN_JS = FEEDS_FN + r"""
(() => {
  const txt = document.body ? document.body.innerText : "";
  if (!/Feed Status/i.test(txt)) return JSON.stringify({ready: false});
  return JSON.stringify({ready: true, feeds: __stFeeds().filter(f => f.icao)});
})()
"""


def pick_js(name):
    """On an airport page: the player link of the feed called `name` (or the first one up)."""
    return FEEDS_FN + "(() => { const want = " + json.dumps(name) + r""";
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9#]+/g, " ").trim();
  const feeds = document.body ? __stFeeds().filter(f => f.mount) : [];
  let f = feeds.find(x => norm(x.name) === norm(want)) ||
          feeds.find(x => norm(x.name).includes(norm(want)) || norm(want).includes(norm(x.name))) ||
          feeds.find(x => /^UP$/i.test(x.status)) || feeds[0];
  return JSON.stringify(f || null);
})()"""


# Reads the player state on a listening page and presses its Play button when needed.
# Returns "playing", "buffering", "clicked" or "none". Never calls audio.play() itself:
# LiveATC's player keeps its own state and must be started with its own button.
PLAYER_JS = r"""
((mode) => {
  if (document.querySelector('iframe[src*="challenges.cloudflare.com"], .cf-turnstile, #challenge-form, #cf-challenge-running'))
    return "verify";
  const text = document.body ? document.body.innerText : "";
  if (/\bplaying\b/i.test(text)) return "playing";
  const buffering = /buffering|connecting|loading/i.test(text);
  if (mode === "check" || (buffering && mode !== "force")) return buffering ? "buffering" : "none";
  for (const b of document.querySelectorAll("button, a, input[type=button], [role=button]")) {
    const t = (b.innerText || b.value || b.getAttribute("aria-label") || b.title || "").trim();
    if (/^\W*Play\W*$/i.test(t) && !b.disabled) { b.click(); return "clicked"; }
  }
  return buffering ? "buffering" : "none";
})("%s")
"""
