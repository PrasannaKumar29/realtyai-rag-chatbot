"""Atomic local output for offline Wasalt derived files."""

import os
from pathlib import Path
import tempfile


def write_text_atomic(path, text, replace=False):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.wasalt-offline-',suffix='.tmp',delete=False) as handle:
            temporary=Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary,path)
        else:
            os.link(temporary,path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
