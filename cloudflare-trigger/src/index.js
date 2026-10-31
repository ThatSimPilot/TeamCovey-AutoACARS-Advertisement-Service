// Starts the ACARS bot workflow on GitHub every 5 minutes, but only when no run is
// already in progress or queued (a run that is still following a flight keeps going).
// GITHUB_TOKEN is a fine-grained token with Actions: read and write on this repo.
const REPO = "ThatSimPilot/TeamCovey-AutoACARS-Advertisement-Service";
const WORKFLOW = "acars.yml";
const API = `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}`;

function headers(env) {
  return {
    Authorization: `Bearer ${env.GITHUB_TOKEN}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "acars-trigger",
  };
}

// Returns "in_progress" or "queued" if a run is already active, otherwise null.
async function activeRun(env) {
  for (const status of ["in_progress", "queued"]) {
    const res = await fetch(`${API}/runs?status=${status}&per_page=1`, { headers: headers(env) });
    if (!res.ok) throw new Error(`list ${status} runs failed: ${res.status}`);
    const { total_count } = await res.json();
    if (total_count > 0) return status;
  }
  return null;
}

export default {
  async scheduled(event, env, ctx) {
    const active = await activeRun(env);
    if (active) {
      console.log(`skipped: a run is already ${active}`);
      return;
    }
    const res = await fetch(`${API}/dispatches`, {
      method: "POST",
      headers: headers(env),
      body: JSON.stringify({ ref: "main" }),
    });
    if (!res.ok) throw new Error(`dispatch failed: ${res.status} ${await res.text()}`);
    console.log(`dispatched ${WORKFLOW} (${res.status})`);
  },
};
