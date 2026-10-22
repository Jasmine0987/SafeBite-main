# Deploying SafeBite (closed beta)

One container serves both the API and the static frontend, so the browser only talks to one origin.

1. `docker build -t safebite .` (repo root). The image installs Tesseract and libzbar0.
2. Run it behind HTTPS. Most hosts (Render, Fly.io, Railway, a VPS with Caddy or nginx) terminate TLS for you and forward `X-Forwarded-Proto: https`; the API then sends the HSTS header automatically.
3. Mount a persistent volume at `/data` (the SQLite file lives there) and back it up.
4. Ollama is optional. Without it only `/explain-*` returns 503. To enable it, run Ollama as a second service and set `OLLAMA_BASE_URL`.
5. Check: `GET /health`, then sign up (the consent box is required), scan, and use "Report a problem".

Already in place: salted PBKDF2 passwords, 30-day session expiry, per-user data, 10 MB upload limit, security headers, CORS allow-list (no wildcard).

Not covered here, still your job: rate limiting on `/api/auth/*` and `/api/scan` (put it in the reverse proxy), account-deletion tooling, database backups, and a legal review of `frontend/terms.html`.
Untested here: the Dockerfile itself (no Docker in the sandbox this was written in).
