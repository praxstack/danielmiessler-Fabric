package cli

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/danielmiessler/fabric/internal/core"
	"github.com/danielmiessler/fabric/internal/plugins/ai"
)

// handleConfigurationCommands handles configuration-related commands.
// handleConfigurationCommands processes configuration-related CLI flags and performs the requested setup or migrations.
// It handles pattern DB population, vendor setup, and default model configuration. It returns (handled, err) where
// handled is true when a configuration command was processed (the caller should treat this as a handled/exit case)
// and err reports any failure encountered while performing the requested actions.
func handleConfigurationCommands(currentFlags *Flags, registry *core.PluginRegistry) (handled bool, err error) {
	if currentFlags.UpdatePatterns {
		if err = registry.PatternsLoader.PopulateDB(); err != nil {
			return true, err
		}
		// Save configuration in case any paths were migrated during pattern loading.
		err = registry.SaveEnvFile()
		return true, err
	}

	shouldConfigureModel := currentFlags.ConfigureModel || currentFlags.ChangeDefaultModel
	shouldConfigureProvider := currentFlags.ConfigureProvider != ""
	if !shouldConfigureProvider && !shouldConfigureModel {
		return false, nil
	}

	if registry == nil {
		return true, errors.New("fabric configuration is not initialized")
	}

	selectedVendor := strings.TrimSpace(currentFlags.Vendor)
	if shouldConfigureProvider {
		if err = registry.SetupVendor(currentFlags.ConfigureProvider); err != nil {
			return true, err
		}
		if selectedVendor == "" {
			selectedVendor = currentFlags.ConfigureProvider
		}
	}

	if shouldConfigureModel {
		if err = configureDefaultModel(registry, selectedVendor, currentFlags.Model); err != nil {
			return true, err
		}
	}

	return true, nil
}

// configureDefaultModel determines and persists the default provider and model using available model metadata,
// an optional vendor constraint, and an optional explicit model selection.
//
// If requestedModel is provided in a vendor|model form or matches an available model, that selection is applied.
// When no explicit selection is given, the function lists available models (respecting vendorFilter) and prompts
// the user on stdin to choose by number or exact name (vendor|model is accepted when vendorFilter is empty).
//
// The resolved vendor and model are saved into the registry defaults and persisted to the environment file.
// An error is returned on invalid vendor/model selections, when no configured vendors or models are available,
// on input read failures, or if persisting the defaults fails.
func configureDefaultModel(registry *core.PluginRegistry, vendorFilter, requestedModel string) error {
	vendorFilter = strings.TrimSpace(vendorFilter)
	requestedModel = strings.TrimSpace(requestedModel)

	models, modelsErr := registry.GetModels()
	if requestedModel != "" {
		vendorName, modelName, handled, err := resolveExplicitModelSelection(registry, models, modelsErr, vendorFilter, requestedModel)
		if err != nil {
			return err
		}
		if handled {
			return persistDefaultModel(registry, vendorName, modelName)
		}
	}

	if modelsErr != nil {
		if isNoConfiguredVendorsError(modelsErr) {
			return newConfigureModelBootstrapError(vendorFilter)
		}
		return modelsErr
	}

	if vendorFilter != "" {
		models = models.FilterByVendor(vendorFilter)
		if len(models.GroupsItems) == 0 {
			return newVendorHasNoModelsError(vendorFilter)
		}
	}

	if requestedModel == "" {
		models.PrintWithVendor(false, registry.Defaults.Vendor.Value, registry.Defaults.Model.Value)

		prompt := "\nEnter model number or exact model name"
		if vendorFilter == "" {
			prompt += " (or Vendor|Model)"
		}
		fmt.Printf("%s: ", prompt)

		reader := bufio.NewReader(os.Stdin)
		selection, readErr := reader.ReadString('\n')
		if readErr != nil && !errors.Is(readErr, io.EOF) {
			return readErr
		}
		requestedModel = strings.TrimSpace(selection)
		if requestedModel == "" {
			return errors.New("no model selected")
		}
	}

	vendorName, modelName, err := resolveDefaultModelSelection(models, vendorFilter, requestedModel)
	if err != nil {
		return err
	}

	return persistDefaultModel(registry, vendorName, modelName)
}

// persistDefaultModel updates the registry's default vendor and model, writes them into the process environment, prints confirmation lines, and persists the environment file.
// It returns an error if setting either environment variable fails or if saving the registry's env file fails.
func persistDefaultModel(registry *core.PluginRegistry, vendorName, modelName string) error {
	registry.Defaults.Vendor.Value = vendorName
	registry.Defaults.Model.Value = modelName
	if err := os.Setenv(registry.Defaults.Vendor.EnvVariable, vendorName); err != nil {
		return err
	}
	if err := os.Setenv(registry.Defaults.Model.EnvVariable, modelName); err != nil {
		return err
	}

	fmt.Printf("Default provider: %s\n", vendorName)
	fmt.Printf("Default model: %s\n", modelName)

	return registry.SaveEnvFile()
}

// resolveExplicitModelSelection determines whether requestedModel specifies an explicit
// model selection and, if so, resolves and returns the canonical vendor and model.
// 
// If requestedModel is empty the function does nothing (handled == false).
// If requestedModel is in "Vendor|Model" form it validates the vendor against
// vendorFilter (if provided), resolves the canonical vendor name via the registry,
// and, when model metadata is available, canonicalizes the model name.
// If requestedModel is not in "Vendor|Model" form but a vendorFilter is provided,
// the function resolves the canonical vendor name from vendorFilter and, when
// model metadata is available, canonicalizes the requestedModel within that vendor.
// 
// When the function takes responsibility for the selection it returns handled == true.
// It returns an error when the vendor cannot be resolved or when the selection's
// vendor conflicts with the vendorFilter.
func resolveExplicitModelSelection(
	registry *core.PluginRegistry,
	models *ai.VendorsModels,
	modelsErr error,
	vendorFilter, requestedModel string,
) (vendorName string, modelName string, handled bool, err error) {
	if requestedModel == "" {
		return "", "", false, nil
	}

	if vendor, model, ok := splitVendorModelSelection(requestedModel); ok {
		if vendorFilter != "" && !strings.EqualFold(vendorFilter, vendor) {
			return "", "", true, fmt.Errorf("selection vendor %q does not match requested vendor %q", vendor, vendorFilter)
		}

		canonicalVendor, found := canonicalVendorName(registry, vendor)
		if !found {
			return "", "", true, fmt.Errorf("vendor %q was not found", vendor)
		}

		if modelsErr == nil && modelExistsForVendor(models, canonicalVendor, model) {
			model = canonicalModelName(models, canonicalVendor, model)
		}

		return canonicalVendor, model, true, nil
	}

	if vendorFilter == "" {
		return "", "", false, nil
	}

	canonicalVendor, found := canonicalVendorName(registry, vendorFilter)
	if !found {
		return "", "", true, fmt.Errorf("vendor %q was not found", vendorFilter)
	}

	if modelsErr == nil {
		filtered := models.FilterByVendor(canonicalVendor)
		if len(filtered.GroupsItems) > 0 && modelExistsForVendor(filtered, canonicalVendor, requestedModel) {
			requestedModel = canonicalModelName(filtered, canonicalVendor, requestedModel)
		}
	}

	return canonicalVendor, requestedModel, true, nil
}

// canonicalVendorName looks up the canonical vendor name for the given vendor
// by searching the registry's VendorManager and VendorsAll.
// It returns the resolved canonical name and true if a match is found, or an
// empty string and false otherwise.
func canonicalVendorName(registry *core.PluginRegistry, vendor string) (string, bool) {
	for _, manager := range []*ai.VendorsManager{registry.VendorManager, registry.VendorsAll} {
		if manager == nil {
			continue
		}
		if resolved := manager.FindByName(vendor); resolved != nil {
			return resolved.GetName(), true
		}
	}
	return "", false
}

// resolveDefaultModelSelection resolves a user-provided selection into a vendor and model pair.
// It accepts a numeric index (selecting by listed item number), a "Vendor|Model" spec, or a plain model name.
// It returns the resolved vendor name and the canonical model name, or an error if the selection is empty,
// the vendor in a Vendor|Model spec conflicts with a provided vendor filter, the model does not exist, or
// the model name is ambiguous across multiple vendors.
func resolveDefaultModelSelection(models *ai.VendorsModels, vendorFilter, selection string) (vendorName string, modelName string, err error) {
	selection = strings.TrimSpace(selection)
	if selection == "" {
		return "", "", errors.New("no model selected")
	}

	if index, parseErr := strconv.Atoi(selection); parseErr == nil {
		return models.GetGroupAndItemByItemNumber(index)
	}

	if vendor, model, ok := splitVendorModelSelection(selection); ok {
		if vendorFilter != "" && !strings.EqualFold(vendorFilter, vendor) {
			return "", "", fmt.Errorf("selection vendor %q does not match requested vendor %q", vendor, vendorFilter)
		}
		if !modelExistsForVendor(models, vendor, model) {
			return "", "", fmt.Errorf("model %q was not found for vendor %q", model, vendor)
		}
		return vendor, canonicalModelName(models, vendor, model), nil
	}

	vendors := models.FindGroupsByItem(selection)
	if len(vendors) == 0 {
		return "", "", fmt.Errorf("model %q was not found in available models", selection)
	}
	if len(vendors) > 1 {
		return "", "", fmt.Errorf("model %q is available from multiple vendors; use --vendor or Vendor|Model", selection)
	}

	return vendors[0], canonicalModelName(models, vendors[0], selection), nil
}

// splitVendorModelSelection parses selection of the form "Vendor|Model".
// It returns the vendor and model parts with surrounding whitespace trimmed and ok==true
// only if the input contains a single '|' separator and both parts are non-empty.
func splitVendorModelSelection(selection string) (vendor string, model string, ok bool) {
	parts := strings.SplitN(selection, "|", 2)
	if len(parts) != 2 {
		return "", "", false
	}

	vendor = strings.TrimSpace(parts[0])
	model = strings.TrimSpace(parts[1])
	if vendor == "" || model == "" {
		return "", "", false
	}
	return vendor, model, true
}

// modelExistsForVendor reports whether the VendorsModels contains the given model for the specified vendor,
// using case-insensitive comparisons for both vendor and model names.
func modelExistsForVendor(models *ai.VendorsModels, vendor, model string) bool {
	for _, groupItems := range models.GroupsItems {
		if !strings.EqualFold(groupItems.Group, vendor) {
			continue
		}
		for _, item := range groupItems.Items {
			if strings.EqualFold(item, model) {
				return true
			}
		}
	}
	return false
}

// canonicalModelName returns the canonical model name for the given vendor when a case-insensitive
// match is found in models.GroupsItems. If no matching vendor or model is found, it returns the
// provided model unchanged.
func canonicalModelName(models *ai.VendorsModels, vendor, model string) string {
	for _, groupItems := range models.GroupsItems {
		if !strings.EqualFold(groupItems.Group, vendor) {
			continue
		}
		for _, item := range groupItems.Items {
			if strings.EqualFold(item, model) {
				return item
			}
		}
	}
	return model
}
