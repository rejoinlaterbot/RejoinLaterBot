# Architecture

## Boundaries

- `telegram/routers`: aiogram commands, callbacks, membership events, transient FSM.
- `services/telegram_access.py`: fresh permissions and fail-closed public identity.
- `services/delivery.py`: Managed invites, public fallback, block/pause handling.
- `db/repository.py`: encryption-aware persistence, hard deletion, atomic counters.
- `crypto.py`: AES-256-GCM and blind-index HMAC.
- `app.py`: long-polling composition. A webhook entry point can reuse all services.

The FSM uses process memory only for incomplete wizard choices. Restarting loses an
unfinished wizard but not a confirmed return. Confirmed returns live only in
PostgreSQL; no future timer/task is created for an individual row.

## Database schema

`break_records` contains a UUID, mode, visibility, encrypted user/chat IDs, HMAC blind
indexes, optional encrypted public locator, UTC return timestamp, delivery mark/method,
and pause state. `(user_lookup_hash, chat_lookup_hash)` is unique. There are no title,
profile, message, completion-history, or deletion-history columns.

`user_preferences` contains only an encrypted user ID, its blind index, and locale.
`aggregate_counters` contains only counter key/value pairs.

The due query uses:

```sql
SELECT *
FROM break_records
WHERE return_at <= NOW()
  AND delivery_sent = FALSE
  AND delivery_paused = FALSE
ORDER BY return_at
LIMIT 100
FOR UPDATE SKIP LOCKED;
```

`ix_break_due_pending` is a partial B-tree on `return_at` with the two false predicates.
On production-like data, verify it after `ANALYZE break_records` with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM break_records
WHERE return_at <= NOW() AND delivery_sent = FALSE AND delivery_paused = FALSE
ORDER BY return_at LIMIT 100;
```

## Delivery state machine

Managed delivery first rechecks Invite Users and membership. A current member causes
hard deletion. A non-member receives a one-person expiring invite. Lost permission
uses a public locator only after its current ID matches the original. Without a safe
fallback the row is paused and retried after a bot-permission event.

Public Reminder validates the current ID, sends a normal `t.me` link, commits
`delivery_sent=true`, and hard-deletes in a separate transaction. A startup cleanup
removes a marked row left by a crash. Managed public fallback uses the same protocol.

## Username reassignment defense

If the stored username resolves to another chat ID, delivery fails closed and no
lookup-by-original-ID escape hatch is used. Only when the old username cannot resolve
at all may a best-effort `getChat(original_chat_id)` supply a new username, and only
when the returned ID is exactly the original. A changed title is irrelevant.
