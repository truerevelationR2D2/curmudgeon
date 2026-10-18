// Notes persistence. Pure data functions: no DOM access here.
// Saved shape: { version: 1, notes: [...] }. Version 0 was a bare array of notes with numeric ids.
const STORAGE_KEY = 'notes';
const BACKUP_KEY = 'notes-backup';
const SCHEMA_VERSION = 1;

function newId() {
  if (window.crypto && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

function makeNote() {
  return { id: newId(), title: 'Untitled', body: '', updated: Date.now() };
}

// Accepts a record of any saved version; returns a valid note or null.
function normalizeNote(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const id = (typeof raw.id === 'string' && raw.id) || (typeof raw.id === 'number' && String(raw.id)) || newId();
  return {
    id,
    title: typeof raw.title === 'string' ? raw.title : 'Untitled',
    body: typeof raw.body === 'string' ? raw.body : '',
    updated: Number.isFinite(raw.updated) ? raw.updated : 0,
  };
}

function backupRaw(raw) {
  try { localStorage.setItem(BACKUP_KEY, raw); } catch (e) { /* storage is already failing; the load message says so */ }
}

// Returns { notes, problem }. problem is a sentence for the user, or null.
function loadNotes() {
  let raw;
  try {
    raw = localStorage.getItem(STORAGE_KEY);
  } catch (e) {
    return { notes: [], problem: 'This browser is blocking storage, so notes cannot be saved here. Allow site data and reload.' };
  }
  if (raw === null) return { notes: [], problem: null };

  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    backupRaw(raw);
    return { notes: [], problem: `Saved notes could not be read. The unreadable data was kept under "${BACKUP_KEY}".` };
  }
  const list = Array.isArray(data) ? data : (data && Array.isArray(data.notes) ? data.notes : null);
  if (!list) {
    backupRaw(raw);
    return { notes: [], problem: `Saved notes were in an unknown format. They were kept under "${BACKUP_KEY}".` };
  }

  const seen = new Set();
  const notes = [];
  for (const item of list) {
    const note = normalizeNote(item);
    if (!note) continue;
    if (seen.has(note.id)) note.id = newId();
    seen.add(note.id);
    notes.push(note);
  }
  if (notes.length < list.length) {
    backupRaw(raw);
    return { notes, problem: `${list.length - notes.length} unreadable note(s) were skipped. The original data was kept under "${BACKUP_KEY}".` };
  }
  return { notes, problem: null };
}

// Returns null on success, or a sentence for the user saying what failed and what to do.
function saveNotes(notes) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: SCHEMA_VERSION, notes }));
    return null;
  } catch (e) {
    if (e && e.name === 'QuotaExceededError') return 'Not saved: browser storage is full. Delete old notes to free space.';
    return `Not saved: the browser refused to store notes (${e && e.name ? e.name : 'unknown error'}).`;
  }
}
