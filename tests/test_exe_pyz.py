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
import subprocess
import textwrap
import zipfile
from os.path import join

import pytest

from .conftest import PyeBuilder


@pytest.fixture
def builder(venv_exe, venv_cli, tmp_path):
    return PyeBuilder().setup(venv_exe, venv_cli, tmp_path)


def _build_pyz(venv_cli, source_dir, output_path, ext=None, main=None):
    """Helper to build a .pyz via pyecli build-zip."""
    args = ['build-zip', f'--source={source_dir}', f'--output={output_path}']
    if ext:
        args.append(f'--ext={ext}')
    if main:
        args.append(f'--main={main}')
    venv_cli.pyconcrete_cli(*args)


def _make_source_dir(tmp_path, name, files):
    """Create a source directory with the given files dict {relative_path: content}."""
    src_dir = join(str(tmp_path), name)
    os.makedirs(src_dir, exist_ok=True)
    for rel_path, content in files.items():
        full_path = join(src_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write(content)
    return src_dir


def test_exe_pyz__basic(venv_exe, venv_cli, tmp_path):
    """__main__.pye prints output, verify stdout."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_basic',
        {
            '__main__.py': 'print("hello from pyz")',
        },
    )
    pyz_path = join(str(tmp_path), 'app_basic.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path)

    output = venv_exe.pyconcrete(pyz_path)
    assert output.strip() == 'hello from pyz'


def test_exe_pyz__import_submodule(venv_exe, venv_cli, tmp_path):
    """__main__.pye imports another .pye from same zip."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_sub',
        {
            '__main__.py': textwrap.dedent(
                """\
            import helper
            helper.greet()
        """
            ),
            'helper.py': textwrap.dedent(
                """\
            def greet():
                print("hello from helper")
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_sub.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path)

    output = venv_exe.pyconcrete(pyz_path)
    assert output.strip() == 'hello from helper'


def test_exe_pyz__with_package(venv_exe, venv_cli, tmp_path):
    """Nested package imports within zip."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_pkg',
        {
            '__main__.py': textwrap.dedent(
                """\
            from mypkg.util import add
            print(add(2, 3))
        """
            ),
            'mypkg/__init__.py': '',
            'mypkg/util.py': textwrap.dedent(
                """\
            def add(a, b):
                return a + b
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_pkg.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path)

    output = venv_exe.pyconcrete(pyz_path)
    assert output.strip() == '5'


def test_exe_pyz__no_main_should_fail(venv_exe, venv_cli, tmp_path):
    """Zip without __main__.pye returns non-zero."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_nomain',
        {
            'helper.py': 'x = 1',
        },
    )
    pyz_path = join(str(tmp_path), 'app_nomain.pyz')
    # Use .zip extension to bypass .pyz validation, then rename
    zip_path = join(str(tmp_path), 'app_nomain.zip')
    _build_pyz(venv_cli, src_dir, zip_path)
    os.rename(zip_path, pyz_path)

    p = subprocess.Popen(
        [venv_exe.pyconcrete_exe, pyz_path],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    p.communicate()
    assert p.returncode != 0


def test_exe_pyz__sys_argv(venv_exe, venv_cli, tmp_path):
    """Verify sys.argv[0] is the .pyz path."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_argv',
        {
            '__main__.py': textwrap.dedent(
                """\
            import sys
            print(sys.argv[0])
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_argv.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path)

    output = venv_exe.pyconcrete(pyz_path)
    assert os.path.basename(output.strip()) == 'app_argv.pyz'


def test_exe_pyz__sys_path(venv_exe, venv_cli, tmp_path):
    """Verify sys.path[0] is the .pyz file itself."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_path',
        {
            '__main__.py': textwrap.dedent(
                """\
            import sys
            print(sys.path[0])
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_path.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path)

    output = venv_exe.pyconcrete(pyz_path)
    assert output.strip().endswith('app_path.pyz')


def test_exe_pyz__entry_point(venv_exe, venv_cli, tmp_path):
    """build-zip -m 'mymod:main' generates __main__.pye that calls mymod.main()."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_entry',
        {
            'mymod.py': textwrap.dedent(
                """\
            def main():
                print("entry point works")
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_entry.pyz')
    _build_pyz(venv_cli, src_dir, pyz_path, main='mymod:main')

    # Verify __main__.pye exists in the zip
    with zipfile.ZipFile(pyz_path, 'r') as zf:
        assert '__main__.pye' in zf.namelist()

    output = venv_exe.pyconcrete(pyz_path)
    assert output.strip() == 'entry point works'


def test_exe_pyz__entry_point_invalid_format(venv_cli, tmp_path):
    """-m 'invalid' (no colon) raises error."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_invalid',
        {
            'mymod.py': textwrap.dedent(
                """\
            def main():
                pass
        """
            ),
        },
    )
    pyz_path = join(str(tmp_path), 'app_invalid.pyz')
    with pytest.raises(subprocess.CalledProcessError):
        _build_pyz(venv_cli, src_dir, pyz_path, main='invalid')


def test_exe_pyz__pyz_without_main_or_entry_point(venv_cli, tmp_path):
    """.pyz output without __main__.py or -m raises error."""
    src_dir = _make_source_dir(
        tmp_path,
        'app_nomainpy',
        {
            'helper.py': 'x = 1',
        },
    )
    pyz_path = join(str(tmp_path), 'app_nomainpy.pyz')
    with pytest.raises(subprocess.CalledProcessError):
        _build_pyz(venv_cli, src_dir, pyz_path)
