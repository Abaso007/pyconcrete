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
from subprocess import CalledProcessError

import pytest

from .conftest import PyeBuilder, Venv


def test_zip_import__single_module(venv_lib, venv_cli, tmpdir):
    """Import a single .pye module from a zip archive."""
    output = (
        PyeBuilder()
        .setup(venv_lib, venv_cli, tmpdir)
        .add_module_in_zip('modules', 'hello.py', source_code="GREETING = 'hello from zip'")
        .build()
        .run_py(
            source_code="""
            import hello
            print(hello.GREETING)
        """
        )
    )
    assert output == 'hello from zip'


def test_zip_import__package_with_init(venv_lib, venv_cli, tmpdir):
    """Import a package (with __init__.pye) from a zip archive."""
    output = (
        PyeBuilder()
        .setup(venv_lib, venv_cli, tmpdir)
        .add_module_in_zip('modules', 'mypkg/__init__.py', source_code="PKG_NAME = 'mypkg'")
        .build()
        .run_py(
            source_code="""
            import mypkg
            print(mypkg.PKG_NAME)
        """
        )
    )
    assert output == 'mypkg'


def test_zip_import__package_submodule(venv_lib, venv_cli, tmpdir):
    """Import a submodule from a package inside a zip archive."""
    output = (
        PyeBuilder()
        .setup(venv_lib, venv_cli, tmpdir)
        .add_module_in_zip('modules', 'mypkg/__init__.py', source_code="pass")
        .add_module_in_zip('modules', 'mypkg/util.py', source_code="VALUE = 42")
        .build()
        .run_py(
            source_code="""
            from mypkg.util import VALUE
            print(VALUE)
        """
        )
    )
    assert output == '42'


def test_zip_import__nested_package(venv_lib, venv_cli, tmpdir):
    """Import a nested sub-package from a zip archive."""
    output = (
        PyeBuilder()
        .setup(venv_lib, venv_cli, tmpdir)
        .add_module_in_zip('modules', 'pkg/__init__.py', source_code="pass")
        .add_module_in_zip('modules', 'pkg/sub/__init__.py', source_code="pass")
        .add_module_in_zip('modules', 'pkg/sub/mod.py', source_code="NESTED = 'deep'")
        .build()
        .run_py(
            source_code="""
            from pkg.sub.mod import NESTED
            print(NESTED)
        """
        )
    )
    assert output == 'deep'


@pytest.mark.parametrize("ext", [".t", ".tw"])
def test_zip_import__custom_ext(tmp_path_factory, tmpdir, ext):
    """build-zip with custom extension should produce importable zip."""
    venv = Venv(
        env_dir=tmp_path_factory.mktemp('venv_zip_ext_'),
        pyconcrete_ext=ext,
        install_mode='lib',
        install_cli=True,
    )
    output = (
        PyeBuilder()
        .setup(venv, venv, tmpdir)
        .add_module_in_zip('modules', 'hello.py', source_code="GREETING = 'hello from custom ext zip'")
        .build(ext=ext)
        .run_py(
            source_code="""
            import hello
            print(hello.GREETING)
        """
        )
    )
    assert output == 'hello from custom ext zip'


def test_zip_import__module_not_found(venv_lib, venv_cli, tmpdir):
    """Importing a module that does not exist in the zip should raise ImportError."""
    with pytest.raises(CalledProcessError):
        (
            PyeBuilder()
            .setup(venv_lib, venv_cli, tmpdir)
            .add_module_in_zip('modules', 'hello.py', source_code="GREETING = 'hello from zip'")
            .build()
            .run_py(source_code="import nonexistent")
        )


def test_zip_import__reimport_reload(venv_lib, venv_cli, tmpdir):
    """importlib.reload should re-execute the module from the zip."""
    output = (
        PyeBuilder()
        .setup(venv_lib, venv_cli, tmpdir)
        .add_module_in_zip('modules', 'hello.py', source_code="GREETING = 'hello from zip'")
        .build()
        .run_py(
            source_code="""
            import importlib
            import hello
            print(hello.GREETING)
            hello.GREETING = 'changed'
            importlib.reload(hello)
            print(hello.GREETING)
        """
        )
    )
    lines = output.splitlines()
    assert lines[0] == 'hello from zip'
    assert lines[1] == 'hello from zip'
