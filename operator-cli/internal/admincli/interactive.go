package admincli

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"sort"
	"strconv"
	"strings"
	"unicode/utf8"
)

const defaultDialogWidth = 80

type dialogAction int

const (
	dialogValue dialogAction = iota
	dialogBack
	dialogCancel
	dialogExit
)

type interactiveSession struct {
	application *Application
	input       InteractiveInput
	renderer    InteractiveRenderer
	global      GlobalOptions
	config      EffectiveConfig
	checked     bool
	exiting     bool
}

type outcomeRenderer struct {
	Renderer
	failure *CLIError
}

func (renderer *outcomeRenderer) Error(global GlobalOptions, command string, failure *CLIError) {
	renderer.failure = failure
	renderer.Renderer.Error(global, command, failure)
}

func (renderer *outcomeRenderer) Backend(global GlobalOptions, command *Command, response BackendResponse, exitCode int) *CLIError {
	failure := renderer.Renderer.Backend(global, command, response, exitCode)
	if failure != nil {
		renderer.failure = failure
	}
	return failure
}

func (renderer *outcomeRenderer) LocalSuccess(global GlobalOptions, command *Command, result LocalResult) *CLIError {
	failure := renderer.Renderer.LocalSuccess(global, command, result)
	if failure != nil {
		renderer.failure = failure
	}
	return failure
}

// RunInteractive starts the registry-generated line-oriented operator dialog.
func (application *Application) RunInteractive(ctx context.Context, global GlobalOptions) int {
	input, inputOK := application.Input.(InteractiveInput)
	renderer, rendererOK := application.Renderer.(InteractiveRenderer)
	if !inputOK || !rendererOK || !input.IsTerminal() || !renderer.IsTerminal() {
		failure := invalidInvocation("cli requires interactive input and output terminals")
		failure.NextStep = "Use a direct lzug-admin object/action subcommand for pipes, scripts, or CI."
		application.Renderer.Error(global, "cli", failure)
		return failure.ExitCode
	}
	config, failure := application.Config.Resolve(global)
	if failure != nil {
		application.Renderer.Error(global, "cli", failure)
		return failure.ExitCode
	}
	session := &interactiveSession{
		application: application,
		input:       input,
		renderer:    renderer,
		global:      global,
		config:      config,
	}
	return session.run(ctx)
}

func (session *interactiveSession) run(ctx context.Context) int {
	if err := session.write("lzug-admin - geführter Modus\n\n"); err != nil {
		return ExitUnexpected
	}
	session.showTarget()
	for {
		if ctx.Err() != nil {
			session.write("\nSitzung durch Ctrl+C beendet.\n")
			return ExitInterrupted
		}
		selection, action, err := session.home(ctx)
		if err != nil {
			return session.readFailure(ctx, err, true)
		}
		switch action {
		case dialogExit:
			session.write("Sitzung beendet.\n")
			return ExitOK
		case dialogBack, dialogCancel:
			continue
		}
		if selection == "search" {
			command, next, code := session.search(ctx)
			if code != ExitOK {
				return code
			}
			if next == dialogExit {
				return ExitOK
			}
			if command != nil {
				if code = session.command(ctx, command); code != ExitOK {
					return code
				}
				if session.exiting {
					session.write("Sitzung beendet.\n")
					return ExitOK
				}
			}
			continue
		}
		if selection == "target" {
			if code := session.changeTarget(ctx); code != ExitOK {
				return code
			}
			continue
		}
		if selection == "verbose" {
			session.global.Verbose = !session.global.Verbose
			session.write(fmt.Sprintf("Ausführliche Ausgabe: %s.\n", onOff(session.global.Verbose)))
			continue
		}
		if group, found := session.application.Registry.Group(selection); found {
			command, next, code := session.group(ctx, group)
			if code != ExitOK {
				return code
			}
			if next == dialogExit {
				return ExitOK
			}
			if command != nil {
				if code = session.command(ctx, command); code != ExitOK {
					return code
				}
				if session.exiting {
					session.write("Sitzung beendet.\n")
					return ExitOK
				}
			}
			continue
		}
		if command, found := session.application.Registry.Find([]string{selection}); found {
			if code := session.command(ctx, command); code != ExitOK {
				return code
			}
			if session.exiting {
				session.write("Sitzung beendet.\n")
				return ExitOK
			}
		}
	}
}

func (session *interactiveSession) home(ctx context.Context) (string, dialogAction, error) {
	entries := make([]string, 0)
	session.write("\nObjekt wählen:\n")
	for _, group := range session.application.Registry.Groups() {
		entries = append(entries, group.Name)
		session.write(fmt.Sprintf("  %d. %s - %s\n", len(entries), group.Name, group.Summary))
	}
	for _, command := range session.application.Registry.Commands() {
		if len(command.Path) != 1 {
			continue
		}
		entries = append(entries, command.Path[0])
		session.write(fmt.Sprintf("  %d. %s - %s%s\n", len(entries), command.Name(), command.Summary, session.availability(command)))
	}
	session.write("  Suche, Ziel, Verbose, Hilfe, Beenden\n")
	for {
		value, err := session.input.ReadLine(ctx, "> ")
		if err != nil {
			return "", dialogCancel, err
		}
		normalized := normalizeAction(value)
		switch normalized {
		case "hilfe":
			session.write("Wählen Sie eine Nummer oder einen Objektnamen. Suche findet Name, Hilfe und Suchbegriffe. Ziel ändert Engine und Container nur für diese Sitzung.\n")
			continue
		case "beenden":
			return "", dialogExit, nil
		case "zurueck", "abbrechen":
			return "", dialogCancel, nil
		case "suchen", "suche", "search":
			return "search", dialogValue, nil
		case "ziel", "target":
			return "target", dialogValue, nil
		case "verbose":
			return "verbose", dialogValue, nil
		}
		if index, err := strconv.Atoi(value); err == nil && index > 0 && index <= len(entries) {
			return entries[index-1], dialogValue, nil
		}
		for _, entry := range entries {
			if value == entry {
				return entry, dialogValue, nil
			}
		}
		session.write("Ungültige Auswahl. Geben Sie Hilfe für die verfügbaren Aktionen ein.\n")
		if ctx.Err() != nil {
			return "", dialogCancel, ctx.Err()
		}
	}
}

func (session *interactiveSession) group(ctx context.Context, group CommandGroup) (*Command, dialogAction, int) {
	commands := session.application.Registry.CommandsInGroup(group.Name)
	session.write(fmt.Sprintf("\n%s: %s\n", group.Name, group.Description))
	for index, command := range commands {
		session.write(fmt.Sprintf("  %d. %s - %s%s\n", index+1, command.Path[1], command.Summary, session.availability(command)))
	}
	for {
		value, action, err := session.readValue(ctx, "Aktion (Nummer, Hilfe, Zurück, Beenden): ")
		if err != nil {
			return nil, dialogCancel, session.readFailure(ctx, err, false)
		}
		if action == dialogBack || action == dialogCancel {
			return nil, dialogBack, ExitOK
		}
		if action == dialogExit {
			return nil, dialogExit, ExitOK
		}
		switch normalizeAction(value) {
		case "hilfe":
			session.write(group.Description + "\n")
			continue
		}
		if index, err := strconv.Atoi(value); err == nil && index > 0 && index <= len(commands) {
			return commands[index-1], dialogValue, ExitOK
		}
		for _, command := range commands {
			if value == command.Path[1] {
				return command, dialogValue, ExitOK
			}
		}
		session.write("Ungültige Aktion.\n")
	}
}

func (session *interactiveSession) search(ctx context.Context) (*Command, dialogAction, int) {
	query, action, err := session.readValue(ctx, "Suchbegriff: ")
	if err != nil {
		return nil, dialogCancel, session.readFailure(ctx, err, false)
	}
	if action != dialogValue {
		return nil, action, ExitOK
	}
	commands := session.application.Registry.Search(query)
	if len(commands) == 0 {
		session.write("Keine passenden Commands gefunden.\n")
		return nil, dialogBack, ExitOK
	}
	session.write("Treffer:\n")
	for index, command := range commands {
		session.write(fmt.Sprintf("  %d. %s - %s%s\n", index+1, command.Name(), command.Summary, session.availability(command)))
	}
	for {
		value, action, err := session.readValue(ctx, "Command wählen (Nummer): ")
		if err != nil {
			return nil, dialogCancel, session.readFailure(ctx, err, false)
		}
		if action != dialogValue {
			return nil, action, ExitOK
		}
		index, err := strconv.Atoi(value)
		if err == nil && index > 0 && index <= len(commands) {
			return commands[index-1], dialogValue, ExitOK
		}
		session.write("Ungültige Auswahl.\n")
	}
}

func (session *interactiveSession) command(ctx context.Context, command *Command) int {
	if command.Name() == "cli" {
		session.write("Nicht ausführbar: Der geführte Modus ist bereits aktiv.\n")
		return ExitOK
	}
	if reason := session.unavailable(command); reason != "" {
		session.write("Nicht ausführbar: " + reason + "\n")
		return ExitOK
	}
	session.write(fmt.Sprintf("\n%s\n%s\n", command.Name(), command.Description))
	args, action, err := session.collect(ctx, command)
	if err != nil {
		return session.readFailure(ctx, err, false)
	}
	if action == dialogExit {
		session.exiting = true
		return ExitOK
	}
	if action != dialogValue {
		session.write("Auftrag vor Ausführung abgebrochen. Es wurde kein Transportauftrag gesendet.\n")
		return ExitOK
	}
	if command.Mutating {
		session.summary(command, args)
	}
	for {
		if commandNeedsBackendTarget(command) && !session.checked {
			if command.Name() != "system status" {
				session.write("Ziel wird vor dem ersten Backendauftrag geprüft.\n")
				if code, failure, interrupted := session.execute(ctx, mustCommand(session.application.Registry, "system", "status"), nil); code != ExitOK {
					session.result("system status", code, failure)
					if interrupted {
						session.write("Der Ausgang nach Abbruch oder Transportverlust ist unbekannt. Prüfen Sie den Status vor einem neuen Auftrag.\n")
					}
					session.write("Der ausgewählte Command wurde nicht gestartet. Lokale Commands bleiben verfügbar.\n")
					return ExitOK
				}
				session.checked = true
			}
		}
		code, failure, interrupted := session.execute(ctx, command, args)
		if code == ExitOK && command.Name() == "system status" {
			session.checked = true
		}
		session.result(command.Name(), code, failure)
		if code == ExitInterrupted && interrupted {
			session.write("Der Ausgang nach Abbruch oder Transportverlust ist unbekannt. Prüfen Sie den Status vor einem neuen Auftrag.\n")
			return ExitOK
		}
		if code == ExitOK || !command.RetrySafe || failure == nil || unknownOutcome(failure) {
			if code != ExitOK && unknownOutcome(failure) {
				session.write("Keine Wiederholung angeboten: Der Ausgang kann unbekannt sein. Nutzen Sie einen passenden Status- oder Diagnose-Command.\n")
			}
			return ExitOK
		}
		answer, action, err := session.readValue(ctx, "Sicher wiederholbaren Auftrag erneut ausführen? [j/N]: ")
		if err != nil {
			return session.readFailure(ctx, err, false)
		}
		if action == dialogExit {
			session.exiting = true
			return ExitOK
		}
		if action != dialogValue || !isYes(answer) {
			return ExitOK
		}
		session.write("Bestätigungen und Geheimnisse werden für die Wiederholung erneut erfasst.\n")
	}
}

func commandNeedsBackendTarget(command *Command) bool {
	return command.Transport == ContainerExecTransport || (command.UsesConfig && command.Name() != "config inspect")
}

func (session *interactiveSession) collect(ctx context.Context, command *Command) ([]string, dialogAction, error) {
	values := Values{}
	for {
		for _, argument := range orderedArguments(command.Arguments) {
			value, action, err := session.field(ctx, argument.Name, argument.Summary, argument.Required, argument.Choices, "", false, values)
			if err != nil || action != dialogValue {
				return nil, action, err
			}
			if value == "" {
				delete(values, argument.Name)
			} else {
				values[argument.Name] = value
			}
		}
		for _, option := range orderedOptions(command.Options) {
			if hasIdentitySources(command) && (option.Name == "identity-stdin" || option.Name == "identity-prompt") {
				continue
			}
			value, action, err := session.option(ctx, option, values)
			if err != nil || action != dialogValue {
				return nil, action, err
			}
			if value == nil {
				delete(values, option.Name)
			} else {
				values[option.Name] = value
			}
		}
		if hasIdentitySources(command) && values.String("identity-file") == "" {
			values["identity-prompt"] = true
		}
		args := valuesToArgs(command, values)
		if _, failure := parseCommandOptions(command, args); failure == nil {
			return args, dialogValue, nil
		} else {
			session.write(fmt.Sprintf("Validierungsfehler: %s\n", failure.Message))
			answer, action, err := session.readValue(ctx, "Eingaben korrigieren? [J/n]: ")
			if err != nil || action != dialogValue {
				return nil, action, err
			}
			if normalizeAction(answer) == "n" || normalizeAction(answer) == "nein" {
				return nil, dialogCancel, nil
			}
		}
	}
}

func hasIdentitySources(command *Command) bool {
	found := map[string]bool{}
	for _, option := range command.Options {
		found[option.Name] = true
	}
	return found["identity-file"] && found["identity-stdin"] && found["identity-prompt"]
}

func (session *interactiveSession) field(ctx context.Context, name, summary string, required bool, choices []string, defaultText string, danger bool, values Values) (string, dialogAction, error) {
	current := ""
	if value, exists := values[name]; exists {
		current = fmt.Sprint(value)
	}
	for {
		extra := ""
		if len(choices) > 0 {
			extra += " [" + strings.Join(choices, "/") + "]"
		}
		if current != "" {
			extra += " [aktuell: " + current + "]"
		} else if defaultText != "" {
			extra += " [Standard: " + defaultText + "]"
		} else if !required {
			extra += " [optional]"
		}
		if danger {
			extra += " [Danger Zone: zum Freigeben exakt " + name + " eingeben]"
		}
		value, action, err := session.readValue(ctx, name+extra+": ")
		if err != nil || action != dialogValue {
			return "", action, err
		}
		if normalizeAction(value) == "hilfe" {
			session.write(summary + "\n")
			continue
		}
		if danger {
			if value == "" || normalizeAction(value) == "nein" || normalizeAction(value) == "n" {
				return "false", dialogValue, nil
			}
			if value != name {
				session.write("Die semantische Freigabe stimmt nicht.\n")
				continue
			}
			return "true", dialogValue, nil
		}
		if value == "" {
			if current != "" {
				return current, dialogValue, nil
			}
			if defaultText != "" {
				return defaultText, dialogValue, nil
			}
			if required {
				session.write("Dieses Feld ist erforderlich. " + summary + "\n")
				continue
			}
			return "", dialogValue, nil
		}
		if len(choices) > 0 && !contains(choices, value) {
			session.write("Erlaubt sind: " + strings.Join(choices, ", ") + ".\n")
			continue
		}
		return value, dialogValue, nil
	}
}

func (session *interactiveSession) option(ctx context.Context, option OptionSpec, values Values) (any, dialogAction, error) {
	if option.Kind == BooleanOption {
		value, action, err := session.field(ctx, option.Name, option.Summary, false, nil, option.DefaultText, option.DangerZone, values)
		if err != nil || action != dialogValue {
			return nil, action, err
		}
		if option.DangerZone {
			return value == "true", dialogValue, nil
		}
		if value == "" {
			return nil, dialogValue, nil
		}
		if isYes(value) || value == "true" {
			return true, dialogValue, nil
		}
		if normalizeAction(value) == "n" || normalizeAction(value) == "nein" || value == "false" {
			return false, dialogValue, nil
		}
		session.write("Bitte j/ja oder n/nein eingeben.\n")
		return session.option(ctx, option, values)
	}
	value, action, err := session.field(ctx, option.Name, option.Summary, option.Required, option.Choices, option.DefaultText, false, values)
	if err != nil || action != dialogValue || value == "" {
		return nil, action, err
	}
	if option.Kind == IntegerOption {
		parsed, err := strconv.Atoi(value)
		if err != nil || option.Positive && parsed <= 0 {
			session.write("Bitte eine gültige positive Ganzzahl eingeben.\n")
			return session.option(ctx, option, values)
		}
		return parsed, dialogValue, nil
	}
	return value, dialogValue, nil
}

func (session *interactiveSession) execute(ctx context.Context, command *Command, args []string) (int, *CLIError, bool) {
	original := session.application.Renderer
	recorder := &outcomeRenderer{Renderer: original}
	session.application.Renderer = recorder
	defer func() { session.application.Renderer = original }()
	commandContext, stop := signal.NotifyContext(ctx, os.Interrupt)
	defer stop()
	code := session.application.Execute(commandContext, command.Path, args, session.global)
	return code, recorder.failure, commandContext.Err() != nil
}

func (session *interactiveSession) summary(command *Command, args []string) {
	values, failure := parseCommandOptions(command, args)
	if failure != nil {
		return
	}
	session.write("\nZusammenfassung vor der Ausführung:\n")
	session.write(fmt.Sprintf("  Ziel: engine=%s, container=%s\n", session.config.Engine.Value, session.config.Container.Value))
	session.write("  Wirkung: " + command.Description + "\n")
	for _, argument := range command.Arguments {
		if value, ok := values[argument.Name]; ok {
			session.write(fmt.Sprintf("  %s: %v\n", argument.Name, value))
		}
	}
	for _, option := range command.Options {
		if value, ok := values[option.Name]; ok {
			session.write(fmt.Sprintf("  %s: %v\n", option.Name, value))
		}
	}
	if len(command.Secrets) > 0 {
		session.write("  Geheimnisse: werden sicher ohne Echo neu erfasst\n")
	}
}

func (session *interactiveSession) result(name string, code int, failure *CLIError) {
	if code == ExitOK {
		session.write(fmt.Sprintf("Ergebnis: %s erfolgreich (Exit Code 0).\n", name))
		return
	}
	class := "unknown"
	if failure != nil {
		class = failure.Class
	}
	state := "fehlgeschlagen"
	if class == "confirmation_declined" || class == "interrupted" {
		state = "abgebrochen"
	}
	session.write(fmt.Sprintf("Ergebnis: %s %s (%s, Exit Code %d).\n", name, state, class, code))
}

func (session *interactiveSession) changeTarget(ctx context.Context) int {
	engine, action, err := session.field(ctx, "engine", "Container engine for this session.", true, []string{"auto", "docker", "podman"}, session.config.Engine.Value, false, Values{})
	if err != nil {
		return session.readFailure(ctx, err, false)
	}
	if action != dialogValue {
		return ExitOK
	}
	container, action, err := session.field(ctx, "container", "Exact application container name for this session.", true, nil, session.config.Container.Value, false, Values{})
	if err != nil {
		return session.readFailure(ctx, err, false)
	}
	if action != dialogValue {
		return ExitOK
	}
	global := session.global
	global.Engine, global.EngineSet = engine, true
	global.Container, global.ContainerSet = container, true
	config, failure := session.application.Config.Resolve(global)
	if failure != nil {
		session.application.Renderer.Error(global, "cli", failure)
		return ExitOK
	}
	session.global, session.config, session.checked = global, config, false
	session.config.Engine.Source = "session"
	session.config.Container.Source = "session"
	session.showTarget()
	return ExitOK
}

func (session *interactiveSession) showTarget() {
	container := session.config.Container.Value
	if container == "" {
		container = "<nicht gesetzt>"
	}
	session.write(fmt.Sprintf("Sitzungsziel: engine=%s (%s), container=%s (%s)\n", session.config.Engine.Value, session.config.Engine.Source, container, session.config.Container.Source))
}

func (session *interactiveSession) availability(command *Command) string {
	if reason := session.unavailable(command); reason != "" {
		return " [nicht ausführbar: " + reason + "]"
	}
	return ""
}

func (session *interactiveSession) unavailable(command *Command) string {
	if command.Name() == "cli" {
		return "Sitzung bereits aktiv"
	}
	if command.Transport == ContainerExecTransport && session.config.Container.Value == "" {
		return "kein Container im Sitzungsziel"
	}
	return ""
}

func (session *interactiveSession) readValue(ctx context.Context, prompt string) (string, dialogAction, error) {
	value, err := session.input.ReadLine(ctx, prompt)
	if errors.Is(err, errInputInterrupted) || errors.Is(err, io.EOF) {
		return "", dialogBack, nil
	}
	if err != nil {
		return "", dialogCancel, err
	}
	switch normalizeAction(value) {
	case "zurueck":
		return "", dialogBack, nil
	case "abbrechen":
		return "", dialogCancel, nil
	case "beenden":
		return "", dialogExit, nil
	default:
		return value, dialogValue, nil
	}
}

func (session *interactiveSession) readFailure(ctx context.Context, err error, main bool) int {
	if ctx.Err() != nil || errors.Is(err, errInputInterrupted) {
		if main {
			session.write("\nSitzung durch Ctrl+C beendet.\n")
		}
		return ExitInterrupted
	}
	if errors.Is(err, io.EOF) {
		session.write("\nEingabeterminal geschlossen.\n")
		return ExitInvalidInvocation
	}
	session.write("\nInteraktive Eingabe fehlgeschlagen.\n")
	return ExitUnexpected
}

func (session *interactiveSession) write(text string) error {
	return session.renderer.Dialog(wrapDialog(text, dialogWidth()))
}

func (registry *Registry) Search(query string) []*Command {
	needle := strings.ToLower(strings.TrimSpace(query))
	if needle == "" {
		return nil
	}
	matches := make([]*Command, 0)
	for _, command := range registry.commands {
		haystack := []string{command.Name(), command.Summary, command.Description}
		haystack = append(haystack, command.SearchTerms...)
		if strings.Contains(strings.ToLower(strings.Join(haystack, "\n")), needle) {
			matches = append(matches, command)
		}
	}
	return matches
}

func orderedArguments(arguments []ArgumentSpec) []ArgumentSpec {
	result := append([]ArgumentSpec(nil), arguments...)
	sort.SliceStable(result, func(left, right int) bool { return result[left].Required && !result[right].Required })
	return result
}

func orderedOptions(options []OptionSpec) []OptionSpec {
	result := append([]OptionSpec(nil), options...)
	sort.SliceStable(result, func(left, right int) bool { return result[left].Required && !result[right].Required })
	return result
}

func valuesToArgs(command *Command, values Values) []string {
	args := make([]string, 0)
	for _, argument := range command.Arguments {
		if value, ok := values[argument.Name]; ok {
			args = append(args, fmt.Sprint(value))
		}
	}
	for _, option := range command.Options {
		value, ok := values[option.Name]
		if !ok {
			continue
		}
		if option.Kind == BooleanOption {
			if enabled, _ := value.(bool); enabled {
				args = append(args, "--"+option.Name)
			}
			continue
		}
		args = append(args, "--"+option.Name, fmt.Sprint(value))
	}
	return args
}

func mustCommand(registry *Registry, path ...string) *Command {
	command, found := registry.Find(path)
	if !found {
		panic("required registry command is missing: " + strings.Join(path, " "))
	}
	return command
}

func unknownOutcome(failure *CLIError) bool {
	if failure == nil {
		return false
	}
	return failure.Class == string(RuntimeEngineFailed) || failure.Class == "interrupted" || failure.Class == "timeout"
}

func normalizeAction(value string) string {
	replacer := strings.NewReplacer("ä", "ae", "ö", "oe", "ü", "ue", "ß", "ss")
	return replacer.Replace(strings.ToLower(strings.TrimSpace(value)))
}

func isYes(value string) bool {
	normalized := normalizeAction(value)
	return normalized == "j" || normalized == "ja" || normalized == "y" || normalized == "yes"
}

func onOff(value bool) string {
	if value {
		return "ein"
	}
	return "aus"
}

func dialogWidth() int {
	width, err := strconv.Atoi(os.Getenv("COLUMNS"))
	if err != nil || width < 20 {
		return defaultDialogWidth
	}
	return width
}

func wrapDialog(text string, width int) string {
	var output strings.Builder
	for _, line := range strings.SplitAfter(text, "\n") {
		hasNewline := strings.HasSuffix(line, "\n")
		line = strings.TrimSuffix(line, "\n")
		if utf8.RuneCountInString(line) <= width || strings.TrimSpace(line) == "" {
			output.WriteString(line)
			if hasNewline {
				output.WriteByte('\n')
			}
			continue
		}
		indent := line[:len(line)-len(strings.TrimLeft(line, " "))]
		words := strings.Fields(line)
		output.WriteString(indent)
		column := utf8.RuneCountInString(indent)
		for index, word := range words {
			wordWidth := utf8.RuneCountInString(word)
			separator := 0
			if column > 0 {
				separator = 1
			}
			if column > 0 && column+separator+wordWidth > width {
				output.WriteByte('\n')
				output.WriteString(indent)
				column = utf8.RuneCountInString(indent)
				separator = 0
			}
			if separator > 0 {
				output.WriteByte(' ')
				column++
			}
			output.WriteString(word)
			column += wordWidth
			if index == len(words)-1 && hasNewline {
				output.WriteByte('\n')
			}
		}
	}
	return output.String()
}
