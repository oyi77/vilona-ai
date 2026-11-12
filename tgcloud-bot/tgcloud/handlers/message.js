// handlers/message.js — Vilona AI v2 command router (runs on Telegram infra).
// Registration + admin flow lives here; trading/runtime commands are routed
// through the central relay (RELAY_URL + RELAY_BOT_TOKEN env) to the user's
// outbound desktop client. See README "Multi-tenancy architecture".
import { api, db } from 'sdk';
import { eq, and } from 'sdk/db';
import { users, settings } from '../schema.js';

const HELP = `Vilona AI commands:

/start — register / login
/devices — your paired desktop clients + status
/license — license status of your devices
/status — positions and daily P/L (async, from your desktop)
/balance — account balance (async, from your desktop)
/setkeys — configure exchange keys LOCALLY in the desktop app
/pair <name> — generate a pairing token for a desktop client
/setup_relay <url> <token> — admin: set central relay
/help — this message
Runtime (your desktop must be online):
/start_scan — start trading engine
/stop_scan — stop trading engine
/emergency_stop — immediately halt
/emergency_reset — admin confirmation required
Approval (admin):
/users — list registered users
/approve <chat_id> — approve pending registration
/decline <chat_id> — remove a registration`;

function esc(s) {
  return String(s ?? '').replace(/([_*\[\]()~`>#+\-=|{}.!\\])/g, '\\$1');
}

// ---- Central relay (control plane) -------------------------------------
// Desktop binaries phone home to RELAY_URL; this bot drives them through the
// same server. Server-to-server auth uses RELAY_BOT_TOKEN.
// Values are stored in the `settings` table because TGCloud's V8 isolate has
// no `process.env`. Admin sets them once via `/setup_relay <url> <token>`.

const SETTING_KEYS = { url: 'relay_url', token: 'relay_bot_token' };

async function loadRelayConfig() {
  const rows = await db.select().from(settings).all();
  const map = Object.fromEntries(rows.map(r => [r.key, r.value]));
  return {
    url: (map[SETTING_KEYS.url] || '').replace(/\/+$/, ''),
    token: map[SETTING_KEYS.token] || '',
  };
}

async function relayReady() {
  const { url, token } = await loadRelayConfig();
  return !!(url && token);
}

async function relay(method, path, body) {
  const { url, token } = await loadRelayConfig();
  const opts = { method, headers: { 'X-Relay-Token': token } };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(`${url}${path}`, opts);
  const text = await res.text();
  let data = null;
  try { data = JSON.parse(text); } catch { /* non-json */ }
  if (!res.ok) {
    const detail = data?.detail || text.slice(0, 200);
    throw new Error(`relay ${method} ${path} -> ${res.status}: ${detail}`);
  }
  return data ?? {};
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
  // Under the relay model, MT5/exchange keys live ONLY on the user's desktop
  // binary. Never accept or store secrets in chat/cloud.
  if (cmd === 'setkeys') {
    await api.sendMessage({
      chat_id: chatId,
      text: 'Exchange/API keys are configured locally in the Vilona desktop app '
          + '(Settings → Account). They are never sent through Telegram or stored on the server.',
    });
    return;
  }

  if (cmd === 'setbackend') {
    await api.sendMessage({
      chat_id: chatId,
      text: 'Not needed — the desktop app connects outbound to the central relay automatically. '
          + 'Pair a device with /pair <name>.',
    });
    return;
  }

  // ---------- admin: configure central relay (stored in DB, no env needed) --
  if (cmd === 'setup_relay') {
    if (!isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    if (args.length < 2) {
      const { url } = await loadRelayConfig();
      await api.sendMessage({ chat_id: chatId, text: `Usage: /setup_relay <relay_url> <relay_bot_token>\nCurrent URL: ${url || '(not set)'}` });
      return;
    }
    const url = args[0].replace(/\/+$/, '');
    const token = args.slice(1).join(' ').trim();
    await db.insert(settings).values({ key: SETTING_KEYS.url, value: url }).onConflictDoUpdate({ target: settings.key, set: { value: url } }).run();
    await db.insert(settings).values({ key: SETTING_KEYS.token, value: token }).onConflictDoUpdate({ target: settings.key, set: { value: token } }).run();
    await api.sendMessage({ chat_id: chatId, text: `Relay configured: ${url}` });
    return;
  }

  // ---------- device pairing (any approved user) ----------
  if (cmd === 'pair') {
    if (!(await relayReady())) { await api.sendMessage({ chat_id: chatId, text: 'Relay not configured on server.' }); return; }
    const name = args.join(' ').slice(0, 64) || 'desktop';
    try {
      const d = await relay('POST', '/relay/pair', { chat_id: chatId, name });
      await api.sendMessage({
        chat_id: chatId, parse_mode: 'MarkdownV2',
        text: `Pairing token for *${esc(name)}*:\n\`\`\`${d.token}\`\`\`\n\n`
            + `⚠️ *Shown once — keep it secret.* Put it in the desktop app config `
            + `(\`vilona_RELAY_DEVICE_TOKEN\`) and restart it.`,
      });
    } catch (e) {
      await api.sendMessage({ chat_id: chatId, text: `Pair failed: ${e.message}` });
    }
    return;
  }

  if (cmd === 'devices' || cmd === 'license') {
    if (!(await relayReady())) { await api.sendMessage({ chat_id: chatId, text: 'Relay not configured on server.' }); return; }
    try {
      const st = await relay('GET', `/relay/status/${chatId}`);
      const devs = st.devices || [];
      if (!devs.length) { await api.sendMessage({ chat_id: chatId, text: 'No devices paired. Use /pair <name>.' }); return; }
      const lines = devs.map(d => {
        const seen = d.last_seen ? d.last_seen.replace('T', ' ').slice(0, 19) : 'never';
        return `• ${d.name || d.device_id.slice(0, 8)} — ${d.license_status} — last seen ${seen}`;
      });
      if (cmd === 'license') {
        await api.sendMessage({ chat_id: chatId, text: `Licenses:\n${lines.join('\n')}` });
      } else {
        await api.sendMessage({ chat_id: chatId, text: `Devices (${devs.length}):\n${lines.join('\n')}\nPending commands: ${st.pending_commands ?? 0}` });
      }
    } catch (e) {
      await api.sendMessage({ chat_id: chatId, text: `Status failed: ${e.message}` });
    }
    return;
  }

  // ---------- runtime / trading commands (routed to desktop via relay) ----
  const OP_BY_CMD = {
    status: 'status', balance: 'balance',
    start_scan: 'runtime.start', stop_scan: 'runtime.stop',
    emergency_stop: 'runtime.emergency_stop', emergency_reset: 'runtime.emergency_reset',
  };
  if (OP_BY_CMD[cmd]) {
    if ((cmd === 'emergency_reset') && !isAdmin) { await api.sendMessage({ chat_id: chatId, text: 'Admin only' }); return; }
    if (!(await relayReady())) { await api.sendMessage({ chat_id: chatId, text: 'Relay not configured on server.' }); return; }
    const opArgs = cmd === 'emergency_stop' ? { reason: args.join(' ') || 'emergency stop from Telegram' } : {};
    try {
      const r = await relay('POST', '/relay/command', { chat_id: chatId, op: OP_BY_CMD[cmd], args: opArgs });
      const label = { status: '📊 Status', balance: '💰 Balance', 'runtime.start': '▶️ Start',
                      'runtime.stop': '⏹ Stop', 'runtime.emergency_stop': '🛑 Emergency stop',
                      'runtime.emergency_reset': '🔓 Reset' }[OP_BY_CMD[cmd]] || OP_BY_CMD[cmd];
      await api.sendMessage({
        chat_id: chatId,
        text: `${label} queued for ${(r.command_ids || []).length} device(s). Results appear in /devices shortly — your desktop must be online.`,
      });
    } catch (e) {
      await api.sendMessage({ chat_id: chatId, text: `${cmd} failed: ${e.message}` });
    }
    return;
  }
}