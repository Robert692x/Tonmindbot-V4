import { DexPair, calculateRisk, riskEmoji } from "./analyzer";

const DEXSCREENER_BASE = "https://dexscreener.com/ton";
const MAX_SUMMARY_ITEMS = 10;

function fmtUsd(v: number): string {
  if (v >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (v >= 1_000_000)     return `$${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000)         return `$${(v / 1_000).toFixed(1)}K`;
  return `$${Math.round(v).toLocaleString("en")}`;
}

function fmtPrice(v: number): string {
  if (v === 0) return "$0";
  if (v >= 1)  return `$${v.toFixed(2)}`;
  if (v >= 0.001) return `$${v.toFixed(4)}`;
  return `$${v.toFixed(8)}`;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Full HTML card for one listing. */
export function formatListing(pair: DexPair): string {
  const base = pair.baseToken ?? {};
  const name = esc(base.name ?? base.symbol ?? "Unknown");
  const symbol = esc(base.symbol ?? "?");
  const address = base.address ?? "";

  const liquidity = pair.liquidity?.usd ?? 0;
  const volume = pair.volume?.h24 ?? 0;
  const fdv = pair.fdv ?? 0;
  const price = parseFloat(pair.priceUsd ?? "0");
  const pairAddress = pair.pairAddress ?? "";
  const dexId = esc((pair.dexId ?? "unknown").toUpperCase().replace(/-/g, "."));
  const age = pair._ageMinutes ?? 0;

  const risk = calculateRisk(pair);
  const emoji = riskEmoji(risk.score);
  const dexUrl = pair.url ?? `${DEXSCREENER_BASE}/${pairAddress}`;
  const factorsText = risk.factors.length
    ? risk.factors.map((f) => `  • ${esc(f)}`).join("\n")
    : "  None";

  const lines = [
    "🚀 <b>New Listing</b>",
    "",
    `Name: <b>${name}</b> (${symbol})`,
    "Chain: <b>TON</b>",
    `Price: ${fmtPrice(price)}`,
    `Liquidity: ${fmtUsd(liquidity)}`,
    `Volume: ${fmtUsd(volume)}`,
    `FDV: ${fmtUsd(fdv)}`,
    `Age: ${age.toFixed(1)} min`,
    "",
    `Risk: ${emoji} <b>${risk.level}</b> (${risk.score}/100)`,
    "",
    "Factors:",
    factorsText,
    "",
    `DEX: ${dexId}`,
  ];

  if (address) {
    lines.push(`Contract:\n<a href="https://tonviewer.com/${address}">${address.slice(0, 10)}…</a>`);
  }
  lines.push(`Link: <a href="${dexUrl}">DexScreener</a>`);

  return lines.join("\n");
}

/** Compact multi-token summary (up to MAX_SUMMARY_ITEMS). */
export function formatListingsSummary(listings: DexPair[]): string {
  if (!listings.length) {
    return "<b>New Listings (TON)</b>\n\nNo new listings in the last 20 minutes.";
  }

  const sep = "─".repeat(24);
  const count = listings.length;
  const lines: string[] = [`🚀 <b>New Listings (TON)</b> — ${count} found\n`, sep];

  for (const pair of listings.slice(0, MAX_SUMMARY_ITEMS)) {
    const symbol = esc((pair.baseToken?.symbol ?? "?").slice(0, 12));
    const liquidity = pair.liquidity?.usd ?? 0;
    const age = pair._ageMinutes ?? 0;
    const pairAddress = pair.pairAddress ?? "";
    const risk = calculateRisk(pair);
    const emoji = riskEmoji(risk.score);
    const dexUrl = pair.url ?? `${DEXSCREENER_BASE}/${pairAddress}`;

    lines.push(
      `${emoji} <b>${symbol}</b>  ` +
      `Liq: ${fmtUsd(liquidity)}  ` +
      `Age: ${age.toFixed(1)}m  ` +
      `Risk: ${risk.score}  ` +
      `<a href="${dexUrl}">DEX</a>`
    );
  }

  if (count > MAX_SUMMARY_ITEMS) {
    lines.push(`\n+ ${count - MAX_SUMMARY_ITEMS} more…`);
  }

  return lines.join("\n");
}

/** Short alert card for background notifications. */
export function formatListingAlert(pair: DexPair): string {
  const base = pair.baseToken ?? {};
  const name = esc(base.name ?? base.symbol ?? "Unknown");
  const symbol = esc(base.symbol ?? "?");
  const address = base.address ?? "";

  const liquidity = pair.liquidity?.usd ?? 0;
  const volume = pair.volume?.h24 ?? 0;
  const pairAddress = pair.pairAddress ?? "";
  const dexId = esc((pair.dexId ?? "unknown").toUpperCase().replace(/-/g, "."));
  const age = pair._ageMinutes ?? 0;

  const risk = calculateRisk(pair);
  const emoji = riskEmoji(risk.score);
  const dexUrl = pair.url ?? `${DEXSCREENER_BASE}/${pairAddress}`;

  const lines = [
    "🚀 <b>New Listing</b>",
    "",
    `Name: <b>${name}</b> (${symbol})`,
    `Liquidity: ${fmtUsd(liquidity)}`,
    `Volume: ${fmtUsd(volume)}`,
    `Age: ${age.toFixed(1)} min`,
    "",
    `Risk: ${emoji} <b>${risk.level}</b> (${risk.score}/100)`,
    "",
    `DEX: ${dexId}`,
  ];

  if (address) {
    lines.push(`Contract:\n<a href="https://tonviewer.com/${address}">${address.slice(0, 10)}…</a>`);
  }
  lines.push(`<a href="${dexUrl}">Open on DexScreener</a>`);

  return lines.join("\n");
}
