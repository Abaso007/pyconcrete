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
import os.path
import platform
import subprocess
import sys

import pytest

from .conftest import PyeBuilder


def test_exe__execute_an_non_exist_file(venv_exe):
    return_code = subprocess.call([venv_exe.pyconcrete_exe, 'non_existing_file.txt'])
    assert return_code == 1


def test_exe__sys_path__should_contain_pye_file_dir(venv_exe, venv_cli, tmpdir):
    builder = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .add_module('test_sys_path', source_code="import sys\nprint('\\n'.join(sys.path))")
        .build()
    )
    pye_path = builder.get_pye_path('test_sys_path')

    # execution
    output = venv_exe.pyconcrete(pye_path)
    output = output.replace('\r\n', '\n')
    paths = output.split('\n')

    # verification
    assert builder.tmp_dir in paths, "the folder of pye-file should be contained in sys.path"


def test_exe__sys_argv__first_arg_should_be_file_name(venv_exe, venv_cli, tmpdir):
    builder = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .add_module('test_sys_argv', source_code="import sys\nprint(' '.join(sys.argv))")
        .build()
    )
    pye_path = builder.get_pye_path('test_sys_argv')

    # execution
    output = venv_exe.pyconcrete(pye_path).strip()

    # verification
    assert output == pye_path


def test_exe__sys_argv__more_arguments(venv_exe, venv_cli, tmpdir):
    builder = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .add_module('test_sys_argv', source_code="import sys\nprint(' '.join(sys.argv))")
        .build()
    )
    pye_path = builder.get_pye_path('test_sys_argv')

    # execution
    output = venv_exe.pyconcrete(pye_path, '-a', '-b', '-c').strip()

    # verification
    assert output == f'{pye_path} -a -b -c'


@pytest.mark.skipif(platform.system() == 'Windows' and sys.version_info < (3, 8), reason="Windows requires python3.8")
def test_exe__sys_argv__in_unicode(venv_exe, venv_cli, tmpdir):
    builder = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .add_module('test_sys_argv', source_code="import sys\nprint(' '.join(sys.argv))")
        .build()
    )
    pye_path = builder.get_pye_path('test_sys_argv')

    # execution
    output = venv_exe.pyconcrete(pye_path, '早安', '=', 'おはようございます').strip()

    # verification
    assert output == f'{pye_path} 早安 = おはようございます'


def test_exe__import_pyconcrete__venv_exe__validate__file__(venv_exe, venv_cli, tmpdir):
    """
    compare to test_lib__import_pyconcrete__venv_lib__validate__file__
    pyconcrete exe embedded `pyconcrete` module doesn't have `__file__` attribute
    """
    output = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .build()
        .run_pye(
            source_code="""
            import pyconcrete
            print(getattr(pyconcrete, '__file__', 'None'))
        """
        )
    )

    # verification
    assert output == 'None'


def test_exe__validate_main__file__full_path(venv_exe, venv_cli, tmpdir):
    builder = (
        PyeBuilder().setup(venv_exe, venv_cli, tmpdir).add_module('test__file__', source_code="print(__file__)").build()
    )
    pye_path = builder.get_pye_path('test__file__')

    # execution
    output = venv_exe.pyconcrete(pye_path).strip()

    # verification
    assert output == pye_path


def test_exe__validate_main__file__relative_path(venv_exe, venv_cli, tmpdir):
    # simulate cmd as: `pyconcrete ../foo.pye`
    # print(__file__) get correct full path
    builder = (
        PyeBuilder().setup(venv_exe, venv_cli, tmpdir).add_module('test__file__', source_code="print(__file__)").build()
    )
    pye_full_path = builder.get_pye_path('test__file__')
    cwd = venv_exe.env_dir
    pye_relative_path = os.path.relpath(pye_full_path, cwd)

    # execution
    output = venv_exe.pyconcrete(pye_relative_path, cwd=cwd).strip()

    # verification
    assert output == pye_full_path
