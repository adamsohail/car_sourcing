/* ============================================================
   Interface : socle
   ============================================================ */
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const plural = (n, one, many) => n > 1 ? many : one;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const dtf = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
function ago(ts) {
  const d = Date.now() - ts;
  if (d < 60000) return 'à l’instant';
  if (d < 3600000) return `il y a ${Math.round(d / 60000)} min`;
  if (d < 86400000) return `il y a ${Math.round(d / 3600000)} h`;
  const j = Math.round(d / 86400000);
  return j === 1 ? 'hier' : `il y a ${j} jours`;
}
const SOURCES = { leboncoin: 'Leboncoin', lacentrale: 'La Centrale', autre: 'Autre site' };

const I = (d, extra = '') => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" ${extra}>${d}</svg>`;
const ICON = {
  opps: I('<path d="M12 2.8 21.2 12 12 21.2 2.8 12Z"/><path d="M12 7.6 16.4 12 12 16.4 7.6 12Z"/>'),
  calc: I('<rect x="5" y="3" width="14" height="18" rx="2.5"/><path d="M8.5 7.5h7"/><path d="M8.6 12h.01M12 12h.01M15.4 12h.01M8.6 15.8h.01M12 15.8h.01M15.4 15.8h.01" stroke-width="2.4"/>'),
  list: I('<path d="M9 6h11M9 12h11M9 18h11"/><path d="M4.5 6h.01M4.5 12h.01M4.5 18h.01" stroke-width="2.6"/>'),
  chart: I('<path d="M4 4v16h16"/><path d="M8.5 16v-4M12.5 16V8M16.5 16v-6"/>'),
  sliders: I('<path d="M4 7h9M18 7h2M4 17h3M12 17h8"/><circle cx="15.5" cy="7" r="2.2"/><circle cx="9.5" cy="17" r="2.2"/>'),
  up: I('<path d="M7 10.5V20H4.2V10.5Z"/><path d="M7 10.5 10.8 3.6c1.6 0 2.5 1.1 2.2 2.7l-.6 3.2h5.4a2 2 0 0 1 2 2.3l-1.1 6.4a2 2 0 0 1-2 1.8H7"/>'),
  x: I('<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>'),
  key: I('<circle cx="8" cy="15.5" r="4"/><path d="M10.9 12.6 19 4.5M16 7.5l2.2 2.2M13.6 9.9l2 2"/>'),
  pin: I('<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11Z"/><circle cx="12" cy="10" r="2.3"/>'),
  clock: I('<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>'),
  ext: I('<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>'),
  chev: I('<path d="M6 9l6 6 6-6"/>'),
  back: I('<path d="M15 5l-7 7 7 7"/>'),
  info: I('<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.8h.01" stroke-width="2.2"/>'),
  warn: I('<path d="M12 3.5 21.5 20h-19Z"/><path d="M12 10v4.5M12 17.2h.01" stroke-width="2.2"/>'),
  search: I('<circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/>'),
  plus: I('<path d="M12 5v14M5 12h14"/>'),
  home: I('<path d="M4 11 12 4l8 7"/><path d="M6.5 9.5V20h11V9.5"/>'),
  down: I('<path d="M12 5v14M6.5 13.5 12 19l5.5-5.5"/>'),
  check: I('<path d="M5 12.5l4.5 4.5L19 7.5"/>'),
  stop: I('<circle cx="12" cy="12" r="9"/><path d="M8.5 8.5l7 7M15.5 8.5l-7 7"/>'),
};
// Panneau « route à caractère prioritaire » : le repère des alertes prioritaires
const DIAMOND = (size = 16) => `<svg viewBox="0 0 20 20" width="${size}" height="${size}" aria-hidden="true"><rect x="3.4" y="3.4" width="13.2" height="13.2" rx="1" transform="rotate(45 10 10)" fill="#fff" stroke="#1B1B1B" stroke-width="1.1"/><rect x="6.2" y="6.2" width="7.6" height="7.6" transform="rotate(45 10 10)" fill="#F5B800"/></svg>`;

const CAR_COLORS = { Blanc: '#F3F5F8', Gris: '#9AA3AF', Noir: '#2B303A', Bleu: '#2F5DA8', Rouge: '#B8352C', Beige: '#CDBB98' };
const CAR_SHAPES = {
  citadine: { d: 'M9 40 L8 33 Q8 29 13 28 L33 25.5 L45 15.5 Q47.5 13.5 51 13.5 L84 13.5 Q88 13.5 90 16.5 L99 27 Q104 28.5 104 32 L104 38 Q104 40 102 40 L95 40 A9 9 0 0 0 77 40 L40 40 A9 9 0 0 0 22 40 Z', g: ['M47.5 16.5 Q49 15.5 51.5 15.5 L64 15.5 L64 25 L36.5 25.3 Z', 'M67 15.5 L84 15.5 Q87 15.5 88.5 18 L94 25 L67 25 Z'], w: [[31, 40, 7], [86, 40, 7]] },
  compacte: { d: 'M8 40 L7 33 Q7 29 12 28 L34 25.5 L47 15 Q49.5 13 53 13 L90 13 Q94 13 96 16 L105 27 Q111 28.5 111 32 L111 38 Q111 40 109 40 L102 40 A9 9 0 0 0 84 40 L40 40 A9 9 0 0 0 22 40 Z', g: ['M49.5 16 Q51 15 53.5 15 L68 15 L68 25 L37.5 25.3 Z', 'M71 15 L90 15 Q93 15 94.5 17.5 L100 25 L71 25 Z'], w: [[31, 40, 7], [93, 40, 7]] },
  berline: { d: 'M7 40 L6 33 Q6 29 11 28 L32 25.5 L44 16 Q46.5 14 50 14 L76 14 Q80 14 82.5 16.5 L90 24.5 L106 26 Q111 27 111 31 L111 38 Q111 40 109 40 L100 40 A9 9 0 0 0 82 40 L39 40 A9 9 0 0 0 21 40 Z', g: ['M46 17 Q47.5 16 50.5 16 L62 16 L62 25 L35.5 25.3 Z', 'M65 16 L76 16 Q79 16 80.5 17.5 L87 25 L65 25 Z'], w: [[30, 40, 7], [91, 40, 7]] },
  suv: { d: 'M8 40 L7 31 Q7 26 12 25.5 L32 23.5 L42 12 Q44 10 48 10 L88 10 Q92 10 94 13 L101 23 Q106 24 106 28 L106 38 Q106 40 104 40 L97 40 A10 10 0 0 0 77 40 L41 40 A10 10 0 0 0 21 40 Z', g: ['M44 13 Q45.5 12 48.5 12 L64 12 L64 22.5 L35 22.8 Z', 'M67 12 L88 12 Q90.5 12 92 14.5 L97 22.5 L67 22.5 Z'], w: [[31, 40, 8], [87, 40, 8]] },
  utilitaire: { d: 'M8 40 L7 30 Q7 25 12 24 L26 22 L36 9 Q38 7 42 7 L102 7 Q106 7 106 11 L106 38 Q106 40 104 40 L97 40 A9 9 0 0 0 79 40 L40 40 A9 9 0 0 0 22 40 Z', g: ['M38 10 Q39.5 9 42 9 L54 9 L54 21 L29.5 21.5 Z'], w: [[31, 40, 7], [88, 40, 7]] },
};
function carSVG(l) {
  const s = CAR_SHAPES[l.body] || CAR_SHAPES.compacte;
  const fill = CAR_COLORS[l.couleur] || CAR_COLORS.Gris;
  return `<svg viewBox="0 0 120 50" aria-hidden="true"><path class="car-body" d="${s.d}" fill="${fill}"/>${s.g.map(g => `<path class="car-glass" d="${g}"/>`).join('')}${s.w.map(([x, y, r]) => `<circle class="car-tyre" cx="${x}" cy="${y}" r="${r}"/><circle class="car-hub" cx="${x}" cy="${y}" r="${(r * .42).toFixed(1)}"/>`).join('')}</svg>`;
}

/* ---------- API du service ---------- */
class ApiError extends Error {
  constructor(status, message, data) { super(message); this.status = status; this.data = data; }
}
function detailText(d) {
  if (!d) return 'Erreur inattendue du serveur.';
  if (typeof d === 'string') return d;
  if (Array.isArray(d.messages)) return d.messages.join(' ; ');
  if (Array.isArray(d.errors)) return d.errors.join(' ; ');
  if (Array.isArray(d)) return d.map(x => x.msg || String(x)).join(' ; ');
  return JSON.stringify(d);
}
const Api = {
  async req(path, opts = {}) {
    let res;
    try {
      res = await fetch(path, { credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, ...opts });
    } catch (e) {
      throw new ApiError(0, 'Connexion au serveur impossible. Vérifiez votre réseau.');
    }
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && path !== '/api/login') { showLogin(); throw new ApiError(401, 'Connexion requise.'); }
    if (!res.ok) throw new ApiError(res.status, detailText(data.detail), data.detail);
    return data;
  },
  get(path) { return this.req(path); },
  post(path, body) { return this.req(path, { method: 'POST', body: JSON.stringify(body) }); },
};

/* ---------- État ---------- */
const Store = { feedback: {} };
const S = {
  feedItems: [], byId: new Map(), evals: new Map(), detail: {}, cfgUsed: defaultConfig(), cfgErrors: null,
  ctx: { kwList: kwList(DEFAULT_KEYWORDS) }, loaded: false, loadError: null,
  view: null, sheetId: null, sheetFromApp: false, lastFocus: null,
  feed: { status: 'todo', period: 7, prioOnly: false, sort: 'marge' },
  list: { q: '', statut: 'all', offset: 0, items: [], counts: {}, total: 0, loading: false, error: null },
  stats: null, statsError: null, ev: null,
  cfgMeta: null, cfgDraftSource: null, draft: null, dirty: false, fieldErrors: {}, preview: null, saving: false,
};
const EMPTY_EV = { statut: 'non_evaluee', n: 0, comps: [], motif: null, niveau: null, cote: null, marge: null };

function ingest(items) {
  for (const it of items) {
    it.body = bodyFor(it.marque, it.modele);
    it.couleur = 'Gris';
    S.byId.set(it.id, it);
    S.evals.set(it.id, it.ev ? { ...it.ev, comps: [] } : EMPTY_EV);
    if (it.fb) Store.feedback[it.id] = it.fb; else delete Store.feedback[it.id];
  }
  return items;
}
async function loadConfig() {
  const r = await Api.get('/api/config');
  S.cfgMeta = r.meta;
  S.cfgDraftSource = r.draft;
  S.cfgErrors = r.errors && r.errors.length ? r.errors : null;
  S.cfgUsed = r.config ? { params: r.config.params, keywords: r.config.keywords, version: r.config.version } : defaultConfig();
  S.ctx = { kwList: kwList(S.cfgUsed.keywords) };
}
async function loadFeed() {
  const r = await Api.get(`/api/opportunities?period=${S.feed.period === 1 ? 1 : Math.max(S.feed.period, 7)}`);
  S.feedItems = ingest(r.items);
}
async function loadDetail(id) {
  const d = await Api.get('/api/listing/' + encodeURIComponent(id));
  ingest([d]);
  S.detail[id] = d;
  S.evals.set(id, { ...(d.ev || EMPTY_EV), comps: d.comps || [] });
  return d;
}
function todoCount(period = 7) {
  if (S.cfgErrors) return 0;
  const since = Date.now() - period * DAY;
  return S.feedItems.filter(l => S.evals.get(l.id).niveau && !Store.feedback[l.id] && l.first_seen_at >= since).length;
}
function emit() { refresh(); }

/* ---------- Connexion ---------- */
function showLogin(message) {
  document.body.classList.add('logged-out');
  $('#view').className = 'login';
  $('#view').innerHTML = `<form class="login-card" id="login-form" onsubmit="return false">
    <div class="brand">${DIAMOND(28)}Sourcing auto</div>
    <div class="field"><label for="pwd">Mot de passe</label><input id="pwd" class="input" type="password" autocomplete="current-password" required></div>
    <p class="err-msg" id="login-err"${message ? '' : ' hidden'}>${esc(message || '')}</p>
    <button type="submit" class="btn btn-primary" data-action="login">Se connecter</button>
  </form>`;
  setTimeout(() => { const i = $('#pwd'); if (i) i.focus(); }, 30);
}
async function doLogin() {
  const pwd = $('#pwd').value;
  try {
    await Api.post('/api/login', { password: pwd });
    document.body.classList.remove('logged-out');
    await boot();
  } catch (e) {
    const el = $('#login-err'); el.hidden = false; el.textContent = e.status === 401 ? 'Mot de passe incorrect.' : e.message;
  }
}
async function boot() {
  const s = await Api.get('/api/session').catch(() => ({ ok: false }));
  if (!s.ok) { showLogin(); return; }
  document.body.classList.remove('logged-out');
  S.view = null;
  $('#view').innerHTML = '<p class="muted" style="padding:40px 0">Chargement des annonces…</p>';
  try {
    await Promise.all([loadConfig(), loadFeed()]);
    S.loaded = true; S.loadError = null;
  } catch (e) {
    if (e.status === 401) return;
    S.loadError = e.message;
  }
  route();
}

/* ---------- Routage ---------- */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, '');
  const [a, ...rest] = h.split('/');
  return { a: a || 'opportunites', b: rest.length ? decodeURIComponent(rest.join('/')) : null };
}
function route() {
  if (document.body.classList.contains('logged-out')) return;
  const { a, b } = parseHash();
  if (a === 'annonce' && b) {
    if (!S.view) show('opportunites');
    openSheet(b);
    return;
  }
  if (S.sheetId) closeSheetDom();
  const v = VIEWS[a] ? a : 'opportunites';
  if (v !== S.view) show(v);
}
function show(v) {
  S.view = v;
  renderView();
  window.scrollTo(0, 0);
}
function renderView() {
  const main = $('#view');
  main.className = S.view === 'evaluer' ? 'wide' : '';
  main.innerHTML = S.loadError && S.view === 'opportunites'
    ? `<div class="note stop" style="margin-top:20px">${ICON.stop}<div class="note-body"><strong>Chargement impossible.</strong> ${esc(S.loadError)}<div class="note-actions"><button type="button" class="btn btn-ghost btn-sm" data-action="reload">Réessayer</button></div></div></div>`
    : VIEWS[S.view].render();
  if (VIEWS[S.view].after) VIEWS[S.view].after();
  updateChrome();
}
function refresh() {
  updateChrome();
  if (!S.view) return;
  if (S.view === 'evaluer') updateEvalResult();
  else if (S.view === 'annonces') updateList();
  else if (S.view === 'reglages') { if (!S.dirty) renderView(); }
  else { const y = window.scrollY; renderView(); window.scrollTo(0, y); }
  if (S.sheetId) renderSheet();
}
function updateChrome() {
  const { a } = parseHash();
  const cur = a === 'annonce' ? S.view : a;
  document.querySelectorAll('.nav a').forEach(el => {
    if (el.dataset.view === cur) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  });
  const n = todoCount(7);
  const badge = $('#nav-badge');
  badge.textContent = n > 99 ? '99+' : String(n);
  badge.hidden = n === 0;
  badge.setAttribute('aria-label', `${n} à traiter`);
  const pill = basePill();
  document.querySelectorAll('[data-slot="base"]').forEach(el => { el.innerHTML = pill; });
  $('#mode-line').innerHTML = '<button type="button" class="btn btn-quiet btn-sm" style="padding:0" data-action="logout">Se déconnecter</button>';
}
function basePill() {
  const cp = S.cfgUsed.params.base_code_postal;
  if (!cp) return `<a class="base-pill missing" href="#/reglages">${ICON.home}Base à renseigner</a>`;
  const g = geocode(cp);
  return `<a class="base-pill" href="#/reglages" title="Voir les réglages">${ICON.home}${esc(g ? g.label : '')} ${esc(cp)}</a>`;
}

/* ---------- Toast et dialogue ---------- */
let toastTimer = null, toastUndo = null;
function toast(msg, undo) {
  const t = $('#toast');
  toastUndo = undo || null;
  t.innerHTML = `<span>${esc(msg)}</span>${undo ? '<button type="button" data-action="toast-undo">Annuler</button>' : ''}`;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.classList.remove('show'); toastUndo = null; }, undo ? 6000 : 3800);
}
function openDialog(html, onReady) {
  const w = $('#dialog');
  w.innerHTML = `<div class="dialog" role="dialog" aria-modal="true" aria-labelledby="dlg-title">${html}</div>`;
  w.hidden = false;
  if (onReady) onReady(w);
}
function closeDialog() { const w = $('#dialog'); w.hidden = true; w.innerHTML = ''; }
