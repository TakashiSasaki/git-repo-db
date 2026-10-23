# C0 author integration validation

Fresh run on `fb5d7b5a0c4b92c8a282daac154e66fa6d361e64`, tree `d2010275a90ae6b6cb728344d5708057a79110cd`. All 10 before/fixed source-case observations and the separate uninstrumented fixed CLI overflow control completed, exit 0. Fixed emitter exact closed ZIP lengths: 2,097,151 and 2,097,152 allowed; 2,097,153 and 2,323,560 refused. Refusals emitted zero stdout bytes and the uploaded-artifact stderr fallback. Compressible data with expanded bytes above 2 MiB and compressed ZIP below 2 MiB succeeded.

Every observed ZIP was already closed. The helper only traced/read the production `body`; it never patched ZIP writers or lengths. ZIP CRC, all index byte counts/digests, unique members, exact selected input bytes, binding and BEGIN/DATA/END SHA256/length/base64 were verified. All artifact inputs remained unchanged.

`workflow-audit.json` statically confirms retained failure propagation, always-run emitter and subsequent always-run `actions/upload-artifact` covering both artifact roots. **Actual hosted overflow, upload and download on this tree were not run by this subagent.** Prior hosted success is not substituted.

`verify_boundaries.py` is the retained PR147 helper adapted only at its expected HEAD assertion. Its historical-before source is a separate negative control; current fixed source hash equals the candidate blob. The parent advanced from merge9f005eb2 to fb5d7b5a before the first attempt. That original stale-HEAD preflight failed before any boundary executed and is retained separately; C0 input invariance was then verified before running. No product source, assertions, workflow or root checkout was edited.

See `SUMMARY.json`, `input-binding.json`, `boundaries/measurements.json`, exact closed ZIPs and `boundaries.log`. These are author integration results, not independent acceptance or Release qualification.
