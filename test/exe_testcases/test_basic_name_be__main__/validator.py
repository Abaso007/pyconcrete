#!/usr/bin/env python
# -*- coding: utf8 -*-
# Create on : 2019/07/14
from __future__ import unicode_literals


def validate(output_lines, *args, **kwargs):
    assert len(output_lines) == 1 and output_lines[0] == '__main__'
    return True
