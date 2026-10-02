# Gaming Platform Frontend

React, TypeScript, and Vite client for the Gaming Platform backend.

## Local development

```powershell
npm ci
$env:VITE_API_BASE_URL = "http://localhost:8000/api/v1"
$env:VITE_WS_URL = "ws://localhost:8000/ws"
npm run dev
```

The API base URL must include `/api/v1`; the WebSocket URL is the backend `/ws`
root. Authentication uses an access token in memory and an HTTP-only refresh
cookie. Game actions and outcomes are submitted to/received from the backend;
the UI does not generate game results locally.

## Checks

```powershell
npm run lint
npm run build
```

## Render

The Render blueprint is `../backend/render.yaml` and includes a static frontend
service. Set `VITE_API_BASE_URL` to `https://<api-host>/api/v1` and
`VITE_WS_URL` to `wss://<api-host>/ws` in that service. Add the frontend origin
to API `CORS_ORIGINS`. GitHub Actions deploys after CI on `main` using Render
deploy-hook secrets; see `../backend/DEPLOYMENT.md`.
