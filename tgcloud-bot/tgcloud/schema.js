import { table, integer, text, boolean, sql } from 'sdk/db';

export const users = table('users', {
  chatId: integer('chat_id').primaryKey(),
  username: text('username').default(''),
  firstName: text('first_name').default(''),
  isAdmin: boolean('is_admin').default(false),
  approved: boolean('approved').default(false),
  registeredAt: integer('registered_at', { mode: 'timestamp' }).default(sql`(unixepoch())`),
  exchangeName: text('exchange_name').default('binance'),
  outBoundUrl: text('out_bound_url').default(''),
  exchangeApiKey: text('exchange_api_key').default(''),
  exchangeApiSecret: text('exchange_api_secret').default(''),
  exchangeSandbox: boolean('exchange_sandbox').default(false),
});

// Central relay config (stored in DB because TGCloud V8 has no `process.env`).
// Admin sets this once via `/setup_relay <url> <token>`; every handler reads it.
export const settings = table('settings', {
  key: text('key').primaryKey(),
  value: text('value').notNull(),
});
