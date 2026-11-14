# Frontend architecture

## Phase 1 implementation
Next.js App Router provides a single foundation screen, root layout, loading
fallback and error boundary. TypeScript strict mode is enabled. Tailwind's
existing navy/cyan palette and shadcn-style Button, Slot and cn utility form the
UI foundation; components.json records aliases and styling configuration.

The HealthPanel requests the real backend status on mount and on explicit retry.
Loading, healthy, degraded and unreachable states are distinct. The shell renders
without a backend connection and performs no scientific calculations.
The no-data message is literal: no scientific results are available.

lib/api-client.ts validates the response at runtime, supports cancellation, and
limits requests to five seconds. NEXT_PUBLIC_API_URL is a build-time public value
and must never contain secrets. Production changes require a frontend rebuild.

Vitest tests components and API failure cases. Playwright verifies the built
application remains usable with the backend unavailable. ESLint and TypeScript
are separate quality gates.

## Future screens (not implemented)
Mission Explorer, Analogue Discovery, Terrain Comparison, Terrain Twin and Evidence
Passport will be feature modules. MapLibre and Three.js will be introduced when
real backend artifacts can be rendered. No maps, fabricated candidates or terrain
metrics are present now. Visualization limits and thresholds require scientific
justification; no universal rover slope thresholds are assumed.

