// handlers/message.js — Vilona AI v2 command router (runs on Telegram infra).
// Registration + admin flow lives here; trading data is proxied to the Python
// backend (OUTBOUND_URL, see README section "Trading backend").
import { api, db } from 'sdk';
import { eq, and } from 'sdk/db';
import { users } from '../schema.js';

const HELP = `Vilona AI commands:

/start — register / login
/status — positions and daily P/L (your account)
/balance — account balance (your account)
/setkeys <exchange> <key> <secret> — connect your own exchange
/help — this message
Approval (admin):
/users — list registered users
/approve <chat_id> — approve pending registration
/decline <chat_id> — remove a registration`;

function esc(s) {
  return String(s ?? '').replace(/([_*\[\]()~`>#+\-=|{}.!\\])/g, '\\$1');
}

async function getRow(chatId) {
  const rows = await db.select().from(users).where(eq(users.chatId, chatId)).all();
  return rows[0] ?? null;
}

async function ensureAdminIfFirst(chatId, username, firstName) {
  const count = await db.$count(users);
  const isAdmin = count === 0;
  await db.insert(users)
    .values({
      chatId, username: username ?? '', firstName: firstName ?? '',
      isAdmin, approved: isAdmin,
    })
    .onConflictDoNothing()
    .run();
  return isAdmin;
}

export default async function (message, ctx) {
  const chatId = message.chat?.id;
  if (!chatId) return;
  const text = (message.text ?? '').trim();
  const [cmdRaw, ...args] = text.split(/\s+/);
  const cmd = (cmdRaw ?? '').toLowerCase().replace(/^\//, '').split('@')[0];
  const from = message.from ?? {};

  const user = await getRow(chatId);

  // ---------- /start: register ----------
  if (cmd === 'start') {
    if (!user) {
      const first = await ensureAdminIfFirst(chatId, from.username, from.first_name);
      if (first) {
        await api.sendMessage({
          chat_id: chatId, parse_mode: 'MarkdownV2',
          text: `*Vilona AI v2* first-time setup complete\\.\n\n`
              + `You are registered as *admin* — approve others with \`/approve <chat_id>\`\\.`,
        });
      } else {
        await api.sendMessage({
          chat_id: chatId, parse_mode: 'MarkdownV2',
          text: `*Vilona AI v2*\n\nRegistration received\\.\n\n`
              + `⚠️ *Pending approval* — an admin must approve you first\\.\n`
              + `Your chat ID: \`${chatId}\`\n\nTry /start again after approval\\.`,
        });
      }
      return;
    }
    if (!user.approved) {
      await api.sendMessage({
        chat_id: chatId, parse_mode: 'MarkdownV2',
        text: `⚠️ *Pending approval*\\nYour chat ID: \`${chatId}\``,
      });
      return;
    }
    await api.sendMessage({
      chat_id: chatId, parse_mode: 'MarkdownV2',
      text: `*Vilona AI v2* is online\\.\n\n` +
            (user.firstName ? `Welcome back, ${esc(user.firstName)}\\! ` : 'Welcome back\\! ') +
            `Commands: /help`,
    });
    return;
  }

  // ---------- guard: everything below requires approval ----------
  const legacyAllowed = false; // legacy allowlist handled by Python backend
  if (!user || !user.approved) {
    if (cmd !== 'help') {
      await api.sendMessage({ chat_id: chatId, text: 'Register first via /start. Pending admin approval.' });
    }
    return;
  }

  const isAdmin = !!user.isAdmin;

  if (cmd === 'help') {
    await api.sendMessage({ chat_id: chatId, text: HELP });
    return;
  }

  // ---------- admin commands ----------
  if (cmd === 'users') {
    if (!isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    const all = await db.select().from(users).orderBy(users.registeredAt).all();
    const lines = ['Registered users:'];
    for (const u of all) {
      const st = u.isAdmin ? 'admin' : (u.approved ? 'active' : 'pending');
      lines.push(`• ${u.chatId} — ${u.username || u.firstName || '?'} [${st}]`);
    }
    await api.sendMessage({ chat_id: chatId, text: lines.join('\n') });
    return;
  }

  if (cmd === 'approve') {
    if (!isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    if (!args[0]) { await api.sendMessage({ chat_id: chatId, text: 'Usage: /approve <chat_id>' }); return; }
    const target = parseInt(args[0], 10);
    const res = await db.update(users).set({ approved: true }).where(eq(users.chatId, target)).run();
    await api.sendMessage({ chat_id: chatId, text: res?.rowsAffected ? `Approved ${target}.` : `${target} not found.` });
    if (res?.rowsAffected) {
      try { await api.sendMessage({ chat_id: target, text: '✅ Your registration was approved. Use /start.' }); } catch {}
    }
    return;
  }

  if (cmd === 'decline') {
    if (!isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    if (!args[0]) { await api.sendMessage({ chat_id: chatId, text: 'Usage: /decline <chat_id>' }); return; }
    const target = parseInt(args[0], 10);
    const res = await db.delete(users).where(eq(users.chatId, target)).run();
    await api.sendMessage({ chat_id: chatId, text: res?.rowsAffected ? `Removed ${target}.` : `${target} not found.` });
    return;
  }

  // ---------- per-user exchange credentials ----------
  if (cmd === 'setkeys') {
    if (args.length < 3) {
      await api.sendMessage({ chat_id: chatId, text: 'Usage: /setkeys <exchange> <api_key> <api_secret>' });
      return;
    }
    await db.update(users).set({
      exchangeName: args[0], exchangeApiKey: args[1], exchangeApiSecret: args[2],
    }).where(eq(users.chatId, chatId)).run();
    await api.sendMessage({ chat_id: chatId, text: `Credentials saved for ${args[0]}.` });
    return;
  }

  if (cmd === 'setbackend') {
    if (!isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    if (!args[0]) {
      const row = await getRow(chatId);
      await api.sendMessage({ chat_id: chatId, text: `Backend URL: ${row?.outBoundUrl || '(not set)'}` });
      return;
    }
    await db.update(users).set({ outBoundUrl: args[0] }).where(eq(users.chatId, chatId)).run();
    await api.sendMessage({ chat_id: chatId, text: `Backend URL set to: ${args[0]}` });
    return;
  }

  // trading commands proxy to Python backend (per-user URL, else env)
  const backend = user.outBoundUrl || process.env.OUTBOUND_URL;
  if (backend && (cmd === 'balance' || cmd === 'status')) {
    try {
      const resp = await fetch(`${backend}/api/${cmd === 'status' ? 'status' : 'balance'}?chat_id=${chatId}`, {
        headers: { 'X-User-Key': String(chatId) },
      });
      const data = await resp.json();
      await api.sendMessage({
        chat_id: chatId, parse_mode: 'MarkdownV2',
        text: `*${cmd === 'status' ? '📊 Status' : '💰 Balance'}*\n\n` +
              Object.entries(data).map(([k, v]) => `*${esc(k)}:* \`${esc(String(v))}\``).join('\n'),
      });
    } catch (e) {
      await api.sendMessage({ chat_id: chatId, text: `Backend unreachable: ${e.message}` });
    }
    return;
  }
}