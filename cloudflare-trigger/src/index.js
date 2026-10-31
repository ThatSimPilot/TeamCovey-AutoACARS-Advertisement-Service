// Starts the ACARS bot workflow on GitHub every 5 minutes.
// GITHUB_TOKEN is a fine-grained token with Actions: read and write on this repo.
const REPO = "ThatSimPilot/TeamCovey-AutoACARS-Advertisement-Service";
const WORKFLOW = "acars.yml";

export default {
  async scheduled(event, env, ctx) {
    const res = await fetch(
      `https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "acars-trigger",
        },
        body: JSON.stringify({ ref: "main" }),
      },
    );
    if (!res.ok) throw new Error(`dispatch failed: ${res.status} ${await res.text()}`);
    console.log(`dispatched ${WORKFLOW} (${res.status})`);
  },
};
