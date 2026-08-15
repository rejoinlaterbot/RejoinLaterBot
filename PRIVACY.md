# Privacy Policy for the official RejoinLaterBot

Last updated: August 15, 2026

This policy describes data processing by the official hosted Telegram bot
`@RejoinLaterBot` (the **Service**), operated by the RejoinLaterBot project
maintainers. It does not cover independent deployments or forks; their operators are
responsible for their own privacy practices.

RejoinLaterBot follows data minimization: privacy takes priority over analytics,
debugging convenience, and optional features. It is a scheduler for unfinished
returns, not an archive of groups a person has left.

## Data the Service processes

When you start the bot, select a group, or schedule a return, the Service processes:

- your numeric Telegram user ID;
- the numeric Telegram chat ID of the selected group;
- your selected interface language;
- the return timestamp, Hidden/Visible choice, private-invitation/public-link mode,
  and delivery state;
- the group's public Telegram username when a public link or public fallback is
  needed;
- commands, button selections, the selected whole-number custom duration, and
  Telegram membership or administrator-status responses needed to perform the
  requested action.

The user ID, chat ID, and public group username are encrypted at rest with
AES-256-GCM. HMAC-SHA-256 pseudonymous lookup hashes of user and chat IDs allow the
Service to find pending records without storing searchable plaintext IDs.

Telegram may provide a group title while the bot checks a group or prepares a visible
notification. The title is used only in memory and is not persisted, cached, or
included in application logs.

## Data the Service does not store

The Service does not store:

- group names, descriptions, avatars, or message history;
- your Telegram username, first name, last name, or phone number;
- completed-return or membership history;
- private invitation URLs or message contents;
- the exact number entered for a custom duration in aggregate analytics.

Private invitation URLs are created in memory and sent through Telegram. They are not
written to the Service database or application logs.

## Why data is processed

The Service uses this data only to:

- remember your language and activate private delivery;
- schedule, display, and deliver the return you requested;
- verify current bot permissions and group identity;
- prevent a reassigned public username from opening the wrong group;
- maintain security, reliability, and privacy-safe aggregate service statistics.

The Service does not sell personal data, use it for advertising, or build profiles of
the groups you use.

## Aggregate statistics and operational logs

The Service keeps all-time counters for visibility choice, predefined duration
bucket, delivery mode, and use of public fallback. These counters contain no user ID,
chat ID, return-record ID, username, or operation timestamp. A custom duration
increments only `duration_custom`; its exact value is not copied to analytics.

Application logs are restricted to operational event names, timestamps, generated
return-record UUIDs, counts, and normalized error types. They must not contain
Telegram IDs, usernames, group titles, invite URLs, messages, or Telegram API error
text. Operational logs are retained only as needed for service security and
reliability.

## Retention and deletion

Pending return records are kept until one of these events occurs:

- an observable return to a managed group permanently deletes the record;
- an immediate return selected from `/status` permanently deletes the record;
- successful delivery of a validated public link marks the record delivered and then
  permanently deletes it;
- an unavailable public destination is reported and the public-link record is
  permanently deleted.

If the bot is blocked, or a private group no longer grants the required permission,
the return may remain pending so delivery can resume after access is restored. Deleting
the Telegram conversation does not cancel a pending return.

The encrypted user ID and selected language in the preference record remain while
needed to operate private delivery and preserve your settings. To request deletion,
follow the contact process below.

There is no soft deletion or completed-return archive. Hard-deleted rows may remain
temporarily in encrypted backups made before deletion. Production backups must be
removed after the configured retention period, which is seven days by default.

Aggregate counters cannot be connected to a person and are kept indefinitely.

## Service providers and disclosures

Telegram processes bot interactions and delivers messages under Telegram's own terms
and privacy policy. Hosting, database, backup, and security providers may process
encrypted or operational data only as needed to run the Service. The maintainers may
also disclose information when required by law or when reasonably necessary to
protect users, the Service, or the public.

## Security

Encryption and lookup-HMAC keys are kept outside PostgreSQL, Git, and the container
image. Backups must be encrypted and stored separately from encryption keys. No
internet service can guarantee absolute security, but the project is designed to
minimize the data exposed by a failure.

Report security vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

## Your choices and requests

You may stop using the Service at any time. Removing the conversation does not delete
pending records, and blocking the bot can prevent delivery.

For a privacy or deletion request, open an issue at the
[project repository](https://github.com/rejoinlaterbot/RejoinLaterBot/issues) asking
the maintainers to establish a private contact channel. Do not post Telegram IDs,
invite links, or other personal data in a public issue. The maintainers may need to
verify that a request relates to your Telegram account before acting on it.

## Changes to this policy

This policy may change when the Service or legal requirements change. Material
updates will be published in the repository with a new “Last updated” date.
