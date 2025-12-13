#!/usr/bin/env python3

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

"""
Minimize a policy conf file for CTS neverallow tests, by leaving only CTS
markers and neverallow rules.
"""

from contextlib import redirect_stdout
import re
import sys

def markers_match(marker1: str, marker2: str) -> bool:
    """
    Checks if two marker lines represent the beginning and end of the same block
    """
    combined = f"{marker1}\n{marker2}"
    pattern1 = r"^\s*# BEGIN_([A-Za-z0-9_]+) .*\n\s*# END_\1\b .*$"
    pattern2 = r"^\s*# END_([A-Za-z0-9_]+) .*\n\s*# BEGIN_\1\b .*$"
    return bool(re.match(pattern1, combined) or re.match(pattern2, combined))

def do_main():
    if len(sys.argv) != 3:
        sys.exit(f"Usage: {sys.argv[0]} input.conf output.conf")

    with open(sys.argv[1], "r") as f:
        blob = f.read()

    # Add newlines after semicolons to separate statements with newlines.
    blob = re.sub(r"^([^#]+;)", "\\1\n", blob, flags=re.MULTILINE)

    # Trim whitespaces.
    blob = re.sub(r"^\s+\n", "", blob, flags=re.MULTILINE)
    blob = re.sub(r"\n+", "\n", blob)

    in_neverallow_rule = False
    outputs = []
    for line in blob.strip().split('\n'):
        if re.search(r"#.*-- this marker is used by CTS --", line):
            if len(outputs) > 0 and markers_match(outputs[-1], line):
                # Two adjacent markers "BEGIN_xxx" and "END_xxx", without any
                # statement between them, regardless of order, are redundant.
                # Remove both.
                outputs.pop()
            else:
                outputs.append(line.rstrip())
            continue

        # Remove comments and then skip empty lines.
        # We can't do this above because we must handle line markers.
        line = re.sub(r"#.*", "", line)
        if line.strip() == "":
            continue

        if line.lstrip().startswith("neverallow"):
            in_neverallow_rule = True

        if in_neverallow_rule:
            outputs.append(line.rstrip())
            if line.endswith(';'):
                in_neverallow_rule = False

    with open(sys.argv[2], "w") as f:
        f.write("\n".join(outputs) + "\n")

if __name__ == "__main__":
    do_main()
