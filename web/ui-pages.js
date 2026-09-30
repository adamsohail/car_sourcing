/* ============================================================
   Évaluer une annonce (calcul fait par le serveur, mêmes règles que les alertes)
   ============================================================ */
const FUELS = ['Essence', 'Diesel', 'Hybride', 'Électrique', 'GPL'];
function emptyEvalForm() {
  return { source: 'manuel', url: '', marque: '', modele: '', version: '', annee: '', km: '', carburant: 'Essence', boite: 'Manuelle', prix: '', vendeur: 'particulier', cp: '', ville: '', description: '' };
}
const toInt = v => { const n = parseNumberFr(v); return isNaN(n) ? null : Math.round(n); };
function missingFields(e) {
  const miss = [];
  if (!e.marque.trim()) miss.push('la marque');
  if (!e.modele.trim()) miss.push('le modèle');
  if (toInt(e.prix) == null) miss.push('le prix');
  if (toInt(e.annee) == null) miss.push('l’année');
  if (toInt(e.km) == null) miss.push('le kilométrage');
  return miss;
}
function joinFr(a) { return a.length < 2 ? a.join('') : a.slice(0, -1).join(', ') + ' et ' + a[a.length - 1]; }

function segCtl(name, value, options) {
  return `<div class="seg-ctl" role="group">${options.map(([v, t]) => `<button type="button" data-ev-seg="${name}" data-v="${v}" aria-pressed="${value === v}">${esc(t)}</button>`).join('')}</div>`;
}
function evField(name, label, opts = {}) {
  const v = S.ev[name], id = 'ev-' + name;
  const ctl = opts.select
    ? `<div class="iw"><select id="${id}" class="input" data-ev="${name}">${opts.select.map(o => `<option${o === v ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>${ICON.chev}</div>`
    : opts.textarea
      ? `<textarea id="${id}" class="input" data-ev="${name}" placeholder="${esc(opts.ph || '')}">${esc(v)}</textarea>`
      : `<div class="iw"><input id="${id}" class="input" data-ev="${name}" value="${esc(v)}" ${opts.attrs || ''} placeholder="${esc(opts.ph || '')}"${opts.unit ? ` style="padding-right:${opts.unit.length * 9 + 22}px"` : ''}>${opts.unit ? `<span class="unit">${esc(opts.unit)}</span>` : ''}</div>`;
  return `<div class="field${opts.full ? ' full' : ''}"><label for="${id}">${esc(label)}</label>${ctl}${opts.help ? `<span class="help">${esc(opts.help)}</span>` : ''}</div>`;
}
function renderEvaluate() {
  if (!S.ev) S.ev = emptyEvalForm();
  const marques = [...new Set(MODELS.map(m => m.marque))].sort();
  const modeles = MODELS.filter(m => !S.ev.marque || strip(m.marque) === strip(S.ev.marque).trim()).map(m => m.modele);
  return `<div class="page-head"><h1>Évaluer une annonce</h1><p class="lede">Saisissez une annonce repérée à la main : la marge est calculée avec les mêmes règles et les mêmes comparables que les alertes.</p></div>
  <div class="eval-layout">
    <form class="panel" id="eval-form" autocomplete="off" onsubmit="return false">
      <div class="form-grid">
        ${evField('url', 'Lien de l’annonce', { full: true, attrs: 'type="url" inputmode="url"', ph: 'https://' })}
        ${evField('marque', 'Marque', { attrs: 'list="dl-marques" autocapitalize="words"', ph: 'Peugeot' })}
        ${evField('modele', 'Modèle', { attrs: 'list="dl-modeles"', ph: '208' })}
        ${evField('version', 'Version', { full: true, ph: '1.2 PureTech 100 Allure' })}
        ${evField('annee', 'Année', { attrs: 'inputmode="numeric" maxlength="4"', ph: '2019' })}
        ${evField('km', 'Kilométrage', { attrs: 'inputmode="numeric"', unit: 'km', ph: '85 000' })}
        ${evField('carburant', 'Carburant', { select: FUELS })}
        <div class="field"><span class="label">Boîte</span>${segCtl('boite', S.ev.boite, [['Manuelle', 'Manuelle'], ['Automatique', 'Auto']])}</div>
        ${evField('prix', 'Prix affiché', { attrs: 'inputmode="numeric"', unit: '€', ph: '9 500' })}
        <div class="field"><span class="label">Vendeur</span>${segCtl('vendeur', S.ev.vendeur, [['particulier', 'Particulier'], ['pro', 'Pro']])}</div>
        ${evField('cp', 'Code postal', { attrs: 'inputmode="numeric" maxlength="5" autocomplete="postal-code"', ph: '69003' })}
        ${evField('ville', 'Ville', { ph: 'Lyon' })}
        ${evField('description', 'Description', { full: true, textarea: true, ph: 'Collez la description du vendeur', help: 'Les mots-clés d’exclusion y sont recherchés.' })}
      </div>
      <div class="toolbar" style="margin-bottom:0"><button type="button" class="btn btn-quiet btn-sm" data-action="ev-clear">Effacer</button></div>
      <datalist id="dl-marques">${marques.map(m => `<option value="${esc(m)}">`).join('')}</datalist>
      <datalist id="dl-modeles">${[...new Set(modeles)].map(m => `<option value="${esc(m)}">`).join('')}</datalist>
    </form>
    <div class="eval-result" id="eval-result" tabindex="-1"></div>
  </div>
  <div class="peek" id="eval-peek" hidden></div>`;
}
let evSeq = 0;
async function updateEvalResult() {
  const box = $('#eval-result'), peek = $('#eval-peek');
  if (!box) return;
  const miss = missingFields(S.ev);
  if (miss.length) {
    box.innerHTML = `<div class="panel"><h2>Estimation</h2><p class="muted" style="margin:0">Renseignez ${esc(joinFr(miss))} pour estimer la marge.</p></div>`;
    peek.hidden = true;
    return;
  }
  const seq = ++evSeq;
  box.querySelector('.panel')?.classList.add('busy');
  let res;
  try {
    res = await Api.post('/api/evaluate', S.ev);
  } catch (e) {
    if (seq !== evSeq) return;
    box.innerHTML = `<div class="note stop">${ICON.stop}<div class="note-body"><strong>Estimation impossible.</strong> ${esc(e.message)}</div></div>`;
    return;
  }
  if (seq !== evSeq) return;  // une saisie plus récente est en cours
  const ev = { ...res.ev, comps: [] };
  const d = { prix: toInt(S.ev.prix), prevPrice: null };
  let head, peekV, peekL;
  if (ev.statut === 'exclue') {
    head = `<div class="note stop">${ICON.stop}<div class="note-body"><strong>Exclue : ${esc(motifLabel(ev))}.</strong> ${esc(exclusionHelp(d, ev))}</div></div>`;
    peekV = 'Exclue'; peekL = motifLabel(ev);
  } else if (ev.statut === 'sans_cote') {
    head = `<div class="note warn">${ICON.warn}<div class="note-body"><strong>Aucun comparable trouvé.</strong> Vérifiez l’orthographe de la marque et du modèle, ou comparez à la main.</div></div>`;
    peekV = '—'; peekL = 'Aucun comparable';
  } else {
    const lvl = ev.niveau === 'prioritaire' ? `<span class="tag prio">${DIAMOND(13)}Alerte prioritaire</span>` : ev.niveau ? '<span class="tag">Alerte normale</span>' : '<span class="tag">Sous le seuil</span>';
    head = `<div class="tags" style="margin:0 0 12px">${lvl}<span class="tag">${signal(ev.fiabilite)}${FIAB[ev.fiabilite].label}, ${ev.n} ${plural(ev.n, 'comparable', 'comparables')}</span></div>${receipt(d, ev)}`;
    peekV = fmtSigned(ev.marge); peekL = ev.niveau === 'prioritaire' ? 'Alerte prioritaire' : ev.niveau ? 'Alerte normale' : 'Sous le seuil';
  }
  const place = !res.geocoded ? '<p class="small muted">Lieu non reconnu : le transport est compté à 0 €.</p>' : '';
  box.innerHTML = `<div class="panel"><h2>Estimation</h2>${head}${place}
    <div class="toolbar" style="margin:14px 0 0"><button type="button" class="btn btn-primary" data-action="ev-save">${ICON.plus}Enregistrer dans les annonces</button></div>
    <p class="small muted" style="margin:8px 0 0">L’annonce enregistrée rejoint la liste et sert de comparable pour les suivantes.</p></div>`;
  peek.hidden = false;
  peek.innerHTML = `<div><span class="v${ev.niveau ? ' gain' : ''}">${esc(peekV)}</span><span class="l" style="display:block">${esc(peekL)}</span></div><button type="button" class="btn btn-sm" data-action="ev-scroll">Voir le détail</button>`;
}
let evTimer = null;
function onEvInput() { clearTimeout(evTimer); evTimer = setTimeout(updateEvalResult, 450); }
async function saveEval() {
  if (missingFields(S.ev).length) return;
  try {
    const r = await Api.post('/api/manual', S.ev);
    S.ev = emptyEvalForm();
    renderView();
    toast('Annonce enregistrée');
    S.sheetFromApp = true;
    location.hash = '#/annonce/' + encodeURIComponent(r.id);
  } catch (e) {
    toast('Enregistrement impossible : ' + e.message);
  }
}

/* ============================================================
   Toutes les annonces (recherche et pagination côté serveur)
   ============================================================ */
const LIST_FILTERS = [['all', 'Toutes'], ['alerte', 'Alertes'], ['sous_seuil', 'Sous le seuil'], ['exclue', 'Exclues'], ['sans_cote', 'Sans cote']];
const MOTIFS_SHORT = { prix_hors_bornes: 'Prix hors fourchette', vendeur_pro: 'Vendeur pro', km_max: 'Trop de km', km_par_an: 'Trop de km par an', donnees_incompletes: 'Incomplète', cote_indisponible: 'Sans comparable' };
function shortMotif(ev) { return ev.motif.code === 'mot_cle' ? `« ${ev.motif.detail} »` : (MOTIFS_SHORT[ev.motif.code] || motifLabel(ev)); }

async function loadList(append) {
  const L = S.list;
  if (!append) L.offset = 0;
  L.loading = true; L.error = null;
  const seq = (L.seq = (L.seq || 0) + 1);
  updateList();
  try {
    const qs = new URLSearchParams({ q: L.q, statut: L.statut, limit: '50', offset: String(L.offset) });
    const r = await Api.get('/api/listings?' + qs);
    if (seq !== L.seq) return;
    const items = ingest(r.items);
    L.items = append ? L.items.concat(items) : items;
    L.counts = r.counts; L.total = r.total; L.hasMore = r.items.length === 50;
  } catch (e) {
    if (seq === L.seq) L.error = e.message;
  }
  if (seq === L.seq) { L.loading = false; updateList(); }
}
function renderListings() {
  return `<div class="page-head"><h1>Toutes les annonces</h1><p class="lede">Les annonces reçues sur 90 jours. Toutes sont conservées, alertées ou non : elles servent à calculer la cote.</p></div>
    <div class="search"><label class="sr-only" for="list-q">Rechercher</label>${ICON.search}<input id="list-q" class="input" type="search" placeholder="Marque, modèle, ville, année" value="${esc(S.list.q)}" data-list-q></div>
    <div class="toolbar" id="list-chips"></div>
    <div id="list-rows"></div>`;
}
function listChips() {
  const c = S.list.counts, all = Object.values(c).reduce((a, b) => a + b, 0);
  return LIST_FILTERS.map(([k, t]) => `<button type="button" class="chip sel" data-action="list-statut" data-k="${k}" aria-pressed="${S.list.statut === k}">${t}<span class="count">${fmtNum(k === 'all' ? all : (c[k] || 0))}</span></button>`).join('');
}
function listRows() {
  const L = S.list;
  if (L.error) return `<div class="note stop">${ICON.stop}<div class="note-body">${esc(L.error)}</div></div>`;
  if (!L.items.length) return L.loading ? '<p class="muted">Chargement…</p>' : empty('Aucune annonce', L.q ? 'Aucune annonce ne correspond à cette recherche.' : 'Aucune annonce dans cette catégorie pour l’instant.', L.q ? '<button type="button" class="btn btn-ghost" data-action="list-clear">Effacer la recherche</button>' : '');
  const rows = L.items.map(l => {
    const ev = S.evals.get(l.id);
    let end;
    if (ev.statut === 'alerte') end = `<span class="v gain">${esc(fmtSigned(ev.marge))}</span>${ev.niveau === 'prioritaire' ? `<span style="display:inline-flex;align-items:center;gap:4px">${DIAMOND(12)}Prioritaire</span>` : '<span class="muted">Alerte</span>'}`;
    else if (ev.statut === 'sous_seuil') end = `<span class="v flat">${esc(fmtSigned(ev.marge))}</span><span class="muted">Sous le seuil</span>`;
    else if (ev.motif) end = `<span style="color:var(--stop);font-weight:600">${esc(shortMotif(ev))}</span>`;
    else end = '<span class="muted">Non évaluée</span>';
    return `<button type="button" class="row-item" data-action="open" data-id="${esc(l.id)}"><span style="min-width:0"><span class="ri-title">${esc(l.titre || `${l.marque} ${l.modele}`)}</span><span class="ri-sub"><span>${l.annee ?? '—'}</span><span>${esc(fmtKm(l.km))}</span><span>${esc(fmtEur(l.prix))}</span><span>${esc(l.ville || '')}</span><span>${l.first_seen_at ? ago(l.first_seen_at) : ''}</span></span></span><span class="ri-end">${end}</span></button>`;
  }).join('');
  const more = L.hasMore ? `<div class="more"><button type="button" class="btn btn-ghost" data-action="list-more"${L.loading ? ' disabled' : ''}>${L.loading ? 'Chargement…' : 'Afficher 50 de plus'}</button></div>` : '';
  return `<div class="rows">${rows}</div>${more}`;
}
function updateList() {
  const chips = $('#list-chips'), rows = $('#list-rows');
  if (chips) chips.innerHTML = listChips();
  if (rows) rows.innerHTML = listRows();
}

/* ============================================================
   Suivi (agrégats calculés par BigQuery sur 90 jours)
   ============================================================ */
async function loadStats() {
  try { S.stats = await Api.get('/api/stats'); S.statsError = null; } catch (e) { S.statsError = e.message; }
  if (S.view === 'suivi') renderView();
}
function dayBars(perDay) {
  const days = 14, W = 340, H = 140, pl = 4, pb = 22, pt = 8;
  const start = new Date(); start.setHours(0, 0, 0, 0);
  const t0 = start.getTime() - (days - 1) * DAY;
  const buckets = Array.from({ length: days }, (_, i) => ({ d: new Date(t0 + i * DAY), p: 0, n: 0 }));
  for (const r of perDay) {
    const i = Math.round((new Date(r.jour + 'T00:00:00').getTime() - t0) / DAY);
    if (i >= 0 && i < days) buckets[i][r.alert_level === 'prioritaire' ? 'p' : 'n'] += r.n;
  }
  const max = Math.max(3, ...buckets.map(b => b.p + b.n));
  const bw = (W - pl * 2) / days, Y = v => (H - pb - pt) * v / max;
  const bars = buckets.map((b, i) => {
    const x = pl + i * bw + 3, w = bw - 6, hn = Y(b.n), hp = Y(b.p);
    const lab = (days - 1 - i) % 2 === 0 ? `<text class="axis-l" x="${x + w / 2}" y="${H - 6}" text-anchor="middle">${b.d.getDate()}</text>` : '';
    return `<rect x="${x}" y="${H - pb - hn}" width="${w}" height="${hn}" rx="2" style="fill:var(--bar-fees)"><title>${b.n} normales</title></rect><rect x="${x}" y="${H - pb - hn - hp}" width="${w}" height="${hp}" rx="2" style="fill:var(--prio)"><title>${b.p} prioritaires</title></rect>${lab}`;
  }).join('');
  return { svg: `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Alertes par jour sur 14 jours"><line class="grid" x1="0" x2="${W}" y1="${H - pb}" y2="${H - pb}"/>${bars}</svg>
    <div class="chart-legend"><span><span class="sw" style="background:var(--prio)"></span>Prioritaires</span><span><span class="sw" style="background:var(--bar-fees)"></span>Normales</span></div>`, buckets };
}
function renderSuivi() {
  const head = `<div class="page-head"><h1>Suivi</h1><p class="lede">Ce que l’outil a trouvé et ce que vous en avez fait, pour ajuster les seuils après quelques semaines.</p></div>`;
  if (S.statsError) return head + `<div class="note stop">${ICON.stop}<div class="note-body">${esc(S.statsError)}</div></div>`;
  if (!S.stats) { loadStats(); return head + '<p class="muted">Chargement des statistiques…</p>'; }
  const st = S.stats, p = S.cfgUsed.params;
  const by = Object.fromEntries(st.by_status.map(r => [r.statut, r.n]));
  const fbc = Object.fromEntries(st.feedback.map(r => [r.status, r.n]));
  const total = Object.values(by).reduce((a, b) => a + b, 0);
  const { svg, buckets } = dayBars(st.per_day);
  const last7 = buckets.slice(-7), recent = last7.reduce((s, b) => s + b.p + b.n, 0), recentP = last7.reduce((s, b) => s + b.p, 0);
  const nFb = Object.values(fbc).reduce((a, b) => a + b, 0), pos = (fbc.interessant || 0) + (fbc.achete || 0);
  const funnel = [['Annonces reçues', total, ''], ['Passent les filtres', total - (by.exclue || 0), ''], ['Avec une cote', (by.sous_seuil || 0) + (by.alerte || 0), ''], ['Alertes', by.alerte || 0, 'alert'], ['Intéressantes ou achetées', pos, 'gain'], ['Achetées', fbc.achete || 0, 'gain']];
  const fmax = total || 1, mmax = st.motifs.length ? st.motifs[0].n : 1;
  const buys = st.purchases;
  const withPrice = buys.filter(b => b.purchase_price_eur && b.price_eur);
  const avgNego = withPrice.length ? withPrice.reduce((s, b) => s + (b.price_eur - b.purchase_price_eur) / b.price_eur * 100, 0) / withPrice.length : null;
  const buyRows = buys.map(b => {
    const paid = b.purchase_price_eur;
    const m = b.margin_eur == null ? null : paid ? b.margin_eur + (b.price_eur - paid) * (1 + p.taux_frais_pct / 100) : b.margin_eur;
    return `<tr><td><button type="button" class="card-link" style="position:static" data-action="open" data-id="${esc(b.source + ':' + b.listing_id)}">${esc(b.brand || '')} ${esc(b.model || '')} ${b.year ?? ''}</button></td><td>${esc(fmtEur(b.price_eur))}</td><td>${paid ? esc(fmtEur(paid)) : '—'}</td><td>${paid ? esc(fmtPct((b.price_eur - paid) / b.price_eur * 100)) : '—'}</td><td style="color:var(--gain);font-weight:600">${esc(fmtSigned(m))}</td></tr>`;
  }).join('');
  return head + `
  <div class="kpis">
    <div class="kpi"><span class="v">${recent}</span><span class="l">alertes sur 7 jours</span></div>
    <div class="kpi"><span class="v">${recentP}</span><span class="l">dont prioritaires</span></div>
    <div class="kpi"><span class="v">${nFb ? esc(fmtPct(pos / nFb * 100, 0)) : '—'}</span><span class="l">des avis sont positifs</span></div>
    <div class="kpi"><span class="v">${fbc.achete || 0}</span><span class="l">${plural(fbc.achete || 0, 'véhicule acheté', 'véhicules achetés')}</span></div>
  </div>
  <section><h2>Alertes par jour</h2><div class="panel">${svg}</div></section>
  <section><h2>De l’annonce à l’achat</h2><div class="panel funnel">${funnel.map(([t, n, c]) => `<div class="fn-row"><span class="fn-lab">${t}</span><span class="fn-track"><span class="fn-bar ${c}" style="width:${Math.max(.6, n / fmax * 78)}%"></span><span class="fn-val">${fmtNum(n)}<small>${fmtPct(n / fmax * 100, n / fmax < .1 ? 1 : 0)}</small></span></span></div>`).join('')}</div></section>
  <section><h2>Pourquoi les annonces sont écartées</h2><div class="panel funnel">${st.motifs.length ? st.motifs.map(r => `<div class="fn-row"><span class="fn-lab">${esc(MOTIFS[r.motif] || r.motif)}</span><span class="fn-track"><span class="fn-bar" style="width:${Math.max(.6, r.n / mmax * 78)}%;background:var(--stop);opacity:.75"></span><span class="fn-val">${fmtNum(r.n)}</span></span></div>`).join('') : '<p class="muted small" style="margin:0">Aucune annonce écartée pour l’instant.</p>'}
    <p class="small muted" style="margin:6px 0 0">Les annonces de professionnels écartées restent utilisées pour la cote.</p></div></section>
  <section><h2>Achats</h2>${buys.length ? `
    <div class="note${avgNego != null ? ' good' : ''}">${ICON.info}<div class="note-body">${avgNego != null
      ? `<strong>Remise moyenne obtenue : ${esc(fmtPct(avgNego))}</strong> sur ${withPrice.length} ${plural(withPrice.length, 'achat', 'achats')}. C’est un repère pour ajuster la décote de revente, réglée à ${esc(fmtPct(p.decote_negociation_pct))}.`
      : 'Indiquez le prix payé lors du marquage Acheté pour mesurer la négociation obtenue.'}</div></div>
    <div class="panel table-scroll"><table class="buy-table"><thead><tr><th>Véhicule</th><th>Affiché</th><th>Payé</th><th>Remise</th><th>Marge estimée</th></tr></thead><tbody>${buyRows}</tbody></table></div>`
    : empty('Aucun achat enregistré', 'Marquez une opportunité Acheté et indiquez le prix payé : la remise obtenue s’affichera ici.', '<a class="btn btn-ghost" href="#/opportunites">Voir les opportunités</a>')}</section>`;
}
