// Copyright (C) 2019 The Android Open Source Project
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
	"github.com/google/blueprint"

	"android/soong/android"
)

type dependencyTag struct {
	blueprint.BaseDependencyTag
	name string
}

var (
	pctx = android.NewPackageContext("android/soong/selinux")
)

// pathForModuleOut is same as android.PathForModuleOut, except that it uses DeviceName() as its
// intermediate directory name for system_ext/product/vendor/odm modules, to avoid rebuilding upon
// target change. Contents of system modules (core sepolicy) should be identical across devices, so
// they falls back to android.PathForModuleOut.
func pathForModuleOut(ctx android.ModuleContext, paths ...string) android.OutputPath {
	if ctx.Platform() && !ctx.InstallInRecovery() {
		return android.PathForModuleOut(ctx, paths...).OutputPath
	}

	return android.PathForModuleOut(ctx, ctx.Config().DeviceName()).Join(ctx, paths...)
}

// flagsToM4Macros converts given map to a list of M4's -D parameters to guard te files and contexts
// files.
func flagsToM4Macros(flags map[string]string) []string {
	flagMacros := []string{}
	for _, flag := range android.SortedKeys(flags) {
		flagMacros = append(flagMacros, "-D target_flag_"+flag+"="+flags[flag])
	}
	return flagMacros
}
