#!/bin/bash
# The workspace for this case: one small file with a real bug, in a git repository.
set -euo pipefail
cat > app.js <<'JS'
function total(items) {
  let t = 0;
  for (let i = 0; i <= items.length; i++) t += items[i].price;
  return t;
}
module.exports = { total };
JS
git init -q && git add app.js && git -c user.email=eval@example.invalid -c user.name=eval commit -qm "app"
