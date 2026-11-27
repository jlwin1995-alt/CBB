"use strict";
const $ = (s, r = document) => r.querySelector(s);
const ET = "America/New_York";
const fmtT = iso => new Date(iso).toLocaleString("en-US", {timeZone: ET, weekday: "short", hour: "numeric", minute: "2-digit"}) + " ET";
const pct = x => x == null ? "–" : (100 * x).toFixed(1) + "%";
const n1 = x => x == null ? "–" : (Math.round(x * 10) / 10).toString();
const signed = x => x == null ? "–" : (x > 0 ? "+" : "") + (Math.round(x * 10) / 10);
function wilson(k, n) { if (!n) return [0, 1]; const z = 1.96, p = k / n, d = 1 + z * z / n, c = p + z * z / (2 * n), m = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return [(c - m) / d, (c + m) / d]; }
const rate = o => !o || !o.n ? "–" : `${pct(o.hit / o.n)} <span class="mut">(${o.hit}/${o.n}, ${pct(wilson(o.hit, o.n)[0])}–${pct(wilson(o.hit, o.n)[1])})</span>`;
const D = {};
async function load() {
  for (const k of ["board", "scorecard", "teams", "consistency", "lineups"]) { const r = await fetch(`data/${k}.json?v=${Date.now()}`); D[k] = r.ok ? await r.json() : null; }
  const a = D.scorecard && D.scorecard.asof; if (a) $("#asof").textContent = "updated " + fmtT(a);
  const m = D.scorecard && D.scorecard.tally && D.scorecard.tally.model && D.scorecard.tally.model.all;
  const b = $("#banner"); b.hidden = false;
  b.textContent = "Model v1 is unproven against PrizePicks lines" + (m ? `: its side won ${m.hit} of ${m.n} graded lines so far (break-even is 54.4%).` : " (no graded projections yet; it is tied with a season average in backtests).") + " Only PrizePicks lines are shown; the consensus is the other books' median.";
}
let CUR = null;                                   // the page being shown, so sort clicks and selects re-render the right one
const S = {market: "", edge: 0, cons: false, hideBig: false, q: "", sort: {k: "edge", asc: false}};
const bigGap = () => { const f = D.scorecard && D.scorecard.flags && D.scorecard.flags.big_gap; return f && f.active ? f : null; };
const bigTxt = f => `Lines where the projection is ${Math.round(f.threshold * 100)}%+ away from the PrizePicks line have won ${f.big.hit} of ${f.big.n} (${pct(f.big.rate)}), against ${f.rest.hit} of ${f.rest.n} (${pct(f.rest.rate)}) for smaller gaps. ${f.significant ? "The difference is statistically clear." : "That difference is not yet statistically settled (z = " + f.z + "), so treat it as a caution, not a rule."} A big gap looks more like projection error than an edge.`;
function sortRows(rows) {
  const {k, asc} = S.sort, v = r => k === "edge" ? (r.edge == null ? null : Math.abs(r.edge) / Math.max(r.pp, .5)) : r[k];
  return rows.slice().sort((a, b) => { const x = v(a), y = v(b); if (x == null) return 1; if (y == null) return -1; return (typeof x === "string" ? x.localeCompare(y) : x - y) * (asc ? 1 : -1); });
}

// ---------- player consistency: spikes or steady? (display only) ------------------------------------------------------------------
const esc = t => String(t ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const CONS_CLASS = {Steady: "good", Average: "mut", Volatile: "hot"};
function consBars(c, w = 62, h = 18) {
  const a = c.last || []; if (a.length < 3) return "";
  const mx = Math.max(...a, c.fp.median * 1.1), bw = w / a.length, my = (h - c.fp.median / mx * h).toFixed(1);
  return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" class="cbars">${a.map((v, i) => { const bh = Math.max(1, v / mx * h), hi = v >= c.fp.median * 1.3, lo = v <= c.fp.median * 0.7;
    return `<rect x="${(i * bw + 0.5).toFixed(1)}" y="${(h - bh).toFixed(1)}" width="${(bw - 1).toFixed(1)}" height="${bh.toFixed(1)}" fill="${hi ? "var(--good)" : lo ? "var(--bad)" : "var(--mut)"}"/>`; }).join("")}<line x1="0" x2="${w}" y1="${my}" y2="${my}" stroke="var(--fg)" stroke-width=".6" stroke-dasharray="2 2"/></svg>`;
}
function consTip(c) {
  const f = c.fp, rel = D.consistency.rel || {}, t = k => c[k] && c[k].tag ? `${k.toUpperCase()}: ${c[k].tag}${c[k].shape ? " (" + c[k].shape + ")" : ""}` : "";
  return esc(`Last ${c.n} games of ${D.consistency.min_minutes}+ min (this and last season). FP median ${n1(f.median)}, floor ${n1(f.floor)}, ceiling ${n1(f.ceil)}; CV ${f.cv} (${f.adj} x comparable players). Spikes (1.3x his median or more) in ${Math.round((f.spike || 0) * 100)}% of games, duds (0.7x or less) in ${Math.round((f.dud || 0) * 100)}%. ${["pts", "reb", "ast"].map(t).filter(Boolean).join("; ")}. Bars: his last 10 FP games (green = spike, red = dud), dashed = median. The tag describes recent games; it is not a forecast (spread repeats only modestly: split-half r ${rel.odd_even ?? "n/a"} odd vs even games, ${rel.earlier_later ?? "n/a"} earlier vs later).`);
}
function consCell(pid) {
  const c = D.consistency && D.consistency.players && pid ? D.consistency.players[pid] : null;
  if (!c || !c.fp.tag) return `<span class="mut" title="Needs ${D.consistency ? D.consistency.min_games : 8}+ games of ${D.consistency ? D.consistency.min_minutes : 12}+ minutes across this and last season">n/a</span>`;
  return `<span title="${consTip(c)}"><span class="pill ${CONS_CLASS[c.fp.tag]}">${c.fp.tag}${c.fp.shape ? " · " + c.fp.shape : ""}</span> ${consBars(c)}</span>`;
}


// ---------- projected starters, inferred from recent starts (display only) ---------------------------------------------------------
let PSET = null;
function isProjStarter(pid) {
  if (!PSET) { PSET = new Set(); if (D.lineups) for (const id in D.lineups.teams) for (const c of D.lineups.teams[id].players.slice(0, 5)) PSET.add(c.pid); }
  return PSET.has(pid);
}
function startersStrip(id, label) {
  const L = D.lineups && D.lineups.teams && D.lineups.teams[id]; if (!L || !L.players.length) return "";
  const acc = D.lineups.acc && D.lineups.acc.absences_known;
  const chip = c => `<span class="pill" title="${esc(c.name)}: started ${c.s} of his last ${c.gp} games (${c.mpg} min a game)">★ ${esc(c.name)} <span class="mut">${esc(c.pos)} ${c.s}/${c.gp}</span></span>`;
  return `<p class="sub" title="Inferred, not announced, and availability is not modelled (no injury feed). ${acc && acc.avg_right ? `Backtest on ${D.lineups.acc.team_games} team-games: even knowing who sat out it names ${acc.avg_right.toFixed(1)} of the 5 starters on average (${Math.round(acc.four_plus * 100)}% of the time 4 or 5 right, ${Math.round(acc.exact * 100)}% exactly right).` : ""}"><b>${esc(label)}</b> <span class="mut">(last ${L.games} games' starts)</span>: ${L.players.slice(0, 5).map(chip).join(" ")}</p>`;
}

const LINE_COLS = [["player", "Player", 1], ["team", "Team", 1], ["market", "Market", 1], ["pp", "PrizePicks"], ["cons", "Consensus"], ["gap", "PP − cons"], ["proj", "Proj"], ["edge", "Edge"], ["lean", "Lean"], ["min", "Min"], ["consist", "Consistency", 1]];
function gameLinesHTML(g) {
  let h = "", shown = 0;
    let rows = g.lines.filter(l => (!S.market || l.market === S.market) && (!S.cons || l.cons != null) && (!S.q || l.player.toLowerCase().includes(S.q.toLowerCase()))
      && (!S.edge || (l.edge != null && Math.abs(l.edge) / Math.max(l.pp, .5) >= S.edge))
      && !(S.hideBig && bigGap() && l.edge != null && Math.abs(l.edge) / Math.max(l.pp, .5) >= bigGap().threshold));
    if (!rows.length) return {html: "", n: 0}; shown += rows.length; rows = sortRows(rows);
    const sp = g.spread_home == null ? "" : ` · spread ${g.home} ${g.spread_home > 0 ? "+" : ""}${g.spread_home}, total ${g.total}`;
    h += `<div class="gh"><b>${g.away} @ ${g.home}</b><span>${fmtT(g.start_utc)}${sp}</span></div><div class="tw"><table><thead><tr>${LINE_COLS.map(([k, t, l]) => `<th class="${l ? "l " : ""}${S.sort.k === k ? "on" + (S.sort.asc ? " asc" : "") : ""}" data-k="${k}">${t}</th>`).join("")}</tr></thead><tbody>`;
    for (const l of rows) {
      const rel = l.edge == null ? null : l.edge / Math.max(l.pp, .5), lean = l.edge == null ? "–" : (l.edge > 0 ? "Over" : "Under");
      h += `<tr><td class="l">${isProjStarter(l.pid) ? '<span class="star" title="Projected starter">★</span> ' : ""}${l.player}</td><td class="l mut">${(l.team || "").replace(/ [A-Z][\w.'’&-]*( [A-Z][\w.'’&-]*)?$/, "")}</td><td class="l">${l.market}</td><td>${n1(l.pp)}</td>
      <td ${l.book_lines ? `title="${l.book_lines}"` : ""}>${l.cons == null ? "–" : n1(l.cons) + ` <span class="mut">×${l.n_books}</span>`}</td><td class="${l.gap == null ? "mut" : ""}">${signed(l.gap)}</td>
      <td>${n1(l.proj)}</td><td class="${rel == null ? "mut" : rel > 0 ? "good" : "bad"}">${signed(l.edge)}${rel == null ? "" : ` <span class="mut">${Math.round(rel * 100)}%</span>`}${rel != null && bigGap() && Math.abs(rel) >= bigGap().threshold ? ` <span class="flag" title="${bigTxt(bigGap()).replace(/"/g, "'")}">big gap</span>` : ""}</td><td>${lean}</td><td class="mut">${l.min == null ? "–" : Math.round(l.min)}</td><td class="l">${consCell(l.pid)}</td></tr>`;
    }
    h += "</tbody></table></div>";
  return {html: h, n: shown};
}

function board() {
  CUR = board;
  const B = D.board; if (!B || !B.games.length) { $("#view").innerHTML = "<h2>Board</h2><p class='sub'>No upcoming PrizePicks lines yet. Lines appear a few hours before tip for marquee games.</p>"; return; }
  const markets = [...new Set(B.games.flatMap(g => g.lines.map(l => l.market)))];
  let h = `<h2>Board</h2><p class="sub">PrizePicks lines for games that have not been graded. Edge = projection minus the PrizePicks line; “Lean” is the side the projection favours. Click a header to sort.</p>
  ${bigGap() ? `<div class="flagbox"><b>Big-gap watch.</b> ${bigTxt(bigGap())}</div>` : ""}
  <div class="bar"><label>Market <select id="fm"><option value="">All</option>${markets.map(m => `<option ${S.market === m ? "selected" : ""}>${m}</option>`).join("")}</select></label>
  <label>Edge ≥ <select id="fe">${[[0, "any"], [.1, "10%"], [.2, "20%"], [.3, "30%"]].map(([v, t]) => `<option value="${v}" ${S.edge == v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
  <label><input type="checkbox" id="fc" ${S.cons ? "checked" : ""}> only lines with a consensus</label>
  ${bigGap() ? `<label><input type="checkbox" id="fb" ${S.hideBig ? "checked" : ""}> hide big gaps (${Math.round(bigGap().threshold * 100)}%+)</label>` : ""}
  <label>Player <input id="fq" value="${S.q}" placeholder="search"></label></div>`;
  let shown = 0;
  for (const g of B.games) { const r = gameLinesHTML(g); h += r.html; shown += r.n; }
  if (!shown) h += "<p class='mut'>Nothing matches these filters.</p>";
  h += `<p class="note">Projection = expected minutes × shrunk per-minute rates × opponent × pace (points, threes), un-shrunk on points/assists/threes. A blank projection means the player is an unranked newcomer with under 3 games or is not on the ESPN roster. Availability is not modelled: a player with a line is assumed to play.</p>`;
  $("#view").innerHTML = h;
  $("#fm").onchange = e => { S.market = e.target.value; board(); }; $("#fe").onchange = e => { S.edge = +e.target.value; board(); };
  $("#fc").onchange = e => { S.cons = e.target.checked; board(); };
  if ($("#fb")) $("#fb").onchange = e => { S.hideBig = e.target.checked; board(); }; $("#fq").onchange = e => { S.q = e.target.value; board(); };
  bindSort();
}
function bindSort() { document.querySelectorAll("th[data-k]").forEach(th => th.onclick = () => { const k = th.dataset.k; S.sort = {k, asc: S.sort.k === k ? !S.sort.asc : false}; CUR(); }); }
const MARKET_NAMES = {player_points: "Points", player_rebounds: "Rebounds", player_assists: "Assists", player_threes: "Threes", player_points_rebounds_assists: "PTS+REB+AST"};
function tallyRow(label, t) {
  if (!t || !t.decided) return `<tr><td class="l">${label}</td><td colspan="5" class="mut">no decided lines</td></tr>`;
  const w = wilson(t.over, t.decided);
  return `<tr><td class="l">${label}</td><td>${t.decided}</td><td>${t.over}</td><td>${t.under}</td><td>${pct(t.over_rate)}</td><td class="mut">${pct(w[0])}–${pct(w[1])}</td><td>${t.mean_actual_minus_line == null ? "–" : signed(t.mean_actual_minus_line)}</td></tr>`;
}
const tHead = "<thead><tr><th class='l'></th><th>Decided</th><th>Over</th><th>Under</th><th>Over rate</th><th>95% range</th><th>Actual − line</th></tr></thead>";
function scorecard() {
  const S_ = D.scorecard; if (!S_ || !S_.tally || !S_.tally.total) { $("#view").innerHTML = "<h2>Scorecard</h2><p class='sub'>Nothing graded yet.</p>"; return; }
  const t = S_.tally, tot = t.total, m = t.model || {};
  let h = `<h2>Scorecard</h2><p class="sub">PrizePicks closing lines graded against ESPN box scores through ${t.through}. A push (stat equals the line) and a player with 0 minutes (void) are not counted.</p>
  <div class="cards"><div class="card"><b>${t.graded_rows}</b><span>PrizePicks lines graded${t.pending_rows ? ` (${t.pending_rows} waiting)` : ""}</span></div>
  <div class="card"><b>${pct(tot.over_rate)}</b><span>went Over (${tot.over} of ${tot.decided})</span></div>
  <div class="card"><b>${m.all ? pct(m.all.hit_rate) : "–"}</b><span>model side won${m.all ? ` (${m.all.hit} of ${m.all.n})` : " (no projections graded yet)"}</span></div>
  <div class="card"><b>${pct(S_.breakeven)}</b><span>break-even needed</span></div></div>
  <h3>Lines vs results</h3><div class="tw"><table>${tHead}<tbody>${tallyRow("All", tot)}${Object.entries(t.by_market || {}).map(([k, v]) => tallyRow(k.replace("player_", ""), v)).join("")}</tbody></table></div>
  <h3>PrizePicks line vs the sportsbook consensus</h3><div class="tw"><table>${tHead}<tbody>${Object.entries(t.by_consensus_gap || {}).map(([k, v]) => tallyRow(k.replace(/^pp /, "PrizePicks "), v)).join("")}</tbody></table></div>
  <p class="note">Sportsbooks post props for marquee games only, so most lines have no consensus yet.</p>`;
  if (m.all) {
    const f = S_.flags && S_.flags.big_gap;
    h += f && f.active ? `<div class="flagbox"><b>Big-gap watch.</b> ${bigTxt(f)}</div>` : (f && f.big && f.big.n ? `<p class="note">Big-gap watch is off: lines with a ${Math.round(f.threshold * 100)}%+ gap have won ${f.big.hit} of ${f.big.n}, against ${f.rest.hit} of ${f.rest.n} for smaller gaps. It switches on when the big-gap bucket has ${f.min_n}+ lines and trails by ${Math.round(f.margin * 100)}+ points.</p>` : "");
    h += `<h3>Model: how often the side its projection favoured won</h3><div class="tw"><table><thead><tr><th class="l"></th><th class="l">Won / lines (95% range)</th></tr></thead><tbody>
    <tr><td class="l">All</td><td class="l">${rate(m.all)}</td></tr>${Object.entries(m.by_market || {}).map(([k, v]) => `<tr><td class="l">${k.replace("player_", "")}</td><td class="l">${rate(v)}</td></tr>`).join("")}
    ${Object.entries(m.by_edge || {}).map(([k, v]) => `<tr><td class="l">edge ${k}${k === "20%+" && S_.flags && S_.flags.big_gap && S_.flags.big_gap.active ? ' <span class="flag">watch</span>' : ""}</td><td class="l">${rate(v)}</td></tr>`).join("")}
    <tr><td class="l">picked Over</td><td class="l">${rate(m.overs_picked)}</td></tr><tr><td class="l">picked Under</td><td class="l">${rate(m.unders_picked)}</td></tr></tbody></table></div>`;
    if (m.by_market_side) {
      const sideRows = (o, lab) => Object.entries(o).map(([k, v]) => `<tr><td class="l">${lab(k)}</td><td class="l">${rate(v.all)}</td><td class="l">${rate(v.over)}</td><td class="l">${rate(v.under)}</td></tr>`).join("");
      h += `<h3>Model by category and side (running tally)</h3><div class="tw"><table><thead><tr><th class="l"></th><th class="l">All picks</th><th class="l">Picked Over</th><th class="l">Picked Under</th></tr></thead><tbody>
      <tr><td class="l"><b>All</b></td><td class="l">${rate(m.all)}</td><td class="l">${rate(m.overs_picked)}</td><td class="l">${rate(m.unders_picked)}</td></tr>
      ${sideRows(m.by_market_side, k => (MARKET_NAMES[k] || k.replace("player_", "")))}${sideRows(m.by_edge_side || {}, k => "edge " + k)}</tbody></table></div>
      <p class="note">Won / lines for each side the model picked, with a 95% range; ${pct(S_.breakeven)} is break-even. Several slices have under 100 lines, so read them as indications. Updated with every graded run.</p>`;
    }
  } else h += `<h3>Model</h3><p class="note">The model's projections are logged before tip and graded against the closing line once the game is final; none are graded yet. Retro-projecting the first 100 lines gave 42 wins (history before each game, actual rosters), so treat it as unproven.</p>`;
  h += `<h3>By day</h3><div class="tw"><table>${tHead}<tbody>${Object.entries(t.by_date || {}).sort((a, b) => b[0].localeCompare(a[0])).map(([k, v]) => tallyRow(k, v)).join("")}</tbody></table></div>
  <h3>Backtest: model vs a player's season-to-date average</h3><div class="tw"><table><thead><tr><th class="l">Window</th><th>Fantasy-pt error: model</th><th>average</th><th>Minutes error: model</th><th>average</th></tr></thead><tbody>
  ${S_.backtest.map(r => `<tr><td class="l">${r.window}</td><td>${r.fp_model}</td><td>${r.fp_avg}</td><td>${r.min_model}</td><td>${r.min_avg}</td></tr>`).join("")}</tbody></table></div>
  <p class="note">Mean absolute error, lower is better. The model ties the average from December on; in November it is better on fantasy points and worse on minutes.</p>
  <h3>Latest graded lines</h3><div class="tw" style="max-height:60vh"><table><thead><tr><th class="l">Date</th><th class="l">Player</th><th class="l">Market</th><th>Line</th><th>Cons</th><th>Proj</th><th>Actual</th><th>Result</th><th>Model</th></tr></thead><tbody>
  ${S_.recent.map(r => `<tr><td class="l mut">${r.date}</td><td class="l">${r.player}</td><td class="l">${r.market}</td><td>${n1(r.pp)}</td><td>${n1(r.cons)}</td><td>${n1(r.proj)}</td><td>${n1(r.actual)}</td><td class="${r.result === "over" ? "good" : r.result === "under" ? "bad" : "mut"}">${r.result}</td>
  <td class="${!r.pick || !["over", "under"].includes(r.result) ? "mut" : r.pick === r.result ? "good" : "bad"}">${r.pick || "–"}</td></tr>`).join("")}</tbody></table></div>`;
  $("#view").innerHTML = h;
}

// ---------- Matchups: team comparison, unit strength, allowed by position (display only) ---------------------------------------------
const MS = {tca: "", tcb: "", tcw: "season", tcg: ""};
let MBIND = null;
function matchupHTML(o = {}) {
  const T = D.teams;
  if (!T || !T.teams || !T.teams.length) return o.embed ? "" : "<h2>Matchups</h2><p class='sub'>No team data yet.</p>";
  const tm = Object.fromEntries(T.teams.map(r => [r.id, r])), list = [...T.teams].sort((a, b) => a.team.localeCompare(b.team));
  const games = ((D.board && D.board.games) || []).filter(g => g.home_id != null && tm[g.home_id] && tm[g.away_id]);
  if (o.away != null && tm[o.away] && tm[o.home]) { MS.tca = o.away; MS.tcb = o.home; }
  if (!MS.tca || !tm[MS.tca] || !MS.tcb || !tm[MS.tcb]) {
    if (games[0]) { MS.tcg = games[0].event; MS.tca = games[0].away_id; MS.tcb = games[0].home_id; } else { MS.tca = list[0].id; MS.tcb = list[1].id; }
  }
  const A = tm[MS.tca], B = tm[MS.tcb], w = MS.tcw, a = A[w], b = B[w], lg = T.league[w];
  const rk = (side, r, k) => { const v = r[w]["rk_" + side] && r[w]["rk_" + side][k], n = T.teams.length; return v ? `<span class="rkn ${v <= n / 6 ? "good" : v > n - n / 6 ? "bad" : "mut"}">${v}</span>` : ""; };
  const f1 = x => x == null ? "–" : (Math.round(x * 10) / 10).toFixed(1);
  const ROWS = [
    {l: "Points", k: "pts", v: x => x.pts, t: x => f1(x.pts)},
    {l: "FG", k: "fg_pct", v: x => x.fg_pct, t: x => `${f1(x.fgm)}/${f1(x.fga)} <span class="mut">${f1(x.fg_pct)}%</span>`},
    {l: "3PT", k: "fg3_pct", v: x => x.fg3_pct, t: x => `${f1(x.fg3m)}/${f1(x.fg3a)} <span class="mut">${f1(x.fg3_pct)}%</span>`},
    {l: "FT", k: "ft_pct", v: x => x.ft_pct, t: x => `${f1(x.ftm)}/${f1(x.fta)} <span class="mut">${f1(x.ft_pct)}%</span>`},
    {l: "Rebounds", k: "reb", v: x => x.reb, t: x => f1(x.reb)}, {l: "Offensive reb", k: "oreb", v: x => x.oreb, t: x => f1(x.oreb)}, {l: "Defensive reb", k: "dreb", v: x => x.dreb, t: x => f1(x.dreb)},
    {l: "Assists", k: "ast", v: x => x.ast, t: x => f1(x.ast)}, {l: "Steals", k: "stl", v: x => x.stl, t: x => f1(x.stl)}, {l: "Blocks", k: "blk", v: x => x.blk, t: x => f1(x.blk)},
    {l: "Turnovers", k: "tov", v: x => x.tov, t: x => f1(x.tov)}, {l: "Personal fouls", k: "pf", v: x => x.pf, t: x => f1(x.pf)},
    {l: "Points per 100 poss", k: "ortg", v: x => x.ortg, t: x => f1(x.ortg)}];
  const sec = (title, side, note) => `<h3>${title}</h3><p class="sub">${note}</p><div class="cmp">${ROWS.map(r => {
    const x = a[side], y = b[side], vx = r.v(x), vy = r.v(y), sh = vx != null && vy != null && vx + vy > 0 ? 100 * vx / (vx + vy) : 50;
    return `<div class="cr"><div class="cv l">${rk(side === "for" ? "for" : "al", A, r.k)}${r.t(x)}</div><div class="cl">${r.l}</div><div class="cv r">${r.t(y)}${rk(side === "for" ? "for" : "al", B, r.k)}</div><div class="cb"><i style="width:${sh}%"></i></div></div>`; }).join("")}</div>`;
  const tblh = (cols, rows) => `<div class="tw"><table><thead><tr>${cols.map(([k, t, l]) => `<th class="${l ? "l" : ""}">${t}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr>${cols.map(([k, t, l]) => `<td class="${l ? "l" : ""}">${r[k]}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  const meet = (X, Y, label) => {
    const rows = [["Points", "pts"], ["FG%", "fg_pct"], ["3PM", "fg3m"], ["FTA", "fta"], ["Rebounds", "reb"], ["Assists", "ast"], ["Turnovers", "tov"], ["Pts / 100 poss", "ortg"]];
    const data = rows.map(([n, k]) => { const o = X[w].for[k], d = Y[w].allowed[k], l = lg.for[k], hi = k !== "tov", up = (o - l) * (hi ? 1 : -1) > 0, dn = (d - l) * (hi ? 1 : -1) > 0;
      return {s: n, o: f1(o), d: f1(d), lg: f1(l), e: up && dn ? `<span class="good">both help</span>` : !up && !dn ? `<span class="bad">both hurt</span>` : `<span class="mut">mixed</span>`}; });
    return tblh([["s", esc(label), 1], ["o", `${esc(X.team.split(" ").slice(0, -1).join(" "))} scored`], ["d", `${esc(Y.team.split(" ").slice(0, -1).join(" "))} allowed`], ["lg", "League"], ["e", "Both above/below league"]], data);
  };
  // unit strength
  const UN = {G: "Guards", F: "Forwards", C: "Centers"}, tierCls = t => t === "Top third" ? "good" : t === "Bottom third" ? "bad" : "mut";
  const uside = (U, pos, right) => { const u = U && U[w] && U[w][pos]; if (!u) return `<div class="cv ${right ? "r" : "l"} mut">no minutes yet</div>`;
    const pct_ = 100 * (u.of - u.rank + 1) / u.of, chip = `<span class="pill ${tierCls(u.tier)}">${u.tier}</span>`, txt = `<b>${f1(u.fp40)}</b> <span class="mut">FP/40 · #${u.rank}</span>`;
    return `<div class="cv ${right ? "r" : "l"}" title="${f1(u.fp40)} fantasy points per 40 minutes (${f1(u.pts40)} pts, ${f1(u.reb40)} reb, ${f1(u.ast40)} ast), rank ${u.rank} of ${u.of} teams; ${f1(u.mpg)} of the team's 200 minutes a game">${right ? chip + " " + txt : txt + " " + chip}<div class="meter ${right ? "r" : ""}"><i class="${tierCls(u.tier)}" style="width:${pct_.toFixed(0)}%"></i></div></div>`; };
  const unitSec = () => `<h3>Unit strength</h3><p class="sub">Fantasy points per 40 minutes produced by each team's guards, forwards and centers (PrizePicks scoring), ranked among all Division I teams with ${T.min_games}+ games: <span class="good">top third</span>, middle, <span class="bad">bottom third</span>. Units seen for few minutes are pulled toward the league average before ranking. It describes the players, not who is available tonight. Display only.</p>
    <div class="cmp">${["G", "F", "C"].map(pos => `<div class="cr">${uside(A.units, pos, false)}<div class="cl">${UN[pos]}</div>${uside(B.units, pos, true)}</div>`).join("")}</div>`;
  // allowed by position
  const rel = T.vspos_rel || {}, PN = {G: "guards", F: "forwards", C: "centers"}, VS = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"], LB = {pts: "PTS", reb: "REB", ast: "AST", fg3m: "3PM", stl: "STL", blk: "BLK", tov: "TOV"};
  const vrank = {};
  for (const pos of ["G", "F", "C"]) for (const st of VS) { const k = pos + "_" + st; T.teams.filter(r => r.vspos && r.vspos[k] != null).sort((x, y) => y.vspos[k] - x.vspos[k]).forEach((r, i, arr) => { (vrank[r.id] = vrank[r.id] || {})[k] = {rank: i + 1, of: arr.length}; }); }
  const vpos = team => {
    const nm = team.team.split(" ").slice(0, -1).join(" "), cells = ["G", "F", "C"], data = VS.map(st => { const row = {s: LB[st]};
      for (const pos of cells) { const k = pos + "_" + st, v = team.vspos[k], r_ = vrank[team.id] && vrank[team.id][k], r2 = rel[k] == null ? 0 : rel[k], noisy = r2 < 0.2;
        row[pos] = v == null ? "" : `<span class="${noisy ? "mut" : v > 1 ? "good" : v < -1 ? "bad" : "mut"}" title="Reliability (odd vs even games, across teams) ${r2.toFixed(2)}${noisy ? ": mostly noise" : ""}">${v > 0 ? "+" : ""}${f1(v)}%</span> <span class="rkn mut">${r_ ? r_.rank : ""}</span>`; }
      return row; });
    return `<div>${tblh([["s", `${esc(nm)} allows to`, 1], ["G", "Guards"], ["F", "Forwards"], ["C", "Centers"]], data)}</div>`;
  };
  const gsel = games.length ? `<label>Game <select id="mg"><option value="" ${MS.tcg ? "" : "selected"}>custom</option>${games.map(g => `<option value="${g.event}" ${g.event === MS.tcg ? "selected" : ""}>${esc(g.away)} @ ${esc(g.home)}</option>`).join("")}</select></label>` : "";
  const opt = (id, cur) => `<select id="${id}">${list.map(r => `<option value="${r.id}" ${r.id == cur ? "selected" : ""}>${esc(r.team)}</option>`).join("")}</select>`;
  const oppTxt = r => Object.entries(r.opp_tiers).map(([k, v]) => `${v} ${k}`).join(", ");
  const head = (r, win) => `<b>${esc(r.team)}</b> <span class="pill">${r.tier}</span> <span class="mut">${r.w}-${r.l} · ${win.g} g · pace ${f1(r.pace)}<br>opponents so far: ${oppTxt(r)}</span>`;
  const intro = `<p class="sub">Per-game team stats from ESPN box scores, and what each team has <b>allowed</b> (the other side's totals in the same games). The small number is the rank among the ${T.teams.length} Division I teams with ${T.min_games}+ games (1 = best for that side: most scored, fewest allowed; green = top sixth, red = bottom sixth). <b>No schedule adjustment:</b> with about five games a team, who it has played dominates, so check the opponent mix under each name before reading anything into a rank. Season to date through ${esc(T.asof)}. Display only: none of this feeds the projections.</p>`;
  const html = `${o.embed ? "" : "<h2>Matchups</h2>" + intro}
    <div class="bar">${o.embed ? "" : `${gsel}<label>Away ${opt("ma", MS.tca)}</label><label>Home ${opt("mb", MS.tcb)}</label>`}<label>Window <select id="mw">${[["season", "Season"], ["l3", "Last 3"]].map(([k, n]) => `<option value="${k}" ${k === w ? "selected" : ""}>${n}</option>`).join("")}</select></label></div>
    <div class="cmphead"><div class="l">${head(A, a)}</div><div class="r">${head(B, b)}</div></div>
    <div class="cmpgrid"><div>${unitSec()}</div>
    <div>${sec("Scored per game", "for", "What each team does with the ball.")}</div>
    <div>${sec("Allowed per game", "allowed", "What each team gives up to its opponents (turnovers and steals here are the ones it forced).")}</div></div>
    <h3>Each offence against the other defence</h3><div class="two"><div>${meet(A, B, A.team.split(" ").slice(0, -1).join(" ") + " offence")}</div><div>${meet(B, A, B.team.split(" ").slice(0, -1).join(" ") + " offence")}</div></div>
    <h3>Allowed by position</h3><p class="sub">Per-minute stats each defence has allowed to guards, forwards and centers, against the league at that position (green = allows more, red = allows less), pulled toward zero by minutes seen. The small number is the rank (1 = allows the most). Grey = split-half reliability under 0.2, which is most of the table this early: with about five games a team, none of these cells is steady yet. Display only.</p>
    <div class="two">${vpos(A)}${vpos(B)}</div>`;
  MBIND = () => {
    const on = (id, fn) => { const el = $("#" + id); if (el) el.onchange = fn; };
    on("mg", e => { const g = games.find(x => x.event === e.target.value); if (g) { MS.tcg = g.event; MS.tca = g.away_id; MS.tcb = g.home_id; } else MS.tcg = ""; CUR(); });
    on("ma", e => { MS.tca = +e.target.value; MS.tcg = ""; CUR(); }); on("mb", e => { MS.tcb = +e.target.value; MS.tcg = ""; CUR(); });
    on("mw", e => { MS.tcw = e.target.value; CUR(); });
  };
  return html;
}
function matchups() { CUR = matchups; $("#view").innerHTML = matchupHTML(); if (MBIND) MBIND(); }

// one-line unit strength for a team id: guards / forwards / centers as a tier arrow
function unitBrief(id) {
  const t = (D.teams && D.teams.teams || []).find(r => r.id === id), u = t && t.units && t.units.season; if (!u) return "";
  const nm = t.team.split(" ").slice(0, -1).join(" ");
  const mk = (pos, n) => { const x = u[pos]; if (!x) return ""; const c = x.tier === "Top third" ? "good" : x.tier === "Bottom third" ? "bad" : "mut", a = x.tier === "Top third" ? "▲" : x.tier === "Bottom third" ? "▼" : "•";
    return `<span class="${c}" title="${esc(nm)} ${n}: ${x.tier}, #${x.rank} of ${x.of} (${x.fp40} FP/40)">${pos}${a}</span>`; };
  return `<b>${esc(nm)}</b> ${["G", "F", "C"].map(p => mk(p, {G: "guards", F: "forwards", C: "centers"}[p])).join(" ")}`;
}

// ---------- Game: the matchup, the players' lines with projections and the consistency tag, all for one game ------------------------------
const G = {ev: "", cmp: false, lines: true};
function game() {
  CUR = game;
  const B = D.board;
  if (!B || !B.games.length) { $("#view").innerHTML = "<h2>Game</h2><p class='sub'>No upcoming PrizePicks lines yet. Lines appear a few hours before tip for marquee games. Use Matchups to compare any two teams.</p>"; return; }
  if (!B.games.some(x => x.event === G.ev)) G.ev = B.games[0].event;
  const g = B.games.find(x => x.event === G.ev), tm = D.teams && D.teams.teams ? Object.fromEntries(D.teams.teams.map(r => [r.id, r])) : {};
  const sect = (id, title, hint, body, open) => `<details class="gsec" data-gs="${id}" ${open ? "open" : ""}><summary><b>${title}</b> <span class="mut">${hint}</span></summary>${body}</details>`;
  const hasT = g.home_id != null && tm[g.home_id] && tm[g.away_id];
  const lines = gameLinesHTML(g);
  const sp = g.spread_home == null ? "" : ` · spread ${esc(g.home)} ${g.spread_home > 0 ? "+" : ""}${g.spread_home}, total ${g.total}`;
  $("#view").innerHTML = `<h2>Game</h2><p class="sub">Pick a game once: the team matchup, then every PrizePicks line for it with the model's projection, edge and each player's consistency tag. Edge = projection minus the PrizePicks line; "Lean" is the side the projection favours. Click a header to sort.</p>
    ${bigGap() ? `<div class="flagbox"><b>Big-gap watch.</b> ${bigTxt(bigGap())}</div>` : ""}
    <div class="bar"><label>Game <select id="gg">${B.games.map(x => `<option value="${x.event}" ${x.event === G.ev ? "selected" : ""}>${esc(x.away)} @ ${esc(x.home)} · ${fmtT(x.start_utc)}</option>`).join("")}</select></label><span class="mut">${esc(g.away)} @ ${esc(g.home)}${sp}</span></div>
    ${hasT ? sect("cmp", "Team comparison", unitBrief(g.away_id) + " &nbsp;vs&nbsp; " + unitBrief(g.home_id) + " <span class='mut'>(click to open: scored and allowed, vs position, opponent mix)</span>", matchupHTML({embed: true, away: g.away_id, home: g.home_id}), G.cmp === true) : ""}
    <h3>Projected starters</h3><p class="note">Inferred from who has been starting, not announced; there is no injury feed on the college side, so a starter who is out tonight is not replaced here. Check the news before tip.</p>
    <div class="two">${startersStrip(g.away_id, g.away)}${startersStrip(g.home_id, g.home)}</div>
    <h3>Lines and projections</h3>${lines.html || "<p class='mut'>No lines match.</p>"}
    <p class="note">Projection = expected minutes × shrunk per-minute rates × opponent × pace (points, threes), un-shrunk on points/assists/threes. A blank projection means the player is an unranked newcomer with under 3 games or is not on the ESPN roster. Availability is not modelled: a player with a line is assumed to play.</p>`;
  $("#gg").onchange = e => { G.ev = e.target.value; game(); };
  if (MBIND && hasT) MBIND();
  bindSort();
}
document.addEventListener("toggle", e => { const t = e.target; if (t && t.dataset && t.dataset.gs) G[t.dataset.gs] = t.open; }, true);

function route() {
  const v = location.hash.replace("#", "") || "game";
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("on", a.dataset.v === v));
  (v === "scorecard" ? scorecard : v === "matchups" ? matchups : v === "board" ? board : game)();
}
window.addEventListener("hashchange", route);
load().then(route).catch(e => { $("#view").innerHTML = "<p class='bad'>Could not load data: " + e + "</p>"; });
