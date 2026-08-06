"""Load theme.qss, resolving the @ASSETS@ token to an absolute assets path so
QSS url() references (spin-box arrows, etc.) work regardless of cwd."""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_stylesheet() -> str:
    qss = open(os.path.join(HERE, "theme.qss")).read()
    assets = os.path.join(HERE, "assets").replace(os.sep, "/")
    return qss.replace("@ASSETS@", assets)
