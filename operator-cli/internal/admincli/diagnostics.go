package admincli

import (
	"encoding/json"
	"fmt"
)

// Socket diagnostics are immutable runtime snapshots. Do not fall back to
// storage diagnostics or forward arbitrary job, migration or configuration data.
type runtimeDiagnostic struct {
	State      string `json:"state"`
	Ready      *bool  `json:"ready"`
	Active     *int   `json:"active"`
	NextAction struct {
		Code string `json:"code"`
	} `json:"next_action"`
}

type socketDiagnostic struct {
	State                   string `json:"state"`
	Protocol                int    `json:"protocol"`
	Schema                  int    `json:"schema"`
	ActiveConnections       *int   `json:"active_connections"`
	MaxConnections          int    `json:"max_connections"`
	ArtifactCleanupRequired *bool  `json:"artifact_cleanup_required"`
}

func socketDiagnosticOutput(raw json.RawMessage) (map[string]any, string, error) {
	var snapshot struct {
		Runtime *runtimeDiagnostic `json:"runtime"`
		Socket  *socketDiagnostic  `json:"socket"`
	}
	if err := json.Unmarshal(raw, &snapshot); err != nil || snapshot.Runtime == nil || snapshot.Socket == nil {
		return nil, "", fmt.Errorf("invalid socket diagnostic snapshot")
	}
	runtime, socket := snapshot.Runtime, snapshot.Socket
	states := map[string]bool{"stopped": true, "initializing": true, "ready": true, "maintenance": true,
		"migration_required": true, "migrating": true, "error": true, "stopping": true}
	actions := map[string]string{"none": "none", "wait": "wait", "inspect_upgrade": "lzug-admin upgrade status",
		"inspect_recovery": "lzug-admin system doctor"}
	next, actionOK := actions[runtime.NextAction.Code]
	if !states[runtime.State] || !actionOK || runtime.Ready == nil || runtime.Active == nil || *runtime.Active < 0 ||
		(*runtime.Ready && runtime.State != "ready") {
		return nil, "", fmt.Errorf("invalid runtime diagnostic state")
	}
	if (socket.State != "listening" && socket.State != "stopped" && socket.State != "failed") ||
		socket.Protocol != socketProtocol || socket.Schema != socketSchema || socket.ActiveConnections == nil ||
		*socket.ActiveConnections < 0 || socket.MaxConnections <= 0 || socket.ArtifactCleanupRequired == nil {
		return nil, "", fmt.Errorf("invalid socket diagnostic state")
	}
	return map[string]any{"runtime": runtime, "socket": socket},
		fmt.Sprintf("runtime: %s (ready=%t, active=%d)\nsocket: %s (connections=%d)\nnext: %s\n",
			runtime.State, *runtime.Ready, *runtime.Active, socket.State, *socket.ActiveConnections, next), nil
}
