/* ═══════════════════════════════════════════════════════════════════
   Palestine Scholarship Hub — app.js
   APIs: Data Palestine · OpenData.ps · Apify · Anthropic Claude
   ═══════════════════════════════════════════════════════════════════ */

"use strict";

/* ─── CONFIG ──────────────────────────────────────────────────────── */
const CONFIG = {
  // ✏️  Add your Apify token here for live scraper results
  APIFY_TOKEN: "YOUR_APIFY_TOKEN",

  // ✏️  Add your Anthropic API key here for the AI advisor
  ANTHROPIC_KEY: "YOUR_ANTHROPIC_API_KEY",

  ANTHROPIC_MODEL: "claude-sonnet-4-20250514",

  ENDPOINTS: {
    // OpenData.ps CKAN API — education & scholarship packages
    OPENDATA:    "https://www.opendata.ps/api/3/action/package_search?q=education&rows=12",
    // Data Palestine open CKAN endpoint
    DATAPS:      "https://data.palestine.ps/api/3/action/package_search?q=scholarship&rows=12",
    // Apify public dataset actor (scholarship data actor)
    APIFY_ACTOR: "https://api.apify.com/v2/acts/misceres~scholarships-scraper/runs/last/dataset/items",
  },
};

/* ─── CURATED FALLBACK DATA ───────────────────────────────────────── */
const CURATED = [
  {
    id: "c1", source: "curated",
    name: "HESPAL Scholarship",       flag: "🇬🇧", country: "United Kingdom",
    funding: "Fully Funded",          field: "All Fields / CS / AI",
    ielts: "Required (waivable)",     deadline: "Feb 2026",
    desc: "Supports Palestinian students to pursue postgraduate study at UK universities. Covers tuition, living costs, and travel.",
    link: "https://www.britishcouncil.ps/en/study-uk/scholarships/hespal",
  },
  {
    id: "c2", source: "curated",
    name: "DAAD Germany",             flag: "🇩🇪", country: "Germany",
    funding: "Fully Funded",          field: "CS / AI / Engineering",
    ielts: "MOI accepted",            deadline: "Oct 2025",
    desc: "Germany's largest scholarship fund. Strong English-taught CS and AI programs at top German universities.",
    link: "https://www.daad.de/en/",
  },
  {
    id: "c3", source: "curated",
    name: "Erasmus Mundus",           flag: "🇪🇺", country: "Europe (Multi)",
    funding: "Fully Funded",          field: "AI / Data Science / Engineering",
    ielts: "Sometimes optional",      deadline: "Jan 2026",
    desc: "Joint European master's programs with a monthly stipend and full tuition waiver. Study in 2+ countries.",
    link: "https://www.eacea.ec.europa.eu/scholarships/erasmus-mundus-catalogue_en",
  },
  {
    id: "c4", source: "curated",
    name: "Stipendium Hungaricum",    flag: "🇭🇺", country: "Hungary",
    funding: "Fully Funded",          field: "Engineering / CS / Sciences",
    ielts: "Optional",                deadline: "Jan 2026",
    desc: "Full scholarship covering tuition, dormitory, and monthly stipend. No application fee. Palestinian nationals eligible.",
    link: "https://stipendiumhungaricum.hu/",
  },
  {
    id: "c5", source: "curated",
    name: "Türkiye Bursları",         flag: "🇹🇷", country: "Turkey",
    funding: "Fully Funded",          field: "All Fields",
    ielts: "Not required",            deadline: "Feb 2026",
    desc: "Covers tuition, accommodation, monthly allowance, language course, and health insurance for Palestinian students.",
    link: "https://www.turkiyeburslari.gov.tr/",
  },
  {
    id: "c6", source: "curated",
    name: "Czech Government Scholarship", flag: "🇨🇿", country: "Czech Republic",
    funding: "Fully Funded",          field: "Engineering / IT / Sciences",
    ielts: "Optional",                deadline: "Sep 2025",
    desc: "Czech language programs require no IELTS. English programs available at major Czech universities.",
    link: "https://www.dzs.cz/en/",
  },
  {
    id: "c7", source: "curated",
    name: "Polish NAWA Scholarship",  flag: "🇵🇱", country: "Poland",
    funding: "Partial",               field: "Engineering / IT / Medicine",
    ielts: "Optional",                deadline: "Apr 2026",
    desc: "NAWA and Banach Programme scholarships for master's students in Polish or English language programs.",
    link: "https://nawa.gov.pl/en/",
  },
  {
    id: "c8", source: "curated",
    name: "Finnish CIMO Scholarship", flag: "🇫🇮", country: "Finland",
    funding: "Fully Funded",          field: "Technology / CS / AI",
    ielts: "Required (6.0+)",         deadline: "Mar 2026",
    desc: "Scholarship pool for postdoctoral researchers and PhD candidates at Finnish universities.",
    link: "https://www.studyinfinland.fi/scholarships",
  },
];

/* ─── STATE ───────────────────────────────────────────────────────── */
const state = {
  all: [],          // all fetched + curated scholarships
  filtered: [],     // after search/filter
  activeSource: "all",
  chatHistory: [],  // Anthropic message history
  isTyping: false,
};

/* ─── ROADMAP DATA ────────────────────────────────────────────────── */
const ROADMAP = [
  { icon: "📄", text: "Prepare CV and academic transcripts with GPA" },
  { icon: "✉️", text: "Request recommendation letters from professors" },
  { icon: "📋", text: "Get Medium of Instruction (MOI) certificate" },
  { icon: "🖊️", text: "Write a targeted, personal motivation letter" },
  { icon: "🔍", text: "Research scholarships and track deadlines" },
  { icon: "📝", text: "Apply to 8–12 programs to maximize chances" },
  { icon: "🎙️", text: "Prepare for interviews and visa application" },
];

/* ─── QUICK PROMPTS ──────────────────────────────────────────────── */
const QUICK_PROMPTS = [
  "Which scholarships fit a 3.2 GPA for AI/CS?",
  "Can I apply without IELTS?",
  "Best fully funded master's in Europe for Palestinians?",
  "What documents do I need to apply?",
  "What's the difference between HESPAL and DAAD?",
];

/* ══════════════════════════════════════════════════════════════════
   API FETCHERS
   ══════════════════════════════════════════════════════════════════ */

/**
 * Map a raw CKAN package into our scholarship shape.
 */
function mapCKAN(item, index, sourceLabel) {
  return {
    id: `${sourceLabel}-${index}`,
    source: sourceLabel,
    name: item.title || "Education Dataset",
    flag: sourceLabel === "dataps" ? "🇵🇸" : "📡",
    country: "Palestine / International",
    funding: "See Details",
    field: (item.tags || []).map((t) => t.display_name).join(" / ") || "Education",
    ielts: "See link",
    deadline: item.metadata_modified
      ? new Date(item.metadata_modified).toLocaleDateString("en-GB", { month: "short", year: "numeric" })
      : "—",
    desc:
      (item.notes || "").slice(0, 180).replace(/\n/g, " ").trim() ||
      "Dataset from " + (sourceLabel === "dataps" ? "Data Palestine" : "OpenData.ps"),
    link: item.url || (sourceLabel === "dataps"
      ? "https://data.palestine.ps"
      : "https://www.opendata.ps"),
  };
}

/**
 * Map an Apify dataset item.
 */
function mapApify(item, index) {
  return {
    id: `apify-${index}`,
    source: "apify",
    name: item.name || item.title || "Scholarship Opportunity",
    flag: item.countryFlag || "🌍",
    country: item.country || "International",
    funding: item.funding || item.type || "See Details",
    field: item.field || item.discipline || "Various",
    ielts: item.ielts || item.languageRequirement || "See link",
    deadline: item.deadline || item.closingDate || "See link",
    desc: item.description || item.summary || "Scholarship data sourced via Apify scraper.",
    link: item.url || item.link || "https://apify.com/store",
  };
}

/**
 * Fetch from OpenData.ps CKAN API.
 */
async function fetchOpenData() {
  const res = await fetch(CONFIG.ENDPOINTS.OPENDATA);
  if (!res.ok) throw new Error(`OpenData.ps: ${res.status}`);
  const json = await res.json();
  const results = json?.result?.results || [];
  return results.map((item, i) => mapCKAN(item, i, "opendata"));
}

/**
 * Fetch from Data Palestine CKAN API.
 */
async function fetchDataPalestine() {
  const res = await fetch(CONFIG.ENDPOINTS.DATAPS);
  if (!res.ok) throw new Error(`Data Palestine: ${res.status}`);
  const json = await res.json();
  const results = json?.result?.results || [];
  return results.map((item, i) => mapCKAN(item, i, "dataps"));
}

/**
 * Fetch from Apify dataset actor.
 */
async function fetchApify() {
  if (CONFIG.APIFY_TOKEN === "YOUR_APIFY_TOKEN") {
    throw new Error("Apify token not configured");
  }
  const url = `${CONFIG.ENDPOINTS.APIFY_ACTOR}?token=${CONFIG.APIFY_TOKEN}&limit=20`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Apify: ${res.status}`);
  const json = await res.json();
  const items = Array.isArray(json) ? json : json.data || json.items || [];
  return items.map((item, i) => mapApify(item, i));
}

/* ══════════════════════════════════════════════════════════════════
   STATUS INDICATORS
   ══════════════════════════════════════════════════════════════════ */
function setStatus(id, online, label) {
  const el = document.getElementById(`status-${id}`);
  if (!el) return;
  const dot = el.querySelector(".status-dot");
  dot.className = "status-dot " + (online ? "online" : "offline");
  el.childNodes[1].textContent = " " + label;
}

function setLoaderItem(id, state) {
  const el = document.getElementById(`ls-${id}`);
  if (!el) return;
  el.className = `ls-item ${state}`;
}

/* ══════════════════════════════════════════════════════════════════
   MAIN FETCH ORCHESTRATOR
   ══════════════════════════════════════════════════════════════════ */
async function loadAllData() {
  showLoading(true);
  let allData = [];

  const loaderText = document.getElementById("loaderText");

  // ── OpenData.ps ────────────────────────────────────────────────
  loaderText && (loaderText.textContent = "Fetching from OpenData.ps…");
  try {
    const data = await fetchOpenData();
    allData = allData.concat(data);
    setStatus("opendata", true, "Online");
    setLoaderItem("opendata", "done");
    console.log(`✅ OpenData.ps: ${data.length} items`);
  } catch (e) {
    setStatus("opendata", false, "Unavailable");
    setLoaderItem("opendata", "failed");
    console.warn("OpenData.ps:", e.message);
  }

  // ── Data Palestine ─────────────────────────────────────────────
  loaderText && (loaderText.textContent = "Fetching from Data Palestine…");
  try {
    const data = await fetchDataPalestine();
    allData = allData.concat(data);
    setStatus("dataps", true, "Online");
    setLoaderItem("dataps", "done");
    console.log(`✅ Data Palestine: ${data.length} items`);
  } catch (e) {
    setStatus("dataps", false, "Unavailable");
    setLoaderItem("dataps", "failed");
    console.warn("Data Palestine:", e.message);
  }

  // ── Apify ──────────────────────────────────────────────────────
  loaderText && (loaderText.textContent = "Fetching from Apify Scraper…");
  try {
    const data = await fetchApify();
    allData = allData.concat(data);
    setStatus("apify", true, "Online");
    setLoaderItem("apify", "done");
    console.log(`✅ Apify: ${data.length} items`);
  } catch (e) {
    setStatus("apify", false, CONFIG.APIFY_TOKEN === "YOUR_APIFY_TOKEN" ? "No token" : "Unavailable");
    setLoaderItem("apify", "failed");
    console.warn("Apify:", e.message);
  }

  // ── Always add curated fallback ────────────────────────────────
  allData = allData.concat(CURATED);

  state.all = allData;
  state.filtered = allData;

  updateStatTotal(allData.length);
  applyFilters();
  showLoading(false);
}

/* ══════════════════════════════════════════════════════════════════
   RENDER
   ══════════════════════════════════════════════════════════════════ */
function showLoading(show) {
  document.getElementById("loadingState").classList.toggle("hidden", !show);
  document.getElementById("cardsGrid").classList.toggle("hidden", show);
}

function updateStatTotal(n) {
  const el = document.getElementById("statTotal");
  if (el) el.textContent = n + "+";
}

function renderCards(data) {
  const grid = document.getElementById("cardsGrid");
  const empty = document.getElementById("emptyState");
  const count = document.getElementById("resultsCount");

  count.textContent = `${data.length} result${data.length !== 1 ? "s" : ""}`;

  if (data.length === 0) {
    grid.innerHTML = "";
    grid.classList.add("hidden");
    empty.classList.remove("hidden");
    return;
  }

  empty.classList.add("hidden");
  grid.classList.remove("hidden");

  grid.innerHTML = data.map((s, i) => `
    <div class="s-card" style="animation-delay:${i * 0.055}s">
      <div class="s-card-top">
        <div class="s-card-left">
          <div class="s-card-flag">${s.flag || "🎓"}</div>
          <div>
            <div class="s-card-name">${esc(s.name)}</div>
            <div class="s-card-country">${esc(s.country)}</div>
          </div>
        </div>
        <span class="s-card-badge ${s.funding === "Partial" ? "partial" : ""}">
          ${esc(s.funding)}
        </span>
      </div>

      <div class="s-card-meta">
        <div class="meta-row"><span class="ml">Field</span><span class="mv">${esc(s.field)}</span></div>
        <div class="meta-row"><span class="ml">IELTS</span><span class="mv">${esc(s.ielts)}</span></div>
      </div>

      <p class="s-card-desc">${esc(s.desc)}</p>

      <div class="s-card-source">
        Source: <span>${sourceLabel(s.source)}</span>
      </div>

      <div class="s-card-foot">
        <span class="s-card-deadline">📅 ${esc(s.deadline)}</span>
        <a href="${esc(s.link)}" target="_blank" rel="noopener noreferrer" class="s-card-link">
          View →
        </a>
      </div>
    </div>
  `).join("");
}

function renderSkeletons(n = 6) {
  const grid = document.getElementById("cardsGrid");
  grid.classList.remove("hidden");
  grid.innerHTML = Array.from({ length: n }).map(() => `
    <div class="skeleton-card">
      <div class="skel" style="height:18px;width:55%;margin-bottom:8px"></div>
      <div class="skel" style="height:13px;width:35%"></div>
      <div style="margin-top:16px;display:flex;flex-direction:column;gap:8px">
        <div class="skel" style="height:11px;width:80%"></div>
        <div class="skel" style="height:11px;width:66%"></div>
      </div>
      <div style="margin-top:16px;display:flex;flex-direction:column;gap:6px">
        <div class="skel" style="height:10px"></div>
        <div class="skel" style="height:10px;width:90%"></div>
        <div class="skel" style="height:10px;width:72%"></div>
      </div>
      <div class="skel" style="height:32px;width:100px;margin-top:24px;align-self:flex-end"></div>
    </div>
  `).join("");
}

function sourceLabel(src) {
  return { dataps: "Data Palestine", opendata: "OpenData.ps", apify: "Apify Scraper", curated: "Curated" }[src] || src;
}

function esc(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/* ══════════════════════════════════════════════════════════════════
   SEARCH & FILTER
   ══════════════════════════════════════════════════════════════════ */
function applyFilters() {
  const q       = document.getElementById("searchInput").value.toLowerCase().trim();
  const country = document.getElementById("countryFilter").value;
  const funding = document.getElementById("fundingFilter").value;
  const field   = document.getElementById("fieldFilter").value;
  const src     = state.activeSource;

  const result = state.all.filter((s) => {
    if (src !== "all" && s.source !== src) return false;
    if (q && ![s.name, s.field, s.country, s.desc].some((v) => (v || "").toLowerCase().includes(q))) return false;
    if (country && s.country !== country) return false;
    if (funding && s.funding !== funding) return false;
    if (field && !s.field.toLowerCase().includes(field.toLowerCase())) return false;
    return true;
  });

  state.filtered = result;
  renderCards(result);
  renderActiveFilters({ q, country, funding, field });
}

function renderActiveFilters({ q, country, funding, field }) {
  const wrap = document.getElementById("activeFilters");
  const tags = [];
  if (q)       tags.push({ label: `"${q}"`, clear: () => { document.getElementById("searchInput").value = ""; applyFilters(); } });
  if (country) tags.push({ label: `🌍 ${country}`, clear: () => { document.getElementById("countryFilter").value = ""; applyFilters(); } });
  if (funding) tags.push({ label: `💰 ${funding}`, clear: () => { document.getElementById("fundingFilter").value = ""; applyFilters(); } });
  if (field)   tags.push({ label: `📚 ${field}`, clear: () => { document.getElementById("fieldFilter").value = ""; applyFilters(); } });

  wrap.innerHTML = tags.map((t, i) =>
    `<span class="filter-tag">${esc(t.label)}<button onclick="clearFilter(${i})">×</button></span>`
  ).join("");
  wrap._clearFns = tags.map((t) => t.clear);
}

window.clearFilter = function (i) {
  const wrap = document.getElementById("activeFilters");
  if (wrap._clearFns && wrap._clearFns[i]) wrap._clearFns[i]();
};

/* ══════════════════════════════════════════════════════════════════
   ROADMAP
   ══════════════════════════════════════════════════════════════════ */
function renderRoadmap() {
  const container = document.getElementById("roadmapSteps");
  if (!container) return;
  container.innerHTML = ROADMAP.map((step, i) => `
    <div class="r-step" style="animation-delay:${i * 0.08}s">
      <div class="r-step-num">${String(i + 1).padStart(2, "0")}</div>
      <div class="r-step-icon">${step.icon}</div>
      <p class="r-step-text">${esc(step.text)}</p>
    </div>
  `).join("");
}

/* ══════════════════════════════════════════════════════════════════
   AI ADVISOR — Anthropic API
   ══════════════════════════════════════════════════════════════════ */
const SYSTEM_PROMPT = `You are a knowledgeable and supportive scholarship advisor for Palestinian students seeking fully funded opportunities in Europe and beyond.

You have expertise in:
- HESPAL (UK) - British Council Palestine scholarship
- DAAD (Germany) - fully funded with MOI accepted
- Erasmus Mundus (Europe) - joint master's programs, sometimes no IELTS
- Stipendium Hungaricum (Hungary) - no IELTS for some programs
- Türkiye Bursları (Turkey) - no IELTS required
- Czech Government Scholarship - Czech language programs need no IELTS
- Polish NAWA scholarship - partial funding

You help students with:
- GPA-based matching (most need 3.0+ out of 4.0 or 70%+)
- IELTS alternatives (MOI certificate, no-IELTS programs)
- Application deadlines and timelines
- Motivation letter tips
- Required documents (CV, transcripts, MOI, recommendation letters)
- Visa processes

Keep answers concise (4–6 lines), practical, and encouraging. Use bullet points when listing options. Never refuse to help.`;

function renderQuickPrompts() {
  const container = document.getElementById("quickPrompts");
  if (!container) return;
  container.innerHTML = QUICK_PROMPTS.map((p) =>
    `<button class="qp-btn" onclick="sendChatMessage('${p.replace(/'/g, "\\'")}')">${esc(p)}</button>`
  ).join("");
}

function appendMessage(role, content) {
  const container = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = `msg msg-${role}`;
  div.innerHTML = `
    <div class="msg-label">${role === "ai" ? "✦ ADVISOR" : "YOU"}</div>
    <div class="msg-bubble">${esc(content)}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function showTyping() {
  const container = document.getElementById("chatMessages");
  const div = document.createElement("div");
  div.className = "msg msg-ai";
  div.id = "typingIndicator";
  div.innerHTML = `
    <div class="msg-label">✦ ADVISOR</div>
    <div class="typing-bubble">
      <div class="t-dot"></div>
      <div class="t-dot"></div>
      <div class="t-dot"></div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

async function sendChatMessage(text) {
  const input = document.getElementById("chatInput");
  const sendBtn = document.getElementById("chatSend");
  const msg = text || input.value.trim();
  if (!msg || state.isTyping) return;

  input.value = "";
  state.isTyping = true;
  sendBtn.disabled = true;

  appendMessage("user", msg);
  state.chatHistory.push({ role: "user", content: msg });
  showTyping();

  try {
    if (CONFIG.ANTHROPIC_KEY === "YOUR_ANTHROPIC_API_KEY") {
      throw new Error("API key not configured");
    }

    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": CONFIG.ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: CONFIG.ANTHROPIC_MODEL,
        max_tokens: 1000,
        system: SYSTEM_PROMPT,
        messages: state.chatHistory,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `HTTP ${res.status}`);
    }

    const data = await res.json();
    const reply = data.content?.find((c) => c.type === "text")?.text
      || "I'm sorry, I couldn't generate a response. Please try again.";

    hideTyping();
    appendMessage("ai", reply);
    state.chatHistory.push({ role: "assistant", content: reply });

  } catch (err) {
    hideTyping();
    const isNoKey = err.message.includes("not configured");
    const fallback = isNoKey
      ? "⚙️ To enable the AI advisor, add your Anthropic API key in CONFIG.ANTHROPIC_KEY inside app.js.\n\nIn the meantime, here are quick answers:\n• No IELTS: Hungary, Turkey, Czech Republic\n• Best for CS/AI: DAAD, Erasmus Mundus\n• No fee required: Stipendium Hungaricum\n• Deadline check: most close Jan–Mar 2026"
      : `Sorry, I encountered an error: ${err.message}. Please check your API key and try again.`;
    appendMessage("ai", fallback);
    state.chatHistory.push({ role: "assistant", content: fallback });
  } finally {
    state.isTyping = false;
    sendBtn.disabled = false;
    document.getElementById("chatInput").focus();
  }
}

/* ══════════════════════════════════════════════════════════════════
   NAVBAR SCROLL EFFECT
   ══════════════════════════════════════════════════════════════════ */
function initNavbar() {
  const navbar = document.getElementById("navbar");
  window.addEventListener("scroll", () => {
    navbar.style.boxShadow = window.scrollY > 30
      ? "0 4px 32px rgba(0,0,0,.5)"
      : "none";
  }, { passive: true });

  const hamburger = document.getElementById("hamburger");
  const mobileMenu = document.getElementById("mobileMenu");
  hamburger.addEventListener("click", () => {
    mobileMenu.classList.toggle("open");
  });
  // Close menu when link is clicked
  mobileMenu.querySelectorAll("a").forEach((a) => {
    a.addEventListener("click", () => mobileMenu.classList.remove("open"));
  });
}

/* ══════════════════════════════════════════════════════════════════
   EVENTS
   ══════════════════════════════════════════════════════════════════ */
function initEvents() {
  // Search button
  document.getElementById("searchBtn").addEventListener("click", applyFilters);

  // Search on Enter
  document.getElementById("searchInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter") applyFilters();
  });

  // Filter selects — live update
  ["countryFilter", "fundingFilter", "fieldFilter"].forEach((id) => {
    document.getElementById(id).addEventListener("change", applyFilters);
  });

  // Source tabs
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.activeSource = btn.dataset.source;
      applyFilters();
    });
  });

  // Retry button
  const retryBtn = document.getElementById("retryBtn");
  if (retryBtn) retryBtn.addEventListener("click", loadAllData);

  // Chat send button
  document.getElementById("chatSend").addEventListener("click", () => sendChatMessage());

  // Chat Enter key
  document.getElementById("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) sendChatMessage();
  });
}

/* ══════════════════════════════════════════════════════════════════
   INIT
   ══════════════════════════════════════════════════════════════════ */
document.addEventListener("DOMContentLoaded", () => {
  initNavbar();
  initEvents();
  renderRoadmap();
  renderQuickPrompts();

  // Show initial AI greeting
  appendMessage("ai",
    "Hi! 👋 I'm your scholarship advisor. Ask me anything about fully funded scholarships, IELTS requirements, GPA thresholds, or how to write a strong motivation letter."
  );

  // Show skeletons while loading
  renderSkeletons(6);
  loadAllData();
});