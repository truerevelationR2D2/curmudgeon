// Simple persistence layer
let notes = JSON.parse(localStorage.getItem('notes')) || [];
let currentNote = null;
let saveTimer = null;

function createNote() {
  const note = { id: Date.now(), title: 'Untitled', body: '', updated: Date.now() };
  notes.push(note);
  persist();
  return note;
}

function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    currentNote.title = document.getElementById('title').value;
    currentNote.body = document.getElementById('body').value;
    currentNote.updated = Date.now();
    persist();
  }, 500);
}

function persist() {
  try {
    localStorage.setItem('notes', JSON.stringify(notes));
  } catch (e) {}
}

function deleteNote(id) {
  notes = notes.filter(n => n.id !== id);
  persist();
}
