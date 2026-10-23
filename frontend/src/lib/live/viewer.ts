// The anonymous ID this browser goes by, kept in the browser, with no sign-in. A replay started with
// it replaces the viewer's previous one, so trying the jump points one after another never crowds
// out anyone else's replay (replayer/runs.py).

import { viewerIdPattern } from "./contract";

const KEY = "footnote.viewer";

// Where storage is blocked (a private window, say) the ID lasts as long as the page.
let unsaved: string | undefined;

export function viewerId(): string {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved && viewerIdPattern.test(saved)) return saved;
    const id = crypto.randomUUID();
    localStorage.setItem(KEY, id);
    return id;
  } catch {
    unsaved ??= crypto.randomUUID();
    return unsaved;
  }
}
