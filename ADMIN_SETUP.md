# Telegram administrator setup

Add RejoinLaterBot as an administrator only in groups that should support Managed
Return. Grant exactly:

- **Invite Users** (`can_invite_users`)

RejoinLaterBot needs the Invite Users permission only to create a new invitation when
a scheduled return becomes available. It does not need Ban Users, Delete Messages,
Change Group Info, Pin Messages, Manage Topics, or Promote Members.

Users first open the bot privately and run `/add`. Telegram's native picker does not
request that the bot be added or promoted. After the user chooses a group, the bot
checks its existing membership, administrator status, and `Invite Users`. When all
three pass, it completes Managed Return privately and checks the permission again
immediately before invite creation. When they do not pass, a verified public link is
offered only for a public group. A private group requires the administrator setup above.

For reliable early-return deletion, keep Telegram chat-member updates enabled for the
bot. If Invite Users is restored after an overdue private-group return, the
`my_chat_member` update wakes the database scheduler.
