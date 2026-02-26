function stripPath(root, path) {
  if (!path.startsWith('$.')) return;
  const parts = path.slice(2).split('.');
  let cursor = root;
  for (let i = 0; i < parts.length - 1; i += 1) {
    const p = parts[i];
    if (p.endsWith(']')) {
      const [k, idxRaw] = p.split('[');
      const idx = Number(idxRaw.replace(']', ''));
      cursor = cursor?.[k]?.[idx];
    } else {
      cursor = cursor?.[p];
    }
    if (cursor == null) return;
  }
  const leaf = parts[parts.length - 1];
  if (leaf.endsWith(']')) {
    const [k, idxRaw] = leaf.split('[');
    const idx = Number(idxRaw.replace(']', ''));
    if (Array.isArray(cursor?.[k])) cursor[k].splice(idx, 1);
  } else if (cursor && Object.prototype.hasOwnProperty.call(cursor, leaf)) {
    delete cursor[leaf];
  }
}

export function applyBlockRules(payload, blockedJsonPaths = []) {
  const next = structuredClone(payload);
  for (const p of blockedJsonPaths) stripPath(next, p);
  return next;
}
