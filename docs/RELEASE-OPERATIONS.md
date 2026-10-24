# Public-mode preparation

Prepared configuration is reviewable in deploy/Caddyfile, deploy/kyp.service and deploy/environment.example. Nothing has been published or installed as a system service.

## Runtime configuration

`KYP_PUBLIC_MODE=1` requires PostgreSQL, an HTTPS `KYP_PUBLIC_ORIGIN` and a random `KYP_OPERATION_SECRET` of at least 32 characters. Keep the same secret on every worker and restart; rotating it invalidates existing capabilities. Keep secrets outside source control in a protected environment file. A public-mode SQLite start fails deliberately.

Public mode creates separate ephemeral scan_sessions/request_buckets tables alongside the catalog; catalog schema remains v3. Session migration is intentionally excluded from catalog migration. Capabilities are HMAC hashed. Stored session fields are random ID, hashed capability, expiry, scalar OCR quality and parsing-mode metadata. Image/label text is never stored. Sessions expire after 30 minutes; a background sweep removes expired records approximately once per minute while healthy. Rate buckets contain keyed hashes rather than raw client IPs and expire at the minute boundary.

Requests share counters across workers: 6 image/orientation requests and 120 other requests per client per minute. Counters are atomic; 429 responses include Retry-After. These fixed-window limits are an initial guard, not a completed abuse/load assessment. Confirm proxy trust and actual client IP behavior during deployment testing.

The example systemd service binds Uvicorn to 127.0.0.1:8001 with two workers and trusts forwarded headers only from localhost. Caddy is the HTTPS entry point and bounds request bodies. Do not expose that upstream port or trust arbitrary proxy addresses. Set the actual KYP_DOMAIN when provisioning Caddy. API access logs are disabled in the service; do not add body/capability logging at the proxy.

Install Python requirements, Node and the locked Tesseract runtime/model before starting the restricted service. The standard runtime uses only temporary files and PostgreSQL, and loads OCR models read-only. RapidOCR is opt-in and needs its isolated dependency/model/license review before using it in a deployed runtime. Review system paths/users before installing the service example.

## Verification already run

- Real PostgreSQL integration: capabilities survive distinct API instances; HTTPS/host enforcement, no-store/HSTS and rate-limit responses pass.
- Shared counter/capability/expiry tests pass on SQLite and PostgreSQL (public serving still requires PostgreSQL).
- Caddy configuration validates in an isolated container without published ports. Validation used caddy:2 digest sha256:504a44d7d74bd2bc28a66afc4774912fc21223ca8a67734af1c54ab2f999b489. This checks configuration syntax, not a real certificate/domain.

## Before live deployment

Use a real configured domain/host, protect secrets, restrict database access, back up the reviewed catalog and rehearse restoration. Verify HTTPS/certificate renewal, proxy headers, request/upload limits, rate behavior, expiry sweeps, temporary-file cleanup, restart behavior and representative load. Complete content/dependency/device/pilot gates described in STAGE1-REMAINING-WORK.md. No clean-security or live-TLS sign-off is inferred from local tests.

Primary references: https://caddyserver.com/docs/caddyfile/directives/reverse_proxy and https://www.uvicorn.org/deployment/.
