package admincli

// TargetRuntimeFactory connects to an explicitly supplied local socket endpoint.
// It owns only the connections it opens.
type TargetRuntimeFactory struct {
}

func NewTargetRuntimeFactory() *TargetRuntimeFactory {
	return &TargetRuntimeFactory{}
}

func (factory *TargetRuntimeFactory) Transport(config EffectiveConfig) Transport {
	return socketTransportForConfig(config)
}

func (factory *TargetRuntimeFactory) ArtifactTransport(config EffectiveConfig) ArtifactTransport {
	return socketTransportForConfig(config)
}

func (factory *TargetRuntimeFactory) ReleaseInspector(_ EffectiveConfig) ReleaseInspector {
	return unsupportedSocketRelease{} // Engine-free release approval belongs to #272.
}

func socketTransportForConfig(config EffectiveConfig) *SocketTransport {
	if endpoint := config.target("endpoint"); endpoint != "" {
		return &SocketTransport{Endpoint: endpoint}
	}
	return &SocketTransport{Path: "/run/lzug-admin/admin.sock"}
}
