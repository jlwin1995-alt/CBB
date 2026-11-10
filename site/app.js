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
  for (const k of ["board", "scorecard"]) { const r = await fetch(`data/${k}.json?v=${Date.now()}`); D[k] = r.ok ? await r.json() : null; }
  const a = D.scorecard && D.scorecard.asof; if (a) $("#asof").textContent = "updated " + fmtT(a);
  const m = D.scorecard && D.scorecard.tally && D.scorecard.tally.model && D.scorecard.tally.model.all;
  const b = $("#banner"); b.hidden = false;
  b.textContent = "Model v1 is unproven against PrizePicks lines" + (m ? `: its side won ${m.hit} of ${m.n} graded lines so far (break-even is 54.4%).` : " (no graded projections yet; it is tied with a season average in backtests).") + " Only PrizePicks lines are shown; the consensus is the other books' median.";
}
const S = {market: "", edge: 0, cons: false, hideBig: false, q: "", sort: {k: "edge", asc: false}};
const bigGap = () => { const f = D.scorecard && D.scorecard.flags && D.scorecard.flags.big_gap; return f && f.active ? f : null; };
const bigTxt = f => `Lines where the projection is ${Math.round(f.threshold * 100)}%+ away from the PrizePicks line have won ${f.big.hit} of ${f.big.n} (${pct(f.big.rate)}), against ${f.rest.hit} of ${f.rest.n} (${pct(f.rest.rate)}) for smaller gaps. ${f.significant ? "The difference is statistically clear." : "That difference is not yet statistically settled (z = " + f.z + "), so treat it as a caution, not a rule."} A big gap looks more like projection error than an edge.`;
function sortRows(rows) {
  const {k, asc} = S.sort, v = r => k === "edge" ? (r.edge == null ? null : Math.abs(r.edge) / Math.max(r.pp, .5)) : r[k];
  return rows.slice().sort((a, b) => { const x = v(a), y = v(b); if (x == null) return 1; if (y == null) return -1; return (typeof x === "string" ? x.localeCompare(y) : x - y) * (asc ? 1 : -1); });
}
function board() {
  const B = D.board; if (!B || !B.games.length) { $("#view").innerHTML = "<h2>Board</h2><p class='sub'>No upcoming PrizePicks lines yet. Lines appear a few hours before tip for marquee games.</p>"; return; }
  const markets = [...new Set(B.games.flatMap(g => g.lines.map(l => l.market)))];
  let h = `<h2>Board</h2><p class="sub">PrizePicks lines for games that have not been graded. Edge = projection minus the PrizePicks line; “Lean” is the side the projection favours. Click a header to sort.</p>
  ${bigGap() ? `<div class="flagbox"><b>Big-gap watch.</b> ${bigTxt(bigGap())}</div>` : ""}
  <div class="bar"><label>Market <select id="fm"><option value="">All</option>${markets.map(m => `<option ${S.market === m ? "selected" : ""}>${m}</option>`).join("")}</select></label>
  <label>Edge ≥ <select id="fe">${[[0, "any"], [.1, "10%"], [.2, "20%"], [.3, "30%"]].map(([v, t]) => `<option value="${v}" ${S.edge == v ? "selected" : ""}>${t}</option>`).join("")}</select></label>
  <label><input type="checkbox" id="fc" ${S.cons ? "checked" : ""}> only lines with a consensus</label>
  ${bigGap() ? `<label><input type="checkbox" id="fb" ${S.hideBig ? "checked" : ""}> hide big gaps (${Math.round(bigGap().threshold * 100)}%+)</label>` : ""}
  <label>Player <input id="fq" value="${S.q}" placeholder="search"></label></div>`;
  const cols = [["player", "Player", 1], ["team", "Team", 1], ["market", "Market", 1], ["pp", "PrizePicks"], ["cons", "Consensus"], ["gap", "PP − cons"], ["proj", "Proj"], ["edge", "Edge"], ["lean", "Lean"], ["min", "Min"]];
  let shown = 0;
  for (const g of B.games) {
    let rows = g.lines.filter(l => (!S.market || l.market === S.market) && (!S.cons || l.cons != null) && (!S.q || l.player.toLowerCase().includes(S.q.toLowerCase()))
      && (!S.edge || (l.edge != null && Math.abs(l.edge) / Math.max(l.pp, .5) >= S.edge))
      && !(S.hideBig && bigGap() && l.edge != null && Math.abs(l.edge) / Math.max(l.pp, .5) >= bigGap().threshold));
    if (!rows.length) continue; shown += rows.length; rows = sortRows(rows);
    const sp = g.spread_home == null ? "" : ` · spread ${g.home} ${g.spread_home > 0 ? "+" : ""}${g.spread_home}, total ${g.total}`;
    h += `<div class="gh"><b>${g.away} @ ${g.home}</b><span>${fmtT(g.start_utc)}${sp}</span></div><div class="tw"><table><thead><tr>${cols.map(([k, t, l]) => `<th class="${l ? "l " : ""}${S.sort.k === k ? "on" + (S.sort.asc ? " asc" : "") : ""}" data-k="${k}">${t}</th>`).join("")}</tr></thead><tbody>`;
    for (const l of rows) {
      const rel = l.edge == null ? null : l.edge / Math.max(l.pp, .5), lean = l.edge == null ? "–" : (l.edge > 0 ? "Over" : "Under");
      h += `<tr><td class="l">${l.player}</td><td class="l mut">${(l.team || "").replace(/ [A-Z][\w.'’&-]*( [A-Z][\w.'’&-]*)?$/, "")}</td><td class="l">${l.market}</td><td>${n1(l.pp)}</td>
      <td ${l.book_lines ? `title="${l.book_lines}"` : ""}>${l.cons == null ? "–" : n1(l.cons) + ` <span class="mut">×${l.n_books}</span>`}</td><td class="${l.gap == null ? "mut" : ""}">${signed(l.gap)}</td>
      <td>${n1(l.proj)}</td><td class="${rel == null ? "mut" : rel > 0 ? "good" : "bad"}">${signed(l.edge)}${rel == null ? "" : ` <span class="mut">${Math.round(rel * 100)}%</span>`}${rel != null && bigGap() && Math.abs(rel) >= bigGap().threshold ? ` <span class="flag" title="${bigTxt(bigGap()).replace(/"/g, "'")}">big gap</span>` : ""}</td><td>${lean}</td><td class="mut">${l.min == null ? "–" : Math.round(l.min)}</td></tr>`;
    }
    h += "</tbody></table></div>";
  }
  if (!shown) h += "<p class='mut'>Nothing matches these filters.</p>";
  h += `<p class="note">Projection = expected minutes × shrunk per-minute rates × opponent × pace (points, threes), un-shrunk on points/assists/threes. A blank projection means the player is an unranked newcomer with under 3 games or is not on the ESPN roster. Availability is not modelled: a player with a line is assumed to play.</p>`;
  $("#view").innerHTML = h;
  $("#fm").onchange = e => { S.market = e.target.value; board(); }; $("#fe").onchange = e => { S.edge = +e.target.value; board(); };
  $("#fc").onchange = e => { S.cons = e.target.checked; board(); };
  if ($("#fb")) $("#fb").onchange = e => { S.hideBig = e.target.checked; board(); }; $("#fq").onchange = e => { S.q = e.target.value; board(); };
  document.querySelectorAll("th[data-k]").forEach(th => th.onclick = () => { const k = th.dataset.k; S.sort = {k, asc: S.sort.k === k ? !S.sort.asc : false}; board(); });
}
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
function route() {
  const v = location.hash.replace("#", "") || "board";
  document.querySelectorAll("nav a").forEach(a => a.classList.toggle("on", a.dataset.v === v));
  (v === "scorecard" ? scorecard : board)();
}
window.addEventListener("hashchange", route);
load().then(route).catch(e => { $("#view").innerHTML = "<p class='bad'>Could not load data: " + e + "</p>"; });
