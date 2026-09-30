/* ============================================================
   Réglages : lecture seule, la référence est le Google Sheet
   ============================================================ */
function paramValue(key, v) {
  const m = PARAM_META[key];
  if (m.kind === 'bool') return v ? 'Oui' : 'Non';
  if (m.kind === 'select') return (m.options.find(o => o.value === v) || { label: v }).label;
  if (m.kind === 'cp') { if (!v) return 'À renseigner'; const g = geocode(v); return g ? `${v}, ${g.label}` : v; }
  if (v == null || v === '') return '—';
  const n = m.kind === 'dec' ? new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(v) : fmtNum(v);
  return m.unit ? `${n}${NB}${m.unit}` : n;
}
function renderSettings() {
  const p = S.cfgUsed.params;
  const sheet = Store.sheetUrl
    ? `<a class="btn btn-primary" href="${esc(Store.sheetUrl)}" target="_blank" rel="noopener">${ICON.ext}Modifier dans le Google Sheet</a>` : '';
  const errors = S.cfgErrors
    ? `<div class="note stop" role="alert">${ICON.stop}<div class="note-body"><strong>Le Google Sheet contient des erreurs : les alertes sont suspendues.</strong><ul class="err-list">${S.cfgErrors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div></div>` : '';
  return `<div class="page-head"><h1>Réglages</h1><p class="lede">Les réglages se modifient dans le Google Sheet partagé. Ils sont relus à chaque run, toutes les 10 minutes, et une valeur invalide suspend les alertes plutôt que de filtrer avec une configuration fausse.</p>
    <div class="toolbar">${sheet}<button type="button" class="btn btn-ghost" data-action="reload-config">Relire le Sheet</button></div></div>
    ${errors}
    ${PARAM_GROUPS.map(g => `<div class="group"><h2>${esc(g.title)}</h2>${g.intro ? `<p>${esc(g.intro)}</p>` : ''}<div class="group-body">${g.keys.map(k => `
      <div class="field row"><span class="label">${esc(PARAM_META[k].label)}</span><span class="ctl ro-value">${esc(paramValue(k, p[k]))}</span>${PARAM_META[k].help ? `<span class="help">${esc(PARAM_META[k].help)}</span>` : ''}</div>`).join('')}</div></div>`).join('')}
    <div class="group"><h2>Mots-clés d’exclusion</h2><p>Recherchés dans le titre et la description, sans tenir compte des accents ni des majuscules, sur des mots entiers.</p>
      <div class="group-body"><div class="kw-editor"><ul class="kw-list" style="margin:0">${S.cfgUsed.keywords.map(k => `<li style="padding-right:11px">${esc(k)}</li>`).join('')}</ul></div></div></div>
    <p class="small muted">Version des réglages : ${esc(S.cfgUsed.version)}. Chaque évaluation enregistre la version utilisée.</p>`;
}

/* ============================================================
   Retours (Intéressant, Pas intéressant, Acheté)
   ============================================================ */
async function sendFeedback(id, fb) {
  const prev = Store.feedback[id] || null;
  if (fb) Store.feedback[id] = fb; else delete Store.feedback[id];
  emit();
  try {
    await Api.post('/api/feedback', { id, statut: fb ? fb.statut : 'aucun', prix_achat: fb ? fb.prix_achat ?? null : null });
    return true;
  } catch (e) {
    if (prev) Store.feedback[id] = prev; else delete Store.feedback[id];
    emit();
    toast('Avis non enregistré : ' + e.message);
    return false;
  }
}
async function setFeedback(id, val) {
  const prev = Store.feedback[id] || null;
  if (prev && prev.statut === val) {
    if (await sendFeedback(id, null)) toast('Avis retiré : l’annonce est de nouveau à traiter', () => sendFeedback(id, prev));
    return;
  }
  if (val === 'achete') { openBuyDialog(id, prev); return; }
  if (await sendFeedback(id, { statut: val, at: Date.now() })) {
    toast(val === 'interessant' ? 'Marquée intéressante' : 'Marquée pas intéressante', () => sendFeedback(id, prev));
  }
}
function openBuyDialog(id, prev) {
  const l = S.byId.get(id);
  openDialog(`<h2 id="dlg-title">Marquer comme achetée</h2><p>${esc(l.titre || `${l.marque} ${l.modele}`)}, affichée ${esc(fmtEur(l.prix))}.</p>
    <div class="field"><label for="buy-price">Prix payé</label><div class="iw"><input id="buy-price" class="input" inputmode="numeric" value="${l.prix ? esc(nf0.format(l.prix)) : ''}" style="padding-right:34px"><span class="unit">€</span></div>
    <span class="help">Facultatif. Sert à mesurer la négociation obtenue dans le suivi.</span><span class="err-msg" id="buy-err" hidden></span></div>
    <div class="actions"><button type="button" class="btn btn-ghost" data-action="dlg-cancel">Annuler</button><button type="button" class="btn btn-primary" data-action="buy-confirm" data-id="${esc(id)}">Marquer achetée</button></div>`,
    w => { const i = $('#buy-price', w); i.focus(); i.select(); });
  S.buyPrev = prev;
}
async function confirmBuy(id) {
  const raw = $('#buy-price').value.trim();
  let price = null;
  if (raw) {
    price = toInt(raw);
    if (price == null || price <= 0) { const e = $('#buy-err'); e.hidden = false; e.textContent = 'Saisissez un montant en euros, ou laissez vide.'; return; }
  }
  const prev = S.buyPrev;
  closeDialog();
  if (await sendFeedback(id, { statut: 'achete', prix_achat: price, at: Date.now() })) {
    S.stats = null;
    toast('Marquée achetée', () => sendFeedback(id, prev));
  }
}

/* ============================================================
   Vues, événements, démarrage
   ============================================================ */
const VIEWS = {
  opportunites: { render: renderFeed },
  evaluer: { render: renderEvaluate, after: updateEvalResult },
  annonces: { render: renderListings, after: () => loadList(false) },
  suivi: { render: renderSuivi },
  reglages: { render: renderSettings },
};

async function reloadFeed() {
  try { await loadFeed(); S.loadError = null; } catch (e) { S.loadError = e.message; }
  renderView();
}

document.addEventListener('click', e => {
  const t = e.target.closest('[data-action], [data-ev-seg]');
  if (!t) return;
  if (t.dataset.evSeg) {
    S.ev[t.dataset.evSeg] = t.dataset.v;
    t.parentElement.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b === t)));
    onEvInput(); return;
  }
  const a = t.dataset.action, id = t.dataset.id;
  switch (a) {
    case 'login': doLogin(); break;
    case 'logout': Api.post('/api/logout', {}).finally(() => showLogin()); break;
    case 'reload': boot(); break;
    case 'reload-config': loadConfig().then(() => { renderView(); toast('Réglages relus'); }).catch(err => toast(err.message)); break;
    case 'open': S.sheetFromApp = true; location.hash = '#/annonce/' + encodeURIComponent(id); break;
    case 'close-sheet': closeSheet(); break;
    case 'fb': setFeedback(id, t.dataset.val); break;
    case 'tab': S.feed.status = t.dataset.tab; renderView(); break;
    case 'prio': S.feed.prioOnly = !S.feed.prioOnly; renderView(); break;
    case 'period-30': S.feed.period = 30; reloadFeed(); break;
    case 'toast-undo': if (toastUndo) { const u = toastUndo; toastUndo = null; u(); $('#toast').classList.remove('show'); } break;
    case 'dlg-cancel': closeDialog(); break;
    case 'buy-confirm': confirmBuy(id); break;
    case 'list-statut': S.list.statut = t.dataset.k; loadList(false); break;
    case 'list-more': S.list.offset += 50; loadList(true); break;
    case 'list-clear': S.list.q = ''; renderView(); break;
    case 'ev-clear': S.ev = emptyEvalForm(); renderView(); break;
    case 'ev-save': saveEval(); break;
    case 'ev-scroll': $('#eval-result').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }); break;
  }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches('[data-action="period"]')) { S.feed.period = +t.value; reloadFeed(); }
  else if (t.matches('[data-action="sort"]')) { S.feed.sort = t.value; renderView(); }
  else if (t.matches('select[data-ev]')) { S.ev[t.dataset.ev] = t.value; onEvInput(); }
});
let listTimer = null;
document.addEventListener('input', e => {
  const t = e.target;
  if (t.matches('[data-ev]')) {
    S.ev[t.dataset.ev] = t.value;
    if (t.dataset.ev === 'marque') {
      const dl = $('#dl-modeles');
      if (dl) dl.innerHTML = [...new Set(MODELS.filter(m => strip(m.marque) === strip(t.value).trim()).map(m => m.modele))].map(m => `<option value="${esc(m)}">`).join('');
    }
    onEvInput();
  } else if (t.matches('[data-list-q]')) {
    S.list.q = t.value;
    clearTimeout(listTimer); listTimer = setTimeout(() => loadList(false), 300);
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    if (!$('#dialog').hidden) { closeDialog(); return; }
    if (S.sheetId) closeSheet();
  } else if (e.key === 'Enter') {
    if (e.target.id === 'pwd') { e.preventDefault(); doLogin(); }
    else if (e.target.id === 'buy-price') { e.preventDefault(); confirmBuy($('[data-action="buy-confirm"]').dataset.id); }
  }
});
$('#scrim').addEventListener('click', () => closeSheet());
$('#dialog').addEventListener('click', e => { if (e.target.id === 'dialog') closeDialog(); });
window.addEventListener('hashchange', route);
// Rafraîchit le fil toutes les 5 minutes quand l'onglet est visible.
setInterval(() => { if (!document.hidden && S.loaded && S.view === 'opportunites' && !S.sheetId) reloadFeed(); }, 5 * 60 * 1000);

boot();
