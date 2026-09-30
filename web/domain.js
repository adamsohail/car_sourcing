/* ============================================================
   Utilitaires côté navigateur : formats, géographie, libellés des réglages
   ============================================================ */
const DAY = 86400000;
const NOW = Date.now();
const YEAR = new Date(NOW).getFullYear();

const _nf0 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 0 });
// Espace insécable standard : l'espace fine est presque invisible dans certaines polices
const nf0 = { format: v => _nf0.format(v).replace(/\u202f/g, '\u00a0') };
const nf1 = new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const NB = '\u00a0';

function fmtEur(v) { return v == null || !isFinite(v) ? '—' : nf0.format(Math.round(v)) + NB + '€'; }
function fmtSigned(v) {
  if (v == null || !isFinite(v)) return '—';
  const r = Math.round(v);
  return (r > 0 ? '+' : r < 0 ? '−' : '') + nf0.format(Math.abs(r)) + NB + '€';
}
function fmtNum(v) { return v == null || !isFinite(v) ? '—' : nf0.format(Math.round(v)); }
function fmtKm(v) { return v == null || !isFinite(v) ? '—' : nf0.format(Math.round(v)) + NB + 'km'; }
function fmtPct(v, d = 1) { return v == null || !isFinite(v) ? '—' : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: d }).format(v) + NB + '%'; }

function strip(s) { return String(s ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
function median(a) {
  if (!a.length) return null;
  const s = [...a].sort((x, y) => x - y);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}
function haversine(a, b) {
  const R = 6371, rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad, dLon = (b.lon - a.lon) * rad;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function mulberry32(seed) {
  return function () {
    seed |= 0; seed = seed + 0x6D2B79F5 | 0;
    let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function pickW(rng, entries) {
  const tot = entries.reduce((s, e) => s + e[1], 0);
  let r = rng() * tot;
  for (const e of entries) { r -= e[1]; if (r <= 0) return e[0]; }
  return entries[entries.length - 1][0];
}
function normal(rng, mu, sd) {
  const u = 1 - rng(), v = rng();
  return mu + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}
function parseNumberFr(s) {
  if (typeof s === 'number') return s;
  const t = String(s ?? '').trim().replace(/[\s\u00a0\u202f]/g, '').replace(',', '.');
  if (!/^-?\d+(\.\d+)?$/.test(t)) return NaN;
  return parseFloat(t);
}

/* ---------- Géographie (remplace l'API Adresse côté interface) ---------- */
// Préfecture de chaque département : [lat, lon, ville]
const DEPTS = {
  '01': [46.205, 5.225, 'Bourg-en-Bresse'], '02': [49.564, 3.620, 'Laon'], '03': [46.566, 3.333, 'Moulins'],
  '04': [44.092, 6.236, 'Digne-les-Bains'], '05': [44.559, 6.079, 'Gap'], '06': [43.703, 7.266, 'Nice'],
  '07': [44.735, 4.599, 'Privas'], '08': [49.773, 4.720, 'Charleville-Mézières'], '09': [42.965, 1.607, 'Foix'],
  '10': [48.297, 4.074, 'Troyes'], '11': [43.212, 2.353, 'Carcassonne'], '12': [44.350, 2.575, 'Rodez'],
  '13': [43.296, 5.370, 'Marseille'], '14': [49.183, -0.371, 'Caen'], '15': [44.926, 2.440, 'Aurillac'],
  '16': [45.648, 0.156, 'Angoulême'], '17': [46.160, -1.151, 'La Rochelle'], '18': [47.081, 2.399, 'Bourges'],
  '19': [45.267, 1.771, 'Tulle'], '2A': [41.919, 8.738, 'Ajaccio'], '2B': [42.697, 9.450, 'Bastia'],
  '21': [47.322, 5.041, 'Dijon'], '22': [48.514, -2.765, 'Saint-Brieuc'], '23': [46.171, 1.871, 'Guéret'],
  '24': [45.184, 0.721, 'Périgueux'], '25': [47.238, 6.024, 'Besançon'], '26': [44.933, 4.892, 'Valence'],
  '27': [49.024, 1.151, 'Évreux'], '28': [48.446, 1.489, 'Chartres'], '29': [47.996, -4.102, 'Quimper'],
  '30': [43.837, 4.360, 'Nîmes'], '31': [43.605, 1.444, 'Toulouse'], '32': [43.646, 0.586, 'Auch'],
  '33': [44.838, -0.579, 'Bordeaux'], '34': [43.611, 3.877, 'Montpellier'], '35': [48.117, -1.678, 'Rennes'],
  '36': [46.811, 1.691, 'Châteauroux'], '37': [47.394, 0.685, 'Tours'], '38': [45.188, 5.724, 'Grenoble'],
  '39': [46.675, 5.555, 'Lons-le-Saunier'], '40': [43.890, -0.500, 'Mont-de-Marsan'], '41': [47.586, 1.336, 'Blois'],
  '42': [45.440, 4.387, 'Saint-Étienne'], '43': [45.043, 3.885, 'Le Puy-en-Velay'], '44': [47.218, -1.554, 'Nantes'],
  '45': [47.903, 1.909, 'Orléans'], '46': [44.448, 1.441, 'Cahors'], '47': [44.203, 0.616, 'Agen'],
  '48': [44.518, 3.500, 'Mende'], '49': [47.478, -0.563, 'Angers'], '50': [49.116, -1.090, 'Saint-Lô'],
  '51': [48.957, 4.365, 'Châlons-en-Champagne'], '52': [48.111, 5.139, 'Chaumont'], '53': [48.073, -0.770, 'Laval'],
  '54': [48.692, 6.184, 'Nancy'], '55': [48.772, 5.160, 'Bar-le-Duc'], '56': [47.658, -2.760, 'Vannes'],
  '57': [49.120, 6.176, 'Metz'], '58': [46.990, 3.159, 'Nevers'], '59': [50.629, 3.057, 'Lille'],
  '60': [49.430, 2.081, 'Beauvais'], '61': [48.432, 0.091, 'Alençon'], '62': [50.291, 2.777, 'Arras'],
  '63': [45.778, 3.087, 'Clermont-Ferrand'], '64': [43.295, -0.370, 'Pau'], '65': [43.233, 0.078, 'Tarbes'],
  '66': [42.699, 2.895, 'Perpignan'], '67': [48.573, 7.752, 'Strasbourg'], '68': [48.079, 7.358, 'Colmar'],
  '69': [45.764, 4.836, 'Lyon'], '70': [47.619, 6.155, 'Vesoul'], '71': [46.307, 4.828, 'Mâcon'],
  '72': [48.006, 0.199, 'Le Mans'], '73': [45.564, 5.918, 'Chambéry'], '74': [45.899, 6.129, 'Annecy'],
  '75': [48.857, 2.352, 'Paris'], '76': [49.443, 1.099, 'Rouen'], '77': [48.540, 2.660, 'Melun'],
  '78': [48.804, 2.130, 'Versailles'], '79': [46.323, -0.465, 'Niort'], '80': [49.894, 2.296, 'Amiens'],
  '81': [43.929, 2.148, 'Albi'], '82': [44.018, 1.355, 'Montauban'], '83': [43.124, 5.928, 'Toulon'],
  '84': [43.949, 4.806, 'Avignon'], '85': [46.670, -1.426, 'La Roche-sur-Yon'], '86': [46.580, 0.340, 'Poitiers'],
  '87': [45.834, 1.261, 'Limoges'], '88': [48.172, 6.449, 'Épinal'], '89': [47.798, 3.567, 'Auxerre'],
  '90': [47.638, 6.863, 'Belfort'], '91': [48.629, 2.441, 'Évry'], '92': [48.892, 2.207, 'Nanterre'],
  '93': [48.908, 2.440, 'Bobigny'], '94': [48.790, 2.455, 'Créteil'], '95': [49.036, 2.063, 'Cergy'],
};
// [ville, code postal, lat, lon, poids dans les données de démo]
const CITIES = [
  ['Paris', '75011', 48.859, 2.379, 10], ['Marseille', '13005', 43.293, 5.395, 6], ['Lyon', '69003', 45.759, 4.861, 6],
  ['Toulouse', '31000', 43.605, 1.444, 5], ['Nice', '06000', 43.703, 7.266, 3], ['Nantes', '44000', 47.218, -1.554, 4],
  ['Montpellier', '34000', 43.611, 3.877, 3], ['Strasbourg', '67000', 48.573, 7.752, 3], ['Bordeaux', '33000', 44.838, -0.579, 4],
  ['Lille', '59000', 50.629, 3.057, 4], ['Rennes', '35000', 48.117, -1.678, 3], ['Reims', '51100', 49.258, 4.032, 2],
  ['Toulon', '83000', 43.124, 5.928, 2], ['Saint-Étienne', '42000', 45.440, 4.387, 2], ['Le Havre', '76600', 49.494, 0.107, 2],
  ['Grenoble', '38000', 45.188, 5.724, 2], ['Dijon', '21000', 47.322, 5.041, 2], ['Angers', '49000', 47.478, -0.563, 2],
  ['Nîmes', '30000', 43.837, 4.360, 2], ['Clermont-Ferrand', '63000', 45.778, 3.087, 2], ['Le Mans', '72000', 48.006, 0.199, 2],
  ['Aix-en-Provence', '13100', 43.529, 5.447, 2], ['Brest', '29200', 48.390, -4.486, 2], ['Tours', '37000', 47.394, 0.685, 2],
  ['Amiens', '80000', 49.894, 2.296, 2], ['Limoges', '87000', 45.834, 1.261, 1.5], ['Perpignan', '66000', 42.699, 2.895, 1.5],
  ['Metz', '57000', 49.120, 6.176, 1.5], ['Besançon', '25000', 47.238, 6.024, 1.5], ['Orléans', '45000', 47.903, 1.909, 1.5],
  ['Rouen', '76000', 49.443, 1.099, 1.5], ['Mulhouse', '68100', 47.750, 7.336, 1.5], ['Caen', '14000', 49.183, -0.371, 1.5],
  ['Nancy', '54000', 48.692, 6.184, 1.5], ['Argenteuil', '95100', 48.947, 2.248, 1.5], ['Montreuil', '93100', 48.861, 2.443, 1.5],
  ['Avignon', '84000', 43.949, 4.806, 1], ['Poitiers', '86000', 46.580, 0.340, 1], ['Pau', '64000', 43.295, -0.370, 1],
  ['La Rochelle', '17000', 46.160, -1.151, 1], ['Valence', '26000', 44.933, 4.892, 1], ['Troyes', '10000', 48.297, 4.074, 1],
  ['Chambéry', '73000', 45.564, 5.918, 1], ['Annecy', '74000', 45.899, 6.129, 1], ['Béziers', '34500', 43.344, 3.215, 1],
  ['Bayonne', '64100', 43.493, -1.475, 1], ['Vannes', '56000', 47.658, -2.760, 1], ['Quimper', '29000', 47.996, -4.102, 1],
  ['Chartres', '28000', 48.446, 1.489, 1], ['Bourges', '18000', 47.081, 2.399, 1], ['Colmar', '68000', 48.079, 7.358, 1],
  ['Niort', '79000', 46.323, -0.465, 1], ['Ajaccio', '20000', 41.919, 8.738, 0.4], ['Évreux', '27000', 49.024, 1.151, 1],
  ['Saint-Brieuc', '22000', 48.514, -2.765, 1], ['Périgueux', '24000', 45.184, 0.721, 1], ['Agen', '47000', 44.203, 0.616, 0.8],
  ['Carcassonne', '11000', 43.212, 2.353, 0.8], ['Auxerre', '89000', 47.798, 3.567, 0.8], ['Charleville-Mézières', '08000', 49.773, 4.720, 0.7],
];
function deptOf(cp) {
  if (!/^\d{5}$/.test(cp)) return null;
  let d = cp.slice(0, 2);
  if (d === '20') d = (+cp < 20200) ? '2A' : '2B';
  return d;
}
function geocode(cp, ville) {
  cp = String(cp ?? '').trim();
  const v = ville ? strip(ville).trim() : '';
  const exact = CITIES.find(c => c[1] === cp) || (v && CITIES.find(c => strip(c[0]) === v && deptOf(c[1]) === deptOf(cp)));
  if (exact) return { lat: exact[2], lon: exact[3], approx: false, label: exact[0] };
  const d = deptOf(cp);
  if (d && DEPTS[d]) return { lat: DEPTS[d][0], lon: DEPTS[d][1], approx: true, label: DEPTS[d][2] };
  return null;
}

const DEFAULT_PARAMS = {
  prix_min_eur: 2000, prix_max_eur: 30000, km_max: 200000, km_par_an_max: 20000,
  vendeur_particulier_uniquement: true, taux_frais_pct: 10, decote_negociation_pct: 6,
  cout_transport_eur_km: 0.30, base_code_postal: '', marge_min_eur: 1000, marge_prioritaire_eur: 2000,
  comparables_min: 5, fenetre_comparables_jours: 90, regime_fiscal: 'particulier',
};
const DEFAULT_KEYWORDS = ['accidenté', 'pour pièces', 'moteur HS', 'non roulant', 'sans CT', 'épave', 'sinistré', 'VEI', 'boîte HS', 'joint de culasse'];

const PARAM_GROUPS = [
  { id: 'filtres', title: 'Filtres des annonces', intro: 'Une annonce qui ne passe pas un filtre est enregistrée mais jamais alertée.', keys: ['prix_min_eur', 'prix_max_eur', 'km_max', 'km_par_an_max', 'vendeur_particulier_uniquement'] },
  { id: 'marge', title: 'Calcul de la marge', intro: 'Marge = cote après décote − prix − frais − transport.', keys: ['taux_frais_pct', 'decote_negociation_pct', 'cout_transport_eur_km', 'base_code_postal', 'regime_fiscal'] },
  { id: 'alertes', title: 'Seuils d’alerte', intro: null, keys: ['marge_min_eur', 'marge_prioritaire_eur'] },
  { id: 'cote', title: 'Cote de marché', intro: 'La cote est la médiane des prix des annonces comparables : même marque, modèle, carburant et boîte, année ±1 et ±20 000 km.', keys: ['comparables_min', 'fenetre_comparables_jours'] },
];
const PARAM_META = {
  prix_min_eur: { label: 'Prix minimum', unit: '€', kind: 'int', min: 0, max: 1000000 },
  prix_max_eur: { label: 'Prix maximum', unit: '€', kind: 'int', min: 1, max: 1000000 },
  km_max: { label: 'Kilométrage maximum', unit: 'km', kind: 'int', min: 1, max: 1000000 },
  km_par_an_max: { label: 'Kilomètres par an maximum', unit: 'km/an', kind: 'int', min: 1, max: 200000, help: 'Calculé avec un âge minimum d’un an pour les véhicules récents.' },
  vendeur_particulier_uniquement: { label: 'Particuliers uniquement', kind: 'bool', help: 'Les annonces de professionnels restent utilisées pour calculer la cote.' },
  taux_frais_pct: { label: 'Frais par véhicule', unit: '% du prix', kind: 'dec', min: 0, max: 100, help: 'Remise en état, contrôle technique, carte grise : en pourcentage du prix d’achat.' },
  decote_negociation_pct: { label: 'Décote de revente', unit: '%', kind: 'dec', min: 0, max: 100, help: 'Écart attendu entre le prix affiché des comparables et le prix de vente réel.' },
  cout_transport_eur_km: { label: 'Coût du transport', unit: '€/km', kind: 'dec', min: 0, max: 10, help: 'Appliqué à la distance routière estimée (vol d’oiseau × 1,3).' },
  base_code_postal: { label: 'Code postal de la base', kind: 'cp', help: 'Point d’arrivée des véhicules achetés.' },
  regime_fiscal: { label: 'Régime fiscal', kind: 'select', options: [{ value: 'particulier', label: 'Particulier, sans TVA' }, { value: 'pro_tva_marge', label: 'Professionnel, TVA sur marge (bientôt)', disabled: true }] },
  marge_min_eur: { label: 'Marge minimum pour alerter', unit: '€', kind: 'int', min: 0, max: 100000 },
  marge_prioritaire_eur: { label: 'Marge d’une alerte prioritaire', unit: '€', kind: 'int', min: 0, max: 100000 },
  comparables_min: { label: 'Comparables minimum', unit: 'annonces', kind: 'int', min: 1, max: 100, help: 'En dessous, les critères sont élargis une fois : année ±2 et ±40 000 km.' },
  fenetre_comparables_jours: { label: 'Période des comparables', unit: 'jours', kind: 'int', min: 7, max: 365 },
};

const MOTIFS = {
  prix_hors_bornes: 'Prix hors fourchette',
  vendeur_pro: 'Vendeur professionnel',
  km_max: 'Kilométrage trop élevé',
  km_par_an: 'Trop de kilomètres par an',
  mot_cle: 'Mot-clé d’exclusion',
  donnees_incompletes: 'Données incomplètes',
  cote_indisponible: 'Aucun comparable',
};

function kwRegex(kw) {
  const k = strip(kw).trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  return new RegExp('(^|[^\\p{L}\\p{N}])(' + k + ')(?=$|[^\\p{L}\\p{N}])', 'u');
}
// Texte normalisé + table de correspondance vers l'original (pour surligner)
function normMap(text) {
  let out = ''; const map = [];
  for (let i = 0; i < text.length; i++) {
    const n = strip(text[i]);
    for (const ch of n) { out += ch; map.push(i); }
  }
  return { out, map };
}

function keywordRanges(text, kwList) {
  const { out, map } = normMap(text);
  const ranges = [];
  for (const { re } of kwList) {
    const g = new RegExp(re.source, 'gu');
    let m;
    while ((m = g.exec(out))) {
      const start = m.index + m[1].length, end = start + m[2].length;
      ranges.push([map[start], map[end - 1] + 1]);
      g.lastIndex = end;
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  return ranges;
}

const MODELS = [
  { marque: 'Renault', modele: 'Clio', body: 'citadine', base: 19500, dep: .11, w: 10, auto: .1, v: { Essence: ['1.0 TCe 90 Zen', '0.9 TCe 75 Limited', '1.2 16V 75 Trend'], Diesel: ['1.5 dCi 90 Business', '1.5 Blue dCi 85 Intens'], Hybride: ['E-Tech 140 Intens'] }, f: { Essence: .6, Diesel: .33, Hybride: .07 } },
  { marque: 'Peugeot', modele: '208', body: 'citadine', base: 20000, dep: .11, w: 10, auto: .15, v: { Essence: ['1.2 PureTech 100 Allure', '1.2 PureTech 82 Like', '1.2 PureTech 75 Active'], Diesel: ['1.5 BlueHDi 100 Active', '1.6 BlueHDi 75 Access'], 'Électrique': ['e-208 136 GT'] }, f: { Essence: .64, Diesel: .3, 'Électrique': .06 } },
  { marque: 'Peugeot', modele: '308', body: 'compacte', base: 27000, dep: .12, w: 7, auto: .3, v: { Essence: ['1.2 PureTech 130 Allure', '1.2 PureTech 110 Active'], Diesel: ['1.5 BlueHDi 130 GT Line', '1.6 BlueHDi 120 Allure'] }, f: { Essence: .5, Diesel: .5 } },
  { marque: 'Peugeot', modele: '3008', body: 'suv', base: 33000, dep: .12, w: 6, auto: .4, v: { Diesel: ['1.5 BlueHDi 130 Allure', '2.0 BlueHDi 180 GT'], Essence: ['1.2 PureTech 130 GT Line'], Hybride: ['Hybrid 225 GT'] }, f: { Diesel: .6, Essence: .34, Hybride: .06 } },
  { marque: 'Volkswagen', modele: 'Golf', body: 'compacte', base: 28000, dep: .11, w: 7, auto: .3, v: { Essence: ['1.0 TSI 110 Life', '1.5 TSI 130 Style', 'GTI 245'], Diesel: ['2.0 TDI 150 Style', '1.6 TDI 115 Confortline'] }, f: { Essence: .5, Diesel: .5 } },
  { marque: 'Volkswagen', modele: 'Polo', body: 'citadine', base: 20000, dep: .11, w: 6, auto: .15, v: { Essence: ['1.0 TSI 95 Life', '1.0 MPI 80 Trendline'], Diesel: ['1.6 TDI 95 Confortline'] }, f: { Essence: .72, Diesel: .28 } },
  { marque: 'Toyota', modele: 'Yaris', body: 'citadine', base: 21000, dep: .09, w: 6, auto: .5, v: { Hybride: ['Hybride 116h Design', 'Hybride 100h Dynamic'], Essence: ['1.0 VVT-i 72 France', '1.5 VVT-i 125 Collection'] }, f: { Hybride: .75, Essence: .25 } },
  { marque: 'Dacia', modele: 'Sandero', body: 'citadine', base: 14000, dep: .10, w: 7, auto: .03, v: { Essence: ['TCe 90 Stepway', 'SCe 75 Essentiel'], GPL: ['ECO-G 100 Confort', 'TCe 100 Bi-Fuel Stepway'], Diesel: ['dCi 75 Ambiance'] }, f: { Essence: .6, GPL: .3, Diesel: .1 } },
  { marque: 'Citroën', modele: 'C3', body: 'citadine', base: 18000, dep: .12, w: 6, auto: .08, v: { Essence: ['PureTech 83 Feel', 'PureTech 110 Shine'], Diesel: ['BlueHDi 100 Shine', 'BlueHDi 75 Feel'] }, f: { Essence: .6, Diesel: .4 } },
  { marque: 'Renault', modele: 'Captur', body: 'suv', base: 24000, dep: .11, w: 6, auto: .25, v: { Essence: ['TCe 90 Zen', 'TCe 130 Intens'], Diesel: ['dCi 90 Business', 'Blue dCi 115 Intens'], Hybride: ['E-Tech 145 Techno'] }, f: { Essence: .58, Diesel: .32, Hybride: .1 } },
  { marque: 'Renault', modele: 'Mégane', body: 'compacte', base: 26000, dep: .13, w: 5, auto: .25, v: { Diesel: ['1.5 dCi 110 Intens', '1.5 Blue dCi 115 Business'], Essence: ['1.3 TCe 140 Zen', '1.2 TCe 130 Bose'] }, f: { Diesel: .55, Essence: .45 } },
  { marque: 'Renault', modele: 'Zoe', body: 'citadine', base: 30000, dep: .16, w: 3, v: { 'Électrique': ['R110 Zen', 'R135 Intens', 'Life R90'] }, f: { 'Électrique': 1 } },
  { marque: 'Ford', modele: 'Fiesta', body: 'citadine', base: 18000, dep: .13, w: 4, auto: .1, v: { Essence: ['1.0 EcoBoost 100 Titanium', '1.1 75 Trend'], Diesel: ['1.5 TDCi 85 Business'] }, f: { Essence: .7, Diesel: .3 } },
  { marque: 'Opel', modele: 'Corsa', body: 'citadine', base: 18500, dep: .13, w: 4, auto: .1, v: { Essence: ['1.2 75 Edition', '1.2 Turbo 100 Elegance'], Diesel: ['1.5 D 100 GS Line'] }, f: { Essence: .7, Diesel: .3 } },
  { marque: 'Skoda', modele: 'Octavia', body: 'berline', base: 28000, dep: .11, w: 4, auto: .45, v: { Diesel: ['2.0 TDI 150 Style', '1.6 TDI 115 Ambition'], Essence: ['1.5 TSI 150 Business'] }, f: { Diesel: .6, Essence: .4 } },
  { marque: 'BMW', modele: 'Série 1', body: 'compacte', base: 32000, dep: .12, w: 4, auto: .6, v: { Diesel: ['116d Lounge', '118d Business Design'], Essence: ['118i M Sport', '116i Edition'] }, f: { Diesel: .55, Essence: .45 } },
  { marque: 'Audi', modele: 'A3', body: 'compacte', base: 33000, dep: .11, w: 4, auto: .55, v: { Diesel: ['30 TDI 116 Design', '1.6 TDI 110 Ambiente'], Essence: ['35 TFSI 150 S line', '1.0 TFSI 116 Sport'] }, f: { Diesel: .55, Essence: .45 } },
  { marque: 'Mercedes-Benz', modele: 'Classe A', body: 'compacte', base: 35000, dep: .12, w: 3, auto: .7, v: { Diesel: ['180 d Progressive', '180 d Business Line'], Essence: ['200 AMG Line', '160 Intuition'] }, f: { Diesel: .5, Essence: .5 } },
  { marque: 'Tesla', modele: 'Model 3', body: 'berline', base: 48000, dep: .13, w: 2, yearMin: 2019, v: { 'Électrique': ['Standard Plus', 'Grande Autonomie AWD', 'Propulsion'] }, f: { 'Électrique': 1 } },
  { marque: 'Dacia', modele: 'Duster', body: 'suv', base: 20000, dep: .10, w: 4, auto: .05, v: { Diesel: ['dCi 115 4x2 Prestige', 'Blue dCi 115 Journey'], Essence: ['TCe 130 Journey'], GPL: ['ECO-G 100 Confort'] }, f: { Diesel: .5, Essence: .3, GPL: .2 } },
  { marque: 'Fiat', modele: '500', body: 'citadine', base: 16500, dep: .12, w: 4, auto: .1, v: { Essence: ['1.2 69 Lounge', '0.9 TwinAir Pop'], Hybride: ['1.0 Hybrid Dolcevita'] }, f: { Essence: .88, Hybride: .12 } },
  { marque: 'Toyota', modele: 'C-HR', body: 'suv', base: 31000, dep: .10, w: 3, yearMin: 2017, v: { Hybride: ['122h Distinctive', '184h GR Sport', '122h Dynamic'] }, f: { Hybride: 1 } },
  { marque: 'Renault', modele: 'Kangoo', body: 'utilitaire', base: 23000, dep: .10, w: 3, auto: .02, v: { Diesel: ['1.5 dCi 90 Grand Confort', 'Blue dCi 95 Extra'], 'Électrique': ['Z.E. 33 Grand Confort'] }, f: { Diesel: .9, 'Électrique': .1 } },
  { marque: 'Peugeot', modele: 'Partner', body: 'utilitaire', base: 23000, dep: .11, w: 2, auto: .02, v: { Diesel: ['1.6 BlueHDi 100 Premium', '1.5 BlueHDi 100 Asphalt'] }, f: { Diesel: 1 } },
  { marque: 'Kia', modele: 'Sportage', body: 'suv', base: 31000, dep: .11, w: 3, auto: .4, v: { Diesel: ['1.6 CRDi 136 Active', '1.7 CRDi 115 Motion'], Essence: ['1.6 T-GDi 150 Design'], Hybride: ['1.6 T-GDi 230 HEV GT-Line'] }, f: { Diesel: .5, Essence: .3, Hybride: .2 } },
  { marque: 'Mini', modele: 'Cooper', body: 'citadine', base: 26000, dep: .10, w: 1, auto: .4, v: { Essence: ['136 ch Edition', 'S 178 ch Chili'], Diesel: ['D 116 ch Business'] }, f: { Essence: .8, Diesel: .2 } },
  { marque: 'Alfa Romeo', modele: 'Giulietta', body: 'compacte', base: 28000, dep: .14, w: .6, auto: .3, yearMax: 2020, v: { Diesel: ['2.0 JTDm 150 Super'], Essence: ['1.4 TB 120 Distinctive'] }, f: { Diesel: .6, Essence: .4 } },
];

function bodyFor(marque, modele) {
  const m = MODELS.find(x => strip(x.marque) === strip(marque).trim() && strip(x.modele) === strip(modele).trim());
  return m ? m.body : 'compacte';
}

function defaultConfig() {
  return { params: { ...DEFAULT_PARAMS }, keywords: [...DEFAULT_KEYWORDS], version: '—' };
}
function kwList(keywords) { return keywords.map(kw => ({ kw, re: kwRegex(kw) })); }
