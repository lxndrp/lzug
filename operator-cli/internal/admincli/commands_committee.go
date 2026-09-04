package admincli

import (
	"fmt"
	"regexp"
	"strings"
)

var idempotencyKeyPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$`)

func committeeCommands() []Command {
	bootstrapOptions := append(committeeIdentityOptions(false), committeePersonOptions()...)
	completeOptions := append(committeeIdentityOptions(true), committeePersonOptions()...)
	return []Command{
		{
			Path:        []string{"committee", "bootstrap"},
			Summary:     "Bootstrap a complete examination committee.",
			Description: "Create one committee, select its initial chair and optional deputy, and issue any required invitations atomically.",
			Examples: []string{
				"lzug-admin --container lzug committee bootstrap --idempotency-key bootstrap-001 --name 'PA Nord' --ihk 'IHK Teststadt' --occupation 'Fachinformatiker/in' --chair-existing-email chair@example.invalid --chair-member-status ordinary --chair-representing-side employer",
			},
			Options:        bootstrapOptions,
			Transport:      ContainerExecTransport,
			BackendCommand: "committee-bootstrap",
			LegacyForms:    []string{"committee-bootstrap"},
			Output: OutputSpec{Human: HumanInvitations, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints newly issued one-time invitation tokens; JSON includes the technical bootstrap result.", ResultKeys: []string{
				"committee_id", "bootstrap_state", "person_ids", "membership_ids", "account_ids", "invitations", "replayed",
			}},
			Validate: validateCommitteeSelection,
			BuildRequest: simpleRequest("committee-bootstrap", func(values, _ Values) map[string]any {
				arguments := committeeSelectionArguments(values)
				arguments["committee"] = map[string]any{
					"name":       values.String("name"),
					"ihk":        values.String("ihk"),
					"occupation": values.String("occupation"),
				}
				return arguments
			}),
		},
		{
			Path:        []string{"committee", "complete"},
			Summary:     "Complete an existing examination committee.",
			Description: "Complete one imported committee with its chair and optional deputy using an idempotent administration request.",
			Examples: []string{
				"lzug-admin --container lzug committee complete --idempotency-key complete-001 --committee-id 7 --chair-existing-email chair@example.invalid --chair-member-status ordinary --chair-representing-side employer",
			},
			Options:        completeOptions,
			Transport:      ContainerExecTransport,
			BackendCommand: "committee-complete",
			LegacyForms:    []string{"committee-complete"},
			Output: OutputSpec{Human: HumanInvitations, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints newly issued one-time invitation tokens; JSON includes the technical completion result.", ResultKeys: []string{
				"committee_id", "bootstrap_state", "person_ids", "membership_ids", "account_ids", "invitations", "replayed",
			}},
			Validate: validateCommitteeSelection,
			BuildRequest: simpleRequest("committee-complete", func(values, _ Values) map[string]any {
				arguments := committeeSelectionArguments(values)
				arguments["committee_id"] = values.Int("committee-id")
				return arguments
			}),
		},
		{
			Path:        []string{"committee", "reinvite"},
			Summary:     "Reissue one eligible committee invitation.",
			Description: "Reissue an invitation for one committee account through an idempotent administration request.",
			Examples: []string{
				"lzug-admin --container lzug committee reinvite --idempotency-key reinvite-001 --committee-id 7 --email member@example.invalid",
			},
			Options: []OptionSpec{
				idempotencyOption(),
				{Name: "committee-id", ValueName: "ID", Summary: "Positive committee identifier.", Kind: IntegerOption, Required: true, Positive: true},
				{Name: "email", ValueName: "EMAIL", Summary: "Eligible committee account email address.", Kind: StringOption, Required: true},
			},
			Transport:      ContainerExecTransport,
			BackendCommand: "committee-reinvite",
			LegacyForms:    []string{"committee-reinvite"},
			Output:         OutputSpec{Human: HumanInvitations, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Prints the newly issued one-time invitation token; JSON includes the technical result.", ResultKeys: []string{"committee_id", "account_ids", "invitations", "replayed"}},
			Validate:       validateIdempotencyKey,
			BuildRequest: simpleRequest("committee-reinvite", func(values, _ Values) map[string]any {
				return map[string]any{
					"idempotency_key": values.String("idempotency-key"),
					"committee_id":    values.Int("committee-id"),
					"email":           values.String("email"),
				}
			}),
		},
		committeeLifecycleCommand("deactivate", true),
		committeeLifecycleCommand("reactivate", false),
	}
}

func committeeIdentityOptions(existing bool) []OptionSpec {
	options := []OptionSpec{idempotencyOption()}
	if existing {
		return append(options, OptionSpec{Name: "committee-id", ValueName: "ID", Summary: "Positive committee identifier.", Kind: IntegerOption, Required: true, Positive: true})
	}
	return append(options,
		OptionSpec{Name: "name", ValueName: "NAME", Summary: "Committee name.", Kind: StringOption, Required: true},
		OptionSpec{Name: "ihk", ValueName: "NAME", Summary: "Responsible chamber of commerce.", Kind: StringOption, Required: true},
		OptionSpec{Name: "occupation", ValueName: "NAME", Summary: "Training occupation.", Kind: StringOption, Required: true},
	)
}

func idempotencyOption() OptionSpec {
	return OptionSpec{Name: "idempotency-key", ValueName: "KEY", Summary: "Unique retry key with at least eight safe characters.", Kind: StringOption, Required: true}
}

func committeePersonOptions() []OptionSpec {
	options := []OptionSpec{}
	for _, prefix := range []string{"chair", "deputy"} {
		label := "Chair"
		if prefix == "deputy" {
			label = "Deputy chair"
		}
		options = append(options,
			OptionSpec{Name: prefix + "-existing-email", ValueName: "EMAIL", Summary: label + " existing person email.", Kind: StringOption},
			OptionSpec{Name: prefix + "-first-name", ValueName: "NAME", Summary: label + " new person first name.", Kind: StringOption},
			OptionSpec{Name: prefix + "-last-name", ValueName: "NAME", Summary: label + " new person last name.", Kind: StringOption},
			OptionSpec{Name: prefix + "-email", ValueName: "EMAIL", Summary: label + " new person email.", Kind: StringOption},
			OptionSpec{Name: prefix + "-mobile", ValueName: "NUMBER", Summary: label + " optional new person mobile number.", Kind: StringOption},
			OptionSpec{Name: prefix + "-member-status", ValueName: "STATUS", Summary: label + " membership status.", Kind: StringOption, Choices: []string{"ordinary", "deputy"}},
			OptionSpec{Name: prefix + "-representing-side", ValueName: "SIDE", Summary: label + " represented side.", Kind: StringOption, Choices: []string{"employer", "employee", "school"}},
		)
	}
	return options
}

func validateCommitteeSelection(values Values) error {
	if err := validateIdempotencyKey(values); err != nil {
		return err
	}
	if _, err := committeePersonSelection(values, "chair", true); err != nil {
		return err
	}
	if _, err := committeePersonSelection(values, "deputy", false); err != nil {
		return err
	}
	return nil
}

func validateIdempotencyKey(values Values) error {
	if !idempotencyKeyPattern.MatchString(values.String("idempotency-key")) {
		return fmt.Errorf("--idempotency-key must contain 8 to 128 safe characters")
	}
	return nil
}

func committeeSelectionArguments(values Values) map[string]any {
	arguments := map[string]any{"idempotency_key": values.String("idempotency-key")}
	chair, _ := committeePersonSelection(values, "chair", true)
	deputy, _ := committeePersonSelection(values, "deputy", false)
	arguments["chair"] = chair
	if deputy != nil {
		arguments["deputy"] = deputy
	}
	return arguments
}

func committeePersonSelection(values Values, prefix string, required bool) (map[string]any, error) {
	existingEmail := values.String(prefix + "-existing-email")
	firstName := values.String(prefix + "-first-name")
	lastName := values.String(prefix + "-last-name")
	email := values.String(prefix + "-email")
	mobile := values.String(prefix + "-mobile")
	memberStatus := values.String(prefix + "-member-status")
	representingSide := values.String(prefix + "-representing-side")

	existing := strings.TrimSpace(existingEmail) != ""
	newPerson := anyNonEmpty(firstName, lastName, email, mobile)
	membership := anyNonEmpty(memberStatus, representingSide)
	if !existing && !newPerson && !membership {
		if required {
			return nil, fmt.Errorf("%s person selection is required", prefix)
		}
		return nil, nil
	}
	if existing == newPerson || !membership || memberStatus == "" || representingSide == "" {
		return nil, fmt.Errorf("%s requires exactly one existing or new person path and both membership options", prefix)
	}
	selection := map[string]any{
		"member_status":     memberStatus,
		"representing_side": representingSide,
	}
	if existing {
		selection["mode"] = "existing"
		selection["email"] = existingEmail
		return selection, nil
	}
	if strings.TrimSpace(firstName) == "" || strings.TrimSpace(lastName) == "" || strings.TrimSpace(email) == "" {
		return nil, fmt.Errorf("%s new person requires first name, last name and email", prefix)
	}
	selection["mode"] = "new"
	selection["first_name"] = firstName
	selection["last_name"] = lastName
	selection["email"] = email
	if strings.TrimSpace(mobile) != "" {
		selection["mobile"] = mobile
	}
	return selection, nil
}

func anyNonEmpty(values ...string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return true
		}
	}
	return false
}

func committeeLifecycleCommand(action string, confirmation bool) Command {
	command := Command{
		Path:        []string{"committee", action},
		Summary:     strings.ToUpper(action[:1]) + action[1:] + " an examination committee.",
		Description: strings.ToUpper(action[:1]) + action[1:] + " one committee with an idempotent, reasoned administration request.",
		Examples: []string{
			fmt.Sprintf("lzug-admin --container lzug committee %s --idempotency-key %s-001 --committee-id 7 --reason 'Operator decision'%s", action, action, map[bool]string{true: " --force"}[confirmation]),
		},
		Options: []OptionSpec{
			idempotencyOption(),
			{Name: "committee-id", ValueName: "ID", Summary: "Positive committee identifier.", Kind: IntegerOption, Required: true, Positive: true},
			{Name: "reason", ValueName: "TEXT", Summary: "Required lifecycle reason.", Kind: StringOption, Required: true},
		},
		Transport:      ContainerExecTransport,
		BackendCommand: "committee-" + action,
		LegacyForms:    []string{"committee-" + action},
		Output:         OutputSpec{Human: HumanSilent, Verbose: VerboseSummary, JSON: JSONProjected, Summary: "Successful human output is silent; JSON includes the technical lifecycle result.", ResultKeys: []string{"committee_id", "active", "reason", "replayed"}},
		Validate:       validateIdempotencyKey,
		BuildRequest: simpleRequest("committee-"+action, func(values, _ Values) map[string]any {
			return map[string]any{
				"idempotency_key": values.String("idempotency-key"),
				"committee_id":    values.Int("committee-id"),
				"reason":          values.String("reason"),
			}
		}),
	}
	if confirmation {
		command.Confirmation = ConfirmationSpec{
			Required: true,
			Prompt: func(values Values, _ EffectiveConfig) string {
				return fmt.Sprintf("Deactivate committee %d and suspend its use?", values.Int("committee-id"))
			},
		}
	}
	return command
}
