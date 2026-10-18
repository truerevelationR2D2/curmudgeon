const els = {
  search: document.getElementById('search'),
  newBtn: document.getElementById('new'),
  list: document.getElementById('list'),
  empty: document.getElementById('empty'),
  title: document.getElementById('title'),
  body: document.getElementById('body'),
  status: document.getElementById('status'),
  sharedBox: document.getElementById('shared-box'),
  sharedStatus: document.getElementById('shared-status'),
  shared: document.getElementById('shared'),
};

const SAVE_DELAY_MS = 500;
const SHARED_DELAY_MS = 250;

const loaded = loadNotes();
let notes = loaded.notes;
let currentId = null;
// The pending save captures its note id and values when the user types, never when the timer fires.
let pending = null;

function findNote(id) {
  return notes.find(n => n.id === id) || null;
}

function setStatus(text, isError) {
  els.status.textContent = text;
  els.status.classList.toggle('error', Boolean(isError));
}

function commit() {
  const problem = saveNotes(notes);
  setStatus(problem || 'Saved', Boolean(problem));
  return !problem;
}

function flushSave() {
  if (!pending) return;
  clearTimeout(pending.timer);
  const p = pending;
  pending = null;
  const note = findNote(p.id);
  if (!note) return;
  note.title = p.title;
  note.body = p.body;
  note.updated = Date.now();
  commit();
  renderList();
}

function onEdit() {
  if (currentId === null) return;
  if (pending) clearTimeout(pending.timer);
  pending = { id: currentId, title: els.title.value, body: els.body.value, timer: setTimeout(flushSave, SAVE_DELAY_MS) };
  setStatus('Saving…', false);
}

function renderList() {
  const q = els.search.value.trim().toLowerCase();
  const shown = notes
    .filter(n => n.title.toLowerCase().includes(q))
    .sort((a, b) => b.updated - a.updated);

  const frag = document.createDocumentFragment();
  for (const n of shown) {
    const name = n.title || 'Untitled';
    const li = document.createElement('li');
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'open';
    open.dataset.id = n.id;
    open.textContent = name;
    if (n.id === currentId) open.setAttribute('aria-current', 'true');
    const del = document.createElement('button');
    del.type = 'button';
    del.className = 'del';
    del.dataset.id = n.id;
    del.textContent = 'Delete';
    del.setAttribute('aria-label', `Delete note "${name}"`);
    li.append(open, del);
    frag.append(li);
  }
  els.list.replaceChildren(frag);

  if (notes.length === 0) els.empty.textContent = 'No notes yet. Press New note to start one.';
  else if (shown.length === 0) els.empty.textContent = `No notes match "${els.search.value.trim()}".`;
  else els.empty.textContent = '';
  els.empty.hidden = els.empty.textContent === '';
}

function selectNote(id) {
  flushSave();
  const note = id === null ? null : findNote(id);
  currentId = note ? note.id : null;
  els.title.value = note ? note.title : '';
  els.body.value = note ? note.body : '';
  els.title.disabled = !note;
  els.body.disabled = !note;
  renderList();
}

function createNote() {
  flushSave();
  const note = makeNote();
  notes.push(note);
  commit();
  selectNote(note.id);
  els.title.focus();
  els.title.select();
}

function deleteNote(id) {
  const note = findNote(id);
  if (!note) return;
  if (!window.confirm(`Delete "${note.title || 'Untitled'}"? This cannot be undone.`)) return;
  flushSave();
  notes = notes.filter(n => n.id !== id);
  commit();
  if (currentId === id) selectNote(null);
  else renderList();
}

let sharedTimer = null;
let sharedCtrl = null;

function searchShared(query) {
  clearTimeout(sharedTimer);
  if (sharedCtrl) sharedCtrl.abort();
  sharedCtrl = null;
  if (!query) {
    els.sharedBox.hidden = true;
    els.shared.replaceChildren();
    return;
  }
  sharedTimer = setTimeout(async () => {
    const ctrl = new AbortController();
    sharedCtrl = ctrl;
    els.sharedBox.hidden = false;
    els.sharedStatus.textContent = 'Searching shared notes…';
    try {
      const res = await fetch('/api/shared?q=' + encodeURIComponent(query), { signal: ctrl.signal });
      if (!res.ok) throw new Error(`server answered ${res.status}`);
      const data = await res.json();
      if (ctrl !== sharedCtrl) return;
      const items = Array.isArray(data) ? data.filter(s => s && typeof s.title === 'string') : [];
      els.shared.replaceChildren(...items.map(s => {
        const li = document.createElement('li');
        li.textContent = s.title;
        return li;
      }));
      els.sharedStatus.textContent = items.length ? `${items.length} shared note(s)` : 'No shared notes match.';
    } catch (e) {
      if (e.name === 'AbortError' || ctrl !== sharedCtrl) return;
      els.shared.replaceChildren();
      els.sharedStatus.textContent = `Shared notes could not be loaded (${e.message}). Your own notes are not affected. Try again later.`;
    }
  }, SHARED_DELAY_MS);
}

els.list.addEventListener('click', (ev) => {
  const btn = ev.target.closest('button[data-id]');
  if (!btn) return;
  if (btn.classList.contains('del')) deleteNote(btn.dataset.id);
  else selectNote(btn.dataset.id);
});
els.newBtn.addEventListener('click', createNote);
els.title.addEventListener('input', onEdit);
els.body.addEventListener('input', onEdit);
els.search.addEventListener('input', () => {
  renderList();
  searchShared(els.search.value.trim());
});
window.addEventListener('pagehide', flushSave);
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') flushSave();
});

if (loaded.problem) setStatus(loaded.problem, true);
const newest = notes.slice().sort((a, b) => b.updated - a.updated)[0];
selectNote(newest ? newest.id : null);
