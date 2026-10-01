/* ============================================================
   Opportunités et fiche détaillée
   ============================================================ */
const FB_LABELS = { interessant: 'Intéressant', pas_interessant: 'Pas intéressant', achete: 'Acheté' };
const FB_ICONS = { interessant: ICON.up, pas_interessant: ICON.x, achete: ICON.key };
const FIAB = {
  fiable: { l: 3, label: 'Cote fiable' },
  moyenne: { l: 2, label: 'Cote moyenne' },
  faible: { l: 1, label: 'Cote peu fiable' },
};
const PERIODS = { 1: 'les dernières 24 heures', 7: 'les 7 derniers jours', 30: 'les 30 derniers jours' };

function motifLabel(ev) {
  if (!ev.motif) return ev.statut === 'sous_seuil' ? 'Sous le seuil' : '';
  if (ev.motif.code === 'mot_cle') return `Mot-clé « ${ev.motif.detail} »`;
  return MOTIFS[ev.motif.code] || ev.motif.code;
}
function signal(fiab) {
  const f = FIAB[fiab];
  return f ? `<span class="signal l${f.l}" aria-hidden="true"><i></i><i></i><i></i></span>` : '';
}
function place(l, ev) {
  const where = l.ville ? `${esc(l.ville)}${l.cp ? ` (${esc(l.cp.slice(0, 2))})` : ''}` : 'Lieu inconnu';
  return ev.distance != null ? `${where}, à ${fmtNum(ev.distance)}${NB}km` : where;
}

function splitBar(l, ev, lg) {
  if (ev.cote == null || ev.marge == null) return '';
  const parts = [['s-buy', l.prix, 'Prix d’achat'], ['s-fees', ev.frais, 'Frais'], ['s-transport', ev.transport, 'Transport'], ['s-nego', ev.decote, 'Décote de revente']];
  const costs = parts.reduce((s, p) => s + p[1], 0);
  const total = Math.max(ev.cote, costs);
  if (ev.marge >= 0) parts.push(['s-gain', ev.marge, 'Marge']);
  const segs = parts.filter(p => p[1] > 0).map(([c, v, t]) => `<span class="${c}" style="flex:${(v / total).toFixed(4)} 1 0" title="${esc(t)} ${esc(fmtEur(v))}"></span>`).join('');
  const label = `Répartition de la cote de ${fmtEur(ev.cote)} : achat ${fmtEur(l.prix)}, frais ${fmtEur(ev.frais)}, transport ${fmtEur(ev.transport)}, décote ${fmtEur(ev.decote)}, marge ${fmtSigned(ev.marge)}.`;
  return `<div class="split${lg ? ' lg' : ''}" role="img" aria-label="${esc(label)}">${segs}</div>`;
}

function fbButtons(id) {
  const cur = Store.feedback[id] && Store.feedback[id].statut;
  return `<div class="fb" role="group" aria-label="Votre avis">${['interessant', 'pas_interessant', 'achete'].map(v =>
    `<button type="button" data-action="fb" data-id="${esc(id)}" data-val="${v}" aria-pressed="${cur === v}">${FB_ICONS[v]}${FB_LABELS[v]}</button>`).join('')}</div>`;
}

function thumb(l, big) {
  if (l.photo) return `<img class="${big ? 'hero-photo' : 'thumb'}" src="${esc(l.photo)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement('div'),{className:'${big ? 'glyph-lg' : 'glyph'}',innerHTML:carSVG({body:'${esc(l.body)}',couleur:'Gris'})}))">`;
  return `<div class="${big ? 'glyph-lg' : 'glyph'}">${carSVG(l)}</div>`;
}

function card(l) {
  const ev = S.evals.get(l.id);
  const fb = Store.feedback[l.id];
  const prio = ev.niveau === 'prioritaire';
  const hasM = ev.cote != null && ev.marge != null;
  const tags = [];
  if (prio) tags.push(`<span class="tag prio">${DIAMOND(13)}Prioritaire</span>`);
  if (l.prevPrice && l.prevPrice > l.prix) tags.push(`<span class="tag drop">${ICON.down}Baisse de ${esc(fmtEur(l.prevPrice - l.prix))}</span>`);
  if (!ev.niveau && ev.statut === 'sous_seuil') tags.push('<span class="tag">Sous le seuil</span>');
  if (ev.statut === 'exclue' || ev.statut === 'sans_cote') tags.push(`<span class="tag stop">${esc(motifLabel(ev))}</span>`);
  if (l.detailIndisponible) tags.push('<span class="tag warn">Description non vérifiée</span>');
  if (l.manual) tags.push('<span class="tag info">Saisie manuelle</span>');
  const kmAnOver = ev.kmAn != null && ev.kmAn > S.cfgUsed.params.km_par_an_max;
  return `<article class="card${prio ? ' prio' : ''}${fb && fb.statut === 'pas_interessant' ? ' dim' : ''}">
    <div class="card-top">
      ${thumb(l)}
      <div>
        <h3 class="card-title"><button type="button" class="card-link" data-action="open" data-id="${esc(l.id)}">${esc(l.marque)} ${esc(l.modele)}</button></h3>
        <div class="card-version">${esc(l.version || '')}</div>
        <div class="card-price">${esc(fmtEur(l.prix))}${l.prevPrice && l.prevPrice > l.prix ? `<s>${esc(fmtEur(l.prevPrice))}</s>` : ''}</div>
      </div>
      <div class="card-margin">${hasM
        ? `<span class="m-val${ev.marge < 0 ? ' neg' : ev.niveau ? '' : ' flat'}">${esc(fmtSigned(ev.marge))}</span><span class="m-lab">marge estimée</span>`
        : '<span class="m-val flat">—</span><span class="m-lab">non évaluable</span>'}</div>
    </div>
    <ul class="specs">
      <li><b>${l.annee ?? '—'}</b></li>
      <li><b>${fmtNum(l.km)}</b> km</li>
      <li${kmAnOver ? ' class="over"' : ''}><b>${fmtNum(ev.kmAn)}</b> km/an</li>
      <li>${esc(l.carburant)}</li><li>${l.boite === 'Automatique' ? 'Auto' : 'Manuelle'}</li>
    </ul>
    ${hasM ? `${splitBar(l, ev)}<div class="split-legend"><span>Achat <b>${esc(fmtEur(l.prix))}</b></span><span>Cote <b>${esc(fmtEur(ev.cote))}</b></span></div>` : ''}
    ${tags.length ? `<div class="tags">${tags.join('')}</div>` : ''}
    <div class="card-foot">
      <span class="it">${ICON.pin}${place(l, ev)}</span>
      ${ev.fiabilite ? `<span class="it">${signal(ev.fiabilite)}${FIAB[ev.fiabilite].label}, ${ev.n} ${plural(ev.n, 'comparable', 'comparables')}</span>` : ''}
      <span class="it">${ICON.clock}${ago(l.first_seen_at)}</span>
    </div>
    ${fbButtons(l.id)}
  </article>`;
}

function feedData() {
  const f = S.feed;
  const todo = [], byFb = { interessant: [], pas_interessant: [], achete: [] };
  for (const l of S.feedItems) {
    const fb = Store.feedback[l.id];
    if (fb && byFb[fb.statut]) { byFb[fb.statut].push(l); continue; }
    const ev = S.evals.get(l.id);
    if (!S.cfgErrors && ev.niveau && l.first_seen_at >= Date.now() - f.period * DAY) todo.push(l);
  }
  const sorters = {
    marge: (a, b) => (S.evals.get(b.id).marge ?? -1e9) - (S.evals.get(a.id).marge ?? -1e9),
    recent: (a, b) => b.first_seen_at - a.first_seen_at,
    distance: (a, b) => (S.evals.get(a.id).distance ?? 1e9) - (S.evals.get(b.id).distance ?? 1e9),
  };
  let items = f.status === 'todo' ? todo : byFb[f.status];
  const prioCount = todo.filter(l => S.evals.get(l.id).niveau === 'prioritaire').length;
  if (f.status === 'todo' && f.prioOnly) items = items.filter(l => S.evals.get(l.id).niveau === 'prioritaire');
  items = [...items].sort(sorters[f.sort] || sorters.marge);
  return { items, todo, byFb, prioCount };
}

function selectChip(action, value, options, label) {
  return `<label class="select-chip"><span class="sr-only">${esc(label)}</span><select data-action="${action}">${options.map(([v, t]) => `<option value="${v}"${String(v) === String(value) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>${ICON.chev}</label>`;
}

function renderFeed() {
  const f = S.feed, p = S.cfgUsed.params;
  const { items, todo, byFb, prioCount } = feedData();
  const notes = [];
  if (S.cfgErrors) {
    const first = !S.cfgMeta;
    notes.push(`<div class="note ${first ? 'warn' : 'stop'}" role="alert">${first ? ICON.sliders : ICON.stop}<div class="note-body"><strong>${first ? 'Enregistrez vos réglages pour démarrer.' : 'Réglages invalides : aucune alerte n’est calculée.'}</strong> ${first ? 'Le job attend une première version, avec au moins le code postal de votre base.' : ''}${first ? '' : `<ul class="err-list">${S.cfgErrors.map(e => `<li>${esc(e)}</li>`).join('')}</ul>`}<div class="note-actions"><a class="btn btn-primary btn-sm" href="#/reglages">Ouvrir les réglages</a></div></div></div>`);
  }
  const tabs = [['todo', 'À traiter', todo.length], ['interessant', 'Intéressantes', byFb.interessant.length], ['achete', 'Achetées', byFb.achete.length], ['pas_interessant', 'Pas intéressantes', byFb.pas_interessant.length]];
  let lede;
  if (f.status === 'todo') {
    lede = todo.length
      ? `${todo.length} ${plural(todo.length, 'annonce', 'annonces')} à traiter sur ${PERIODS[f.period]}, dont ${prioCount} ${plural(prioCount, 'prioritaire', 'prioritaires')}.`
      : `Aucune annonce à traiter sur ${PERIODS[f.period]}.`;
  } else {
    lede = { interessant: 'Les annonces que vous avez marquées intéressantes.', achete: 'Les véhicules que vous avez achetés.', pas_interessant: 'Les annonces écartées. Retirez votre avis pour les remettre à traiter.' }[f.status];
  }
  const toolbar = `<div class="toolbar">
    ${f.status === 'todo' ? `<button type="button" class="chip" data-action="prio" aria-pressed="${f.prioOnly}">${DIAMOND(15)}Prioritaires</button>
    ${selectChip('period', f.period, [[1, '24 heures'], [7, '7 jours'], [30, '30 jours']], 'Période')}` : ''}
    <span class="spacer"></span>
    ${selectChip('sort', f.sort, [['marge', 'Par marge'], ['recent', 'Par date'], ['distance', 'Par distance']], 'Trier')}
  </div>`;
  let list;
  if (items.length) list = items.map(card).join('');
  else if (f.status === 'todo' && f.prioOnly && todo.length) list = empty('Aucune alerte prioritaire', `Désactivez le filtre pour voir ${plural(todo.length, 'l’alerte normale', `les ${todo.length} alertes normales`)}.`, `<button type="button" class="btn btn-ghost" data-action="prio">Voir toutes les alertes</button>`);
  else if (f.status === 'todo') list = empty('Rien à traiter', `Aucune nouvelle annonce ne dépasse ${fmtEur(p.marge_min_eur)} de marge sur ${PERIODS[f.period]}.`, `${f.period < 30 ? '<button type="button" class="btn btn-ghost" data-action="period-30">Voir 30 jours</button>' : ''}<a class="btn btn-ghost" href="#/reglages">Ajuster la marge minimum</a><a class="btn btn-ghost" href="#/evaluer">Évaluer une annonce</a>`);
  else list = empty({ interessant: 'Aucune annonce intéressante', achete: 'Aucun achat enregistré', pas_interessant: 'Aucune annonce écartée' }[f.status],
    { interessant: 'Touchez Intéressant sur une opportunité pour la garder de côté ici.', achete: 'Touchez Acheté sur une opportunité : le prix payé alimente le suivi de la négociation.', pas_interessant: 'Les annonces marquées Pas intéressant apparaîtront ici.' }[f.status],
    '<button type="button" class="btn btn-ghost" data-action="tab" data-tab="todo">Voir les annonces à traiter</button>');
  return `<div class="page-head"><h1>Opportunités</h1><p class="lede">${lede}</p></div>
    ${notes.join('')}
    <div class="tabs" role="tablist" aria-label="Statut">${tabs.map(([k, t, n]) => `<button type="button" role="tab" data-action="tab" data-tab="${k}" aria-selected="${f.status === k}">${t}<span class="count">${n}</span></button>`).join('')}</div>
    ${toolbar}
    <div>${list}</div>`;
}
function empty(title, text, btns) {
  return `<div class="empty"><h3>${esc(title)}</h3><p>${esc(text)}</p><div class="btns">${btns || ''}</div></div>`;
}

/* ---------- Fiche détaillée ---------- */
function openSheet(id) {
  const sheet = $('#sheet'), scrim = $('#scrim');
  const wasOpen = !!S.sheetId;
  S.sheetId = id;
  if (!wasOpen) S.lastFocus = document.activeElement;
  renderSheet();
  if (!S.detail[id]) {
    loadDetail(id).then(() => { if (S.sheetId === id) renderSheet(); }).catch(e => {
      if (S.sheetId !== id) return;
      $('#sheet .sheet-body').innerHTML = `<div class="note stop">${ICON.stop}<div class="note-body"><strong>Annonce introuvable.</strong> ${esc(e.message)}</div></div>`;
    });
  }
  sheet.hidden = false; scrim.hidden = false;
  document.body.style.overflow = 'hidden';
  requestAnimationFrame(() => { sheet.classList.add('open'); scrim.classList.add('open'); });
  if (!wasOpen) setTimeout(() => { const b = $('#sheet [data-action="close-sheet"]'); if (b) b.focus({ preventScroll: true }); }, 60);
  $('#sheet .sheet-body').scrollTop = 0;
}
function closeSheet() {
  if (S.sheetFromApp) { S.sheetFromApp = false; history.back(); }
  else location.hash = '#/' + (S.view || 'opportunites');
}
function closeSheetDom() {
  const sheet = $('#sheet'), scrim = $('#scrim');
  S.sheetId = null;
  sheet.classList.remove('open'); scrim.classList.remove('open');
  document.body.style.overflow = '';
  const done = () => { if (!S.sheetId) { sheet.hidden = true; scrim.hidden = true; } };
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) done(); else setTimeout(done, 320);
  if (S.lastFocus && document.contains(S.lastFocus)) S.lastFocus.focus({ preventScroll: true });
}

function highlight(text, kwList) {
  const ranges = keywordRanges(text, kwList);
  let out = '', pos = 0;
  for (const [a, b] of ranges) {
    if (a < pos) continue;
    out += esc(text.slice(pos, a)) + '<mark>' + esc(text.slice(a, b)) + '</mark>';
    pos = b;
  }
  return out + esc(text.slice(pos));
}

function receipt(l, ev) {
  const p = S.cfgUsed.params;
  const n = ev.n;
  const rows = [
    ['', 'Cote de marché', `médiane de ${n} ${plural(n, 'comparable', 'comparables')}`, fmtEur(ev.cote)],
    ['s-nego', `Décote de revente ${fmtPct(p.decote_negociation_pct)}`, null, '−' + fmtEur(ev.decote)],
    ['sub', 'Prix de revente estimé', null, fmtEur(ev.revente)],
    ['s-buy', 'Prix d’achat', l.prevPrice > l.prix ? `affiché ${fmtEur(l.prevPrice)} auparavant` : 'prix affiché', '−' + fmtEur(l.prix)],
    ['s-fees', `Frais ${fmtPct(p.taux_frais_pct)}`, 'du prix d’achat', '−' + fmtEur(ev.frais)],
    ['s-transport', 'Transport', ev.distance != null ? `${fmtKm(ev.distance)} × ${nf2.format(p.cout_transport_eur_km)}${NB}€/km` : 'base non renseignée', Math.round(ev.transport) ? '−' + fmtEur(ev.transport) : fmtEur(0)],
  ];
  const html = rows.map(([c, k, sub, v]) => `<div class="r${c === 'sub' ? ' sub' : ''}"><span class="k">${c && c !== 'sub' ? `<span class="sw ${c}"></span>` : ''}<span>${esc(k)}${sub ? `<small>${esc(sub)}</small>` : ''}</span></span><span class="v">${esc(v)}</span></div>`).join('');
  let th;
  if (ev.niveau === 'prioritaire') th = `Alerte prioritaire : la marge dépasse ${fmtEur(p.marge_prioritaire_eur)}.`;
  else if (ev.niveau === 'normale') th = `Alerte normale : il manque ${fmtEur(p.marge_prioritaire_eur - ev.marge)} pour passer prioritaire.`;
  else th = `Sous le seuil d’alerte : il manque ${fmtEur(p.marge_min_eur - ev.marge)} pour atteindre ${fmtEur(p.marge_min_eur)}.`;
  return `<div class="receipt">${html}<div class="r total"><span class="k"><span class="sw s-gain"></span>Marge nette estimée</span><span class="v${ev.marge < 0 ? ' neg' : ''}">${esc(fmtSigned(ev.marge))}</span></div></div>
    ${splitBar(l, ev, true)}<p class="threshold">${esc(th)}</p>`;
}

function niceTicks(a, b, n) {
  const span = b - a || 1;
  const step0 = span / n, mag = 10 ** Math.floor(Math.log10(step0)), f = step0 / mag;
  const step = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * mag;
  const out = [];
  for (let v = Math.ceil(a / step) * step; v <= b + 1e-9; v += step) out.push(v);
  return out;
}
function scatter(l, ev) {
  const W = 340, H = 190, pl = 60, pr = 12, pt = 14, pb = 30;
  const pts = ev.comps;
  const xs = pts.map(c => c.km).concat(l.km), ys = pts.map(c => c.prix).concat(l.prix, ev.cote);
  let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const px = (x1 - x0) * .08 || 5000, py = (y1 - y0) * .1 || 800;
  x0 = Math.max(0, x0 - px); x1 += px; y0 = Math.max(0, y0 - py); y1 += py;
  const X = v => pl + (v - x0) / (x1 - x0) * (W - pl - pr);
  const Y = v => pt + (1 - (v - y0) / (y1 - y0)) * (H - pt - pb);
  const xt = niceTicks(x0, x1, 3), yt = niceTicks(y0, y1, 3);
  const grid = yt.map(v => `<line class="grid" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}"/><text class="axis-l" x="${pl - 6}" y="${Y(v) + 4}" text-anchor="end">${nf0.format(v)}${NB}€</text>`).join('')
    + xt.map(v => `<text class="axis-l" x="${X(v)}" y="${H - 10}" text-anchor="middle">${nf0.format(v)}${NB}km</text>`).join('');
  const dots = pts.map(c => `<circle class="dot${c.vendeur === 'pro' ? ' pro' : ''}" cx="${X(c.km).toFixed(1)}" cy="${Y(c.prix).toFixed(1)}" r="4"><title>${c.annee}, ${fmtKm(c.km)}, ${fmtEur(c.prix)}</title></circle>`).join('');
  const my = Y(ev.cote);
  const me = `<rect class="me" x="${X(l.km) - 6}" y="${Y(l.prix) - 6}" width="12" height="12" transform="rotate(45 ${X(l.km)} ${Y(l.prix)})"/>`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Prix des comparables selon le kilométrage, avec la cote et cette annonce">${grid}<line class="med" x1="${pl}" x2="${W - pr}" y1="${my}" y2="${my}"/><text class="med-l" x="${W - pr}" y="${my - 5}" text-anchor="end">Cote ${esc(fmtEur(ev.cote))}</text>${dots}${me}</svg>
    <div class="chart-legend"><span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="4" class="dot" style="fill:var(--bar-fees)"/></svg>Particulier</span><span><svg width="10" height="10" viewBox="0 0 10 10"><circle cx="5" cy="5" r="3.6" style="fill:none;stroke:var(--bar-fees);stroke-width:1.5"/></svg>Professionnel</span><span>${DIAMOND(12)}Cette annonce</span></div>`;
}

function renderSheet() {
  const id = S.sheetId, l = S.byId.get(id);
  if (!l) {
    $('#sheet .sheet-head').innerHTML = `<button type="button" class="icon-btn" data-action="close-sheet" aria-label="Fermer la fiche">${ICON.back}</button>`;
    $('#sheet .sheet-body').innerHTML = '<p class="muted">Chargement de l’annonce…</p>';
    $('#sheet .sheet-foot').innerHTML = '';
    return;
  }
  const detail = S.detail[id];
  const ci = detail && detail.compsInfo;
  const ev = S.evals.get(id), p = S.cfgUsed.params;
  const src = SOURCES[l.source] || 'Saisie manuelle';
  const link = l.url && /^https?:/.test(l.url)
    ? `<a class="btn btn-ghost btn-sm" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${ICON.ext}Voir l’annonce</a>`
    : `<span class="btn btn-ghost btn-sm" aria-disabled="true" title="${l.demo ? 'Les annonces de démonstration n’ont pas de lien' : 'Aucun lien saisi'}">${ICON.ext}Voir l’annonce</span>`;
  $('#sheet .sheet-head').innerHTML = `<button type="button" class="icon-btn" data-action="close-sheet" aria-label="Fermer la fiche">${ICON.back}</button><span class="src">${esc(src)}</span>${link}`;
  const tags = [];
  if (ev.niveau === 'prioritaire') tags.push(`<span class="tag prio">${DIAMOND(13)}Prioritaire</span>`);
  else if (ev.niveau === 'normale') tags.push('<span class="tag">Alerte normale</span>');
  if (l.prevPrice > l.prix) tags.push(`<span class="tag drop">${ICON.down}Baisse de ${esc(fmtEur(l.prevPrice - l.prix))}</span>`);
  tags.push(`<span class="tag">${l.vendeur === 'pro' ? 'Professionnel' : 'Particulier'}</span>`);
  let status = '';
  if (ev.statut === 'exclue') status = `<div class="note stop">${ICON.stop}<div class="note-body"><strong>Exclue : ${esc(motifLabel(ev))}.</strong> ${esc(exclusionHelp(l, ev))}</div></div>`;
  else if (ev.statut === 'sans_cote') status = `<div class="note warn">${ICON.warn}<div class="note-body"><strong>Aucune annonce comparable</strong> sur ${p.fenetre_comparables_jours} jours, même en élargissant à année ±2 et ±40${NB}000${NB}km. La marge ne peut pas être estimée.</div></div>`;
  if (l.detailIndisponible) status += `<div class="note warn">${ICON.warn}<div class="note-body"><strong>Page de l’annonce inaccessible.</strong> L’évaluation utilise les seules données de l’email d’alerte : la description n’a pas été vérifiée.</div></div>`;
  const kmAnOver = ev.kmAn != null && ev.kmAn > p.km_par_an_max;
  const comps = [...ev.comps].sort((a, b) => Math.abs(a.km - l.km) - Math.abs(b.km - l.km));
  const fb = Store.feedback[id];
  const body = `
    <div class="d-hero">
      <div class="hero-media">${thumb(l, true)}</div>
      <div><h2 class="d-title" id="sheet-title">${esc(l.marque)} ${esc(l.modele)}</h2><div class="d-version">${esc(l.version || '')}</div></div>
      <div class="d-price"><span class="p">${esc(fmtEur(l.prix))}</span>${l.prevPrice > l.prix ? `<s>${esc(fmtEur(l.prevPrice))}</s>` : ''}</div>
    </div>
    <div class="tags">${tags.join('')}</div>
    ${fb && fb.statut === 'achete' ? `<div class="note good" style="margin-top:14px">${ICON.key}<div class="note-body"><strong>Achetée${fb.prix_achat ? ` ${esc(fmtEur(fb.prix_achat))}` : ''}.</strong>${fb.prix_achat ? ` Remise obtenue : ${esc(fmtEur(l.prix - fb.prix_achat))}.` : ''}</div></div>` : ''}
    <div style="margin-top:14px">${status}</div>
    ${ev.cote != null && ev.marge != null ? `<section><h2>Marge estimée</h2>${receipt(l, ev)}</section>` : ''}
    ${!detail && ev.n ? '<section><h2>Comparables</h2><p class="muted">Chargement des comparables…</p></section>' : ''}
    ${ev.comps.length && ci && ci.fiabilite ? `<section><h2>Comparables</h2><div class="panel">
      <p class="small" style="margin:0 0 10px;display:flex;gap:8px;align-items:flex-start">${signal(ci.fiabilite)}<span><strong>Marché actuel : ${FIAB[ci.fiabilite].label.toLowerCase()}.</strong> ${esc(fiabText(ci))}</span></p>
      ${ev.cote != null && (ci.n !== ev.n || Math.round(ci.cote) !== Math.round(ev.cote)) ? `<p class="small muted" style="margin:-4px 0 10px">L’évaluation a retenu une cote de ${esc(fmtEur(ev.cote))} sur ${ev.n} ${plural(ev.n, 'comparable', 'comparables')}. Le marché a évolué depuis : cote actuelle ${esc(fmtEur(ci.cote))}.</p>` : ''}
      ${scatter(l, { comps: ev.comps, cote: ci.cote })}
      <table class="comp-table"><thead><tr><th>Année</th><th>Kilométrage</th><th class="r">Prix</th><th>Vendeur</th></tr></thead><tbody>
      ${comps.slice(0, 8).map(c => `<tr><td>${c.annee}</td><td>${fmtNum(c.km)}</td><td class="r">${esc(fmtEur(c.prix))}</td><td class="t">${c.vendeur === 'pro' ? 'Pro' : 'Particulier'}, ${esc(c.ville)}</td></tr>`).join('')}
      </tbody></table>${comps.length > 8 ? `<p class="small muted" style="margin:8px 0 0">Et ${comps.length - 8} ${plural(comps.length - 8, 'autre', 'autres')}.</p>` : ''}
    </div></section>` : ''}
    <section><h2>Caractéristiques</h2><dl class="specs-grid">
      ${[['Année', l.annee ?? '—'], ['Kilométrage', fmtKm(l.km)], ['Kilomètres par an', `<span${kmAnOver ? ' style="color:var(--stop)"' : ''}>${fmtKm(ev.kmAn)}</span>`], ['Carburant', esc(l.carburant)], ['Boîte', esc(l.boite)], ['Couleur', esc(l.couleur || '—')],
        ['Localisation', `${esc(l.ville || '—')} ${esc(l.cp || '')}`], ['Distance de la base', ev.distance != null ? `${fmtKm(ev.distance)} par la route` : (p.base_code_postal ? 'Lieu inconnu' : 'Base non renseignée')],
        ['Première vue', esc(dtf.format(l.first_seen_at))], ['Dernière vue', esc(dtf.format(l.last_seen_at))]].map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`).join('')}
    </dl></section>
    <section><h2>Description</h2>${detail ? (detail.description ? `<p class="desc">${highlight(detail.description, S.ctx.kwList)}</p>` : '<p class="muted">Description non disponible.</p>') : '<p class="muted">Chargement…</p>'}</section>
    <p class="meta">${ev.evaluatedAt ? `Évaluée le ${esc(dtf.format(ev.evaluatedAt))} avec la version ${esc(ev.configVersion || '')} des réglages.` : 'Pas encore évaluée.'}</p>`;
  $('#sheet .sheet-body').innerHTML = body;
  $('#sheet .sheet-foot').innerHTML = fbButtons(id);
}
function fiabText(ev) {
  const p = S.cfgUsed.params, n = ev.n;
  if (ev.fiabilite === 'fiable') return `${n} annonces du même modèle, carburant et boîte, année ±1 et ±20${NB}000${NB}km, vues sur ${p.fenetre_comparables_jours} jours.`;
  if (ev.fiabilite === 'moyenne') return `Critères élargis à année ±2 et ±40${NB}000${NB}km pour réunir ${n} comparables.`;
  return `Seulement ${n} ${plural(n, 'comparable', 'comparables')}, même après élargissement. Vérifiez la cote avant d’appeler.`;
}
function exclusionHelp(l, ev) {
  const p = S.cfgUsed.params;
  switch (ev.motif.code) {
    case 'prix_hors_bornes': return `Le prix sort de la fourchette ${fmtEur(p.prix_min_eur)} à ${fmtEur(p.prix_max_eur)}.`;
    case 'vendeur_pro': return 'Seuls les particuliers sont alertés. L’annonce sert quand même à calculer la cote des autres.';
    case 'km_max': return `Le kilométrage dépasse ${fmtKm(p.km_max)}.`;
    case 'km_par_an': return `${fmtKm(ev.kmAn)} par an, au-delà du maximum de ${fmtKm(p.km_par_an_max)}.`;
    case 'mot_cle': return 'Le mot-clé est surligné dans la description. S’il s’agit d’une fausse alerte, retirez-le des réglages.';
    case 'donnees_incompletes': return 'Le prix, l’année ou le kilométrage manque : l’annonce ne peut pas être évaluée.';
    default: return '';
  }
}
