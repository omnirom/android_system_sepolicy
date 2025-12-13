#!/bin/bash

# Copyright (C) 2023 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
set -e

if [ $# -ne 2 ]; then
    echo "Usage: $0 <top> <ver>"
    exit 1
fi

top=$1
ver=$2 # the version that we're now finalizing

################################################################################
#
# SEPolicy VINTF finalization does:
#
# 1. Snapshots $ver files to system/sepolicy/prebuilts/api/$ver. Policy files
#    (such as *.te) under system/sepolicy/public and system/sepolicy/private,
#    plat_sepolicy.cil, system/etc/selinux/mapping/$ver.cil, and
#    gerenal_sepolicy.conf (neverallow assertions) are copied into the prebuilts
#    directory. Prebuilts will be used for Treble compatibility tests and
#    SEPolicy freeze tests.
#
# 2. Generate compatibility files to system/sepolicy/private/compat/$ver. It
#    contains a mapping information from ToT public types to $ver public types,
#    allowing $ver vendors to access newer types introduced on ToT without
#    regressions.
#
# 3. Update Android.bp to prepare the version bump. Compatibility mapping files
#    and Treble SEPolicy tests depend on BOARD_API_LEVEL.
#
#    * Compatibility mapping files support old vendors. For each old version,
#      there exists one set of compat mapping files. So if we bump the version
#      from ${ver-1} to ${ver}, for example, then ${ver-1} compat mapping files
#      are added to the platform images.
#
#    * Treble SEPolicy tests check if current ToT SEPolicy is compatible with
#      old vendors. IF we bump the version from ${ver-1} to ${ver}, ${ver-1}
#      tests need to be tested.
#
#    Before finalization, Android.bp supports ${ver-1} (-next*) and ${ver}
#    (-trunk*), by installing ${ver-1} compat mapping files and running
#    ${ver-1} Treble SEPolicy tests only when BOARD_API_LEVEL is ${ver}. After
#    version bump, -next* becomes ${ver} and -trunk* becomes ${ver+1}, so
#    Android.bp needs to be updated appropriately.
#
################################################################################


################################################################################
# Step 1. Snapshots $ver files to system/sepolicy/prebuilts/api/$ver
################################################################################
prebuilt_dir=$top/system/sepolicy/prebuilts/api/$ver
mkdir -p "$prebuilt_dir"
cp -r "$top/system/sepolicy/public/" "$prebuilt_dir"
cp -r "$top/system/sepolicy/private/" "$prebuilt_dir"

cat > "$prebuilt_dir/Android.bp" <<EOF
// Automatically generated file, do not edit!
se_policy_conf {
    name: "${ver}_reqd_policy_mask.conf",
    defaults: ["se_policy_conf_flags_defaults"],
    srcs: reqd_mask_policy,
    installable: false,
    build_variant: "user",
    board_api_level: "${ver}",
}

se_policy_cil {
    name: "${ver}_reqd_policy_mask.cil",
    src: ":${ver}_reqd_policy_mask.conf",
    secilc_check: false,
    installable: false,
}

se_policy_conf {
    name: "${ver}_plat_pub_policy.conf",
    defaults: ["se_policy_conf_flags_defaults"],
    srcs: [
        ":se_build_files{.plat_public_${ver}}",
        ":se_build_files{.reqd_mask}",
    ],
    installable: false,
    build_variant: "user",
    board_api_level: "${ver}",
}

se_policy_cil {
    name: "${ver}_plat_pub_policy.cil",
    src: ":${ver}_plat_pub_policy.conf",
    filter_out: [":${ver}_reqd_policy_mask.cil"],
    secilc_check: false,
    installable: false,
}

se_policy_conf {
    name: "${ver}_product_pub_policy.conf",
    defaults: ["se_policy_conf_flags_defaults"],
    srcs: [
        ":se_build_files{.plat_public_${ver}}",
        ":se_build_files{.system_ext_public_${ver}}",
        ":se_build_files{.product_public_${ver}}",
        ":se_build_files{.reqd_mask}",
    ],
    installable: false,
    build_variant: "user",
    board_api_level: "${ver}",
}

se_policy_cil {
    name: "${ver}_product_pub_policy.cil",
    src: ":${ver}_product_pub_policy.conf",
    filter_out: [":${ver}_reqd_policy_mask.cil"],
    secilc_check: false,
    installable: false,
}

se_versioned_policy {
    name: "${ver}_plat_pub_versioned.cil",
    base: ":${ver}_product_pub_policy.cil",
    target_policy: ":${ver}_product_pub_policy.cil",
    version: "${ver}",
    installable: false,
}

se_policy_conf {
    name: "${ver}_plat_policy.conf",
    defaults: ["se_policy_conf_flags_defaults"],
    srcs: [
        ":se_build_files{.plat_public_${ver}}",
        ":se_build_files{.plat_private_${ver}}",
        ":se_build_files{.system_ext_public_${ver}}",
        ":se_build_files{.system_ext_private_${ver}}",
        ":se_build_files{.product_public_${ver}}",
        ":se_build_files{.product_private_${ver}}",
    ],
    installable: false,
    build_variant: "user",
}

se_policy_cil {
    name: "${ver}_plat_policy.cil",
    src: ":${ver}_plat_policy.conf",
    additional_cil_files: [":sepolicy_technical_debt{.plat_private_${ver}}"],
    installable: false,
}

se_policy_binary {
    name: "${ver}_plat_policy",
    srcs: [":${ver}_plat_policy.cil"],
    installable: false,
    dist: {
        targets: ["sepolicy_finalize"],
    },
}
EOF

# Build general_sepolicy.conf, plat_sepolicy.cil, and mapping file for CTS
DIST_DIR=out/dist $top/build/soong/soong_ui.bash --make-mode dist \
    sepolicy_finalize bpmodify bpfmt sepolicy_generate_compat

cp "$top/out/dist/base_plat_sepolicy.cil" "$prebuilt_dir/${ver}_plat_sepolicy.cil"
cp "$top/out/dist/general_sepolicy.conf" "$prebuilt_dir/${ver}_general_sepolicy.conf"
cp "$top/out/dist/base_plat_mapping_file.cil" "$prebuilt_dir/${ver}_mapping.cil"

cat >> "$prebuilt_dir/Android.bp" <<EOF

filegroup {
    name: "${ver}_sepolicy_cts_data",
    srcs: [
        "${ver}_general_sepolicy.conf",
        "${ver}_plat_sepolicy.cil",
        "${ver}_mapping.cil",
    ],
}
EOF

bpmodify="$top/out/host/linux-x86/bin/bpmodify"
$bpmodify -a ":${ver}_sepolicy_cts_data" -m prebuilt_sepolicy_cts_data -property srcs -w \
    $top/system/sepolicy/tests/Android.bp
sed -i "s/FREEZE_TEST_BOARD_API_LEVEL = \".\{6\}\"/FREEZE_TEST_BOARD_API_LEVEL = \"${ver}\"/" \
    $top/system/sepolicy/Android.bp

################################################################################
# Step 2. Generate compatibility files to system/sepolicy/private/compat/$ver
################################################################################

# format of ver is YYYY04
# prev version will be ver - 100, next version will be ver + 100.
# this is not perfect but simplest
prev_ver=$(($ver-100))
next_ver=$(($ver+100))

sed -i '/PLATFORM_SEPOLICY_COMPAT_VERSIONS/,/),/s/'$prev_ver' \\/'$prev_ver' \\\n    '$ver' \\/' \
    $top/build/make/core/config.mk

sepolicy_generate_compat="$top/out/host/linux-x86/bin/sepolicy_generate_compat"
$sepolicy_generate_compat --target-version "$ver" \
    --plat-mapping-file "$top/out/dist/$ver.cil" \
    --base-plat-sepolicy "$top/out/dist/base_plat_sepolicy" \
    --old-plat-sepolicy "$top/out/dist/${ver}_plat_policy" \
    --base-plat-pub-policy "$top/out/dist/base_plat_pub_policy.cil" \

$bpmodify -remove-property -m "${ver}_plat_policy" -property dist -w "$prebuilt_dir/Android.bp"

bpfmt="$top/out/host/linux-x86/bin/bpfmt"
$bpfmt -w "$prebuilt_dir/Android.bp"

# trunk* is now $next_ver, so add plat_sepolicy_genfs_${next_ver} for trunk* builds.
cp "$top/system/sepolicy/compat/plat_sepolicy_genfs_$ver.cil" \
    "$top/system/sepolicy/compat/plat_sepolicy_genfs_${next_ver}.cil"

cat >> "$top/system/sepolicy/compat/Android.bp" <<EOF

prebuilt_etc {
    name: "plat_sepolicy_genfs_$next_ver.cil",
    src: "plat_sepolicy_genfs_$next_ver.cil",
    relative_install_path: "selinux",
}
EOF

sed -i 's/^\("plat_sepolicy_genfs_'$ver'.cil",\)/\1"plat_sepolicy_genfs_'$next_ver'.cil",/g' \
    $top/system/sepolicy/Android.bp


################################################################################
# Step 3. Update Android.bp to prepare the version bump
#
# compatibility mapping files and Treble SEPolicy tests.
################################################################################

# For example, suppose that we're now finalizing 202604. Then Android.bp now
# contains select statements to support 202504 and 202604, like:
#
#     required: [
#         "202404.compat.cil",
#         "plat_202404.cil",
#         ...
#     ] + select(soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"), {
#         "202504": [],
#         default: [
#             "202504.compat.cil",
#             "plat_202504.cil",
#         ],
#     })
#
# After finalization, it should be:
#
#     required: [
#         "202404.compat.cil",
#         "202504.compat.cil",
#         "plat_202404.cil",
#         "plat_202504.cil",
#         ...
#     ] + select(soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"), {
#         "202604": [],
#         default: [
#             "202604.compat.cil",
#             "plat_202604.cil",
#         ],
#     })
#
# A fragile but simplest way to do is:
#
# * Replace "plat_202404.cil," in the list to "plat_202404.cil,plat_202504.cil,".
# * Do the same for other compat files too ("202404.compat.cil", "system_ext_202404.cil", etc.)
# * Replace all occurrences of "202504" in the select statements to "202604".

prev_prev_ver=$(($prev_ver-100))

# plat_${ver}.cil
sed -i 's/\("plat_'$prev_prev_ver'.cil",\)/\1"plat_'$prev_ver'.cil",/g' \
    $top/system/sepolicy/Android.bp

# ${ver}.compat.cil
sed -i 's/\("'$prev_prev_ver'.compat.cil",\)/\1"'$prev_ver'.compat.cil",/g' \
    $top/system/sepolicy/Android.bp

# system_ext_${ver}.cil
sed -i 's/\("system_ext_'$prev_prev_ver'.cil",\)/\1"system_ext_'$prev_ver'.cil",/g' \
    $top/system/sepolicy/Android.bp

# system_ext_${ver}.compat.cil
sed -i 's/\("system_ext_'$prev_prev_ver'.compat.cil",\)/\1"system_ext_'$prev_ver'.compat.cil",/g' \
    $top/system/sepolicy/Android.bp

# product_${ver}.cil
sed -i 's/\("product_'$prev_prev_ver'.cil",\)/\1"product_'$prev_ver'.cil",/g' \
    $top/system/sepolicy/Android.bp

# treble_sepolicy_tests_${ver}
sed -i 's/\("treble_sepolicy_tests_'$prev_prev_ver'",\)/\1"treble_sepolicy_tests_'$prev_ver'",/g' \
    $top/system/sepolicy/Android.bp

# ${prev_ver} to ${ver} in select(PLATFORM_SEPOLICY_VERSION, ...) statements
sed -i "/PLATFORM_SEPOLICY_VERSION/,/})/s/$prev_ver/$ver/g" $top/system/sepolicy/Android.bp

$bpfmt -w "$top/system/sepolicy/Android.bp"

cat >> "$top/system/sepolicy/treble_sepolicy_tests_for_release/Android.bp" <<EOF

java_genrule {
    name: "${ver}_mapping.combined.cil",
    srcs: select(soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"), {
        "${ver}": [],
        default: [
            ":plat_${ver}.cil",
            ":${ver}.ignore.cil",
        ],
    }) + select((
        soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"),
        soong_config_variable("ANDROID", "HAS_BOARD_SYSTEM_EXT_SEPOLICY_PREBUILT_DIRS"),
    ), {
        ("${ver}", default): [],
        (default, true): [
            ":system_ext_${ver}.cil",
            ":system_ext_${ver}.ignore.cil",
        ],
        (default, default): [],
    }) + select((
        soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"),
        soong_config_variable("ANDROID", "HAS_BOARD_PRODUCT_SEPOLICY_PREBUILT_DIRS"),
    ), {
        ("${ver}", default): [],
        (default, true): [
            ":product_${ver}.cil",
            ":product_${ver}.ignore.cil",
        ],
        (default, default): [],
    }),
    out: ["${ver}_mapping.combined.cil"],
    cmd: select(soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"), {
        "${ver}": "touch \$(out)",
        default: "cat \$(in) > \$(out)",
    }),
}

java_genrule {
    name: "treble_sepolicy_tests_${ver}",
    srcs: [
        ":${ver}_plat_pub_policy.cil",
        ":${ver}_mapping.combined.cil",
    ] + select((
        soong_config_variable("ANDROID", "HAS_BOARD_SYSTEM_EXT_SEPOLICY_PREBUILT_DIRS"),
        soong_config_variable("ANDROID", "HAS_BOARD_PRODUCT_SEPOLICY_PREBUILT_DIRS"),
    ), {
        (false, false): [":base_plat_pub_policy.cil"],
        (default, default): [":base_product_pub_policy.cil"],
    }),
    tools: ["treble_sepolicy_tests"],
    out: ["treble_sepolicy_tests_${ver}"],
    cmd: select((
        soong_config_variable("ANDROID", "PLATFORM_SEPOLICY_VERSION"),
        soong_config_variable("ANDROID", "HAS_BOARD_SYSTEM_EXT_SEPOLICY_PREBUILT_DIRS"),
        soong_config_variable("ANDROID", "HAS_BOARD_PRODUCT_SEPOLICY_PREBUILT_DIRS"),
    ), {
        ("${ver}", default, default): "touch \$(out)",
        (default, false, false): "\$(location treble_sepolicy_tests) " +
            "-b \$(location :base_plat_pub_policy.cil) " +
            "-m \$(location :${ver}_mapping.combined.cil) " +
            "-o \$(location :${ver}_plat_pub_policy.cil) && " +
            "touch \$(out)",
        (default, default, default): "\$(location treble_sepolicy_tests) " +
            "-b \$(location :base_product_pub_policy.cil) " +
            "-m \$(location :${ver}_mapping.combined.cil) " +
            "-o \$(location :${ver}_plat_pub_policy.cil) && " +
            "touch \$(out)",
    }),
}
EOF
