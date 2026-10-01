/* ============================================================
   Réglages : modifiables dans l'interface, versionnés côté serveur
   ============================================================ */
const TO_CONFIRM = ['taux_frais_pct', 'cout_transport_eur_km', 'base_code_postal'];

function toInputStr(key, v) {
  const m = PARAM_META[key];
  if (m.kind === 'bool') return v === true || v === 'true' || v === 'VRAI';
  if (v == null) return '';
  if (m.kind === 'dec') return String(v).replace('.', ',');
  if (m.kind === 'int') { const n = parseNumberFr(v); return isNaN(n) ? String(v) : nf0.format(n); }
  return String(v);
}
function draftFromSource(src) {
  const params = {};
  for (const k of Object.keys(PARAM_META)) params[k] = toInputStr(k, src && src.params ? src.params[k] : DEFAULT_PARAMS[k]);
  return { params, keywords: [...((src && src.keywords) || DEFAULT_KEYWORDS)] };
}
// Contrôle immédiat dans le navigateur ; le serveur reste juge (mêmes règles, réponse 422 par champ).
function clientErrors(d) {
  const e = {}, num = {};
  for (const [k, m] of Object.entries(PARAM_META)) {
    const v = d.params[k];
    if (m.kind === 'bool' || m.kind === 'select') continue;
    if (m.kind === 'cp') {
      const t = String(v || '').trim();
      if (!t) e[k] = 'À renseigner : le job en a besoin pour calculer le transport.';
      else if (!/^\d{5}$/.test(t)) e[k] = 'Saisissez un code postal à 5 chiffres.';
      continue;
    }
    const n = parseNumberFr(v);
    if (String(v).trim() === '' || isNaN(n)) { e[k] = 'Saisissez un nombre.'; continue; }
    if (m.kind === 'int' && !Number.isInteger(n)) { e[k] = 'Saisissez un nombre entier.'; continue; }
    if (m.min != null && n < m.min) { e[k] = `Minimum ${nf0.format(m.min)}.`; continue; }
    if (m.max != null && n > m.max) { e[k] = `Maximum ${nf0.format(m.max)}.`; continue; }
    num[k] = n;
  }
  if (num.prix_max_eur != null && num.prix_min_eur != null && num.prix_max_eur <= num.prix_min_eur && !e.prix_max_eur) e.prix_max_eur = 'Doit être supérieur au prix minimum.';
  if (num.marge_prioritaire_eur != null && num.marge_min_eur != null && num.marge_prioritaire_eur < num.marge_min_eur && !e.marge_prioritaire_eur) e.marge_prioritaire_eur = 'Doit être au moins égale à la marge minimum.';
  if (d.keywords.some(k => k.trim().length < 2)) e.mots_cles_exclusion = 'Un mot-clé doit contenir au moins deux caractères.';
  return e;
}
function allErrors() { return { ...S.fieldErrors, ...clientErrors(S.draft) }; }

function settingField(key, err) {
  const m = PARAM_META[key], v = S.draft.params[key], id = 'f-' + key;
  const flag = !S.cfgMeta && TO_CONFIRM.includes(key) ? `<span class="tag confirm">${key === 'base_code_postal' ? 'À renseigner' : 'À confirmer'}</span>` : '';
  if (m.kind === 'bool') {
    return `<div class="field" id="w-${key}"><div class="switch-row"><label for="${id}" style="font-weight:600">${esc(m.label)}</label><label class="switch"><input type="checkbox" id="${id}" data-param="${key}"${v ? ' checked' : ''}><span></span></label></div>${m.help ? `<span class="help">${esc(m.help)}</span>` : ''}</div>`;
  }
  let ctl;
  if (m.kind === 'select') {
    ctl = `<div class="iw ctl"><select id="${id}" class="input" data-param="${key}">${m.options.map(o => `<option value="${o.value}"${o.value === v ? ' selected' : ''}${o.disabled ? ' disabled' : ''}>${esc(o.label)}</option>`).join('')}</select>${ICON.chev}</div>`;
  } else {
    const pad = m.unit ? `style="padding-right:${Math.min(110, m.unit.length * 8.5 + 22)}px"` : '';
    ctl = `<div class="iw ctl"><input id="${id}" class="input" data-param="${key}" inputmode="${m.kind === 'dec' ? 'decimal' : 'numeric'}" value="${esc(v)}" ${pad}${m.kind === 'cp' ? ' maxlength="5" placeholder="69003" autocomplete="postal-code"' : ''} aria-describedby="e-${key}">${m.unit ? `<span class="unit">${esc(m.unit)}</span>` : ''}</div>`;
  }
  const g = m.kind === 'cp' && /^\d{5}$/.test(String(v).trim()) ? geocode(String(v).trim()) : null;
  const help = m.kind === 'cp' ? (g ? `${g.label}${g.approx ? ' (position approchée)' : ''}. ${m.help}` : m.help) : m.help;
  return `<div class="field row${err ? ' err' : ''}" id="w-${key}"><label for="${id}">${esc(m.label)}${flag}</label>${ctl}${help ? `<span class="help" id="h-${key}">${esc(help)}</span>` : ''}<span class="err-msg" id="e-${key}"${err ? '' : ' hidden'}>${esc(err || '')}</span></div>`;
}
function kwEditor(err) {
  return `<ul class="kw-list" aria-label="Mots-clés">${S.draft.keywords.map((k, i) => `<li>${esc(k)}<button type="button" data-action="kw-remove" data-i="${i}" aria-label="Retirer ${esc(k)}">${ICON.x}</button></li>`).join('')}</ul>
    <div class="kw-add"><label class="sr-only" for="kw-new">Nouveau mot-clé</label><input id="kw-new" class="input" placeholder="Ex. : embrayage HS" enterkeyhint="done"><button type="button" class="btn btn-ghost" data-action="kw-add">Ajouter</button></div>
    ${err ? `<p class="err-msg">${esc(err)}</p>` : ''}`;
}
function renderSettings() {
  if (!S.dirty || !S.draft) { S.draft = draftFromSource(S.cfgDraftSource); S.fieldErrors = {}; }
  if (!S.cfgMeta) S.dirty = true;  // premier enregistrement : la barre d'enregistrement reste visible
  const errs = allErrors(), meta = S.cfgMeta;
  const intro = meta
    ? 'Chaque enregistrement crée une nouvelle version et s’applique dès le run suivant, dans les 10 minutes. Une valeur invalide est refusée avant d’être enregistrée.'
    : 'Aucun réglage n’est encore enregistré : vérifiez les valeurs ci-dessous, renseignez au moins le code postal de votre base, puis enregistrez. Le job démarre avec cette première version.';
  const stored = S.cfgErrors && meta ? `<div class="note stop" role="alert">${ICON.stop}<div class="note-body"><strong>La version enregistrée est invalide : les alertes sont suspendues.</strong><ul class="err-list">${S.cfgErrors.map(e => `<li>${esc(e)}</li>`).join('')}</ul></div></div>` : '';
  return `<div class="page-head"><h1>Réglages</h1><p class="lede">${intro}</p></div>
    ${stored}
    ${PARAM_GROUPS.map(g => `<div class="group"><h2>${esc(g.title)}</h2>${g.intro ? `<p>${esc(g.intro)}</p>` : ''}<div class="group-body">${g.keys.map(k => settingField(k, errs[k])).join('')}</div></div>`).join('')}
    <div class="group"><h2>Mots-clés d’exclusion</h2><p>Recherchés dans le titre et la description, sans tenir compte des accents ni des majuscules, sur des mots entiers.</p><div class="group-body"><div class="kw-editor" id="kw-editor">${kwEditor(errs.mots_cles_exclusion)}</div></div></div>
    <p class="small muted">${meta ? `Version ${meta.number}${meta.savedAt ? `, enregistrée le ${esc(dtf.format(meta.savedAt))}` : ''}. ` : ''}<button type="button" class="btn btn-quiet btn-sm" style="min-height:28px;padding:0 4px;color:var(--blue)" data-action="settings-defaults">Rétablir les valeurs initiales</button></p>
    <div class="savebar" id="savebar"${S.dirty ? '' : ' hidden'}>${savebarHtml(errs)}</div>`;
}
function savebarHtml(errs) {
  const n = Object.keys(errs).length;
  let txt;
  if (n) txt = `Corrigez ${plural(n, 'le champ en rouge', `les ${n} champs en rouge`)} pour enregistrer.`;
  else if (S.preview) txt = `Avec ces réglages : environ <b>${S.preview.n}</b> ${plural(S.preview.n, 'alerte', 'alertes')} sur 7 jours, dont ${S.preview.p} ${plural(S.preview.p, 'prioritaire', 'prioritaires')}. Actuellement : ${S.preview.current}.`;
  else txt = S.cfgMeta ? 'Calcul de l’impact…' : 'Prêt pour le premier enregistrement.';
  const cancel = S.cfgMeta ? '<button type="button" class="btn btn-quiet btn-sm" data-action="settings-cancel">Annuler</button>' : '';
  return `<span class="txt" aria-live="polite">${txt}</span>${cancel}<button type="button" class="btn btn-primary btn-sm" data-action="settings-save"${n || S.saving ? ' disabled' : ''}>${S.saving ? 'Enregistrement…' : 'Enregistrer'}</button>`;
}
function refreshSavebar() {
  const bar = $('#savebar');
  if (!bar) return;
  bar.hidden = !S.dirty;
  bar.innerHTML = savebarHtml(allErrors());
}
function refreshFieldErrors() {
  const errs = allErrors();
  for (const k of Object.keys(PARAM_META)) {
    const w = $('#w-' + k), e = $('#e-' + k);
    if (!w || !e) continue;
    w.classList.toggle('err', !!errs[k]);
    e.hidden = !errs[k]; e.textContent = errs[k] || '';
  }
}
let previewTimer = null, previewSeq = 0;
function schedulePreview() {
  S.preview = null;
  refreshSavebar();
  clearTimeout(previewTimer);
  if (Object.keys(clientErrors(S.draft)).length || !S.cfgMeta) return;
  previewTimer = setTimeout(async () => {
    const seq = ++previewSeq;
    try {
      const r = await Api.post('/api/config/preview', { params: S.draft.params, keywords: S.draft.keywords });
      if (seq === previewSeq) { S.preview = r; refreshSavebar(); }
    } catch (e) {
      if (seq === previewSeq && e.data && e.data.errors) { S.fieldErrors = e.data.errors; refreshFieldErrors(); refreshSavebar(); }
    }
  }, 500);
}
function onParamInput(el) {
  const key = el.dataset.param;
  S.draft.params[key] = el.type === 'checkbox' ? el.checked : el.value;
  delete S.fieldErrors[key];
  S.dirty = true;
  refreshFieldErrors();
  if (key === 'base_code_postal') {
    const h = $('#h-base_code_postal'), t = String(el.value).trim(), g = /^\d{5}$/.test(t) ? geocode(t) : null;
    if (h) h.textContent = g ? `${g.label}${g.approx ? ' (position approchée)' : ''}. ${PARAM_META.base_code_postal.help}` : PARAM_META.base_code_postal.help;
  }
  schedulePreview();
}
function addKeyword() {
  const i = $('#kw-new'), v = i.value.trim();
  if (!v) { i.focus(); return; }
  if (!S.draft.keywords.some(k => strip(k) === strip(v))) S.draft.keywords.push(v);
  S.dirty = true; refreshKw(); schedulePreview();
  $('#kw-new').focus();
}
function refreshKw() { $('#kw-editor').innerHTML = kwEditor(allErrors().mots_cles_exclusion); refreshSavebar(); }
async function saveSettings() {
  if (Object.keys(clientErrors(S.draft)).length || S.saving) return;
  S.saving = true; refreshSavebar();
  try {
    const r = await Api.post('/api/config', { params: S.draft.params, keywords: S.draft.keywords, based_on: S.cfgMeta ? S.cfgMeta.number : 0 });
    S.saving = false; S.dirty = false; S.preview = null; S.fieldErrors = {};
    await loadConfig();
    await loadFeed().catch(() => {});
    renderView();
    toast(`Réglages enregistrés, version ${r.meta.number}. Ils s’appliquent au prochain run.`);
  } catch (e) {
    S.saving = false;
    if (e.status === 422 && e.data && e.data.errors) { S.fieldErrors = e.data.errors; refreshFieldErrors(); refreshSavebar(); toast('Certaines valeurs sont refusées : voir les champs en rouge.'); }
    else { refreshSavebar(); toast(e.status === 409 ? e.message : 'Enregistrement impossible : ' + e.message); }
  }
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
    case 'settings-save': saveSettings(); break;
    case 'settings-cancel': S.dirty = false; S.preview = null; S.fieldErrors = {}; { const y = scrollY; renderView(); scrollTo(0, y); } break;
    case 'settings-defaults': S.draft = draftFromSource(null); S.draft.params.base_code_postal = S.cfgUsed.params.base_code_postal || ''; S.dirty = true; S.fieldErrors = {}; renderView(); schedulePreview(); break;
    case 'kw-add': addKeyword(); break;
    case 'kw-remove': S.draft.keywords.splice(+t.dataset.i, 1); S.dirty = true; refreshKw(); schedulePreview(); break;
    case 'ev-scroll': $('#eval-result').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' }); break;
  }
});
document.addEventListener('change', e => {
  const t = e.target;
  if (t.matches('[data-action="period"]')) { S.feed.period = +t.value; reloadFeed(); }
  else if (t.matches('[data-action="sort"]')) { S.feed.sort = t.value; renderView(); }
  else if (t.matches('select[data-ev]')) { S.ev[t.dataset.ev] = t.value; onEvInput(); }
  else if (t.matches('[data-param]') && (t.type === 'checkbox' || t.tagName === 'SELECT')) onParamInput(t);
});
let listTimer = null;
document.addEventListener('input', e => {
  const t = e.target;
  if (t.matches('[data-param]') && t.type !== 'checkbox' && t.tagName !== 'SELECT') { onParamInput(t); return; }
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
    else if (e.target.id === 'kw-new') { e.preventDefault(); addKeyword(); }
    else if (e.target.id === 'buy-price') { e.preventDefault(); confirmBuy($('[data-action="buy-confirm"]').dataset.id); }
  }
});
$('#scrim').addEventListener('click', () => closeSheet());
$('#dialog').addEventListener('click', e => { if (e.target.id === 'dialog') closeDialog(); });
window.addEventListener('hashchange', route);
// Rafraîchit le fil toutes les 5 minutes quand l'onglet est visible.
setInterval(() => { if (!document.hidden && S.loaded && S.view === 'opportunites' && !S.sheetId) reloadFeed(); }, 5 * 60 * 1000);

boot();
