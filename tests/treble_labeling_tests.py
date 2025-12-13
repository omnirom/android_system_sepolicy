#!/usr/bin/env python

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
"""Verify that Treble labeling are enforced.

Treble labeling means the following:

1) All platform processes are marked as "coredomain".
2) All platform processes are labeled by platform SEPolicy.
3) All platform files are labeled by platform SEPolicy.
4) All vendor processes are NOT marked as "coredomain".

Note that vendor processes can be "labeled" by platform SEPolicy, if the
processes are generic to all vendors, such as sh / toybox / etc.
"""

import argparse
import collections
import os
import pkgutil
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

import fc_sort
import policy
import yaml

SHARED_LIB_EXTENSION = '.dylib' if sys.platform == 'darwin' else '.so'

App = collections.namedtuple("App", ["package_name", "apk_name"])
ContextEntry = collections.namedtuple("ContextEntry", ["partition", "values"])

def build_argument_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--platform_apks",
        dest="platform_apks",
        metavar="FILE",
        help="Path to a file containing a list of platform apks (one per line)",
        required=True,
    )
    parser.add_argument(
        "--vendor_apks",
        dest="vendor_apks",
        metavar="FILE",
        help="Path to a file containing a list of vendor apks (one per line)",
        required=True,
    )
    parser.add_argument(
        "--precompiled_sepolicy_without_vendor",
        dest="precompiled_sepolicy_without_vendor",
        metavar="FILE",
        help="Path to the precompiled SEPolicy file (excluding vendor)",
        required=True,
    )
    parser.add_argument(
        "--precompiled_sepolicy",
        dest="precompiled_sepolicy",
        metavar="FILE",
        help="Path to the precompiled SEPolicy file (including vendor)",
        required=True,
    )
    parser.add_argument(
        "--platform_seapp_contexts",
        dest="platform_seapp_contexts",
        metavar="FILE",
        nargs="+",
        help="Path to the Platform seapp_contexts file",
        required=True,
    )
    parser.add_argument(
        "--vendor_file_contexts",
        dest="vendor_file_contexts",
        metavar="FILE",
        nargs="+",
        help="Path to the Vendor file_contexts file",
        required=True,
    )
    parser.add_argument(
        "--vendor_seapp_contexts",
        dest="vendor_seapp_contexts",
        metavar="FILE",
        nargs="+",
        help="Path to the Vendor seapp_contexts file",
        required=True,
    )
    parser.add_argument(
        "--aapt2_path",
        dest="aapt2_path",
        metavar="FILE",
        help="Path to the aapt2 executable.",
        required=True,
    )
    parser.add_argument(
        "--tracking_list_file",
        dest="tracking_list_file",
        metavar="FILE",
        help="Path to the yaml file containing a tracking_list_file.",
        required=False,
    )
    parser.add_argument(
        "--treat_as_warnings",
        dest="treat_as_warnings",
        action="store_true",
        help="Treat test failures as warnings instead of errors.",
        required=False,
    )
    parser.add_argument(
        "--debuggable",
        action="store_true",
        help="Exempt treble_labeling_violators from tests.",
        required=False,
    )
    return parser

def TestNoCoredomainInVendorSepolicy(pol_without_vendor, pol, allowlist,
                                     exempted_types):
    """Tests if vendor SEPolicy adds more coredomain types.
    coredomain is only for platform types, so vendor SEPolicy must not add one.
    """
    platform_coredomain_types = pol_without_vendor.QueryTypeAttribute(
        "coredomain", True)
    coredomain_types = pol.QueryTypeAttribute("coredomain", True)

    allowed_types = {entry["domain"] for entry in allowlist}
    violations = coredomain_types - platform_coredomain_types - allowed_types
    violations -= exempted_types

    if violations:
        return ("ERROR: The attribute 'coredomain' is only for platform "
                "SEPolicy, and must not be added by vendor SEPolicy.\n"
                "Please fix these by doing one of these.\n"
                "1) Move these type definitions to system, system_ext, or "
                "product's SEPolicy.\n"
                "2) Remove 'coredomain' from these types.\n"
                "Violations:\n"
                f"{'\n'.join(violations)}\n\n")

    return ""

def TestNoPlatformFilesInVendorFileContexts(vendor_file_contexts, allowlist):
    """Tests if vendor SEPolicy labels any of platform files.
    """
    platform_prefixes = ["/system/", "/system_ext/", "/product/"]
    allowed_platform_prefixes = ["/system/vendor/"]

    fc_sorted = fc_sort.sort(vendor_file_contexts)

    allowed_paths = {entry["path"] for entry in allowlist}
    violations = ""

    for entry in fc_sorted:
        if entry.path in allowed_paths:
            continue
        if policy.MatchPathPrefixes(entry.path, allowed_platform_prefixes):
            continue
        if policy.MatchPathPrefixes(entry.path, platform_prefixes):
            violations += f"{entry.path}\n"

    if violations:
        return ("ERROR: Vendor's file_contexts must not label files in "
                "platform partitions.\nPlease fix these by doing one of "
                "these.\n"
                "1) Move corresponding file_contexts entries to correct "
                "partition's file_contexts.\n"
                "2) Move corresponding files to vendor or odm partition, and "
                "then update file_contexts entries.\n"
                "Violations:\n"
                f"{violations}\n\n")

    return ""

def parse_package_names(apk_list_file, aapt2_path):
    package_names = []

    with open(apk_list_file, "r", encoding="utf-8") as f:
        apk_paths = f.read().split()

    def extract_package_name(apk_path):
        apk_name = os.path.basename(apk_path)
        try:
            package_name = subprocess.check_output(
                [aapt2_path, "dump", "packagename", apk_path],
                text=True,
                encoding="utf-8"
            ).strip()
            return App(package_name, apk_name)
        except subprocess.CalledProcessError as e:
            sys.exit(f"Failed to extract package name from {apk_path}: {e}")

    with ThreadPoolExecutor() as executor:
        futures = [executor.submit(extract_package_name, apk_path)
                   for apk_path in apk_paths]
        for future in as_completed(futures):
            package_names.append(future.result())

    return package_names

def find_partition_of_contexts(contexts_path):
    basename = os.path.basename(contexts_path)

    partition_prefixes = {
        "plat_": "system",
        "system_ext_": "system_ext",
        "product_": "product",
        "vendor_": "vendor",
        "odm_": "odm",
    }

    for prefix, partition in partition_prefixes.items():
        if basename.startswith(prefix):
            return partition

    sys.exit(f"Can't guess the partition from '{contexts_path}', expected one "
             f"of {list(partition_prefixes.keys())}\n")

def parse_seapp_contexts_values(line: str):
    values = collections.defaultdict(str)

    for token in line.split():
        try:
            key, value = token.split("=")
        except ValueError:
            sys.exit(f"malformed seapp_contexts line: '{line}' contains a "
                     "token without '='\n")
        if key in values:
            sys.exit(f"malformed seapp_contexts line: '{line}' contains two or "
                     "more '{key}='\n")
        values[key] = value

    # store the raw line for error messages.
    values["_raw"] = line

    return values

def parse_seapp_contexts(seapp_contexts_path):
    entries = []
    partition = find_partition_of_contexts(seapp_contexts_path)

    with open(seapp_contexts_path, "r", encoding="utf-8") as f:
        for line in f:
            if "#" in line:
                line = line[:line.find("#")]
            line = line.strip()
            if not line or line.startswith("neverallow"):
                continue

            entries.append(ContextEntry(partition,
                                        parse_seapp_contexts_values(line)))

    return entries

def package_name_match(package_name, pattern):
    """Checks if a package name matches a given pattern.

    The pattern can end with an asterisk (*) for prefix matching
    (case-insensitive). Otherwise, it performs an exact case-insensitive match.

    This name matching code is from seapp_context_lookup_internal function in
    external/selinux/libselinux/src/android/android_seapp.c.
    """
    package_name = package_name.lower()
    pattern = pattern.lower()

    if pattern.endswith("*"):
        return package_name.startswith(pattern[:-1])
    else:
        return package_name == pattern

def TestNoPlatformAppsInVendorSeappContexts(platform_apps,
                                            vendor_seapp_entries,
                                            allowlist,
                                            exempted_types):
    """Tests if vendor SEPolicy labels any of preinstalled platform apps.
    Platform apps can't be labeled with vendor SEPolicy. Also vendor's
    seapp_contexts must use 'name=' condition, because vendor's seapp_contexts
    shouldn't need generic entries.
    """
    no_name_violations = []
    partition_violations = []

    allowed_apks = {entry["apk"] for entry in allowlist if "apk" in entry}
    allowed_names = {entry["name"] for entry in allowlist if "name" in entry}

    for entry in vendor_seapp_entries:
        values = entry.values
        # Entries in vendor seapp contexts must have "name={name}" condition
        if "name" not in values or not values["name"]:
            no_name_violations.append((entry.partition, values["_raw"]))
            continue
        if values["domain"] in exempted_types:
            continue

        # Such name patterns must not match with platform_apps
        for app in platform_apps:
            if app.apk_name in allowed_apks:
                continue
            if app.package_name in allowed_names:
                continue
            if package_name_match(app.package_name, values["name"]):
                partition_violations.append((app.apk_name, app.package_name,
                                             entry.partition, values["_raw"]))
                break

    result = ""
    if no_name_violations:
        result += ("ERROR: Entries without 'name=' condition are not allowed "
                   "in vendor seapp_contexts.\nPlease fix the following "
                   "violations by adding 'name=<package_name>' condition.\n"
                   "Violations:\n")
        for partition, raw_line in no_name_violations:
            result += f"  seapp_contexts partition: {partition}\n"
            result += f"  line: '{raw_line}'\n"
            result += "---\n"
        result += "\n"

    if partition_violations:
        result += ("ERROR: Platform apps cannot be labeled within vendor's "
                   "seapp_contexts.\nPlease fix the following violations by "
                   "doing one of these.\n"
                   "1) Move these apps to vendor or odm partition, and then "
                   "label the app with types without 'coredomain'.\n"
                   "2) Move these seapp_contexts entries to system, system_ext,"
                   " or product partition's seapp_contexts, and then label the "
                   "apps with 'coredomain' types.\n"
                   "Violations:\n")
        for apk_name, package_name, partition, raw_line in partition_violations:
            result += f"  APK name: {apk_name}\n"
            result += f"  package name: {package_name}\n"
            result += f"  seapp_contexts partition: {partition}\n"
            result += f"  line: '{raw_line}'\n"
            result += "---\n"
        result += "\n"

    return result

def TestCoredomainForAllPlatformApps(platform_apps, platform_seapp_entries,
                                     pol, allowlist, exempted_types):
    """Tests if platform SEPolicy labels any of preinstalled platform apps with
    a non-coredomain label. All preinstalled platform apps are expected to be
    labeled with a coredomain type.
    """
    coredomains = pol.QueryTypeAttribute("coredomain", True)
    violations = []

    allowed_apks = {entry["apk"] for entry in allowlist if "apk" in entry}
    allowed_names = {entry["name"] for entry in allowlist if "name" in entry}

    for entry in platform_seapp_entries:
        values = entry.values
        if not values["name"] or values["domain"] in coredomains:
            continue
        if values["domain"] in exempted_types:
            continue

        for app in platform_apps:
            if app.apk_name in allowed_apks:
                continue
            if app.package_name in allowed_names:
                continue
            if package_name_match(app.package_name, values["name"]):
                violations.append((app.apk_name, app.package_name,
                                   values["domain"]))
                break

    if violations:
        error_message = ("ERROR: All platform apps must be labeled with a "
                         "coredomain type.\nPlease fix the following "
                         "violations by doing one of these.\n"
                         "1) Add 'coredomain' attribute to labels.\n"
                         "2) Move apps and corresponding seapp_contexts entries"
                         " to vendor or odm partition.\n"
                         "Violations:\n")
        for apk_name, package_name, domain in violations:
            error_message += f"  APK name: {apk_name}\n"
            error_message += f"  package name: {package_name}\n"
            error_message += f"  assigned label: {domain}\n"
            error_message += "---\n"
        return error_message + "\n"

    return ""

def TestNoCoredomainForAllVendorApps(vendor_apps, seapp_entries, pol,
                                     allowlist, exempted_types):
    """Tests if any of preinstalled vendor apps are labeled with coredomain
    labels. All preinstalled vendor apps are expected to be non-coredomain.
    """
    coredomains = pol.QueryTypeAttribute("coredomain", True)
    violations = []

    allowed_apks = {entry["apk"] for entry in allowlist if "apk" in entry}
    allowed_names = {entry["name"] for entry in allowlist if "name" in entry}

    for entry in seapp_entries:
        values = entry.values
        if not values["name"] or values["domain"] not in coredomains:
            continue
        if values["domain"] in exempted_types:
            continue

        for app in vendor_apps:
            if app.apk_name in allowed_apks:
                continue
            if app.package_name in allowed_names:
                continue
            if package_name_match(app.package_name, values["name"]):
                violations.append((app.apk_name, app.package_name,
                                   values["domain"]))
                break

    if violations:
        error_message = ("ERROR: All vendor apps must not be labeled with a "
                         "coredomain type.\nPlease fix the following "
                         "violations by doing one of these.\n"
                         "1) Remove the 'coredomain' attribute from labels.\n"
                         "2) Use other labels which are not 'coredomain'.\n"
                         "Violations:\n")
        for apk_name, package_name, domain in violations:
            error_message += f"  APK name: {apk_name}\n"
            error_message += f"  package name: {package_name}\n"
            error_message += f"  assigned label: {domain}\n"
            error_message += "---\n"
        return error_message + "\n"

    return ""

# pylint: disable=redefined-outer-name
def do_main(libpath):
    parser = build_argument_parser()
    args = parser.parse_args()

    tracking_list = {}
    if args.tracking_list_file:
        with open(args.tracking_list_file, "r", encoding="utf-8") as f:
            tracking_list = yaml.safe_load(f) or {}

    pol_without_vendor = policy.Policy(args.precompiled_sepolicy_without_vendor,
                                       None, libpath)
    pol = policy.Policy(args.precompiled_sepolicy, None, libpath)

    platform_apps = parse_package_names(args.platform_apks, args.aapt2_path)
    vendor_apps = parse_package_names(args.vendor_apks, args.aapt2_path)

    platform_seapp_entries = sum([parse_seapp_contexts(path) for path
                                  in args.platform_seapp_contexts], [])
    vendor_seapp_entries = sum([parse_seapp_contexts(path) for path
                                in args.vendor_seapp_contexts], [])

    seapp_entries = platform_seapp_entries + vendor_seapp_entries

    exempted_types = pol.QueryTypeAttribute("treble_labeling_violators", True)

    result = ""

    if not args.debuggable:
        if exempted_types:
            sys.exit("treble_labeling_violators can't be used on user builds.\n"
                     "Please guard it with userdebug_or_eng macro.\n"
                    f"violators:\n{exempted_types}\n")

    result += TestNoCoredomainInVendorSepolicy(
        pol_without_vendor,
        pol,
        tracking_list.get('coredomain_in_vendor', []),
        exempted_types
    )
    result += TestNoPlatformFilesInVendorFileContexts(
        args.vendor_file_contexts,
        tracking_list.get('platform_file_in_vendor_file_contexts', []),
    )
    result += TestNoPlatformAppsInVendorSeappContexts(
        platform_apps,
        vendor_seapp_entries,
        tracking_list.get('platform_apps_in_vendor_seapp_contexts', []),
        exempted_types
    )
    result += TestCoredomainForAllPlatformApps(
        platform_apps,
        platform_seapp_entries,
        pol,
        tracking_list.get('non_coredomain_for_platform_apps', []),
        exempted_types
    )
    result += TestNoCoredomainForAllVendorApps(
        vendor_apps,
        seapp_entries,
        pol,
        tracking_list.get('coredomain_for_vendor_apps', []),
        exempted_types
    )

    if not result:
        return

    result += ("******************************\n"
               "ERROR: SELinux Treble Labeling violations found.\n"
               "Treble Labeling will be enforced for devices with "
               "BOARD_API_LEVEL >= 202604.\n"
               "Please fix all violations. For more details, please refer to:\n"
               "system/sepolicy/tests/treble_labeling_tests.md\n"
               "******************************\n")

    if args.treat_as_warnings:
        result = re.sub(r'(^|\n)ERROR:', r'\1WARNING:', result)

    print(result, file=sys.stderr)

    if not args.treat_as_warnings:
        sys.exit(1)

if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as temp_dir:
        libname = "libsepolwrap" + SHARED_LIB_EXTENSION
        libpath = os.path.join(temp_dir, libname)
        with open(libpath, "wb") as lib:
            blob = pkgutil.get_data("treble_labeling_tests", libname)
            if not blob:
                sys.exit("Error: libsepolwrap does not exist. Is this binary "
                         "corrupted?\n")
            lib.write(blob)
        do_main(libpath)
