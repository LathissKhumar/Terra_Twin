# TerraTwin Vercel Deployment Guide

This guide details how to deploy **TerraTwin** to Vercel and connect it to the high-performance scientific geospatial backend.

---

## 1. Architecture Overview

```
                      ┌───────────────────────────────────────┐
                      │            VERCEL (EDGE/CDN)          │
                      │  Next.js 14+ Frontend (App Router)   │
                      │  • MapLibre GL 2D Geospatial Viewer   │
                      │  • Three.js 3D Terrain Twin Viewer    │
                      │  • Evidence Passport PDF/JSON UI      │
                      └──────────────────┬────────────────────┘
                                         │
                        /api/v1/* (Rewrites or Direct CORS)
                                         ▼
                      ┌───────────────────────────────────────┐
                      │    CONTAINER RUNTIME (Railway/Render)  │
                      │  FastAPI Backend (Python 3.12)        │
                      │  • GDAL / Rasterio / SciPy / NumPy    │
                      │  • ScaleBridge & Terrain Analytics    │
                      │  • Independent Validation Engine      │
                      └──────────────────┬────────────────────┘
                                         │
                                         ▼
                      ┌───────────────────────────────────────┐
                      │         POSTGRESQL 16 + POSTGIS       │
                      │  Spatial candidate indexing & jobs    │
                      └───────────────────────────────────────┘
```

> **Why Frontend on Vercel + Backend on Container?**  
> TerraTwin executes scientific terrain analytics requiring compiled C-libraries (`libgdal`, `libproj`, `libgeos`) and large planetary elevation rasters. Vercel is the world-class hosting platform for Next.js frontend applications, while the Python FastAPI backend runs in standard Docker containers.

---

## 2. Deploying the Frontend to Vercel

### Option A: Via the Vercel Web Dashboard (Recommended)

1. **Push your code** to GitHub or GitLab.
2. Go to [vercel.com/new](https://vercel.com/new) and select your **TerraTwin** repository.
3. Configure the Project Settings:
   - **Framework Preset**: `Next.js`
   - **Root Directory**: Click `Edit` and select `frontend` (or leave at `./` since root `vercel.json` is provided).
   - **Build Command**: `npm run build`
   - **Output Directory**: `.next`
   - **Install Command**: `npm install`
4. Add **Environment Variables**:
   | Variable | Value | Description |
   |---|---|---|
   | `NEXT_PUBLIC_API_URL` | `https://your-backend-domain.com/api/v1` | Public API endpoint for client queries |
   | `BACKEND_API_URL` | `https://your-backend-domain.com/api/v1` | Server-side rewrite destination (avoids CORS) |
5. Click **Deploy**.

---

### Option B: Via the Vercel CLI

From your terminal:

```bash
# Install Vercel CLI if not installed
npm i -g vercel

# Navigate to frontend
cd frontend

# Deploy preview
vercel

# Deploy to production
vercel --prod
```

When prompted:
- **Set up and deploy?**: `y`
- **Which scope?**: Select your account
- **Link to existing project?**: `n`
- **What's your project's name?**: `terratwin`
- **In which directory is your code located?**: `./` (if in `frontend/`) or `frontend` (if in project root)

---

## 3. Connecting the Backend to Vercel

### 1. Allow Vercel Domain in Backend CORS

In your backend `.env` or cloud environment settings, add your Vercel domains to `CORS_ORIGINS`:

```bash
CORS_ORIGINS=https://terratwin.vercel.app,https://terratwin-git-main-*.vercel.app,http://localhost:3000
```

### 2. Built-in Next.js Rewrites (No CORS required)

TerraTwin's `frontend/next.config.ts` includes automatic API rewrites. When you set `BACKEND_API_URL` or `NEXT_PUBLIC_API_URL` on Vercel, requests to:
```
https://your-terratwin-site.vercel.app/api/v1/health
```
are automatically proxied to:
```
https://your-backend-domain.com/api/v1/health
```

---

## 4. Deploying the Backend (to pair with Vercel)

The backend and database can be deployed using the existing `compose.production.yaml` or directly to services like **Railway**, **Render**, or **Fly.io**:

### Deploying to Railway (1-click / CLI)

1. Install Railway CLI:
   ```bash
   npm i -g @railway/cli
   railway login
   ```
2. Initialize project:
   ```bash
   railway init
   ```
3. Provision PostGIS:
   - In the Railway dashboard, click `+ New` -> `Database` -> `PostgreSQL`.
   - In PostgreSQL settings, connect and execute:
     ```sql
     CREATE EXTENSION IF NOT EXISTS postgis;
     ```
4. Deploy Backend:
   - Link the `backend/` directory with Dockerfile to Railway.
   - Configure Railway environment variables:
     ```bash
     PROJECT_NAME=TerraTwin
     ENVIRONMENT=production
     DEBUG=False
     CORS_ORIGINS=https://your-terratwin-project.vercel.app
     DATABASE_URL=postgresql+asyncpg://... (from Railway Postgres connection string)
     ```
5. Copy your Railway public URL (e.g. `https://terratwin-backend.up.railway.app/api/v1`) and paste it as `NEXT_PUBLIC_API_URL` and `BACKEND_API_URL` in Vercel.

---

## 5. Pre-Deployment Validation Checklist

Before deploying, run the automated validation suite locally:

```bash
# 1. Verify frontend typecheck & production build
cd frontend
npm run typecheck
npm run build
npm run test

# 2. Verify backend test suite
cd ../backend
.venv/bin/pytest -v
```

All 14 frontend tests and 115 backend scientific tests must pass.

