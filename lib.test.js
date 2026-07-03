'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const { classifyFile } = require('./lib.js');

test('classifyFile maps extensions to kinds', () => {
  assert.equal(classifyFile('notes.md'), 'markdown');
  assert.equal(classifyFile('a.MARKDOWN'), 'markdown');
  assert.equal(classifyFile('readme.txt'), 'markdown');
  assert.equal(classifyFile('shot.PNG'), 'image');
  assert.equal(classifyFile('pic.jpeg'), 'image');
  assert.equal(classifyFile('roadmap.pdf'), 'pdf');
  assert.equal(classifyFile('update.docx'), 'other');
  assert.equal(classifyFile('noext'), 'other');
});

const { splitSlides } = require('./lib.js');

test('splitSlides splits on --- and drops empties', () => {
  assert.deepEqual(splitSlides('a\n---\nb'), ['a', 'b']);
  assert.deepEqual(splitSlides('only one'), ['only one']);
  assert.deepEqual(splitSlides(''), []);
  assert.deepEqual(splitSlides('a\r\n---\r\nb'), ['a', 'b']);
  assert.deepEqual(splitSlides('  x  \n---\n\n'), ['x']);
});

const { groupFilesByTeam } = require('./lib.js');

test('groupFilesByTeam groups by second path segment, sorted', () => {
  const files = [
    { name: 'notes.md', webkitRelativePath: 'team/Tech/notes.md' },
    { name: 'shot.png', webkitRelativePath: 'team/Tech/shot.png' },
    { name: 'roadmap.pdf', webkitRelativePath: 'team/R&D/roadmap.pdf' },
    { name: 'stray.txt', webkitRelativePath: 'team/stray.txt' }, // skipped: too shallow
  ];
  const groups = groupFilesByTeam(files);
  assert.deepEqual(groups.map((g) => g.team), ['R&D', 'Tech']);
  const tech = groups.find((g) => g.team === 'Tech');
  assert.equal(tech.files.length, 2);
  assert.equal(tech.files[0].kind, 'markdown');
  assert.equal(tech.files[1].kind, 'image');
  assert.equal(tech.files[0].file, files[0]); // original passed through
});

const { buildMinutesMarkdown } = require('./lib.js');

test('buildMinutesMarkdown fills template with empty fallbacks', () => {
  const md = buildMinutesMarkdown({
    org: 'Ospit',
    title: 'Weekly Sync',
    date: '2026-07-03',
    teams: [
      { team: 'Tech', notes: 'Shipped login.' },
      { team: 'R&D', notes: '   ' },
    ],
    decisions: '',
  });
  assert.match(md, /# Weekly Sync/);
  assert.match(md, /\*\*Organization:\*\* Ospit/);
  assert.match(md, /\*\*Date:\*\* 2026-07-03/);
  assert.match(md, /### Tech\n\nShipped login\./);
  assert.match(md, /### R&D\n\n_No updates this week_/);
  assert.match(md, /## Decisions\n\n_None recorded_/);
});
