#!/usr/bin/env python
#
# Copyright 2015 Falldog Hsieh <falldog7@gmail.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import importlib
import importlib.util
import marshal
import os
import struct
import sys
import threading
import zipfile
import zipimport
from importlib._bootstrap_external import _get_supported_file_loaders
from importlib.machinery import SOURCE_SUFFIXES, FileFinder, ModuleSpec, SourceFileLoader

try:
    # for import the module which installed at site-packages
    from . import _pyconcrete  # noqa: E402
except ImportError:
    # for import the module which embedded in pyconcrete exe
    import _pyconcrete  # noqa: E402

__all__ = ["info"]

_pyconcrete_module = _pyconcrete


def decrypt_buffer(data):
    return _pyconcrete_module.decrypt_buffer(data)


def encrypt_file(pyc_filepath, pye_filepath):
    return _pyconcrete_module.encrypt_file(pyc_filepath, pye_filepath)


def info():
    return _pyconcrete_module.info()


def get_ext():
    """get supported file extension, default should be .pye"""
    return _pyconcrete_module.get_ext()


# We need to modify SOURCE_SUFFIXES, because it used in importlib.machinery.all_suffixes function which
# called by inspect.getmodulename and we need to be able to detect the module name relative to .pye files
# because .py can be deleted by us
SOURCE_SUFFIXES.append(get_ext())


def _get_magic_size():
    """Return the size of the pyc header (magic + metadata) for the current Python version."""
    if sys.version_info >= (3, 7):
        # python/Lib/importlib/_bootstrap_external.py _code_to_timestamp_pyc() & _code_to_hash_pyc()
        # MAGIC + HASH + TIMESTAMP + FILE_SIZE
        return 16
    elif sys.version_info >= (3, 3):
        # python/Lib/importlib/_bootstrap_external.py _code_to_bytecode()
        # MAGIC + TIMESTAMP + FILE_SIZE
        return 12
    else:
        # MAGIC + TIMESTAMP
        return 8


class PyeLoader(SourceFileLoader):
    @property
    def magic(self):
        return _get_magic_size()

    @staticmethod
    def _validate_version(data):
        magic = importlib.util.MAGIC_NUMBER
        ml = len(magic)
        if data[:ml] != magic:
            # convert little-endian byte string to unsigned short
            py_magic = struct.unpack('<H', magic[:2])[0]
            pye_magic = struct.unpack('<H', data[:2])[0]
            raise ValueError("Python version doesn't match with magic: python(%d) != pye(%d)" % (py_magic, pye_magic))

    def get_code(self, fullname):
        if not self.path.endswith(get_ext()):
            return super().get_code(fullname)

        path = self.get_filename(fullname)
        data = decrypt_buffer(self.get_data(path))
        self._validate_version(data)
        return marshal.loads(data[self.magic :])

    def get_source(self, fullname):
        if self.path.endswith(get_ext()):
            return None
        return super().get_source(fullname)


class PyeZipImporter:
    """PEP-451 finder+loader for .pye files inside zip archives."""

    _zip_directory_cache = {}
    _cache_lock = threading.Lock()
    _negative_cache = set()

    def __init__(self, path):
        # Pre-check: skip filesystem walk for paths that clearly aren't zip-related.
        # Note: For submodule imports, Python passes sub-paths like '/foo/bar.zip/mypkg'
        #       all package/submodule imports from within zip archives.
        if '.zip' not in path:
            raise ImportError(f"not a zip file: {path}")

        if path in self._negative_cache:
            raise ImportError(f"not a zip file: {path}")

        self._zip_path, self._prefix = self._split_zip_path(path)
        if self._zip_path is None:
            self._negative_cache.add(path)
            raise ImportError(f"not a zip file: {path}")

        # fallback for non-.pye imports (e.g. .pyc) in the same zip
        try:
            self._fallback = zipimport.zipimporter(path)
        except zipimport.ZipImportError:
            raise ImportError(f"not a valid zip file: {path}")

        # thread-safe cache population
        if self._zip_path not in self._zip_directory_cache:
            with self._cache_lock:
                if self._zip_path not in self._zip_directory_cache:
                    try:
                        with zipfile.ZipFile(self._zip_path, 'r') as zf:
                            self._zip_directory_cache[self._zip_path] = set(zf.namelist())
                    except (zipfile.BadZipFile, OSError):
                        raise ImportError(f"not a valid zip file: {self._zip_path}")

    @staticmethod
    def _split_zip_path(path):
        """
        Split '/foo/bar.zip/subdir' into ('/foo/bar.zip', 'subdir').
        Note: Per ZIP Spec, it's only to use forward slash `/` for cross palform
        """
        p = path
        prefix = ''
        while True:
            if os.path.isfile(p) and zipfile.is_zipfile(p):
                return p, prefix
            parent, tail = os.path.split(p)
            if parent == p:
                return None, None
            prefix = tail + '/' + prefix if prefix else tail
            p = parent

    def _get_namelist(self):
        return self._zip_directory_cache.get(self._zip_path, set())

    def _make_path(self, *parts):
        components = [self._prefix] + list(parts) if self._prefix else list(parts)
        return '/'.join(c for c in components if c)

    def _find_pye(self, fullname):
        """Return (zip_internal_path, is_package) or None."""
        # 'mypkg.util' -> 'util', self._prefix already provides the parent path
        tail = fullname.rsplit('.', 1)[-1]
        namelist = self._get_namelist()
        ext = get_ext()

        pkg_init = self._make_path(tail, '__init__' + ext)
        if pkg_init in namelist:
            return pkg_init, True

        mod_path = self._make_path(tail + ext)
        if mod_path in namelist:
            return mod_path, False

        return None

    def _make_file_path(self, zip_internal_path):
        """Build __file__ path with consistent os.sep separators."""
        return self._zip_path + os.sep + zip_internal_path.replace('/', os.sep)

    def _make_pkg_path(self, tail):
        """Build __path__ entry with consistent os.sep separators."""
        return self._zip_path + os.sep + self._make_path(tail).replace('/', os.sep)

    # --- PEP-451 finder protocol ---

    def find_spec(self, fullname, path, target=None):
        found = self._find_pye(fullname)
        if not found:
            return self._fallback.find_spec(fullname, target)

        zip_internal_path, is_package = found
        origin = self._make_file_path(zip_internal_path)

        spec = ModuleSpec(fullname, self, origin=origin, is_package=is_package)
        if is_package:
            tail = fullname.rsplit('.', 1)[-1]
            spec.submodule_search_locations = [self._make_pkg_path(tail)]

        return spec

    # --- PEP-451 loader protocol ---

    def create_module(self, spec):
        return None  # use default module creation

    def exec_module(self, module):
        spec = module.__spec__
        found = self._find_pye(spec.name)
        if not found:
            raise ImportError(f"cannot find {spec.name} in {self._zip_path}")

        zip_internal_path, _is_package = found

        with zipfile.ZipFile(self._zip_path, 'r') as zf:
            encrypted_data = zf.read(zip_internal_path)

        data = decrypt_buffer(encrypted_data)
        PyeLoader._validate_version(data)
        code = marshal.loads(data[_get_magic_size() :])

        exec(code, module.__dict__)

    @classmethod
    def invalidate_caches(cls):
        with cls._cache_lock:
            cls._zip_directory_cache.clear()
            cls._negative_cache.clear()


def install():
    # only put pyconcrete ext/suffix(.pye) for loader, leave default suffixes(SOURCE_SUFFIXES) to default loader
    loader_details = [(PyeLoader, [get_ext()])] + _get_supported_file_loaders()

    sys.path_importer_cache.clear()
    sys.path_hooks.insert(0, FileFinder.path_hook(*loader_details))
    sys.path_hooks.insert(1, PyeZipImporter)


install()
