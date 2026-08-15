# Contributing

By submitting a contribution to this repository,
you agree that your contribution will be licensed
under the Apache License 2.0.
Please only submit code that you have the right to contribute.

Use Python 3.12+, small focused pull requests, and tests for behavior changes. Run:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

All user-facing text belongs in every JSON catalog. Never log or persist an aiogram
Update, Message, Chat, User, CallbackQuery, public username, title, invite URL, or
message text. New persistence fields require a privacy justification and migration.
Completed-return history and soft deletion are out of scope by design.

Security-sensitive changes must include reassignment/fail-closed tests. Public-link
delivery must prove current chat ID equality; matching an old username string is not
proof.

See the full [Apache License 2.0](LICENSE) and report vulnerabilities according to
[SECURITY.md](SECURITY.md).
