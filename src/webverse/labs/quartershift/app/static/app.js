(function () {
  //# sourceMappingURL=app.js.map
  const DOMAIN = window.QS_DOMAIN || "quartershift.local";

  function el(id) { return document.getElementById(id); }
  function clamp(n, a, b) { return Math.max(a, Math.min(b, n)); }

  // -------------------------
  // LEADERBOARD (GraphQL)
  // -------------------------
  async function loadLeaderboard(limit = 10, targetBodyId = "leaderboardBody") {
    const body = el(targetBodyId);
    if (!body) return;

    body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Loading leaderboard…</td></tr>`;

    const query = `
      query Top($limit:Int!) {
        leaderboardTop(limit:$limit) { rank username score }
      }
    `;
    const url = `http://scores.${DOMAIN}/graphql`;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, variables: { limit } }),
      });

      const j = await r.json();
      const rows = (j && j.data && j.data.leaderboardTop) ? j.data.leaderboardTop : [];

      if (!rows || rows.length === 0) {
        body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Leaderboard unavailable.</td></tr>`;
        return;
      }

      body.innerHTML = rows.map(row => {
        const rank = row.rank;
        const user = String(row.username || "");
        const score = Number(row.score || 0);
        const glow = rank === 1 ? "qs-rank1" : (rank === 2 ? "qs-rank2" : (rank === 3 ? "qs-rank3" : ""));
        return `
          <tr class="qs-tr ${glow}">
            <td class="qs-td-rank">${rank}</td>
            <td class="qs-td-user">${escapeHtml(user)}</td>
            <td class="text-end qs-td-score">${score.toLocaleString()}</td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Leaderboard unavailable.</td></tr>`;
    }
  }

  async function loadStandings() {
    const body = el("standingsBody");
    if (!body) return;

    body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Loading standings…</td></tr>`;
    const query = `
      query Top($limit:Int!) {
        leaderboardTop(limit:$limit) { rank username score }
      }
    `;
    const url = `http://scores.${DOMAIN}/graphql`;
    try {
      const r = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, variables: { limit: 50 } }),
      });
      const j = await r.json();
      const rows = (j && j.data && j.data.leaderboardTop) ? j.data.leaderboardTop : [];
      if (!rows || rows.length === 0) {
        body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Standings unavailable.</td></tr>`;
        return;
      }
      body.innerHTML = rows.map(row => `
        <tr class="qs-tr">
          <td class="qs-td-rank">${row.rank}</td>
          <td class="qs-td-user">${escapeHtml(String(row.username || ""))}</td>
          <td class="text-end qs-td-score">${Number(row.score || 0).toLocaleString()}</td>
        </tr>
      `).join("");
    } catch (e) {
      body.innerHTML = `<tr><td colspan="3" class="qs-muted small">Standings unavailable.</td></tr>`;
    }
  }

  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, (m) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    }[m]));
  }

  // -------------------------
  // BLACKJACK (simple client)
  // -------------------------
  const suits = ["♠", "♥", "♦", "♣"];
  const ranks = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"];

  function drawCard() {
    const r = ranks[Math.floor(Math.random() * ranks.length)];
    const s = suits[Math.floor(Math.random() * suits.length)];
    return { r, s };
  }

  function cardValue(rank) {
    if (rank === "A") return 11;
    if (rank === "K" || rank === "Q" || rank === "J") return 10;
    return parseInt(rank, 10);
  }

  function handTotal(cards) {
    let total = 0;
    let aces = 0;
    for (const c of cards) {
      total += cardValue(c.r);
      if (c.r === "A") aces++;
    }
    while (total > 21 && aces > 0) {
      total -= 10;
      aces--;
    }
    return total;
  }

  function renderCards(containerId, cards) {
    const container = el(containerId);
    if (!container) return;
    container.innerHTML = cards.map(c => {
      const isRed = (c.s === "♥" || c.s === "♦");
      return `
        <div class="qs-cardtile ${isRed ? "qs-cardtile-red" : ""}">
          <div class="qs-cardtile-rank">${c.r}</div>
          <div class="qs-cardtile-suit">${c.s}</div>
        </div>
      `;
    }).join("");
  }

  let dealer = [];
  let player = [];
  let inRound = false;
  let stood = false;

  function setStatus(t) {
    const st = el("statusText");
    if (st) st.textContent = t;
  }

  function updateTotals(revealDealer = false) {
    const dTotal = el("dealerTotal");
    const pTotal = el("playerTotal");
    if (pTotal) pTotal.textContent = String(handTotal(player));
    if (dTotal) dTotal.textContent = revealDealer ? String(handTotal(dealer)) : "?";
  }

  function startRound() {
    dealer = [drawCard(), drawCard()];
    player = [drawCard(), drawCard()];
    inRound = true;
    stood = false;

    renderCards("dealerCards", [dealer[0], { r: "?", s: "?" }]);
    renderCards("playerCards", player);
    updateTotals(false);
    setStatus("Hit or Stand.");
  }

  function hit() {
    if (!inRound || stood) return;
    player.push(drawCard());
    renderCards("playerCards", player);
    updateTotals(false);

    const p = handTotal(player);
    if (p > 21) {
      stood = true;
      inRound = false;
      renderCards("dealerCards", dealer);
      updateTotals(true);
      setStatus("Bust. House wins.");
    }
  }

  function stand() {
    if (!inRound) return;
    stood = true;

    while (handTotal(dealer) < 17) {
      dealer.push(drawCard());
    }

    const p = handTotal(player);
    const d = handTotal(dealer);

    renderCards("dealerCards", dealer);
    updateTotals(true);

    inRound = false;

    if (d > 21) return setStatus("Dealer busts. You win.");
    if (p > d) return setStatus("You win.");
    if (p < d) return setStatus("House wins.");
    return setStatus("Push.");
  }

  // boot
  document.addEventListener("DOMContentLoaded", () => {
    const btnReload = el("btnReloadLB");
    if (btnReload) btnReload.addEventListener("click", () => loadLeaderboard(10, "leaderboardBody"));

    loadLeaderboard(10, "leaderboardBody");
    loadStandings();

    const btnNew = el("btnNew");
    const btnHit = el("btnHit");
    const btnStand = el("btnStand");
    if (btnNew) btnNew.addEventListener("click", startRound);
    if (btnHit) btnHit.addEventListener("click", hit);
    if (btnStand) btnStand.addEventListener("click", stand);

    if (el("dealerCards") && el("playerCards")) {
      startRound();
    }
  });
})();
