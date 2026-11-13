#!/usr/bin/env node
// Skip the backup schedule when today's digest has already been published.
import fs from 'node:fs';

const today = new Date().toISOString().slice(0, 10);
let needsUpdate = true;
if (process.env.SKIP_IF_FRESH === 'true') {
  try {
    const response = await fetch(`https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/contents/dashboard_news/today.json?ref=dashboard-data`, {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      signal: AbortSignal.timeout(30000),
    });
    if (response.ok) {
      const envelope = await response.json();
      const raw = Buffer.from(envelope.content.replace(/\s/g, ''), 'base64').toString('utf8');
      needsUpdate = JSON.parse(raw).date !== today;
    } else if (response.status !== 404) {
      throw new Error(`GitHub API HTTP ${response.status}`);
    }
  } catch (error) {
    console.warn(`Could not check existing digest (${error.message}); generating one.`);
  }
}
fs.appendFileSync(process.env.GITHUB_OUTPUT, `needs_update=${needsUpdate}\n`);
console.log(needsUpdate ? `News for ${today} needs an update.` : `News for ${today} is already published.`);
