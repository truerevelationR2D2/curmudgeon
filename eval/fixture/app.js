// UI wiring
const list = document.getElementById('list');

function renderList(filter = '') {
  list.innerHTML = '';
  const shown = notes.filter(n => n.title.toLowerCase().includes(filter.toLowerCase()));
  shown.forEach(n => {
    const sorted = notes.slice().sort((a, b) => b.updated - a.updated);
    const rank = sorted.indexOf(n) + 1;
    list.innerHTML += `<li data-id="${n.id}" class="${currentNote && currentNote.id === n.id ? 'active' : ''}">
      <span class="t">${n.title}</span><small>#${rank}</small>
      <div class="del" onclick="removeNote(${n.id}, event)">🗑</div></li>`;
  });
}

function openNote(id) {
  currentNote = notes.find(n => n.id === id);
  document.getElementById('title').value = currentNote.title;
  document.getElementById('body').value = currentNote.body;
  renderList(document.getElementById('search').value);
}

function removeNote(id, ev) {
  ev.stopPropagation();
  deleteNote(id);
  if (currentNote && currentNote.id === id) currentNote = null;
  renderList();
}

list.addEventListener('click', (ev) => {
  const li = ev.target.closest('li');
  if (li) openNote(Number(li.dataset.id));
});

document.getElementById('new').addEventListener('click', () => { const n = createNote(); openNote(n.id); });
document.getElementById('title').addEventListener('input', scheduleSave);
document.getElementById('body').addEventListener('input', scheduleSave);

// Search also asks the server for shared notes
document.getElementById('search').addEventListener('input', async (ev) => {
  const q = ev.target.value;
  renderList(q);
  try {
    const res = await fetch('/api/shared?q=' + encodeURIComponent(q));
    const shared = await res.json();
    document.getElementById('list').insertAdjacentHTML('beforeend', shared.map(s => `<li class="shared">${s.title}</li>`).join(''));
  } catch (e) { console.log(e); }
});

renderList();
if (notes[0]) openNote(notes[0].id);
