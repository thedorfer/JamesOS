# Terminal security (planned)

Last reviewed: 2026-07-18

No production workspace terminal or privilege broker is currently claimed.

The planned terminal is a PTY running as user `james` in the workspace pane. Jade may propose commands, but modifying commands require an exact visible approval and complete audit record. There will be no default or persistent root shell and no stored sudo password.

Any future privileged operation requires a separately reviewed restricted broker or Polkit design. Approval must be scoped to one exact operation, resource, and time, with deny-by-default behavior and tests proving commands cannot broaden their authority.
