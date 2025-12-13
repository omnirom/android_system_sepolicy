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
	"fmt"
	"io"

	"github.com/google/blueprint/proptools"

	"android/soong/android"
)

var (
	// Should be synced with keys.conf.
	AllPlatformKeys = []string{
		"platform",
		"sdk_sandbox",
		"media",
		"networkstack",
		"shared",
		"testkey",
		"bluetooth",
		"nfc",
	}
)

type macPermissionsProperties struct {
	// keys.conf files to control the mapping of "tags" found in the mac_permissions.xml files.
	Keys []string `android:"path"`

	// Source files for the generated mac_permissions.xml file.
	Srcs []string `android:"path"`

	// Output file name. Defaults to module name
	Stem *string
}

type macPermissionsModule struct {
	android.ModuleBase

	properties  macPermissionsProperties
	outputPath  android.ModuleOutPath
	installPath android.InstallPath
}

func init() {
	android.RegisterModuleType("mac_permissions", macPermissionsFactory)
}

func getAllKeyPaths(ctx android.ModuleContext, dir android.SourcePath) android.Paths {
	var keys android.Paths

	for _, key := range AllPlatformKeys {
		optKey := android.ExistentPathForSource(ctx, dir.Join(ctx, key+".x509.pem").String())
		if optKey.Valid() {
			keys = append(keys, optKey.Path())
		}
	}

	return keys
}

func (m *macPermissionsModule) DepsMutator(ctx android.BottomUpMutatorContext) {
	// do nothing
}

func (m *macPermissionsModule) stem() string {
	return proptools.StringDefault(m.properties.Stem, m.Name())
}

func buildVariant(ctx android.ModuleContext) string {
	if ctx.Config().Eng() {
		return "eng"
	}
	if ctx.Config().Debuggable() {
		return "userdebug"
	}
	return "user"
}

func (m *macPermissionsModule) GenerateAndroidBuildActions(ctx android.ModuleContext) {
	platformKeys := getAllKeyPaths(ctx, ctx.Config().DefaultAppCertificateDir(ctx))
	mainlineKeys := getAllKeyPaths(ctx, ctx.Config().MainlineSepolicyDevCertificatesDir(ctx))
	bluetoothKeys := getAllKeyPaths(ctx, ctx.Config().MainlineBluetoothSepolicyDevCertificatesDir(ctx))
	keys := android.PathsForModuleSrc(ctx, m.properties.Keys)
	srcs := android.PathsForModuleSrc(ctx, m.properties.Srcs)

	m4Keys := android.PathForModuleGen(ctx, "mac_perms_keys.tmp")
	rule := android.NewRuleBuilder(pctx, ctx)
	rule.Command().
		Tool(ctx.Config().PrebuiltBuildTool(ctx, "m4")).
		Text("--fatal-warnings -s").
		FlagForEachArg("-D", ctx.DeviceConfig().SepolicyM4Defs()).
		Inputs(keys).
		FlagWithOutput("> ", m4Keys).
		Implicits(platformKeys).
		Implicits(mainlineKeys).
		Implicits(bluetoothKeys)

	m.outputPath = android.PathForModuleOut(ctx, m.stem())
	rule.Command().Text("DEFAULT_SYSTEM_DEV_CERTIFICATE="+ctx.Config().DefaultAppCertificateDir(ctx).String()).
		Text("MAINLINE_SEPOLICY_DEV_CERTIFICATES="+ctx.Config().MainlineSepolicyDevCertificatesDir(ctx).String()).
		Text("MAINLINE_BLUETOOTH_SEPOLICY_DEV_CERTIFICATES="+ctx.Config().MainlineBluetoothSepolicyDevCertificatesDir(ctx).String()).
		BuiltTool("insertkeys").
		FlagWithArg("-t ", buildVariant(ctx)).
		Input(m4Keys).
		FlagWithOutput("-o ", m.outputPath).
		Inputs(srcs)

	rule.Build("mac_permission", "build "+m.Name())

	m.installPath = android.PathForModuleInstall(ctx, "etc", "selinux")
	ctx.InstallFile(m.installPath, m.stem(), m.outputPath)
}

func (m *macPermissionsModule) AndroidMk() android.AndroidMkData {
	return android.AndroidMkData{
		Class:      "ETC",
		OutputFile: android.OptionalPathForPath(m.outputPath),
		Extra: []android.AndroidMkExtraFunc{
			func(w io.Writer, outputFile android.Path) {
				fmt.Fprintln(w, "LOCAL_MODULE_PATH :=", m.installPath.String())
				fmt.Fprintln(w, "LOCAL_INSTALLED_MODULE_STEM :=", m.stem())
			},
		},
	}
}

// mac_permissions module generates a mac_permissions.xml file from given keys.conf and
// source files. The following variables are supported for keys.conf files.
//
//	DEFAULT_SYSTEM_DEV_CERTIFICATE
//	MAINLINE_SEPOLICY_DEV_CERTIFICATES
//	MAINLINE_BLUETOOTH_SEPOLICY_DEV_CERTIFICATES
func macPermissionsFactory() android.Module {
	m := &macPermissionsModule{}
	m.AddProperties(&m.properties)
	android.InitAndroidArchModule(m, android.DeviceSupported, android.MultilibCommon)
	return m
}
