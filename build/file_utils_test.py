# Copyright 2025 The Android Open Source Project
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
"""Tests for file_utils"""

import file_utils
import unittest


# pylint: disable=missing-docstring
class FileUtilsTest(unittest.TestCase):

    # tests

    def test_removing_markers(self):
        lines = [
            ";;* lms 1 test_sepolicy.cil",
            "(type foo)",
            ";;* lmx 1 foo.te",
            ";;* lme",
            ";;* lmx 1 bar.te",
            ";;* lmx 2 bar.te",
            ";;* lme",
            ";;* lme",
            ";;* lmx 3 bar.te",
            "(allow foo self (file (read)))",
            "(neverallow foo self (file (write)))",
            ";;* lme",
            ";;* lme", # lms 1 test_sepolicy.cil
        ]

        expected = [
            ";;* lms 1 test_sepolicy.cil",
            "(type foo)",
            ";;* lmx 3 bar.te",
            "(allow foo self (file (read)))",
            "(neverallow foo self (file (write)))",
            ";;* lme",
            ";;* lme", # lms 1 test_sepolicy.cil
        ]

        actual = file_utils.remove_redundant_line_markers(lines)

        # Line markers without any statements must be removed
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
