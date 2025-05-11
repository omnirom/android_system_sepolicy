// Copyright 2024 The Android Open Source Project
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Client library to read genfs labels version of the vendor.

use std::fs;

const GENFS_LABELS_VERSION_TXT_PATH: &str = "/vendor/etc/selinux/genfs_labels_version.txt";
const DEFAULT_GENFS_LABELS_VERSION: i32 = 202404;

/// Get genfs labels version from the vendor partition.
///
/// This function reads the genfs labels version from the file
/// `/vendor/etc/selinux/genfs_labels_version.txt`. If the file does not exist or
/// cannot be parsed, it returns a default version of 202404.
///
/// # Returns
///
/// The genfs labels version as an integer.
#[no_mangle]
pub extern "C" fn get_genfs_labels_version() -> i32 {
    match fs::read_to_string(GENFS_LABELS_VERSION_TXT_PATH) {
        Ok(contents) => match contents.trim().parse::<i32>() {
            Ok(version) => version,
            Err(_) => DEFAULT_GENFS_LABELS_VERSION,
        },
        Err(_) => DEFAULT_GENFS_LABELS_VERSION,
    }
}
