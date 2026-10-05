"""Every annotation in app/ must name something that is imported.

Production runs the Dockerfile's Python (3.12), which evaluates a function's
annotations when the module is imported; the dev container's Python 3.14
defers that (PEP 649), so a missing ``from typing import Optional`` passes
every other test here and then crashes the deployed app at startup (it did,
2026-10-05). Reading ``__annotations__`` forces the evaluation on 3.14 too.
"""

import importlib
import inspect
import pkgutil

import app


def _app_modules():
    for info in pkgutil.walk_packages(app.__path__, "app."):
        yield importlib.import_module(info.name)


def _annotated(module):
    for _name, obj in list(vars(module).items()):  # reading annotations can import
        if getattr(obj, "__module__", None) != module.__name__:
            continue
        if inspect.isfunction(obj):
            yield obj
        elif inspect.isclass(obj):
            yield obj
            yield from [m for m in list(vars(obj).values()) if inspect.isfunction(m)]


def test_every_annotation_in_app_resolves():
    broken = []
    for module in _app_modules():
        for obj in _annotated(module):
            try:
                obj.__annotations__
            except NameError as exc:
                broken.append(f"{module.__name__}.{obj.__qualname__}: {exc}")
    assert not broken, (
        "Annotations naming something that is not imported - the deployed "
        "Python 3.12 crashes on import. Add the import (e.g. "
        "`from typing import Any, Dict, Optional`):\n  " + "\n  ".join(broken)
    )
