'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { classifyFile } = require('./web/lib.js');

test('classifyFile maps extensions to kinds', () => {
  assert.equal(classifyFile('notes.md'), 'markdown');
  assert.equal(classifyFile('a.MARKDOWN'), 'markdown');
  assert.equal(classifyFile('readme.txt'), 'markdown');
  assert.equal(classifyFile('shot.PNG'), 'image');
  assert.equal(classifyFile('pic.jpeg'), 'image');
  assert.equal(classifyFile('roadmap.pdf'), 'pdf');
  assert.equal(classifyFile('page.html'), 'html');
  assert.equal(classifyFile('index.HTM'), 'html');
  assert.equal(classifyFile('deck.pptx'), 'office');
  assert.equal(classifyFile('update.docx'), 'office');
  assert.equal(classifyFile('keynote.key'), 'other');   // Office viewer can't render Keynote → link
  assert.equal(classifyFile('notes.odt'), 'other');
  assert.equal(classifyFile('archive.zip'), 'other');
  assert.equal(classifyFile('noext'), 'other');
});

const { isAccepted } = require('./web/lib.js');

test('isAccepted allows docs and pictures, rejects the rest', () => {
  for (const ok of ['a.pdf', 'b.DOCX', 'c.doc', 'd.txt', 'e.md', 'f.png', 'g.JPG', 'h.webp', 'i.pptx', 'j.html']) {
    assert.equal(isAccepted(ok), true, ok);
  }
  for (const no of ['a.zip', 'b.mp4', 'c.exe', 'd.csv', 'noext']) {
    assert.equal(isAccepted(no), false, no);
  }
});

const { groupFilesByTeam } = require('./web/lib.js');

test('groupFilesByTeam: subfolder = team, loose file = its own team (by filename)', () => {
  const files = [
    { name: 'notes.md', webkitRelativePath: 'team/Tech/notes.md' },
    { name: 'shot.png', webkitRelativePath: 'team/Tech/shot.png' },
    { name: 'roadmap.pdf', webkitRelativePath: 'team/R&D/roadmap.pdf' },
    { name: 'Sales.txt', webkitRelativePath: 'team/Sales.txt' }, // loose → team "Sales"
  ];
  const groups = groupFilesByTeam(files);
  assert.deepEqual(groups.map((g) => g.team), ['R&D', 'Sales', 'Tech']);
  const tech = groups.find((g) => g.team === 'Tech');
  assert.equal(tech.files.length, 2);
  assert.equal(tech.files[0].kind, 'markdown');
  assert.equal(tech.files[1].kind, 'image');
  assert.equal(tech.files[0].file, files[0]); // original passed through
  const sales = groups.find((g) => g.team === 'Sales');
  assert.equal(sales.files.length, 1);
  assert.equal(sales.files[0].name, 'Sales.txt'); // extension stripped only from team name
});

const { buildMinutesMarkdown } = require('./web/lib.js');

test('buildMinutesMarkdown fills template with empty fallbacks', () => {
  const md = buildMinutesMarkdown({
    org: 'Ospit',
    title: 'Weekly Sync',
    date: '2026-07-03',
    teams: [
      { team: 'Tech', notes: 'Shipped login.' },
      { team: 'R&D', notes: '   ' },
    ],
  });
  assert.match(md, /# Weekly Sync/);
  assert.match(md, /\*\*Organization:\*\* Ospit/);
  assert.match(md, /\*\*Date:\*\* 2026-07-03/);
  assert.match(md, /### Tech\n\nShipped login\./);
  assert.match(md, /### R&D\n\n_No updates this week_/);
  assert.doesNotMatch(md, /## Decisions/);   // decisions removed — AI minutes carry their own
});

const { meetingStatus } = require('./web/lib.js');

test('meetingStatus maps each explicit status', () => {
  assert.equal(meetingStatus({ status: 'setup' }).label, 'Setup');
  assert.equal(meetingStatus({ status: 'collecting' }).label, 'Collecting');
  assert.equal(meetingStatus({ status: 'ready' }).label, 'Recorded');
  assert.equal(meetingStatus({ status: 'processing' }).label, 'Processing');
  assert.equal(meetingStatus({ status: 'draft' }).label, 'Draft ready');
  assert.equal(meetingStatus({ status: 'published' }).label, 'Published');
  assert.equal(meetingStatus({ status: 'published' }).cls, 'published');
});

test('meetingStatus derives status for un-migrated rows', () => {
  assert.equal(meetingStatus({ is_active: false }).label, 'Published');
  assert.equal(meetingStatus({ is_active: true, minutes_final: '# M' }).label, 'Draft ready');
  assert.equal(meetingStatus({ is_active: true }).label, 'Collecting');
  assert.equal(meetingStatus({}).label, 'Collecting');
});

const { matchRecording } = require('./web/lib.js');

test('matchRecording picks nearest date, null on empty', () => {
  const recs = [
    { id: 'a', title: 'Standup', created_at: '2026-07-20T10:00:00Z' },
    { id: 'b', title: 'Weekly Review', created_at: '2026-07-24T10:00:00Z' },
  ];
  assert.equal(matchRecording({ meeting_date: '2026-07-24', title: 'Weekly Review' }, recs).id, 'b');
  assert.equal(matchRecording({ meeting_date: '2026-07-19', title: 'x' }, recs).id, 'a');
  assert.equal(matchRecording({ meeting_date: '2026-07-24' }, []), null);
});

const { recordingExt } = require('./web/lib.js');

test('recordingExt maps MediaRecorder mimeType to an extension', () => {
  assert.equal(recordingExt('audio/webm;codecs=opus'), 'webm');
  assert.equal(recordingExt('audio/mp4'), 'm4a');
  assert.equal(recordingExt('video/webm'), 'webm');
  assert.equal(recordingExt(''), 'webm');
});
