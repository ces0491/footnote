"""What a draft was made with: the writers' instructions, the match tools and the writer's workflow.

Each part has a version set by hand (prompts.py, tools/server.py, writer.py) and a fingerprint of
the code behind it, so an edit that doesn't move a version still changes what names the part. Both
go into the agents' cache key (worker.py) and into the recording of the agents' evaluations that CI
replays (evals/run.py): a change to what the writers are told or shown makes later replays draft
afresh instead of reusing drafts written before it, and fails CI until the evaluations are recorded
again. The checks a draft passes aren't part of it: a cached or recorded draft is checked again with
today's.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import ModuleType

from footnote.agents import prompts, writer
from footnote.insights import templates
from footnote.tools import server


def fingerprint(*modules: ModuleType, rendered: tuple[str, ...] = ()) -> str:
    """A short hash of the modules' source and of any `rendered` text, line endings aside: a Windows
    checkout has CRLF where CI's has LF, and both must give the same fingerprint."""
    digest = hashlib.sha256()
    for module in modules:
        assert module.__file__ is not None, module.__name__
        digest.update(Path(module.__file__).read_text(encoding="utf-8").replace("\r\n", "\n").encode())
    for text in rendered:
        digest.update(text.replace("\r\n", "\n").encode())
    return digest.hexdigest()[:12]


# The instructions as the model gets them: prompts.py builds them from limits kept in draft.py.
_INSTRUCTIONS = (prompts.MOMENT_WRITER, prompts.CORRECTION_WRITER, prompts.RECAP_WRITER)

VERSIONS = {
    "prompt": f"{prompts.PROMPT_VERSION}+{fingerprint(prompts, rendered=_INSTRUCTIONS)}",
    # What the tools return includes each moment's template wording.
    "tools": f"{server.TOOLS_VERSION}+{fingerprint(server, templates)}",
    "writer": f"{writer.WRITER_VERSION}+{fingerprint(writer)}",
}
