import { Bot, Context, InlineKeyboard } from "grammy";
import { DexPair } from "./analyzer";
import { ListingCache } from "./cache";
import { fetchNewListings } from "./fetcher";
import { formatListing, formatListingAlert, formatListingsSummary } from "./notifier";

// ── Service (shared state per bot instance) ───────────────────────────────────

export class LaunchpadService {
  private readonly cache = new ListingCache();

  async getAllListings(maxItems = 10): Promise<DexPair[]> {
    const raw = await fetchNewListings();
    return raw.slice(0, maxItems);
  }

  async popNewListings(): Promise<DexPair[]> {
    const raw = await fetchNewListings();
    const fresh: DexPair[] = [];

    for (const pair of raw) {
      const addr = pair.pairAddress ?? "";
      if (!addr || this.cache.isSeen(addr)) continue;
      this.cache.markSeen(addr);
      fresh.push(pair);
    }

    if (fresh.length) {
      console.log(`[launchpad] ${fresh.length} new listing(s)`);
    }
    return fresh;
  }

  cleanupCache(): void {
    const removed = this.cache.cleanup();
    if (removed) console.log(`[launchpad] cache: removed ${removed} expired entries`);
  }

  // ── Extension stubs ─────────────────────────────────────────────────────────
  // Replace with real implementations when ready.

  async honeypotCheck(_tokenAddress: string): Promise<{ isHoneypot: boolean; reason: string | null }> {
    // TODO: call honeypot.is or similar API
    return { isHoneypot: false, reason: null };
  }

  async whaleTracking(_pairAddress: string): Promise<Record<string, unknown>[]> {
    // TODO: scan recent large txs via TonAPI
    return [];
  }

  async devWalletAnalysis(_tokenAddress: string): Promise<Record<string, unknown>> {
    // TODO: delegate to DevWalletAnalyzer
    return {};
  }
}

// ── Keyboards ─────────────────────────────────────────────────────────────────

function launchpadKeyboard(): InlineKeyboard {
  return new InlineKeyboard()
    .text("🔄 Обновить",   "listing:refresh").row()
    .text("📊 Top tokens",  "dex:top").text("🚀 Новый листинг", "dex:listing").row()
    .text("⚠️ Risk Analysis","dex:risk").text("🔔 Alerts",        "dex:alerts").row()
    .text("◀️ Назад",       "dex");
}

function launchpadDetailKeyboard(index: number): InlineKeyboard {
  return new InlineKeyboard()
    .text("🔄 Обновить",   `listing:detail:${index}`)
    .text("◀️ Назад",      "dex:listing");
}

// ── Handlers ──────────────────────────────────────────────────────────────────

/**
 * Register launchpad handlers on the bot.
 *
 * @example
 *   import { LaunchpadService, registerLaunchpadHandlers } from "./modules/dex/new-listing/handler";
 *   const launchpad = new LaunchpadService();
 *   registerLaunchpadHandlers(bot, launchpad);
 */
export function registerLaunchpadHandlers(
  bot: Bot<Context>,
  service: LaunchpadService,
): void {
  // ── /listing command ───────────────────────────────────────────────────────
  bot.command("listing", async (ctx) => {
    const listings = await service.getAllListings(10);
    await ctx.reply(formatListingsSummary(listings), {
      parse_mode: "HTML",
      reply_markup: launchpadKeyboard(),
      link_preview_options: { is_disabled: true },
    });
  });

  // ── dex:listing callback ───────────────────────────────────────────────────
  bot.callbackQuery("dex:listing", async (ctx) => {
    await ctx.answerCallbackQuery("Загружаю…");
    const listings = await service.getAllListings(10);
    await ctx.editMessageText(formatListingsSummary(listings), {
      parse_mode: "HTML",
      reply_markup: launchpadKeyboard(),
      link_preview_options: { is_disabled: true },
    });
  });

  // ── listing:refresh callback ───────────────────────────────────────────────
  bot.callbackQuery("listing:refresh", async (ctx) => {
    await ctx.answerCallbackQuery("Обновляю…");
    const listings = await service.getAllListings(10);
    await ctx.editMessageText(formatListingsSummary(listings), {
      parse_mode: "HTML",
      reply_markup: launchpadKeyboard(),
      link_preview_options: { is_disabled: true },
    });
  });

  // ── listing:detail:{index} callback ───────────────────────────────────────
  bot.callbackQuery(/^listing:detail:(\d+)$/, async (ctx) => {
    const index = parseInt(ctx.match[1], 10);
    await ctx.answerCallbackQuery("Загружаю…");

    const listings = await service.getAllListings(10);
    if (!listings.length || index >= listings.length) {
      await ctx.editMessageText(
        "<b>New Listings</b>\n\nТокен недоступен — список обновился.",
        { parse_mode: "HTML", reply_markup: launchpadKeyboard() }
      );
      return;
    }

    const pair = listings[index];
    await ctx.editMessageText(formatListing(pair), {
      parse_mode: "HTML",
      reply_markup: launchpadDetailKeyboard(index),
      link_preview_options: { is_disabled: true },
    });
  });
}

// ── Background alert worker ───────────────────────────────────────────────────

export interface AlertConfig {
  /** Comma-separated chat IDs to send alerts to. */
  chatIds: (number | string)[];
  /** Only alert for listings with risk level >= this value. */
  minRiskLevel?: "Low" | "Medium" | "High";
  /** Poll interval in ms (default 20 s). */
  intervalMs?: number;
}

const RISK_ORDER: Record<string, number> = { Low: 0, Medium: 1, High: 2 };

/**
 * Start a background alert loop.  Returns a cleanup function.
 *
 * @example
 *   const stop = startAlertWorker(bot, launchpad, {
 *     chatIds: [123456789],
 *     minRiskLevel: "Medium",
 *     intervalMs: 20_000,
 *   });
 *   // call stop() to cancel
 */
export function startAlertWorker(
  bot: Bot<Context>,
  service: LaunchpadService,
  config: AlertConfig,
): () => void {
  const { chatIds, minRiskLevel = "Low", intervalMs = 20_000 } = config;
  const minOrder = RISK_ORDER[minRiskLevel] ?? 0;

  const timer = setInterval(async () => {
    try {
      const fresh = await service.popNewListings();

      for (const pair of fresh) {
        const { level } = require("./analyzer").calculateRisk(pair);
        if ((RISK_ORDER[level] ?? 0) < minOrder) continue;

        const text = formatListingAlert(pair);
        for (const chatId of chatIds) {
          await bot.api.sendMessage(chatId, text, {
            parse_mode: "HTML",
            link_preview_options: { is_disabled: true },
          });
        }
      }

      // Clean cache periodically (every ~10 ticks)
      if (Math.random() < 0.1) service.cleanupCache();
    } catch (err) {
      console.error("[launchpad] alert worker error:", err);
    }
  }, intervalMs);

  return () => clearInterval(timer);
}
