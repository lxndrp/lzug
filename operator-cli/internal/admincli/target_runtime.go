package admincli

// TargetRuntimeFactory connects to an explicitly supplied endpoint. The caller
// owns that endpoint and any tunnel behind it; lzug never creates either one.
type TargetRuntimeFactory struct {
	Legacy RuntimeFactory
}

func NewTargetRuntimeFactory() *TargetRuntimeFactory {
	return &TargetRuntimeFactory{Legacy: NewContainerRuntimeFactory()}
}

func (factory *TargetRuntimeFactory) Transport(config EffectiveConfig) Transport {
	if config.target("endpoint") == "" {
		return factory.Legacy.Transport(config)
	}
	return &SocketTransport{Endpoint: config.target("endpoint")}
}

func (factory *TargetRuntimeFactory) ArtifactTransport(config EffectiveConfig) ArtifactTransport {
	if config.target("endpoint") == "" {
		return factory.Legacy.(ArtifactRuntimeFactory).ArtifactTransport(config)
	}
	return &SocketTransport{Endpoint: config.target("endpoint")}
}

func (factory *TargetRuntimeFactory) ReleaseInspector(config EffectiveConfig) ReleaseInspector {
	if config.target("endpoint") == "" {
		return factory.Legacy.ReleaseInspector(config)
	}
	return unsupportedSocketRelease{} // Engine-free release approval belongs to #272.
}
