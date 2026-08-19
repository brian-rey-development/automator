# Architecture Decision Records

Working records of the decisions that shape Automator, grounded in the current code. Status is `accepted` unless an ADR says otherwise.

| ADR | Title |
| --- | --- |
| [0001](0001-layered-architecture.md) | Layered architecture (`ui` -> `services` -> `domain`) |
| [0002](0002-filing-policy-in-domain.md) | Filing policy in `decide_filing` |
| [0003](0003-uncertain-matches-go-to-review.md) | Uncertain matches go to review |
| [0004](0004-dual-duplicate-identity.md) | Dual duplicate identity |
| [0005](0005-engine-generations.md) | Engine generations |
| [0006](0006-frozen-config-and-atomic-store.md) | Frozen config and atomic store |
| [0007](0007-parser-deterministic-defaults.md) | Parser deterministic defaults |
| [0008](0008-copy-mode-source-signatures.md) | Copy mode source signatures |
| [0009](0009-versioned-sqlite-ledger.md) | Versioned SQLite ledger |
| [0010](0010-ui-shell-controllers.md) | UI shell, views, and controllers |

Format is MADR-lite. Each file has Context, Decision, Consequences, and Alternatives considered. New ADRs get the next four-digit number and a row in this table.
