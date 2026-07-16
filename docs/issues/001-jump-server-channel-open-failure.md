# Issue 001: Jump server password authentication can fail with SSH channel open errors

## Symptom

After enabling jump server password authentication, connecting to a target host through a jump server can fail with:

```text
SSH_CHANNEL_ERROR: 跳板机连接失败：SSH 通道打开失败，请检查服务器会话限制或网络状态。
```

## Root cause

The backend reused a single cached jump-server SSH connection and validated that cache by opening an extra remote command session on the jump server. On bastions with strict session/channel limits, that extra health-check session can consume or race with the channel needed for the target connection. The target connection cache key also did not include jump-server identity or target password identity, so a cached target connection could be reused across incompatible jump-server/auth contexts.

There is a separate, expected failure mode when the bastion has `AllowTcpForwarding no` or a restrictive `PermitOpen` policy. CyclopsCmd currently uses AsyncSSH's jump-connection `tunnel` support, which opens an SSH `direct-tcpip` channel from the jump server to the target host. That SSH channel is server-side TCP forwarding, so the bastion must allow TCP forwarding to the target host and port. If forwarding is disabled, authentication to the jump server can succeed while the target connection still fails with `ChannelOpenError: open failed`.

In that environment, fix the bastion policy or use a different connectivity pattern. A future "remote command proxy" mode could avoid `direct-tcpip` by running a tool such as `nc`/`socat` on the jump host, but that would require those tools to be installed and allowed on the bastion and is not the current implementation.

## Fix plan

- Avoid opening command sessions just to validate cached jump-server connections.
- Track jump-server connection identity and include it in target connection cache keys.
- Serialize target tunnel creation per jump connection to reduce channel-open races on constrained bastions.
- Report disabled/restricted TCP forwarding as an actionable tunnel-open failure rather than a generic SSH channel error.
- Add unit coverage for cache-key isolation and lightweight jump-cache reuse.
