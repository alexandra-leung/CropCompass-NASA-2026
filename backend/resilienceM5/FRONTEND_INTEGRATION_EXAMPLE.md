# Frontend guidance — do not overwrite the team's existing files

Edit `frontend/src/api/resilience.ts` only after checking the team's existing
`src/api/client.ts` and whether it uses Axios or fetch. These sample functions
are minimal fetch examples and do not claim to be the existing API client.

```ts
export type ClimateTwinInput = {
  latitude: number;
  longitude: number;
  scenario: 'ssp245' | 'ssp370';
  start_year: number;
  end_year: number;
  top_k: number;
};

export async function getClimateTwins(input: ClimateTwinInput) {
  const response = await fetch('/api/resilience/climate-twin', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  if (!response.ok) throw new Error(`M5 Climate Twin: ${response.status}: ${await response.text()}`);
  return response.json();
}

export async function getStressTest(input: unknown) {
  const response = await fetch('/api/resilience/stress-test', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input)
  });
  if (!response.ok) throw new Error(`M5 stress test: ${response.status}: ${await response.text()}`);
  return response.json();
}
```

If frontend runs on Vite port 5173 and backend port 8000, configure an actual
proxy in existing `frontend/vite.config.ts` for `/api` to
`http://127.0.0.1:8000`, or use the team's existing backend base URL/CORS setup.

## Resilience Lab UI — components to compose with M3

1. Farm field selector and scenario `ssp245`/`ssp370`.
2. Future period (e.g. 2041–2060) and top-3 Climate Twin list.
3. Candidate map pins, measured mismatch summaries (degC, mm/month), monthly
   climate comparison and caveat.
4. Current vs alternative rotations with scenario columns, feasibility flags,
   score components and failed constraints sourced from M2.
5. Farmer-defined irrigation reduction slider (explicitly hypothetical).
6. Rescue Mode summary of actually rerun results, Evidence Passport link.
7. Loading, incomplete-cache, 503 M2-unconnected, and data-missing states.

Do not hardcode climate-twin locations or numerical resilience results in JSX.
