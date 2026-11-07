# Optional selective Exchange

Canonical bounded v8 Exchange protocol, Core export and reception. Export installs
Core/runtime/contracts only. Reception additionally requires an explicitly installed
Operational distribution and initialized durable ledger. Context validation and
paired admission remain explicit optional capabilities when topology or any
supplied section requires them; absence refuses rather than skipping validation.
Installation never creates databases. No sender authentication is claimed.
