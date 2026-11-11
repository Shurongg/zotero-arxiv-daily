#!/usr/bin/env node
// Publish the public daily digest as one stable JSON file for Obsidian.
import fs from 'node:fs';

const repo = process.env.GITHUB_REPOSITORY;
const token = process.env.GITHUB_TOKEN;
const source = '.dashboard-news-output/today.json';
const branch = 'dashboard-data';
const file = 'dashboard_news/today.json';
if (!repo || !token || !process.env.GITHUB_SHA) throw new Error('Missing GitHub Actions repository credentials.');

const raw = fs.readFileSync(source);
const data = JSON.parse(raw.toString('utf8'));
if (data.v !== 1 || !/^\d{4}-\d{2}-\d{2}$/.test(data.date) || !Array.isArray(data.headlines)) {
  throw new Error('News JSON is incomplete; refusing to publish.');
}

async function api(route, method = 'GET', body = null, allow404 = false) {
  const response = await fetch(`https://api.github.com/repos/${repo}${route}`, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(30000),
  });
  if (response.status === 404 && allow404) return null;
  if (!response.ok) throw new Error(`GitHub API ${method} ${route} returned HTTP ${response.status}.`);
  return response.json();
}

if (!await api(`/git/ref/heads/${branch}`, 'GET', null, true)) {
  await api('/git/refs', 'POST', { ref: `refs/heads/${branch}`, sha: process.env.GITHUB_SHA });
}
const previous = await api(`/contents/${file}?ref=${branch}`, 'GET', null, true);
await api(`/contents/${file}`, 'PUT', {
  message: `Update dashboard news for ${data.date}`,
  branch,
  content: raw.toString('base64'),
  ...(previous?.sha ? { sha: previous.sha } : {}),
});
console.log(`Published ${data.headlines.length} headlines for ${data.date} to ${branch}/${file}.`);
