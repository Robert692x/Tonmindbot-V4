export interface RiskResult {
  score: number;
  level: "Low" | "Medium" | "High";
  factors: string[];
}

export interface DexPair {
  pairAddress?: string;
  pairCreatedAt?: number;
  dexId?: string;
  baseToken?: { name?: string; symbol?: string; address?: string };
  quoteToken?: { symbol?: string };
  priceUsd?: string;
  liquidity?: { usd?: number };
  volume?: { h24?: number };
  fdv?: number;
  info?: { websites?: { url: string }[]; socials?: { type: string; url: string }[] };
  url?: string;
  /** Injected by fetcher */
  _ageMinutes?: number;
}

export function calculateRisk(pair: DexPair): RiskResult {
  let score = 0;
  const factors: string[] = [];

  const liquidity = pair.liquidity?.usd ?? 0;
  const volume = pair.volume?.h24 ?? 0;
  const fdv = pair.fdv ?? 0;
  const age = pair._ageMinutes ?? 0;
  const websites = pair.info?.websites ?? [];
  const socials = pair.info?.socials ?? [];

  if (liquidity < 5_000) {
    score += 30;
    factors.push(`Low liquidity ($${liquidity.toLocaleString("en", { maximumFractionDigits: 0 })})`);
  }

  if (volume < 2_000) {
    score += 20;
    factors.push(`Low 24h volume ($${volume.toLocaleString("en", { maximumFractionDigits: 0 })})`);
  }

  if (liquidity > 0 && fdv > 0) {
    const ratio = fdv / liquidity;
    if (ratio > 20) {
      score += 20;
      factors.push(`FDV/Liquidity ratio ${ratio.toFixed(0)}x`);
    }
  }

  if (websites.length === 0 && socials.length === 0) {
    score += 10;
    factors.push("No website or socials");
  }

  if (age < 5) {
    score += 20;
    factors.push(`Very fresh pair (${age.toFixed(1)} min old)`);
  }

  score = Math.min(100, score);

  const level: RiskResult["level"] =
    score < 30 ? "Low" : score < 60 ? "Medium" : "High";

  return { score, level, factors };
}

export function riskEmoji(score: number): string {
  if (score < 30) return "🟢";
  if (score < 60) return "🟡";
  return "🔴";
}
