'use strict';

function classifyFile(name) {
  const ext = String(name).toLowerCase().split('.').pop();
  if (['md', 'markdown', 'txt'].includes(ext)) return 'markdown';
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  return 'other';
}

function splitSlides(text) {
  return String(text)
    .split(/\r?\n---\r?\n/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function groupFilesByTeam(files) {
  const map = new Map();
  for (const f of files) {
    const parts = String(f.webkitRelativePath || f.name).split('/');
    // A file in a subfolder (root/team/file) is grouped under the subfolder name.
    // A file sitting loose in the picked folder becomes its own team, named after
    // the file (extension stripped) — so you can just drop files in, no structure needed.
    const team = parts.length >= 3 ? parts[1] : f.name.replace(/\.[^./]+$/, '');
    if (!map.has(team)) map.set(team, []);
    map.get(team).push({
      name: f.name,
      path: f.webkitRelativePath,
      kind: classifyFile(f.name),
      file: f.file || f, // drop wrappers carry the real File in .file; folder-input items are Files
    });
  }
  return [...map.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([team, files]) => ({ team, files }));
}

function buildMinutesMarkdown({ org, title, date, teams, decisions }) {
  const out = [`# ${title || 'Meeting Minutes'}`, ''];
  if (org) out.push(`**Organization:** ${org}`);
  out.push(`**Date:** ${date || ''}`, '', '## Team Updates', '');
  for (const t of teams || []) {
    out.push(`### ${t.team}`, '');
    out.push(t.notes && t.notes.trim() ? t.notes.trim() : '_No updates this week_', '');
  }
  out.push('## Decisions', '');
  out.push(decisions && decisions.trim() ? decisions.trim() : '_None recorded_', '');
  return out.join('\n');
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { classifyFile, splitSlides, groupFilesByTeam, buildMinutesMarkdown };
}
