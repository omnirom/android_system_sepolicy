// Copyright 2021 The Android Open Source Project
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

package selinux

import (
	"sort"

	"android/soong/android"
)

func init() {
	ctx := android.InitRegistrationContext
	ctx.RegisterModuleType("se_freeze_test", freezeTestFactory)
}

// se_freeze_test compares the plat sepolicy with the prebuilt sepolicy.  Additional directories can
// be specified via Makefile variables: SEPOLICY_FREEZE_TEST_EXTRA_DIRS and
// SEPOLICY_FREEZE_TEST_EXTRA_PREBUILT_DIRS.
func freezeTestFactory() android.Module {
	f := &freezeTestModule{}
	f.AddProperties(&f.properties)
	android.InitAndroidArchModule(f, android.DeviceSupported, android.MultilibCommon)
	return f
}

type freezeTestProperties struct {
	// Frozen SEPolicy version to compare
	Board_api_level *string

	// Path to the base platform public policy cil
	Current_cil *string `android:"path"`

	// Path to the prebuilt cil of given board API level
	Prebuilt_cil *string `android:"path"`
}

type freezeTestModule struct {
	android.ModuleBase

	properties freezeTestProperties

	freezeTestTimestamp android.ModuleOutPath
}

func (f *freezeTestModule) shouldCompareExtraDirs(ctx android.EarlyModuleContext) bool {
	val, _ := ctx.Config().GetBuildFlag("RELEASE_BOARD_API_LEVEL_FROZEN")
	return val == "true"
}

func (f *freezeTestModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
	if ctx.ModuleName() != "se_freeze_test" || ctx.ModuleDir() != "system/sepolicy" {
		// two freeze test modules don't make sense.
		ctx.ModuleErrorf("There can only be 1 se_freeze_test module named se_freeze_test in system/sepolicy")
	}

	f.freezeTestTimestamp = android.PathForModuleOut(ctx, "freeze_test")

	// Freeze test 1: compare ToT sepolicy and prebuilt sepolicy
	currentCil := android.PathForModuleSrc(ctx, String(f.properties.Current_cil))
	prebuiltCil := android.PathForModuleSrc(ctx, String(f.properties.Prebuilt_cil))
	if ctx.Failed() {
		return
	}

	rule := android.NewRuleBuilder(pctx, ctx)
	rule.Command().BuiltTool("sepolicy_freeze_test").
		FlagWithInput("-c ", currentCil).
		FlagWithInput("-p ", prebuiltCil)

	// Freeze test 2: compare extra directories
	// We don't know the exact structure of extra directories, so just directly compare them
	extraDirs := ctx.DeviceConfig().SepolicyFreezeTestExtraDirs()
	extraPrebuiltDirs := ctx.DeviceConfig().SepolicyFreezeTestExtraPrebuiltDirs()

	var implicits []string
	if f.shouldCompareExtraDirs(ctx) {
		if len(extraDirs) != len(extraPrebuiltDirs) {
			ctx.ModuleErrorf("SEPOLICY_FREEZE_TEST_EXTRA_DIRS and SEPOLICY_FREEZE_TEST_EXTRA_PREBUILT_DIRS must have the same number of directories.")
			return
		}

		for _, dir := range append(extraDirs, extraPrebuiltDirs...) {
			glob, err := ctx.GlobWithDeps(dir+"/**/*", []string{"bug_map"} /* exclude */)
			if err != nil {
				ctx.ModuleErrorf("failed to glob sepolicy dir %q: %s", dir, err.Error())
				return
			}
			implicits = append(implicits, glob...)
		}
		sort.Strings(implicits)

		for idx, _ := range extraDirs {
			rule.Command().Text("diff").
				Flag("-r").
				Flag("-q").
				FlagWithArg("-x ", "bug_map"). // exclude
				Text(extraDirs[idx]).
				Text(extraPrebuiltDirs[idx])
		}
	} else {
		if len(extraDirs) > 0 || len(extraPrebuiltDirs) > 0 {
			ctx.ModuleErrorf("SEPOLICY_FREEZE_TEST_EXTRA_DIRS or SEPOLICY_FREEZE_TEST_EXTRA_PREBUILT_DIRS cannot be set before system/sepolicy freezes.")
			return
		}
	}

	rule.Command().Text("touch").
		Output(f.freezeTestTimestamp).
		Implicits(android.PathsForSource(ctx, implicits))

	rule.Build("sepolicy_freeze_test", "sepolicy_freeze_test")
}

func (f *freezeTestModule) AndroidMkEntries() []android.AndroidMkEntries {
	return []android.AndroidMkEntries{android.AndroidMkEntries{
		Class: "FAKE",
		// OutputFile is needed, even though BUILD_PHONY_PACKAGE doesn't use it.
		// Without OutputFile this module won't be exported to Makefile.
		OutputFile: android.OptionalPathForPath(f.freezeTestTimestamp),
		Include:    "$(BUILD_PHONY_PACKAGE)",
		ExtraEntries: []android.AndroidMkExtraEntriesFunc{
			func(ctx android.AndroidMkExtraEntriesContext, entries *android.AndroidMkEntries) {
				entries.SetString("LOCAL_ADDITIONAL_DEPENDENCIES", f.freezeTestTimestamp.String())
			},
		},
	}}
}
