# Copyright 2023 The Android Open Source Project
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

from optparse import OptionParser
import mini_parser
import os
import sys

def do_main():
    usage = "sepolicy_freeze_test "
    usage += "-c current_cil -p prebuilt_cil [--help]"
    parser = OptionParser(usage=usage)
    parser.add_option("-c", "--current", dest="current", metavar="FILE")
    parser.add_option("-p", "--prebuilt", dest="prebuilt", metavar="FILE")

    (options, args) = parser.parse_args()

    if not options.current or not options.prebuilt:
        sys.exit("Must specify both current and prebuilt\n" + parser.usage)
    if not os.path.exists(options.current):
        sys.exit("Current policy " + options.current + " does not exist\n"
                + parser.usage)
    if not os.path.exists(options.prebuilt):
        sys.exit("Prebuilt policy " + options.prebuilt + " does not exist\n"
                + parser.usage)

    current_policy = mini_parser.MiniCilParser(options.current)
    prebuilt_policy = mini_parser.MiniCilParser(options.prebuilt)

    results = ""
    removed_types = prebuilt_policy.types - current_policy.types
    removed_attributes = prebuilt_policy.typeattributes - current_policy.typeattributes
    removed_attributes = set(filter(lambda x: "base_typeattr_" not in x, removed_attributes))

    if removed_types:
        results += "The following public types were removed:\n" + ", ".join(removed_types) + "\n"

    if removed_attributes:
        results += "The following public attributes were removed:\n" + ", ".join(removed_attributes) + "\n"

    if len(results) > 0:
        sys.exit(results)

if __name__ == '__main__':
    do_main()
