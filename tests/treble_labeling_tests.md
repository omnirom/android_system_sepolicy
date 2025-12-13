# SELinux Treble Labeling Tests

This document provides guidance on resolving Treble Labeling violations.

## Understanding SELinux Treble Labeling Tests

The system and the vendor partitions are separated and only allowed to
communicate with stable interfaces. For the system-vendor split, SELinux policy
is also separated into platform SEPolicy (`/system`, `/system_ext` and
`/product`) and vendor SEPolicy (`/vendor` and `/odm`). Each partition has its
own set of SEPolicy files. The build system uses SEPolicy files located under
these directories.

Here, variables wrapped with `$(...)` are Makefile variables.

| Partition     | Directories                                    |
|---------------|------------------------------------------------|
| `/system`     | `system/sepolicy/public` <br> `system/sepolicy/private` |
| `/system_ext` | `$(SYSTEM_EXT_PRIVATE_SEPOLICY_DIRS)` <br> `$(SYSTEM_EXT_PUBLIC_SEPOLICY_DIRS)` |
| `/product`    | `$(PRODUCT_PRIVATE_SEPOLICY_DIRS)` <br> `$(PRODUCT_PUBLIC_SEPOLICY_DIRS)` |
| `/vendor`     | `$(BOARD_SEPOLICY_DIRS)` <br> `$(BOARD_VENDOR_SEPOLICY_DIRS)` |
| `/odm`        | `$(BOARD_ODM_SEPOLICY_DIRS)`                   |

The platform SEPolicy and the vendor SEPolicy can be updated independently, so
it's important to split SEPolicy appropriately. To ensure this SEPolicy split,
there is an attribute named `coredomain` which represents platform processes.
`coredomain` is meant to include all platform processes. Many allow rules,
neverallow assertions, and tests (such as `treble_sepolicy_tests.py`,
`sepolicy_tests.py` and CTS) are written on top of `coredomain`, to enforce the
system-vendor split. Treble Labeling tests are five more tests on top of them
for more robust enforcement. The five tests are as follows:

* No `coredomain` can be defined within the vendor SEPolicy.
* No platform files can be labeled within the vendor SEPolicy.
* No platform apps can be labeled within the vendor SEPolicy.
* All platform apps must be marked as `coredomain`.
* No vendor apps can be marked as `coredomain`.

Treble Labeling tests will be enforced for devices with
`BOARD_API_LEVEL >= 202604`.

## Fixing SELinux Treble Labeling Violations

### 1. No Coredomain in Vendor SEPolicy (`TestNoCoredomainInVendorSepolicy`)

The `coredomain` attribute is exclusively reserved for platform SELinux domains.
This violation occurs when vendor SEPolicy defines or attempts to label a type
with the `coredomain` attribute. Vendor SEPolicy must not introduce or extend
types with this attribute.

**How to Fix:**
Please fix these by doing one of these:

1. **Move Type Definitions:** If the type is for platform processes, move the
  type to a corresponding platform partition's SEPolicy.
2. **Remove `coredomain` Attribute:** If the type is genuinely a vendor-specific
  type, remove the `coredomain` attribute from the type.

### 2. No Platform Files in Vendor File Contexts (`TestNoPlatformFilesInVendorFileContexts`)

Vendor `file_contexts` are intended to define SELinux labels for files located
in `/vendor` and `/odm` partitions. This violation occurs when vendor
`file_contexts` attempt to label files in platform partitions (`/system/`,
`/system_ext/` or `/product/`), except for `/system/vendor/`.

**How to Fix:**
Please fix these by moving the corresponding `file_contexts` entries to the
correct partition's `file_contexts`.

### 3. No Platform Apps in Vendor Seapp Contexts (`TestNoPlatformAppsInVendorSeappContexts`)

This violation indicates one of two issues:
* **Entries without `name=` condition in vendor `seapp_contexts`:** Entries in
  vendor `seapp_contexts` must explicitly specify a `name=` condition to label
  only vendor apps. Generic entries without a `name=` condition are not allowed
  as they could unintentionally label platform apps.
* **Platform apps labeled by vendor policy:** Platform apps must have their
  SELinux labels assigned by platform `seapp_contexts`, not by vendor
  `seapp_contexts`.

**How to Fix:**
Please fix these by doing one of these:
1. **Add `name=` Condition (for generic entries):** For violations missing
  `name=` conditions, add `name=<package_name>` to the violating entries.
2. **Relocate Apps and Labeling (for platform apps in vendor policy):**
  * **Option A:** If the platform app is actually vendor-specific, move the
    platform apps to vendor partitions. Also make sure that the label for the
    app isn't marked as `coredomain` type.
  * **Option B:** Move the corresponding `seapp_contexts` entries to the
    `system`, `system_ext`, or `product` partition's `seapp_contexts`. Then,
    make sure that the label for the app is marked as `coredomain`.

### 4. Coredomain for All Platform Apps (`TestCoredomainForAllPlatformApps`)

All platform apps are expected to be labeled with a `coredomain` type. This
violation occurs when a platform app is incorrectly labeled with a type that is
not a `coredomain`.

**How to Fix:**
Please fix these by doing one of these:
1. **Add `coredomain` Attribute:** Add the `coredomain` attribute to the
  SELinux type assigned to the violating platform app.
2. **Relocate Apps and Contexts:** If the app is genuinely a vendor-specific,
  move the violating app and its corresponding `seapp_contexts` entries to
  the `vendor` or `product` partition.

### 5. No Coredomain for All Vendor Apps (`TestNoCoredomainForAllVendorApps`)

Vendor apps must not be labeled with `coredomain` types. This violation occurs
when a vendor app is incorrectly labeled with a `coredomain` type.

**How to Fix:**
Please fix these by doing one of these:
1. **Remove `coredomain` Attribute:** Remove the `coredomain` attribute from
  the label assigned to the violating vendor app. Or define a new type for the
  app which is not `coredomain`.
2. **Use Non-Coredomain Labels:** If the app needs to be in the platform, e.g.
  using `@hide` APIs or accessing platform internal resources, move the app to
  the `system`, `system_ext` or `product` partition, along with the
  corresponding `seapp_contexts` entry.

## The Tracking List File (`tracking_list.yaml`)

The `tracking_list.yaml` file functions as an **allowlist** to temporarily relax
the build time error for known violations. Violations listed in this file will
not cause the Treble labeling tests to fail. By adding a tracking list file,
users can ensure that no further violations happen.

The file is a YAML dictionary where top-level keys correspond to the specific
violation types checked by the script. Each value is a list of dictionaries,
with each dictionary representing a list of allowed violations.

**Overall Structure:**

```yaml
coredomain_in_vendor:
  - domain: allowed_coredomain_type # SELinux type name
    bug: 1111
  - domain: another_allowed_coredomain_type
    bug: 2222
platform_file_in_vendor_file_contexts:
  - path: /system_ext/bin/vendor_labeled_system_ext_file # file_contexts path
    bug: 3333
  - path: /system_ext/lib/yet\.another\.file\.so
    bug: 4444
platform_apps_in_vendor_seapp_contexts:
  - apk: SomePlatformApp.apk # name of APK
    bug: 112233445
  - name: com.android.platform.app # or name of the package
    bug: 554433221
non_coredomain_for_platform_apps:
  - apk: SomeNonCoredomainApp.apk # name of APK
    bug: 112233445
  - name: com.android.noncoredomain # or name of the package
    bug: 554433221
coredomain_for_vendor_apps:
  - apk: VendorServiceA.apk # name of APK
    bug: 314159265
  - name: vendor.companya.servicea # or name of the package
    bug: 358979323
```

If no such violations are currently allowed, lists can be empty like:
`coredomain_for_vendor_apps: []`

# Configuring the Tracking List in the Build System
The path to your `tracking_list.yaml` file is specified using the
`PRODUCT_SELINUX_TREBLE_LABELING_TRACKING_LIST_FILE` Makefile variable in
`device.mk`. Example in a `device/<vendor>/<device>/<device-name>.mk` file:

```makefile
# Path to the SELinux Treble Labeling tracking list file for this device
PRODUCT_SELINUX_TREBLE_LABELING_TRACKING_LIST_FILE := \
    device/google/your-device/sepolicy/tracking_list.yaml
```

## `treble_labeling_violators`: Exemption for debuggable-only apps

Some debuggable-only (`PRODUCT_PACKAGES_DEBUG`) apps require more permissions
than the Treble enforcement. For example, an app installed to `system_ext` may
need to dump vendor-specific resources. It doesn't make sense to enforce such
debuggable-only apps, because the apps are never meant to be released.

`treble_labeling_violators` is an attribute to exempt debuggable-only apps.
Adding `treble_labeling_violators` to domain types will make the tests skip apps
labeled with such types. The attribute is only for debuggable builds, and using
the attribute on user builds will cause a build error.

```
type ramdump_app, domain;

userdebug_or_eng(`
    # Apps labeled as ramdump_app will be exempted from the labeling tests.
    typeattributeset ramdump_app treble_labeling_violators;
')
```
