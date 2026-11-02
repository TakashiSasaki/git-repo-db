# Durable Operational accounting

Owns WorkLedger, NotesWorkBudget, continuation/checkpoint adapters and opt-in
Operational DDL. Depends only on runtime/contracts. Installation creates no DBs;
explicit initialization is separate. Existing requests refuse missing/replaced or
inconsistent accounting. This package grants no authority acquisition capability.
