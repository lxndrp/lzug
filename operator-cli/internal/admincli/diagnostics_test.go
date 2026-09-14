package admincli

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
)

const liveDiagnostic = `{"runtime":{"state":"ready","ready":true,"active":0,"next_action":{"code":"none"}},"socket":{"state":"listening","protocol":1,"schema":1,"active_connections":1,"max_connections":8,"artifact_cleanup_required":false}}`

func TestSocketDiagnosticsProjectOnlyValidatedPublicFields(t *testing.T) {
	for _, action := range []string{"status", "config", "doctor"} {
		for _, asJSON := range []bool{false, true} {
			t.Run(action+map[bool]string{true: "JSON", false: "Human"}[asJSON], func(t *testing.T) {
				var result map[string]any
				if err := json.Unmarshal([]byte(liveDiagnostic), &result); err != nil {
					t.Fatal(err)
				}
				for _, value := range result {
					value.(map[string]any)["private"] = "secret-token member@example.invalid"
				}
				result["runtime"].(map[string]any)["job"] = map[string]any{"detail": "secret-token"}
				result["runtime"].(map[string]any)["next_action"].(map[string]any)["command"] = "unsafe-command"
				response, _ := json.Marshal(map[string]any{"version": 1, "ok": true, "result": result})
				app, _, _, stdout, stderr := testApplication(t, string(response), 0)
				args := []string{"system", action}
				if asJSON {
					args = append([]string{"--json"}, args...)
				}
				if code := app.Run(context.Background(), args); code != 0 {
					t.Fatalf("exit %d: %s", code, stdout.String())
				}
				for _, forbidden := range []string{"secret-token", "member@example.invalid", "unsafe-command", "private", "job"} {
					if strings.Contains(stdout.String()+stderr.String(), forbidden) {
						t.Fatalf("exposed %s", forbidden)
					}
				}
				if asJSON {
					var envelope struct {
						Result struct {
							Runtime runtimeDiagnostic
							Socket  socketDiagnostic
						}
					}
					if err := json.Unmarshal(stdout.Bytes(), &envelope); err != nil {
						t.Fatal(err)
					}
					if envelope.Result.Runtime.Ready == nil || !*envelope.Result.Runtime.Ready || envelope.Result.Socket.Protocol != 1 {
						t.Fatal("lost validated snapshot")
					}
				} else if !strings.Contains(stdout.String(), "runtime: ready (ready=true") {
					t.Fatal("missing human state")
				}
			})
		}
	}
}

func TestSocketDiagnosticsRejectMalformedSnapshots(t *testing.T) {
	for _, replacement := range [][2]string{
		{`"ready":true`, `"ready":"true"`}, {`"ready":true,`, ``},
		{`"state":"ready"`, `"state":"invented"`}, {`"state":"ready"`, `"state":"error"`},
		{`"active":0`, `"active":-1`}, {`"active":0`, `"active":0.5`},
		{`"code":"none"`, `"code":"secret-token"`},
		{`"protocol":1`, `"protocol":2`}, {`"schema":1`, `"schema":2`},
		{`"active_connections":1`, `"active_connections":-1`},
		{`"max_connections":8`, `"max_connections":0`},
		{`"artifact_cleanup_required":false`, `"artifact_cleanup_required":null`},
		{`"socket":{`, `"unexpected":{`},
	} {
		t.Run(replacement[1]+replacement[0], func(t *testing.T) {
			raw := strings.Replace(liveDiagnostic, replacement[0], replacement[1], 1)
			app, _, _, stdout, _ := testApplication(t, `{"version":1,"ok":true,"result":`+raw+`}`, 0)
			if code := app.Run(context.Background(), []string{"--json", "system", "status"}); code != ExitProtocolIncompatible {
				t.Fatalf("exit %d: %s", code, stdout.String())
			}
		})
	}
}

func TestSocketDiagnosticsRemainUsableWhenRuntimeIsNotReady(t *testing.T) {
	for _, state := range []string{"initializing", "maintenance", "migration_required", "migrating", "error", "stopping", "stopped"} {
		raw := strings.Replace(liveDiagnostic, `"state":"ready"`, `"state":"`+state+`"`, 1)
		raw = strings.Replace(raw, `"ready":true`, `"ready":false`, 1)
		raw = strings.Replace(raw, `"code":"none"`, `"code":"wait"`, 1)
		app, _, _, stdout, _ := testApplication(t, `{"version":1,"ok":true,"result":`+raw+`}`, 0)
		if code := app.Run(context.Background(), []string{"system", "doctor"}); code != 0 || !strings.Contains(stdout.String(), "ready=false") {
			t.Fatalf("state %s: exit %d %s", state, code, stdout.String())
		}
	}
}
