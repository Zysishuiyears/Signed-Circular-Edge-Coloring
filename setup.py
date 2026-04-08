from __future__ import annotations

import warnings
from pathlib import Path
from sys import platform

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup

ROOT = Path(__file__).parent.resolve()
BLISS_ROOT = ROOT / "third_party" / "bliss" / "src"


class OptionalBuildExt(build_ext):
    def run(self) -> None:
        try:
            super().run()
        except Exception as exc:  # pragma: no cover - platform dependent
            self._warn(exc)

    def build_extension(self, ext) -> None:  # type: ignore[override]
        try:
            super().build_extension(ext)
        except Exception as exc:  # pragma: no cover - platform dependent
            self._warn(exc)

    @staticmethod
    def _warn(exc: Exception) -> None:
        warnings.warn(
            f"Skipping optional native extension build: {exc}",
            RuntimeWarning,
            stacklevel=2,
        )


ext_modules = [
    Pybind11Extension(
        "signedcoloring._classification_native",
        [
            "src/signedcoloring/_classification_native.cpp",
            str(BLISS_ROOT / "abstractgraph.cc"),
            str(BLISS_ROOT / "defs.cc"),
            str(BLISS_ROOT / "graph.cc"),
            str(BLISS_ROOT / "orbit.cc"),
            str(BLISS_ROOT / "partition.cc"),
            str(BLISS_ROOT / "uintseqhash.cc"),
            str(BLISS_ROOT / "utils.cc"),
        ],
        include_dirs=[str(BLISS_ROOT)],
        extra_compile_args=[] if platform == "win32" else ["-pthread"],
        extra_link_args=[] if platform == "win32" else ["-pthread"],
        cxx_std=17,
    )
]


setup(
    ext_modules=ext_modules,
    cmdclass={"build_ext": OptionalBuildExt},
)
