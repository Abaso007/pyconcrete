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
import os
import textwrap
from os.path import join
from subprocess import CalledProcessError

import pytest

from .conftest import Venv


def _build_zip(venv_cli, source_dir, output_zip, ext=None):
    """Use pyecli build-zip to compile .py -> .pye and pack into zip."""
    args = ['build-zip', f'--source={source_dir}', f'--output={output_zip}']
    if ext:
        args.append(f'--ext={ext}')
    venv_cli.pyconcrete_cli(*args)


def _write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(textwrap.dedent(content).strip())


def test_zip_import__single_module(venv_lib, venv_cli, tmpdir):
    """Import a single .pye module from a zip archive."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    os.makedirs(source_dir)
    _write_file(
        join(source_dir, 'hello.py'),
        """
        GREETING = 'hello from zip'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        import hello
        print(hello.GREETING)
    """,
    )

    # execution
    output = venv_lib.python(executor_py).strip()

    # verification
    assert output == 'hello from zip'


def test_zip_import__package_with_init(venv_lib, venv_cli, tmpdir):
    """Import a package (with __init__.pye) from a zip archive."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    pkg_dir = join(source_dir, 'mypkg')
    os.makedirs(pkg_dir)
    _write_file(
        join(pkg_dir, '__init__.py'),
        """
        PKG_NAME = 'mypkg'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        import mypkg
        print(mypkg.PKG_NAME)
    """,
    )

    # execution
    output = venv_lib.python(executor_py).strip()

    # verification
    assert output == 'mypkg'


def test_zip_import__package_submodule(venv_lib, venv_cli, tmpdir):
    """Import a submodule from a package inside a zip archive."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    pkg_dir = join(source_dir, 'mypkg')
    os.makedirs(pkg_dir)
    _write_file(
        join(pkg_dir, '__init__.py'),
        """
        pass
    """,
    )
    _write_file(
        join(pkg_dir, 'util.py'),
        """
        VALUE = 42
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        from mypkg.util import VALUE
        print(VALUE)
    """,
    )

    # execution
    output = venv_lib.python(executor_py).strip()

    # verification
    assert output == '42'


def test_zip_import__nested_package(venv_lib, venv_cli, tmpdir):
    """Import a nested sub-package from a zip archive."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    sub_dir = join(source_dir, 'pkg', 'sub')
    os.makedirs(sub_dir)
    _write_file(
        join(source_dir, 'pkg', '__init__.py'),
        """
        pass
    """,
    )
    _write_file(
        join(sub_dir, '__init__.py'),
        """
        pass
    """,
    )
    _write_file(
        join(sub_dir, 'mod.py'),
        """
        NESTED = 'deep'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        from pkg.sub.mod import NESTED
        print(NESTED)
    """,
    )

    # execution
    output = venv_lib.python(executor_py).strip()

    # verification
    assert output == 'deep'


@pytest.mark.parametrize("ext", [".t", ".tw"])
def test_zip_import__custom_ext(tmp_path_factory, tmpdir, ext):
    """build-zip with custom extension should produce importable zip."""
    # prepare venv with custom ext
    venv = Venv(
        env_dir=tmp_path_factory.mktemp('venv_zip_ext_'),
        pyconcrete_ext=ext,
        install_mode='lib',
        install_cli=True,
    )

    source_dir = join(str(tmpdir), 'src')
    os.makedirs(source_dir)
    _write_file(
        join(source_dir, 'hello.py'),
        """
        GREETING = 'hello from custom ext zip'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv, source_dir, zip_path, ext=ext)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        import hello
        print(hello.GREETING)
    """,
    )

    # execution
    output = venv.python(executor_py).strip()

    # verification
    assert output == 'hello from custom ext zip'


def test_zip_import__module_not_found(venv_lib, venv_cli, tmpdir):
    """Importing a module that does not exist in the zip should raise ImportError."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    os.makedirs(source_dir)
    _write_file(
        join(source_dir, 'hello.py'),
        """
        GREETING = 'hello from zip'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        import nonexistent
    """,
    )

    # execution & verification
    with pytest.raises(CalledProcessError):
        venv_lib.python(executor_py)


def test_zip_import__reimport_reload(venv_lib, venv_cli, tmpdir):
    """importlib.reload should re-execute the module from the zip."""
    # prepare
    source_dir = join(str(tmpdir), 'src')
    os.makedirs(source_dir)
    _write_file(
        join(source_dir, 'hello.py'),
        """
        GREETING = 'hello from zip'
    """,
    )

    zip_path = join(str(tmpdir), 'modules.zip')
    _build_zip(venv_cli, source_dir, zip_path)

    executor_py = join(str(tmpdir), 'executor.py')
    _write_file(
        executor_py,
        f"""
        import sys
        import importlib
        import pyconcrete
        sys.path.insert(0, {zip_path!r})
        import hello
        print(hello.GREETING)
        hello.GREETING = 'changed'
        importlib.reload(hello)
        print(hello.GREETING)
    """,
    )

    # execution
    output = venv_lib.python(executor_py).strip()

    # verification
    lines = output.splitlines()
    assert lines[0] == 'hello from zip'
    assert lines[1] == 'hello from zip'
