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
import platform
import subprocess
import sys
import textwrap
from os.path import abspath, dirname, join

import pytest

ROOT_DIR = abspath(join(dirname(__file__), '..'))
PASSPHRASE = 'TestPyconcrete'


def exe_name(name):
    if platform.system() == 'Windows':
        return f'{name}.exe'
    return name


class Venv:
    def __init__(self, env_dir, pyconcrete_ext=None, install_mode='exe', install_cli=False):
        assert install_mode in ('lib', 'exe')
        self.executable = None
        self.bin_dir = None
        self.env_dir = env_dir
        self._pyconcrete_ext = pyconcrete_ext
        self._install_mode = install_mode
        self._install_cli = install_cli
        self.create()

    def create(self):
        subprocess.check_call([sys.executable, '-m', 'virtualenv', str(self.env_dir)])
        if platform.system() == 'Windows':
            self.bin_dir = join(self.env_dir, 'Scripts')
        else:
            self.bin_dir = join(self.env_dir, 'bin')
        self.executable = join(self.bin_dir, exe_name('python'))
        self._ensure_pyconcrete_exist()

    def python(self, *args: [str], shell=False):
        cmd = [self.executable, *args]
        if shell:
            cmd = ' '.join(cmd)
        return subprocess.check_output(cmd, shell=shell).decode()

    def pip(self, *args: [str]):
        return self.python('-m', 'pip', *args)

    @property
    def pyconcrete_exe(self):
        self._ensure_pyconcrete_exist()
        return join(self.bin_dir, exe_name('pyconcrete'))

    def pyconcrete(self, *args: [str], cwd=None):
        self._ensure_pyconcrete_exist()
        return subprocess.check_output([self.pyconcrete_exe, *args], cwd=cwd).decode()

    def pyconcrete_cli(self, *args: [str]):
        self._ensure_pyconcrete_exist()
        cli = join(self.bin_dir, exe_name('pyecli'))
        return subprocess.check_output([cli, *args]).decode()

    @property
    def install_mode(self):
        return self._install_mode

    def _ensure_pyconcrete_exist(self):
        if platform.system() == 'Windows':
            cmd = f'{self.executable} -m pip list | findstr pyconcrete'
        else:
            cmd = f'{self.executable} -m pip list | grep -c pyconcrete'
        proc = subprocess.run(cmd, shell=True)
        pyconcrete_exist = bool(proc.returncode == 0)
        if not pyconcrete_exist:
            args = [
                'install',
                f'--config-settings=setup-args=-Dpassphrase={PASSPHRASE}',
                f'--config-settings=setup-args=-Dext={self._pyconcrete_ext}' if self._pyconcrete_ext else '',
                f'--config-settings=setup-args=-Dmode={self._install_mode}',
                f'--config-settings=setup-args=-Dinstall-cli={"true" if self._install_cli else "false"}',
                '--quiet',
                ROOT_DIR,
            ]
            args = [arg for arg in args if arg]  # filter empty string
            self.pip(*args)


class PyeBuilder:
    def __init__(self):
        self._venv_runner = None
        self._venv_cli = None
        self._tmp_dir = None
        self._modules = []
        self._zip_modules = {}
        self._zip_paths = {}
        self._ext = None
        self._built = False
        self._main_pye_path = None

    def setup(self, venv_runner, venv_cli, tmp_dir):
        """
        Args:
            venv_runner: Venv used to execute scripts (exe mode uses pyconcrete binary, lib mode uses python)
            venv_cli: Venv with pyecli installed, used for compiling .py -> .pye and building zips
            tmp_dir: temporary directory for generated files
        """
        self._venv_runner = venv_runner
        self._venv_cli = venv_cli
        self._tmp_dir = str(tmp_dir)
        return self

    def add_module(self, name, source_code):
        self._modules.append((name, textwrap.dedent(source_code).strip()))
        return self

    def add_module_in_zip(self, zip_name, module_path, source_code):
        self._zip_modules.setdefault(zip_name, []).append((module_path, textwrap.dedent(source_code).strip()))
        return self

    def build(self, ext=None):
        self._ext = ext

        # Encrypt .pye modules
        compile_args = ['compile', '--remove-py']
        if ext:
            compile_args += ['--ext', ext]
        else:
            compile_args.append('--pye')
        for name, code in self._modules:
            py_path = join(self._tmp_dir, f'{name}.py')
            with open(py_path, 'w', encoding='utf-8') as f:
                f.write(code)
            self._venv_cli.pyconcrete_cli(*compile_args, '-s', py_path)

        # Build zip archives
        for zip_name, modules in self._zip_modules.items():
            source_dir = join(self._tmp_dir, f'_zsrc_{zip_name}')
            for rel_path, code in modules:
                full_path = join(source_dir, rel_path)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, 'w') as f:
                    f.write(code)
            zip_path = join(self._tmp_dir, f'{zip_name}.zip')
            args = ['build-zip', f'--source={source_dir}', f'--output={zip_path}']
            if ext:
                args.append(f'--ext={ext}')
            self._venv_cli.pyconcrete_cli(*args)
            self._zip_paths[zip_name] = zip_path
        self._built = True
        return self

    @property
    def tmp_dir(self):
        return self._tmp_dir

    def get_pye_path(self, module_name):
        pye_ext = self._ext or '.pye'
        return join(self._tmp_dir, f'{module_name}{pye_ext}')

    @property
    def zip_paths(self):
        return dict(self._zip_paths)

    @property
    def main_pye_path(self):
        return self._main_pye_path

    def run_pye(self, source_code, args=None, cwd=None):
        """Encrypt source_code to .pye and run via pyconcrete executable."""
        assert self._built, "must call build() before run_pye()"
        assert self._venv_runner.install_mode == 'exe', "venv_runner must install as exe mode"
        source_code = textwrap.dedent(source_code).strip()
        extra_args = args or []

        main_py = join(self._tmp_dir, '__main__.py')
        with open(main_py, 'w', encoding='utf-8') as f:
            f.write(source_code)
        compile_args = ['compile', '--remove-py']
        if self._ext:
            compile_args += ['--ext', self._ext]
        else:
            compile_args.append('--pye')
        self._venv_cli.pyconcrete_cli(*compile_args, '-s', main_py)
        pye_ext = self._ext or '.pye'
        self._main_pye_path = join(self._tmp_dir, f'__main__{pye_ext}')
        return self._venv_runner.pyconcrete(self._main_pye_path, *extra_args, cwd=cwd).strip()

    def run_py(self, source_code, args=None):
        """Run source_code as plain .py via python (pyconcrete imported as lib)."""
        assert self._built, "must call build() before run_py()"
        source_code = textwrap.dedent(source_code).strip()
        extra_args = args or []

        # generate main_py and add pre-processing instruction
        # 1. import pyconcrete
        # 2. insert zip module path for further importing
        preamble_lines = ['import sys', 'import pyconcrete']
        for zip_path in self._zip_paths.values():
            preamble_lines.append(f'sys.path.insert(0, {zip_path!r})')
        full_script = '\n'.join(preamble_lines) + '\n' + source_code
        main_py = join(self._tmp_dir, '_executor.py')
        with open(main_py, 'w') as f:
            f.write(full_script)

        return self._venv_runner.python(main_py, *extra_args).strip()


@pytest.fixture(scope='session')
def venv_exe(tmp_path_factory):
    """
    the virtual environment for testing pyconcrete exe
    """
    return Venv(
        env_dir=tmp_path_factory.mktemp('venv_exe_'),
    )


@pytest.fixture(scope='session')
def venv_cli(tmp_path_factory):
    """
    the virtual environment for testing pyconcrete cli
    """
    return Venv(
        env_dir=tmp_path_factory.mktemp('venv_cli_'),
        install_cli=True,
    )


@pytest.fixture(scope='session')
def venv_lib(tmp_path_factory):
    """
    the virtual environment for testing pyconcrete lib
    """
    return Venv(
        env_dir=tmp_path_factory.mktemp('venv_lib_'),
        install_mode='lib',
    )


@pytest.fixture
def sample_module_path():
    return join(ROOT_DIR, 'tests', 'fixtures', 'sample_module')


@pytest.fixture
def sample_import_sub_module_path():
    return join(ROOT_DIR, 'tests', 'exe_testcases', 'test_import_sub_module')
