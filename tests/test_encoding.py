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
import pytest

from .conftest import PyeBuilder


@pytest.mark.parametrize("text", ["早安", "¡Buenos días!", "おはようございます"])
def test_encoding(venv_exe, venv_cli, tmpdir, text):
    # fix windows encoding issue, write byte to stdout directly
    output = (
        PyeBuilder()
        .setup(venv_exe, venv_cli, tmpdir)
        .build()
        .run_pye(
            source_code=f"""
            import sys
            sys.stdout.buffer.write('{text}'.encode('utf-8'))
        """
        )
    )

    # verification
    assert output == text
