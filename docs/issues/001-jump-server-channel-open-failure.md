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

## Jump-server diagnostics

If `AllowTcpForwarding yes` is already configured but `ChannelOpenError: open failed` still happens, collect logs from the jump server itself. A successful jump-server login followed by an `open failed` usually means the SSH server accepted authentication but refused or could not complete the `direct-tcpip` channel to the target.

Useful checks on the jump server:

```bash
# Confirm the target is reachable from the jump server.
nc -vz <target_ip> <target_port>
timeout 5 bash -c '</dev/tcp/<target_ip>/<target_port>' && echo ok || echo failed

# Confirm the target SSH daemon is reachable and can complete a direct login
# from the jump server network namespace.
ssh -vvv -p <target_port> <target_user>@<target_ip>

# Debian/Ubuntu sshd logs.
sudo journalctl -u ssh -u sshd --since "30 minutes ago"
sudo tail -n 200 /var/log/auth.log

# RHEL/CentOS/openEuler sshd logs.
sudo journalctl -u sshd --since "30 minutes ago"
sudo tail -n 200 /var/log/secure

# Check the effective sshd config after Include/Match rules.
sudo sshd -T | egrep 'allowtcpforwarding|permitopen|disableforwarding|maxsessions'
sudo sshd -T -C user=<jump_user>,host=<client_host>,addr=<client_ip> | egrep 'allowtcpforwarding|permitopen|disableforwarding|maxsessions'
```

If the effective config shows `allowtcpforwarding yes`, `disableforwarding no`, and `permitopen any`, then the SSH forwarding policy is probably not the blocking point. In that case, focus on jump-to-target reachability and target-side controls: wrong target IP from the jump server's network, target sshd down, target firewall/security group, route/ACL issues, or a middlebox resetting/refusing the TCP connection.

When the problem is intermittent or unclear, capture traffic on the jump server while reproducing:

```bash
sudo tcpdump -nn -i any host <target_ip> and port <target_port>
```

The expected successful pattern is a TCP SYN from the jump server to the target followed by SYN/ACK. SYN retries, RST, or no packets point to network/firewall/routing rather than CyclopsCmd's SSH client logic.

Also confirm that the sshd service was reloaded after changing config:

```bash
sudo systemctl reload sshd || sudo systemctl reload ssh
```

For deeper diagnostics, temporarily set `LogLevel VERBOSE` or `LogLevel DEBUG3` in the jump server's sshd config, reload sshd, reproduce once, collect the logs above, and then restore the original log level. Remember to check `Match User`, `Match Group`, `Match Address`, `Include` files, and bastion/PAM/security products, as they can override a global `AllowTcpForwarding yes`.

## Fix plan

- Avoid opening command sessions just to validate cached jump-server connections.
- Track jump-server connection identity and include it in target connection cache keys.
- Serialize target tunnel creation per jump connection to reduce channel-open races on constrained bastions.
- Report disabled/restricted TCP forwarding as an actionable tunnel-open failure rather than a generic SSH channel error.
- Document jump-server-side logs and effective sshd config checks for cases where global `AllowTcpForwarding yes` is not enough.
- Add unit coverage for cache-key isolation and lightweight jump-cache reuse.
