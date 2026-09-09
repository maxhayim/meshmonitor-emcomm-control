# Proposed MeshMonitor native script action buttons

EmComm Control v2.1.0 includes a local browser panel because MeshMonitor script metadata currently exposes display metadata but does not let a script declare operator-run buttons.

A possible future extension:

```yaml
# mm_meta:
#   name: EmComm Control
#   emoji: 🚨
#   language: Python
#   actions:
#     - name: Activate LIVE
#       args: --mode live --confirm-live
#       confirm: true
#       style: danger
#     - name: Exercise Mode
#       args: --mode exercise
#       confirm: true
#     - name: Status
#       args: --mode status
```

Suggested behavior:
- Render declared actions in Installed Scripts / Script Management.
- Reuse MeshMonitor's existing script runner and argument parser.
- Support confirmation dialogs for operational or destructive actions.
- Display the script's JSON `response` / `responses` result.
- Permit only metadata-declared arguments, not arbitrary shell input.
- Keep existing script path validation, timeouts, permissions, and audit behavior.

This would benefit EOC operators and any community script that exposes safe administrative actions without requiring terminal access.
