package cli

import (
	"bytes"
	"os"
	"strings"
	"testing"

	"github.com/danielmiessler/fabric/internal/core"
	"github.com/danielmiessler/fabric/internal/plugins/ai"
	"github.com/danielmiessler/fabric/internal/tools"
	"github.com/stretchr/testify/require"
)

type cliConfigVendor struct {
	cliStubVendor
	envLine    string
	setupCalls int
	configured bool
}

func (v *cliConfigVendor) Setup() error {
	v.setupCalls++
	return nil
}

func (v *cliConfigVendor) IsConfigured() bool {
	return v.configured
}

func (v *cliConfigVendor) SetupFillEnvFileContent(buf *bytes.Buffer) {
	if v.envLine == "" {
		return
	}
	buf.WriteString(v.envLine)
	buf.WriteString("\n")
}

func TestHandleConfigurationCommandsNoop(t *testing.T) {
	handled, err := handleConfigurationCommands(&Flags{}, nil)
	require.False(t, handled)
	require.NoError(t, err)
}

func TestResolveDefaultModelSelection(t *testing.T) {
	t.Parallel()

	models := ai.NewVendorsModels()
	models.AddGroupItems("VendorA", "alpha", "shared")
	models.AddGroupItems("VendorB", "beta", "shared")

	vendor, model, err := resolveDefaultModelSelection(models, "", "2")
	require.NoError(t, err)
	require.Equal(t, "VendorA", vendor)
	require.Equal(t, "shared", model)

	vendor, model, err = resolveDefaultModelSelection(models, "", "VendorB|beta")
	require.NoError(t, err)
	require.Equal(t, "VendorB", vendor)
	require.Equal(t, "beta", model)

	_, _, err = resolveDefaultModelSelection(models, "", "shared")
	require.Error(t, err)
	require.Contains(t, err.Error(), "multiple vendors")
}

func TestConfigureDefaultModelPersistsDefaults(t *testing.T) {
	registry := newConfigurationRegistry(t)

	err := configureDefaultModel(registry, "VendorB", "beta")
	require.NoError(t, err)
	require.Equal(t, "VendorB", registry.Defaults.Vendor.Value)
	require.Equal(t, "beta", registry.Defaults.Model.Value)
	require.Equal(t, "VendorB", os.Getenv("DEFAULT_VENDOR"))
	require.Equal(t, "beta", os.Getenv("DEFAULT_MODEL"))

	envContent, readErr := os.ReadFile(registry.Db.EnvFilePath)
	require.NoError(t, readErr)
	require.Contains(t, string(envContent), "DEFAULT_VENDOR=VendorB")
	require.Contains(t, string(envContent), "DEFAULT_MODEL=beta")
}

func TestHandleConfigurationCommandsConfigureProviderAndModel(t *testing.T) {
	registry := newConfigurationRegistry(t)
	vendor := &cliConfigVendor{
		cliStubVendor: cliStubVendor{name: "ProviderX", models: []string{"x-model"}},
		envLine:       "PROVIDER_X_TOKEN=secret",
		configured:    true,
	}

	registry.VendorManager.Clear()
	registry.VendorsAll = ai.NewVendorsManager()
	registry.VendorsAll.AddVendors(vendor)
	registry.Defaults = tools.NeeDefaults(registry.GetModels)

	handled, err := handleConfigurationCommands(&Flags{
		ConfigureProvider: "ProviderX",
		ConfigureModel:    true,
		Model:             "x-model",
	}, registry)
	require.True(t, handled)
	require.NoError(t, err)
	require.Equal(t, 1, vendor.setupCalls)
	require.NotNil(t, registry.VendorManager.FindByName("ProviderX"))
	require.Equal(t, "ProviderX", registry.Defaults.Vendor.Value)
	require.Equal(t, "x-model", registry.Defaults.Model.Value)

	envContent, readErr := os.ReadFile(registry.Db.EnvFilePath)
	require.NoError(t, readErr)
	require.Contains(t, string(envContent), "PROVIDER_X_TOKEN=secret")
	require.Contains(t, string(envContent), "DEFAULT_VENDOR=ProviderX")
	require.Contains(t, string(envContent), "DEFAULT_MODEL=x-model")
}

func TestConfigureDefaultModelAllowsExplicitVendorModelWithoutCatalog(t *testing.T) {
	registry := newConfigurationRegistry(t)
	registry.VendorManager.Clear()

	err := configureDefaultModel(registry, "VendorB", "custom-model")
	require.NoError(t, err)
	require.Equal(t, "VendorB", registry.Defaults.Vendor.Value)
	require.Equal(t, "custom-model", registry.Defaults.Model.Value)

	envContent, readErr := os.ReadFile(registry.Db.EnvFilePath)
	require.NoError(t, readErr)
	require.Contains(t, string(envContent), "DEFAULT_VENDOR=VendorB")
	require.Contains(t, string(envContent), "DEFAULT_MODEL=custom-model")
}

func TestConfigureDefaultModelAllowsExplicitVendorPipeModelWithoutCatalog(t *testing.T) {
	registry := newConfigurationRegistry(t)
	registry.VendorManager.Clear()

	err := configureDefaultModel(registry, "", "VendorA|direct-model")
	require.NoError(t, err)
	require.Equal(t, "VendorA", registry.Defaults.Vendor.Value)
	require.Equal(t, "direct-model", registry.Defaults.Model.Value)
}

func newConfigurationRegistry(t *testing.T) *core.PluginRegistry {
	t.Helper()

	db := newConfiguredTestDB(t)
	registry, err := core.NewPluginRegistry(db)
	require.NoError(t, err)

	registry.VendorManager = ai.NewVendorsManager()
	registry.VendorsAll = ai.NewVendorsManager()

	vendorA := &cliConfigVendor{
		cliStubVendor: cliStubVendor{name: "VendorA", models: []string{"alpha", "shared"}},
		envLine:       "VENDORA_TOKEN=1",
		configured:    true,
	}
	vendorB := &cliConfigVendor{
		cliStubVendor: cliStubVendor{name: "VendorB", models: []string{"beta", "shared"}},
		envLine:       "VENDORB_TOKEN=1",
		configured:    true,
	}

	registry.VendorManager.AddVendors(vendorA, vendorB)
	registry.VendorsAll.AddVendors(vendorA, vendorB)
	registry.Defaults = tools.NeeDefaults(registry.GetModels)
	registry.Defaults.Vendor.Value = "VendorA"
	registry.Defaults.Model.Value = "alpha"

	t.Cleanup(func() {
		_ = os.Unsetenv("DEFAULT_VENDOR")
		_ = os.Unsetenv("DEFAULT_MODEL")
	})

	return registry
}

func TestSplitVendorModelSelection(t *testing.T) {
	t.Parallel()

	vendor, model, ok := splitVendorModelSelection(" OpenRouter | anthropic/claude-opus-4.6 ")
	require.True(t, ok)
	require.Equal(t, "OpenRouter", vendor)
	require.Equal(t, "anthropic/claude-opus-4.6", model)

	_, _, ok = splitVendorModelSelection("invalid")
	require.False(t, ok)
}

func TestCanonicalModelName(t *testing.T) {
	t.Parallel()

	models := ai.NewVendorsModels()
	models.AddGroupItems("Bedrock", "us.anthropic.claude-opus-4-6-v1")

	require.True(t, modelExistsForVendor(models, "bedrock", "US.ANTHROPIC.CLAUDE-OPUS-4-6-V1"))
	require.Equal(t,
		"us.anthropic.claude-opus-4-6-v1",
		canonicalModelName(models, "bedrock", "US.ANTHROPIC.CLAUDE-OPUS-4-6-V1"),
	)
}

func TestConfigureDefaultModelRejectsUnknownVendor(t *testing.T) {
	registry := newConfigurationRegistry(t)

	err := configureDefaultModel(registry, "MissingVendor", "beta")
	require.Error(t, err)
	require.True(t, strings.Contains(err.Error(), "MissingVendor"))
}

func TestConfigureDefaultModelGuidesWhenVendorIsNotConfigured(t *testing.T) {
	registry := newConfigurationRegistry(t)
	registry.VendorManager.Clear()
	registry.VendorsAll.Clear()

	err := configureDefaultModel(registry, "Bedrock", "")
	require.Error(t, err)
	require.Contains(t, err.Error(), "fabric --configure-provider Bedrock")
	require.Contains(t, err.Error(), "-m <model>")
}

func TestHandleConfigurationCommandsRejectsIncompleteProviderSetup(t *testing.T) {
	registry := newConfigurationRegistry(t)
	vendor := &cliConfigVendor{
		cliStubVendor: cliStubVendor{name: "ProviderY", models: []string{"y-model"}},
		configured:    false,
	}

	registry.VendorManager.Clear()
	registry.VendorsAll = ai.NewVendorsManager()
	registry.VendorsAll.AddVendors(vendor)
	registry.Defaults = tools.NeeDefaults(registry.GetModels)

	handled, err := handleConfigurationCommands(&Flags{
		ConfigureProvider: "ProviderY",
	}, registry)
	require.True(t, handled)
	require.Error(t, err)
	require.Contains(t, err.Error(), "did not produce a valid configuration")
	require.Nil(t, registry.VendorManager.FindByName("ProviderY"))
}
