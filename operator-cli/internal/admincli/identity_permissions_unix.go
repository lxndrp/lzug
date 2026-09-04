//go:build !windows

package admincli

import (
	"fmt"
	"os"
	"syscall"
)

func securePrivateFile(path string) error {
	if err := os.Chmod(path, 0o600); err != nil {
		return err
	}
	return verifyPrivateFile(path)
}

func verifyPrivateFile(path string) error {
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || info.Mode().Perm()&0o077 != 0 {
		return fmt.Errorf("unsafe private identity file")
	}
	stat, ok := info.Sys().(*syscall.Stat_t)
	if !ok || int(stat.Uid) != os.Geteuid() {
		return fmt.Errorf("private identity is not owned by the current user")
	}
	return nil
}
