---
description: The review skill triggers on natural phrasing, without its name.
tags: [smoke]
max_turns: 8
allowed_tools: [Read, Glob, Grep, Skill]
---

Tear this apart before I ship it:

```js
function total(items) { let t = 0; for (let i = 0; i <= items.length; i++) t += items[i].price; return t; }
```
