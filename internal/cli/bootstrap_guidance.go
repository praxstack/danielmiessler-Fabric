package cli

import (
	"errors"
	"fmt"
	"strings"

	"github.com/danielmiessler/fabric/internal/i18n"
)

func isNoConfiguredVendorsError(err error) bool {
	if err == nil {
		return false
	}
	return strings.Contains(err.Error(), i18n.T("vendors_no_ai_vendors_configured_read_models"))
}

func formatListModelsBootstrapGuidance(vendor string) string {
	vendor = strings.TrimSpace(vendor)
	var lines []string
	lines = append(lines, "No AI providers are configured yet.")
	lines = append(lines, "")
	if vendor != "" {
		lines = append(lines, fmt.Sprintf("Configure %s first:", vendor))
		lines = append(lines, fmt.Sprintf("  fabric --configure-provider %s", vendor))
		lines = append(lines, "")
		lines = append(lines, "Or run the full setup flow:")
		lines = append(lines, "  fabric --setup")
		lines = append(lines, "")
		lines = append(lines, fmt.Sprintf("Then retry: fabric --listmodels -V %s", vendor))
		return strings.Join(lines, "\n")
	}

	lines = append(lines, "Configure a provider first, for example:")
	lines = append(lines, "  fabric --configure-provider Bedrock")
	lines = append(lines, "")
	lines = append(lines, "Or run the full setup flow:")
	lines = append(lines, "  fabric --setup")
	lines = append(lines, "")
	lines = append(lines, "Then retry: fabric --listmodels")
	return strings.Join(lines, "\n")
}

func newConfigureModelBootstrapError(vendor string) error {
	vendor = strings.TrimSpace(vendor)
	if vendor == "" {
		return errors.New("no AI providers are configured yet; run `fabric --configure-provider <Vendor>` or `fabric --setup` first")
	}
	return fmt.Errorf(
		"vendor %q is not configured yet; run `fabric --configure-provider %s` first or pass `-m <model>` to persist a known model without probing",
		vendor,
		vendor,
	)
}

func newVendorHasNoModelsError(vendor string) error {
	vendor = strings.TrimSpace(vendor)
	return fmt.Errorf(
		"vendor %q is not configured or has no available models; run `fabric --configure-provider %s` first or pass `-m <model>` to persist a known model without probing",
		vendor,
		vendor,
	)
}
