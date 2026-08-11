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
  if (['html', 'htm'].includes(ext)) return 'html';
  // Only the formats the Office Online viewer can actually render. key/odt/rtf fall
  // through to 'other' → a link, since the viewer would show a broken embed.
  if (['ppt', 'pptx', 'doc', 'docx', 'xls', 'xlsx'].includes(ext)) return 'office';
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

function buildMinutesMarkdown({ org, title, date, teams }) {
  const out = [`# ${title || 'Meeting Minutes'}`, ''];
  if (org) out.push(`**Organization:** ${org}`);
  out.push(`**Date:** ${date || ''}`, '', '## Team Updates', '');
  for (const t of teams || []) {
    out.push(`### ${t.team}`, '');
    out.push(t.notes && t.notes.trim() ? t.notes.trim() : '_No updates this week_', '');
  }
  return out.join('\n');
}

function meetingStatus(m) {
  const S = {
    setup:      { key: 'setup',      label: 'Setup',           cls: 'setup' },
    collecting: { key: 'collecting', label: 'Collecting',      cls: 'collecting' },
    ready:      { key: 'ready',      label: 'Recorded',        cls: 'ready' },
    processing: { key: 'processing', label: 'Processing',      cls: 'processing' },
    draft:      { key: 'draft',      label: 'Draft ready',     cls: 'draft' },
    published:  { key: 'published',  label: 'Published',       cls: 'published' },
  };
  if (m && m.status && S[m.status]) return S[m.status];
  if (m && m.is_active === false) return S.published;
  if (m && m.minutes_final && String(m.minutes_final).trim()) return S.draft;
  return S.collecting;
}

function matchRecording(meeting, recordings) {
  if (!recordings || !recordings.length) return null;
  const target = meeting && meeting.meeting_date ? new Date(meeting.meeting_date + 'T00:00').getTime() : NaN;
  let best = null, bestScore = Infinity;
  recordings.forEach(function (r) {
    const t = new Date(r.created_at).getTime();
    const dateDist = isNaN(target) || isNaN(t) ? 1e15 : Math.abs(t - target);
    const titleBonus = meeting && meeting.title && r.title &&
      r.title.toLowerCase().includes(meeting.title.toLowerCase()) ? -1 : 0;
    const score = dateDist + titleBonus;
    if (score < bestScore) { bestScore = score; best = r; }
  });
  return best;
}

function recordingExt(mimeType) {
  const m = String(mimeType || '').toLowerCase();
  if (m.includes('mp4') || m.includes('m4a') || m.includes('aac')) return 'm4a';
  return 'webm';
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { classifyFile, isAccepted, groupFilesByTeam, buildMinutesMarkdown, meetingStatus, matchRecording, recordingExt };
}
