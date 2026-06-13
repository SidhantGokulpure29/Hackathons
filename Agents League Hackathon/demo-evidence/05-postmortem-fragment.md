# Draft Postmortem Fragment

The payment gateway adapter release 3.18.0 changed retry behavior for authorization calls.

The changed retry behavior increased concurrent writes to the payment ledger during gateway slowness.

The payment ledger writer exhausted the database connection pool in East US and West Europe.

Rollback to 3.17.4 reduced timeout rates and restored most checkout traffic.

The team still needs gateway vendor latency data to confirm whether external slowness triggered the retry storm.
