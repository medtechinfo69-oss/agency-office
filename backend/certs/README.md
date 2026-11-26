# Supabase shared-pooler public root CA

Public certificate, not a secret. Downloaded from the Supabase-published URL:
https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

SHA-256 DER fingerprint:
`807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`

The adapter uses it only for `*.pooler.supabase.com` when the connection string
has no explicit CA path (or says `sslrootcert=system`). It enforces
`sslmode=verify-full`; it never disables certificate or hostname verification.
