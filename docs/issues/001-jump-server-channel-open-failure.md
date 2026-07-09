# Issue 001: Jump server password authentication can fail with SSH channel open errors

## Symptom

After enabling jump server password authentication, connecting to a target host through a jump server can fail with:

```text
SSH_CHANNEL_ERROR: 跳板机连接失败：SSH 通道打开失败，请检查服务器会话限制或网络状态。
```

## Root cause

The backend reused a single cached jump-server SSH connection and validated that cache by opening an extra remote command session on the jump server. On bastions with strict session/channel limits, that extra health-check session can consume or race with the channel needed for the target connection. The target connection cache key also did not include jump-server identity or target password identity, so a cached target connection could be reused across incompatible jump-server/auth contexts.

## Fix plan

- Avoid opening command sessions just to validate cached jump-server connections.
- Track jump-server connection identity and include it in target connection cache keys.
- Serialize target tunnel creation per jump connection to reduce channel-open races on constrained bastions.
- Add unit coverage for cache-key isolation and lightweight jump-cache reuse.
