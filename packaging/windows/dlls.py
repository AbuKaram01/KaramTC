# SPDX-FileCopyrightText: 2026 AbuKaram01
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Which DLLs does an installed KaramTC need that nothing inside it provides?

A machine that has never had the Microsoft Visual C++ Redistributable has no ``msvcp140.dll``. Python's own
installer brings ``vcruntime140.dll``, but libraries such as ctranslate2 (faster-whisper) and onnxruntime also import
``msvcp140.dll``, and Python then fails to import them with "DLL load failed". The CI machine has the Redistributable,
so a program that starts there proves nothing about a clean machine. This script answers the question without
depending on what the machine has:

    python packaging\\windows\\dlls.py scan   --app <installation folder>   [--strict] [--json file] [--github]
    python packaging\\windows\\dlls.py loaded --app <installation folder>   [--strict]

``scan`` reads the import tables of every ``.dll``, ``.pyd`` and ``.exe`` of the installation (and of the Python the
environment is made from) and says, for each DLL they import, whether it is beside the importer or in a folder the
program registers for DLLs, a Windows DLL, a Visual C++ runtime DLL nothing provides, or missing altogether. It reads
the files themselves, so it also runs on a machine without Windows. Delay-loaded imports are listed for information
only: they are looked up when first used, not when the library is loaded.

``loaded`` (Windows only, run with the installed program's own python.exe) imports the libraries the way the program
does and prints where each Visual C++ runtime DLL was actually loaded from: KaramTC's folders, the Python folder, or
Windows. On a machine that has the Redistributable a program can start with ``scan`` still reporting gaps, and this
shows which copy it used.

Only the Python standard library is used, so either command runs with the installed program's own python.exe.
Output is plain ASCII: a Windows console that is not set to UTF-8 would fail on anything else.
"""

from __future__ import annotations

import argparse
import json
import mmap
import os
import re
import struct
import sys
import textwrap
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# -- Reading the import tables of a PE file ---------------------------------------------------------------

_IMPORT_DIRECTORY = 1
_DELAY_IMPORT_DIRECTORY = 13
_MAX_DESCRIPTORS = 4096                  # A real file has a few hundred at most; a damaged one must not loop for ever.


class PeError(ValueError):
    """The file is not a readable Windows executable."""


@dataclass(frozen=True)
class Imports:
    static: tuple[str, ...] = ()         # Loaded together with the file: when one is missing the file does not load.
    delayed: tuple[str, ...] = ()        # Looked up when the file first calls into them.


def _u16(data, at: int) -> int:
    return struct.unpack_from("<H", data, at)[0]


def _u32(data, at: int) -> int:
    return struct.unpack_from("<I", data, at)[0]


def _u64(data, at: int) -> int:
    return struct.unpack_from("<Q", data, at)[0]


def parse_imports(data) -> Imports:
    """The names of the DLLs that the PE file ``data`` (bytes or an mmap) imports."""
    try:
        return _parse_imports(data)
    except (struct.error, IndexError) as error:
        raise PeError(f"truncated or damaged ({error})") from None


def _parse_imports(data) -> Imports:
    if len(data) < 0x40 or bytes(data[:2]) != b"MZ":
        raise PeError("not a Windows executable (no MZ header)")
    pe = _u32(data, 0x3C)
    if bytes(data[pe:pe + 4]) != b"PE\0\0":
        raise PeError("not a Windows executable (no PE signature)")
    coff = pe + 4
    section_count = _u16(data, coff + 2)
    optional_size = _u16(data, coff + 16)
    optional = coff + 20
    magic = _u16(data, optional)
    if magic == 0x20B:                                                         # PE32+ (64-bit)
        directories, count_at, image_base = optional + 112, optional + 108, _u64(data, optional + 24)
    elif magic == 0x10B:                                                       # PE32 (32-bit)
        directories, count_at, image_base = optional + 96, optional + 92, _u32(data, optional + 28)
    else:
        raise PeError(f"unknown optional header 0x{magic:x}")
    directory_count = _u32(data, count_at)
    header_size = _u32(data, optional + 60)

    sections = []
    for index in range(section_count):
        at = optional + optional_size + 40 * index
        virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from("<IIII", data, at + 8)
        sections.append((virtual_address, max(virtual_size, raw_size), raw_pointer))

    def offset(rva: int) -> int:
        for address, size, pointer in sections:
            if address <= rva < address + size:
                return pointer + (rva - address)
        if rva < header_size:
            return rva
        raise PeError(f"an address (0x{rva:x}) lies outside every section")

    def text(rva: int) -> str:
        start = offset(rva)
        end = start
        while end - start < 260 and data[end] != 0:
            end += 1
        return bytes(data[start:end]).decode("latin-1")

    def table(index: int):
        if index >= directory_count:
            return None
        rva, size = struct.unpack_from("<II", data, directories + 8 * index)
        return rva if rva and size else None

    static: list[str] = []
    rva = table(_IMPORT_DIRECTORY)
    if rva is not None:
        at = offset(rva)
        for _ in range(_MAX_DESCRIPTORS):
            name_rva = _u32(data, at + 12)
            if name_rva == 0:
                break
            static.append(text(name_rva))
            at += 20

    delayed: list[str] = []
    rva = table(_DELAY_IMPORT_DIRECTORY)
    if rva is not None:
        at = offset(rva)
        for _ in range(_MAX_DESCRIPTORS):
            attributes, name_rva = struct.unpack_from("<II", data, at)
            if name_rva == 0:
                break
            if not attributes & 1:                                             # Old style: a virtual address, not an RVA.
                name_rva -= image_base
            delayed.append(text(name_rva))
            at += 32
    return Imports(tuple(static), tuple(delayed))


def read_imports(path: Path) -> Imports:
    with open(path, "rb") as handle:
        try:
            mapped = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:                                                     # An empty file cannot be mapped.
            raise PeError("empty file") from None
        with mapped:
            return parse_imports(mapped)


# -- What a DLL name means --------------------------------------------------------------------------------

# The runtime libraries of Visual C++. They come with the Visual C++ Redistributable, not with Windows, so a machine
# that never had a program needing it lacks them. (The Universal C Runtime, ucrtbase.dll and api-ms-win-crt-*, is part of
# Windows 10 and later.)
_VCPP = re.compile(r"^(msvcp\d+|msvcr\d+|vcruntime\d+|vcomp\d+|concrt\d+|vccorlib\d+|vcamp\d+|mfcm?\d+[a-z]*|atl\d+)(_[a-z0-9_]+)?\.dll$")


def is_vcpp_runtime(name: str) -> bool:
    return _VCPP.match(name.lower()) is not None


def is_windows_builtin(name: str) -> bool:
    """API sets are not files at all, and the Universal C Runtime has been part of Windows since Windows 10."""
    lowered = name.lower()
    return lowered.startswith(("api-ms-", "ext-ms-")) or lowered == "ucrtbase.dll"


# -- The scan ---------------------------------------------------------------------------------------------

# Folders that hold no program files of the installed program: the Python installer and the wheelhouse the installer
# carries (beside the program), the wheels inside the GTK runtime, and caches.
_SKIP_AT_TOP = {"wheelhouse", "python"}
_SKIP_ANYWHERE = {"wheels", "__pycache__", ".git"}
_PYTHON_FOLDERS_SCANNED = ("", "DLLs")     # Python's own interpreter and its extension modules, not its Lib\site-packages.
_PE_SUFFIXES = {".dll", ".pyd", ".exe"}


@dataclass
class Report:
    app: str
    python_home: str | None
    files: int = 0
    unreadable: list[tuple[str, str]] = field(default_factory=list)
    # The Visual C++ runtime DLLs that are imported: name -> {"importers": n, "unprovided": [files], "provided_by": [folders]}
    vcpp: dict[str, dict] = field(default_factory=dict)
    missing: dict[str, list[str]] = field(default_factory=dict)         # Static imports nothing provides and Windows lacks.
    delayed: dict[str, list[str]] = field(default_factory=dict)         # Delay-loaded imports nothing provides (information).
    # GTK's command-line tools (gtk\\bin\\*.exe), which KaramTC never starts: how many, and the runtime DLLs they lack beside them.
    tools: dict = field(default_factory=lambda: {"count": 0, "needs": {}})
    allowed: list[str] = field(default_factory=list)

    def problems(self) -> list[str]:
        """What would stop the installed program on a machine that has only Windows and what the installer brought."""
        found = [name for name, entry in sorted(self.vcpp.items()) if entry["unprovided"] and name not in self.allowed]
        found += [name for name in sorted(self.missing) if name not in self.allowed]
        return found


def _python_home_of(app: Path) -> Path | None:
    config = app / ".venv" / "pyvenv.cfg"
    try:
        for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() == "home" and value.strip():
                return Path(value.strip())
    except OSError:
        pass
    return None


def _pe_files(root: Path, *, shallow: tuple[str, ...] | None = None):
    if shallow is not None:
        for name in shallow:
            folder = root / name if name else root
            if folder.is_dir():
                for entry in sorted(folder.iterdir()):
                    if entry.is_file() and entry.suffix.lower() in _PE_SUFFIXES:
                        yield entry
        return
    for folder, directories, names in os.walk(root):
        skipped = _SKIP_ANYWHERE | (_SKIP_AT_TOP if Path(folder) == root else set())
        directories[:] = sorted(d for d in directories if d.lower() not in skipped)
        for name in sorted(names):
            if Path(name).suffix.lower() in _PE_SUFFIXES:
                yield Path(folder) / name


class _Listings:
    """File names (lower case) of folders, read once."""

    def __init__(self) -> None:
        self._cache: dict[str, frozenset[str]] = {}

    def names(self, folder: Path) -> frozenset[str]:
        key = os.path.normcase(str(folder))
        if key not in self._cache:
            try:
                self._cache[key] = frozenset(entry.name.lower() for entry in os.scandir(folder) if entry.is_file())
            except OSError:
                self._cache[key] = frozenset()
        return self._cache[key]


def shared_provider_folders(app: Path, python_home: Path | None, extra: tuple[Path, ...] = ()) -> list[Path]:
    """Folders whose DLLs every library of the installation can use, as the installed program sets them up.

    The Python folder is the application directory of the interpreter. KaramTC puts ``gtk\\bin`` (and, when the
    installer carries one, ``vcruntime``) on the DLL search path at start-up (``winsupport``). Wheels that carry their
    own copies of DLLs (``numpy.libs``, ``av.libs``) register their ``*.libs`` folder from their ``__init__``."""
    folders: list[Path] = []
    if python_home is not None:
        folders.append(python_home)
    folders += [app / "gtk" / "bin", app / "vcruntime"]
    packages = app / ".venv" / "Lib" / "site-packages"
    if packages.is_dir():
        folders += sorted(entry for entry in packages.iterdir() if entry.is_dir() and entry.name.lower().endswith(".libs"))
    folders += list(extra)
    return [folder for folder in folders if folder.is_dir()]


def scan(app: Path, python_home: Path | None = None, system_dir: Path | None = None, allow: tuple[str, ...] = (),
         extra_providers: tuple[Path, ...] = ()) -> Report:
    """Read the imports of every program file of ``app`` and of the Python behind its environment.

    ``system_dir`` is the Windows System32 folder; without it a DLL that is neither beside its importer nor a
    Visual C++ runtime is taken to be a Windows one and is not judged."""
    if python_home is None:
        python_home = _python_home_of(app)
    report = Report(app=str(app), python_home=str(python_home) if python_home else None,
                    allowed=[name.lower() for name in allow])
    listings = _Listings()
    shared = shared_provider_folders(app, python_home, extra_providers)
    shared_names = {folder: listings.names(folder) for folder in shared}

    def label(folder: Path) -> str:
        if python_home is not None and os.path.normcase(str(folder)) == os.path.normcase(str(python_home)):
            return "the Python folder"
        try:
            return str(folder.relative_to(app))
        except ValueError:
            return str(folder)

    importers: dict[str, set[str]] = defaultdict(set)         # VC++ DLL name -> every file that imports it
    unprovided: dict[str, set[str]] = defaultdict(set)
    provided_by: dict[str, set[str]] = defaultdict(set)
    missing: dict[str, set[str]] = defaultdict(set)
    delayed_gaps: dict[str, set[str]] = defaultdict(set)
    tool_needs: dict[str, set[str]] = defaultdict(set)
    tools_folder = app / "gtk" / "bin"

    sources = [(app, _pe_files(app), False)]
    if python_home is not None and python_home.is_dir():
        sources.append((python_home, _pe_files(python_home, shallow=_PYTHON_FOLDERS_SCANNED), True))
    for root, files, outside in sources:
        for path in files:
            report.files += 1
            try:
                imports = read_imports(path)
            except (PeError, OSError) as error:
                report.unreadable.append((_shown(path, root, outside), str(error)))
                continue
            shown = _shown(path, root, outside)
            own = listings.names(path.parent)
            if path.suffix.lower() == ".exe" and path.parent == tools_folder:
                # GTK's command-line tools (gdbus.exe, glib-compile-schemas.exe, cjpeg.exe ...): started on their own, with
                # only their own folder and Windows to look in. KaramTC never starts them, so they are not judged.
                report.tools["count"] += 1
                for raw in imports.static:
                    if is_vcpp_runtime(raw) and raw.lower() not in own:
                        tool_needs[raw.lower()].add(shown)
                continue
            # A program that is started on its own (tesseract.exe, with its own DLLs beside it) looks beside itself and
            # in Windows, not in the folders that the Python process registers.
            use_shared = path.suffix.lower() != ".exe" and not _inside(path, app / "tesseract")
            for kind, names in (("static", imports.static), ("delayed", imports.delayed)):
                for raw in names:
                    name = raw.lower()
                    if name in own:
                        if is_vcpp_runtime(name):
                            importers[name].add(shown)
                            provided_by[name].add(label(path.parent))
                        continue
                    where = next((folder for folder in shared if use_shared and name in shared_names[folder]), None)
                    if where is not None:
                        if is_vcpp_runtime(name):
                            importers[name].add(shown)
                            provided_by[name].add(label(where))
                        continue
                    if is_windows_builtin(name):
                        continue
                    if is_vcpp_runtime(name):
                        if kind == "static":
                            importers[name].add(shown)
                            unprovided[name].add(shown)
                        else:
                            delayed_gaps[name].add(shown)
                        continue
                    if system_dir is not None and not (system_dir / name).exists():
                        (missing if kind == "static" else delayed_gaps)[name].add(shown)

    for name, files in sorted(importers.items()):
        report.vcpp[name] = {
            "importers": len(files),
            "unprovided": sorted(unprovided.get(name, ())),
            "provided_by": sorted(provided_by.get(name, ())),
        }
    report.tools["needs"] = {name: sorted(files) for name, files in sorted(tool_needs.items())}
    report.missing = {name: sorted(files) for name, files in sorted(missing.items())}
    report.delayed = {name: sorted(files) for name, files in sorted(delayed_gaps.items())}
    return report


def _inside(path: Path, folder: Path) -> bool:
    return os.path.normcase(str(path)).startswith(os.path.normcase(str(folder)).rstrip("\\/") + os.sep)


def _shown(path: Path, root: Path, outside: bool) -> str:
    try:
        relative = str(path.relative_to(root))
    except ValueError:
        return str(path)
    return f"[Python folder]\\{relative}" if outside else relative


def _names(files: list[str], limit: int = 4) -> str:
    base = sorted({Path(file.replace("\\", "/")).name for file in files})
    return ", ".join(base[:limit]) + (f", ... ({len(base)} in all)" if len(base) > limit else "")


def format_report(report: Report) -> list[str]:
    lines = [f"Scanned {report.files} program files under {report.app}"
             + (f" and the Python folder {report.python_home}" if report.python_home else "")
             + (f"; {len(report.unreadable)} could not be read." if report.unreadable else ".")]
    for path, why in report.unreadable[:5]:
        lines.append(f"  unreadable: {path} ({why})")
    lines.append("Visual C++ runtime DLLs that the program imports (they come with the Visual C++ Redistributable, not with Windows):")
    if not report.vcpp:
        lines.append("  none")
    for name, entry in report.vcpp.items():
        source = "; ".join(entry["provided_by"]) or "nowhere"
        if entry["unprovided"]:
            allowed = " (allowed)" if name in report.allowed else ""
            lines.append(f"  {name}: imported by {entry['importers']} files; NOT PROVIDED for {len(entry['unprovided'])} of them"
                         f"{allowed}: {_names(entry['unprovided'])}")
            if entry["provided_by"]:
                lines.append(f"      the rest find it in: {source}")
        else:
            lines.append(f"  {name}: imported by {entry['importers']} files; always provided (in: {source})")
    lines.append("Other DLLs that are not beside the importer, not in a folder the program registers and not in System32:")
    if not report.missing:
        lines.append("  none")
    for name, files in report.missing.items():
        lines.append(f"  {name}: {_names(files)}" + (" (allowed)" if name in report.allowed else ""))
    if report.delayed:
        lines.append("Delay-loaded DLLs nothing provides (only needed when the feature that uses them is used; information):")
        for name, files in report.delayed.items():
            lines.append(f"  {name}: {_names(files)}")
    if report.tools["count"]:
        needs = ", ".join(f"{name} ({len(files)})" for name, files in report.tools["needs"].items()) or "nothing from the machine"
        lines.append(f"GTK's {report.tools['count']} command-line tools in gtk\\bin are not started by KaramTC and were not judged; "
                     f"run on their own they would look for: {needs}")
    problems = report.problems()
    if problems:
        lines.append(f"RESULT: {len(problems)} DLL(s) the program needs would have to come from the machine: {', '.join(problems)}")
    else:
        lines.append("RESULT: every DLL that the program loads comes with Windows or with the installation.")
    return lines


def github_summary(report: Report) -> str:
    problems = report.problems()
    out = ["### DLLs the installed program needs from the machine", ""]
    if problems:
        out += [f"**{len(problems)} DLL(s) that nothing in the installation provides:** `{'`, `'.join(problems)}`", ""]
    else:
        out += ["Everything the program loads comes with Windows or with the installation.", ""]
    out += ["| DLL | imported by | not provided for | provided in |", "|---|---|---|---|"]
    for name, entry in report.vcpp.items():
        out.append(f"| `{name}` | {entry['importers']} | {len(entry['unprovided'])}: {_names(entry['unprovided'])} | "
                   f"{'; '.join(entry['provided_by']) or '-'} |")
    for name, files in report.missing.items():
        out.append(f"| `{name}` (missing) | {len(files)} | {len(files)}: {_names(files)} | - |")
    return "\n".join(out) + "\n"


# -- What was loaded --------------------------------------------------------------------------------------

DEFAULT_IMPORTS = ("faster_whisper", "ctranslate2", "onnxruntime", "av", "pymupdf", "PIL.Image")


def classify_loaded(paths: list[str], app: Path, python_home: Path | None, windows_dirs) -> dict[str, list[str]]:
    """Sort the modules of a process by where they were loaded from: the installation, the Python folder, Windows, other.

    ``windows_dirs`` is one folder or several (Windows itself, and the folder of Microsoft Defender, which puts a module
    into every process)."""
    if isinstance(windows_dirs, Path) or windows_dirs is None:
        windows_dirs = [windows_dirs]
    def under(path: str, folder: Path | None) -> bool:
        if folder is None:
            return False
        folder_text = os.path.normcase(str(folder)).rstrip("\\/") + os.sep
        return os.path.normcase(path).startswith(folder_text)

    buckets: dict[str, list[str]] = {"app": [], "python": [], "windows": [], "other": []}
    for path in paths:
        if under(path, app):
            buckets["app"].append(path)
        elif under(path, python_home):
            buckets["python"].append(path)
        elif any(under(path, folder) for folder in windows_dirs):
            buckets["windows"].append(path)
        else:
            buckets["other"].append(path)
    return buckets


def loaded_module_paths() -> list[str]:
    """The full path of every module (DLL or program) loaded into this process. Windows only."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.K32EnumProcessModules.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD,
                                               ctypes.POINTER(wintypes.DWORD)]
    kernel32.K32EnumProcessModules.restype = wintypes.BOOL
    kernel32.K32GetModuleFileNameExW.argtypes = [wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
    kernel32.K32GetModuleFileNameExW.restype = wintypes.DWORD
    process = kernel32.GetCurrentProcess()
    modules = (wintypes.HMODULE * 4096)()
    needed = wintypes.DWORD()
    if not kernel32.K32EnumProcessModules(process, modules, ctypes.sizeof(modules), ctypes.byref(needed)):
        raise ctypes.WinError(ctypes.get_last_error())
    paths = []
    for index in range(min(needed.value // ctypes.sizeof(wintypes.HMODULE), len(modules))):
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel32.K32GetModuleFileNameExW(process, modules[index], buffer, len(buffer)):
            paths.append(buffer.value)
    return paths


def _import_all(app: Path, names: tuple[str, ...]) -> list[tuple[str, str]]:
    """Import what the program imports, GTK first and the way the program does it; the failures are returned."""
    import importlib

    failures: list[tuple[str, str]] = []

    def attempt(name: str, action) -> None:
        try:
            action()
        except BaseException as error:                      # noqa: BLE001 - every failure is the answer here
            failures.append((name, f"{type(error).__name__}: {error}"))

    def prepare() -> None:
        # What main.py does before it imports GTK: the DLL folders (the installer's Visual C++ runtime, then GTK) are made known.
        sys.path.insert(0, str(app / "src"))
        import winsupport

        winsupport.prepare_runtime()

    attempt("winsupport.prepare_runtime", prepare)

    def gtk() -> None:
        import gi

        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gtk                  # noqa: F401

    attempt("GTK and libadwaita", gtk)
    for name in names:
        attempt(name, lambda name=name: importlib.import_module(name))
    return failures


def run_loaded(app: Path, python_home: Path | None, strict: bool, names: tuple[str, ...]) -> int:
    if sys.platform != "win32":
        print("The 'loaded' command lists the DLLs of a running process and works on Windows only.")
        return 2
    if python_home is None:
        python_home = _python_home_of(app)
    failures = _import_all(app, names)
    windows_dirs = [Path(os.environ.get("SystemRoot", r"C:\Windows")),
                    Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft" / "Windows Defender"]
    buckets = classify_loaded(loaded_module_paths(), app, python_home, windows_dirs)
    for name, why in failures:
        print(f"IMPORT FAILED: {name}: {why}")
    bad = []
    print("Visual C++ runtime DLLs of this process, and where each was loaded from:")
    for bucket, title in (("app", "the installation"), ("python", "the Python folder"), ("windows", "Windows"), ("other", "somewhere else")):
        for path in sorted(buckets[bucket]):
            if is_vcpp_runtime(Path(path).name):
                print(f"  {Path(path).name}: {title}: {path}")
                if bucket in ("windows", "other"):
                    bad.append(Path(path).name)
    inside = sorted({Path(path).name for path in buckets["app"]}, key=str.lower)
    print(textwrap.fill(f"Loaded from the installation ({len(inside)} libraries): " + ", ".join(inside), width=118, subsequent_indent="  "))
    outside = [path for path in sorted(buckets["other"]) if not is_vcpp_runtime(Path(path).name)]
    if outside:
        print("Modules loaded from outside the installation, Python and Windows (something of the machine that the program uses):")
        for path in outside:
            print(f"  {path}")
    if failures or bad:
        print(f"RESULT: {len(failures)} import(s) failed; {len(set(bad))} runtime DLL(s) came from the machine instead of the installation"
              + (f": {', '.join(sorted(set(bad)))}" if bad else "."))
        return 1 if strict else 0
    print("RESULT: every import worked and every Visual C++ runtime DLL came from the installation or the Python folder.")
    return 0


# -- Command line -----------------------------------------------------------------------------------------

def _default_app() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Programs" / "KaramTC"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("scan", "loaded"):
        command = commands.add_parser(name)
        command.add_argument("--app", type=Path, default=_default_app(), help="the installation folder")
        command.add_argument("--python-home", type=Path, help="the Python the environment is made from (default: read from .venv\\pyvenv.cfg)")
        command.add_argument("--strict", action="store_true", help="exit with 1 when the answer is bad")
    scanner = commands.choices["scan"]
    scanner.add_argument("--system-dir", type=Path, default=None, help="Windows' System32 (default: the machine's own, on Windows)")
    scanner.add_argument("--provider", type=Path, action="append", default=[], help="another folder whose DLLs the program can use")
    scanner.add_argument("--allow", action="append", default=[], help="a DLL name that may be missing (repeatable)")
    scanner.add_argument("--json", type=Path, help="write the full report here")
    scanner.add_argument("--github", action="store_true", help="also write a job summary and a workflow warning for GitHub Actions")
    commands.choices["loaded"].add_argument("--import", dest="imports", action="append", help="a module to import (default: the program's libraries)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):                  # A user name with Arabic letters must not crash a console that is not UTF-8.
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="backslashreplace")

    if args.command == "loaded":
        return run_loaded(args.app, args.python_home, args.strict, tuple(args.imports or DEFAULT_IMPORTS))

    system_dir = args.system_dir
    if system_dir is None and sys.platform == "win32":
        system_dir = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    if not args.app.is_dir():
        print(f"There is no installation at {args.app}.")
        return 2
    report = scan(args.app, args.python_home, system_dir, tuple(args.allow), tuple(args.provider))
    for line in format_report(report):
        print(line)
    if args.json:
        args.json.write_text(json.dumps(report.__dict__, indent=2, default=str), encoding="utf-8")
    if args.github:
        problems = report.problems()
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(github_summary(report))
        if problems:
            print(f"::warning title=The installed program needs DLLs from the machine::{', '.join(problems)}")
    return 1 if (args.strict and report.problems()) else 0


if __name__ == "__main__":
    sys.exit(main())
