'use strict';

const DOC_EXT = ['md', 'markdown', 'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt',
  'ppt', 'pptx', 'key', 'html', 'htm'];
const IMG_EXT = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

function extOf(name) {
  return String(name).toLowerCase().split('.').pop();
}

function classifyFile(name) {
  const ext = extOf(name);
  if (['md', 'markdown', 'txt'].includes(ext)) return 'markdown';
  if (IMG_EXT.includes(ext)) return 'image';
  if (ext === 'pdf') return 'pdf';
  return 'other';
}

// Only document files and pictures are allowed in.
function isAccepted(name) {
  const ext = extOf(name);
  return DOC_EXT.includes(ext) || IMG_EXT.includes(ext);
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
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown };
}
