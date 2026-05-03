/**
 * Minimal integration example — Telegraf-style (grammY).
 *
 * Run:  npx tsx bot.example.ts
 */
import { Bot } from "grammy";
import {
  LaunchpadService,
  registerLaunchpadHandlers,
  startAlertWorker,
} from "./dex/new-listing/index.js";

const BOT_TOKEN = process.env.BOT_TOKEN;
if (!BOT_TOKEN) throw new Error("BOT_TOKEN env var is required");

const ADMIN_CHAT_ID = process.env.ADMIN_CHAT_ID
  ? parseInt(process.env.ADMIN_CHAT_ID, 10)
  : undefined;

const bot = new Bot(BOT_TOKEN);
const launchpad = new LaunchpadService();

// Register all dex:listing/* and /listing handlers
registerLaunchpadHandlers(bot, launchpad);

// DEX menu — add "Новый листинг" button next to existing items
bot.callbackQuery("dex", async (ctx) => {
  await ctx.answerCallbackQuery();
  const { InlineKeyboard } = await import("grammy");
  const kb = new InlineKeyboard()
    .text("📊 Top tokens",    "dex:top").row()
    .text("🚀 Новый листинг", "dex:listing").row()
    .text("⚠️ Risk Analysis", "dex:risk").row()
    .text("🔔 Alerts",        "dex:alerts").row()
    .text("◀️ Назад",         "menu");

  await ctx.editMessageText("DEX — выберите раздел:", {
    reply_markup: kb,
  });
});

// Start background alert worker (every 20 s, only Medium+ risk)
const stopAlerts = ADMIN_CHAT_ID
  ? startAlertWorker(bot, launchpad, {
      chatIds: [ADMIN_CHAT_ID],
      minRiskLevel: "Medium",
      intervalMs: 20_000,
    })
  : null;

// Graceful shutdown
process.once("SIGINT",  () => { stopAlerts?.(); bot.stop(); });
process.once("SIGTERM", () => { stopAlerts?.(); bot.stop(); });

bot.start();
console.log("Bot started");

/*
──────────────────────────────────────────────────────────────────────────────
EXAMPLE USER MESSAGE for /listing or dex:listing

🚀 New Listings (TON) — 3 found
────────────────────────────
🔴 MEMECOIN   Liq: $2.1K  Age: 1.4m  Risk: 80  DEX
🟡 NEWTOKEN   Liq: $8.5K  Age: 12.0m  Risk: 50  DEX
🟢 SOLID      Liq: $22K   Age: 18.1m  Risk: 20  DEX

[🔄 Обновить]
[📊 Top tokens] [🚀 Новый листинг]
[⚠️ Risk Analysis] [🔔 Alerts]
[◀️ Назад]

──────────────────────────────────────────────────────────────────────────────
EXAMPLE "Детально" card (listing:detail:0)

🚀 New Listing

Name: MEMECOIN (MEM)
Chain: TON
Price: $0.00000042
Liquidity: $2.1K
Volume: $180
FDV: $210K
Age: 1.4 min

Risk: 🔴 High (80/100)

Factors:
  • Low liquidity ($2,100)
  • Low 24h volume ($180)
  • FDV/Liquidity ratio 100x
  • No website or socials
  • Very fresh pair (1.4 min old)

DEX: STON.FI
Contract:
EQAbc123…
Link: DexScreener

[🔄 Обновить] [◀️ Назад]

──────────────────────────────────────────────────────────────────────────────
EXAMPLE background ALERT (Medium+ risk, sent to admin chat)

🚀 New Listing

Name: NEWTOKEN (NTK)
Liquidity: $8.5K
Volume: $900
Age: 12.0 min

Risk: 🟡 Medium (50/100)

DEX: STON.FI
Contract:
EQXyz789…
Open on DexScreener
──────────────────────────────────────────────────────────────────────────────
*/
