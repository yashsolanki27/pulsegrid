# Stack

- Language: Python 3.11+
- Backend framework: FastAPI (for CRM service, ERP service, and the observability webhook receiver)
- Database: PostgreSQL (one instance per service — separate DBs for CRM and ERP, not shared schema)
- API testing: Postman + Newman CLI
- Observability: Prometheus, Grafana, Loki, Alertmanager
- Auth: Microsoft Graph API + Azure AD (OAuth2 Authorization Code flow, MSAL library)
- Infra: Docker + Docker Compose (local dev, no orchestration platform like K8s planned for v1)
- CI: GitHub Actions (for scheduled API health checks)
- External dependency: LogPulse — separate already-deployed FastAPI service on Railway (`https://log-pulse.up.railway.app`); PulseGrid calls it via HTTP, does not modify it
