import { DexPair } from "./analyzer";

const API_URL = "https://api.dexscreener.com/latest/dex/pairs/ton";
const MAX_AGE_MINUTES = 20;
const MIN_LIQUIDITY_USD = 2_000;
const FETCH_TIMEOUT_MS = 8_000;

export async function fetchNewListings(): Promise<DexPair[]> {
  const raw = await getRawPairs();
  if (!raw.length) return [];

  const nowMs = Date.now();
  const cutoffMs = nowMs - MAX_AGE_MINUTES * 60_000;
  const results: DexPair[] = [];

  for (const pair of raw) {
    const createdAt = pair.pairCreatedAt;
    if (!createdAt || createdAt < cutoffMs) continue;

    const liquidity = pair.liquidity?.usd ?? 0;
    if (liquidity < MIN_LIQUIDITY_USD) continue;

    results.push({
      ...pair,
      _ageMinutes: (nowMs - createdAt) / 60_000,
    });
  }

  return results.sort((a, b) => (b.pairCreatedAt ?? 0) - (a.pairCreatedAt ?? 0));
}

async function getRawPairs(): Promise<DexPair[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const res = await fetch(API_URL, { signal: controller.signal });
    if (!res.ok) {
      console.warn(`[launchpad] DexScreener returned HTTP ${res.status}`);
      return [];
    }
    const data = (await res.json()) as { pairs?: DexPair[] };
    return data.pairs ?? [];
  } catch (err) {
    console.warn("[launchpad] fetch failed:", (err as Error).message);
    return [];
  } finally {
    clearTimeout(timer);
  }
}
