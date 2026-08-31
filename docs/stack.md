# Stack

- Language: Python 3.11+
- Backend framework: FastAPI (for CRM service, ERP service, and the observability webhook receiver)
- Database: PostgreSQL (one instance per service — separate DBs for CRM and ERP, not shared schema)
- API testing: Postman + Newman CLI
- Observability: Prometheus, Grafana, Loki, Alertmanager
- Auth: Microsoft Graph API + Azure AD (OAuth2 Authorization Code flow, MSAL library)
- Infra: Docker + Docker Compose (local dev, no orchestration platform like K8s planned for v1)
- CI: GitHub Actions (for scheduled API health checks)
- UI component library: Tabler (v1.4.0) — open-source Bootstrap 5 admin template, loaded via CDN (no build step). CSS: `https://cdn.jsdelivr.net/npm/@tabler/core@1.4.0/dist/css/tabler.min.css`, JS: `https://cdn.jsdelivr.net/npm/@tabler/core@1.4.0/dist/js/tabler.min.js`, Icons: `https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@latest/tabler-icons.min.css`. Chosen for: zero-dependency CDN approach (fits FastAPI+Jinja2 constraint), built-in dark mode (`data-bs-theme="dark"`), pre-built sidebar/table/card/badge components (eliminates custom CSS for Phase 8 screens). MIT license.
- External dependency: LogPulse — separate already-deployed FastAPI service on Railway (`https://log-pulse.up.railway.app`); PulseGrid calls it via HTTP, does not modify it
