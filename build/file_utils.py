# Copyright 2018 - The Android Open Source Project
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

"""File-related utilities."""


import os
import shutil
import tempfile


def make_parent_dirs(file_path):
    """Creates parent directories for the file_path."""
    if os.path.exists(file_path):
        return

    parent_dir = os.path.dirname(file_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir)


def remove_redundant_line_markers(lines):
    """
    Removes any redundant line markers.

    Line markers are to support better error reporting for neverallow rules.
    Line markers, possibly nested, look like:

        ;;* lm(s|x) LINENO FILENAME
        (CIL STATEMENTS)
        ;;* lme

    * lms is used when each of the following CIL statements corresponds to a line
      in the original file.

    * lmx is used when the following CIL statements are all expanded from a
      single high-level language line.

    * lme ends a line mark block.

    Redundant line markers are markers without any statements inside. Normally
    there are no such redundant line markers, but CIL files filtered out by
    filter_out function below may contain those. remove_redundant_line_markers
    find all such redundant line markers and removes all of them. See
    file_utils_test.py for an example.
    """

    marker_stk = []
    valid = [False] * len(lines)

    for idx in range(len(lines)):
        line = lines[idx]
        if line.startswith(";;* lmx") or line.startswith(";;* lms"):
            # line start marker
            marker_stk.append(idx)
        elif line.startswith(";;* lme"): # line end marker
            if valid[marker_stk[-1]]:
                valid[idx] = True
                # propagate valid to parent markers
                if len(marker_stk) >= 2:
                    valid[marker_stk[-2]] = True
            marker_stk.pop()
        else:
            # any other expressions
            valid[idx] = True
            # set the current marker as valid
            if marker_stk:
                valid[marker_stk[-1]] = True

    return [lines[idx] for idx in range(len(lines)) if valid[idx]]

def filter_out(pattern_files, input_file):
    """"Removes lines in input_file that match any line in pattern_files."""

    # Prepares patterns.
    patterns = []
    for f in pattern_files:
        patterns.extend([x for x in open(f).readlines() if not x.startswith(";;*")])

    # Copy lines that are not in the pattern.
    tmp_output = tempfile.NamedTemporaryFile(mode='w+')
    with open(input_file, 'r') as in_file:
        lines = [line for line in in_file.readlines()
                 if line not in patterns and line.strip()]
        lines = remove_redundant_line_markers(lines)
        tmp_output.writelines(lines)

        # Append empty line because a completely empty file
        # will trip up secilc later on:
        tmp_output.write("\n")
        tmp_output.flush()

    # Replaces the input_file.
    shutil.copyfile(tmp_output.name, input_file)
