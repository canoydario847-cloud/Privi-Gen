# Privi: 100 paid policy services

All services evaluate caller-supplied evidence. Two Guard check units per execution, funded by credits or verified paid-plan allowance; see [billing and scope](paid-suite.md).

Catalog discovery is free; policy execution through the supported runner is paid-only. No live data collection or exclusivity is implied.

## GitHub — 35 services

| # | Service ID | Inputs | Policy |
| --- | --- | --- | --- |
| 1 | `privi_branch_gate` | `reviews`, `checks_required`, `force_push` | Require two reviews. Require CI checks. Disable force pushes. |
| 2 | `privi_diff_scope` | `changed_lines`, `changed_files` | Split changes over 500 lines. Split changes over 30 files. |
| 3 | `privi_review_binding` | `head_sha`, `reviewed_sha`, `stale_dismissal` | Review the current head commit. Dismiss stale approvals. |
| 4 | `privi_ci_completion` | `required`, `passed`, `pending` | Run all required checks successfully. Wait for pending checks. |
| 5 | `privi_action_pins` | `refs` | Pin every external action to a full commit SHA. |
| 6 | `privi_workflow_permissions` | `default_permission`, `write_scopes`, `approved_scopes` | Set default permissions to read. Remove unapproved write scopes. |
| 7 | `privi_fork_secret_gate` | `fork`, `receives_secrets`, `executes_head` | Do not expose paid keys to fork PRs. Do not execute untrusted head code with secrets. |
| 8 | `privi_merge_queue` | `queue_enabled`, `merge_group_checks`, `checks_on_merge_sha` | Enable the merge queue. Run CI for merge groups. Test the merge candidate SHA. |
| 9 | `privi_release_provenance` | `source_sha`, `built_sha`, `attestation_verified` | Build the intended source commit. Verify build provenance. |
| 10 | `privi_dependency_delta` | `new_direct`, `new_transitive`, `lockfile_updated` | Review large direct dependency additions. Review transitive dependency growth. Update the dependency lockfile. |
| 11 | `privi_license_allowlist` | `licenses`, `allowed` | Resolve dependencies outside your license allowlist. |
| 12 | `privi_vulnerability_gate` | `critical`, `high`, `scan_age_hours` | Resolve critical findings. Resolve high findings. Refresh the vulnerability scan. |
| 13 | `privi_coverage_delta` | `before_pct`, `after_pct`, `changed_covered_pct` | Restore lost coverage. Cover at least 80% of changed code. |
| 14 | `privi_flaky_test_budget` | `flaky_runs`, `total_runs` | Keep flaky runs at or below 2%. |
| 15 | `privi_artifact_retention` | `days`, `contains_credentials` | Limit artifact retention to 30 days. Remove credentials from artifacts. |
| 16 | `privi_cache_isolation` | `trusted_writer`, `key_includes_lock_hash`, `cross_fork_restore` | Restrict cache writes to trusted jobs. Bind cache keys to the lockfile. Separate fork caches. |
| 17 | `privi_deploy_environment` | `environment_protected`, `reviewers`, `branch_allowed` | Protect the deployment environment. Require a deployment reviewer. Deploy from an allowed branch. |
| 18 | `privi_rollback_readiness` | `previous_artifact_available`, `restore_test_age_days`, `reversible_migration` | Retain the previous release artifact. Test restoration within 30 days. Provide a migration recovery path. |
| 19 | `privi_migration_lock` | `lock_ms`, `budget_ms`, `backfill_batched` | Reduce migration lock time. Batch the backfill. |
| 20 | `privi_api_breaking_change` | `removed_endpoints`, `removed_fields`, `major_bumped` | Version removed endpoints as a major change. Version removed fields as a major change. |
| 21 | `privi_changelog_gate` | `user_visible`, `changelog_updated`, `breaking`, `migration_notes` | Document user-visible changes. Add migration instructions. |
| 22 | `privi_codeowner_coverage` | `changed_paths`, `owned_paths` | Assign owners to every changed path. |
| 23 | `privi_stale_branch` | `behind_commits`, `days_since_sync` | Rebase a branch more than 20 commits behind. Refresh a branch older than seven days. |
| 24 | `privi_commit_identity` | `signed_commits`, `total_commits`, `verified_authors` | Verify signatures on all commits. Verify contributor identities. |
| 25 | `privi_git_lfs_budget` | `new_binary_mb`, `remaining_mb`, `lfs_tracked` | Stay within remaining binary storage. Track large binaries through LFS. |
| 26 | `privi_issue_acceptance` | `criteria`, `tested_criteria`, `linked_issue` | Verify all acceptance criteria. Link the implementation issue. |
| 27 | `privi_test_quarantine` | `quarantined`, `with_owner`, `oldest_days` | Assign an owner to every quarantined test. Resolve quarantine older than 14 days. |
| 28 | `privi_runner_capacity` | `queued_jobs`, `available_slots`, `oldest_wait_seconds` | Add runner capacity or reduce fan-out. Investigate waits over five minutes. |
| 29 | `privi_ci_cost_budget` | `estimated_minutes`, `rate_per_minute`, `budget` | Reduce CI minutes or increase the approved budget. |
| 30 | `privi_release_freeze` | `freeze_active`, `deploy_requested`, `exception_approved` | Obtain an approved freeze exception. |
| 31 | `privi_webhook_delivery` | `failed`, `delivered`, `oldest_retry_seconds` | Keep failures below 1% of deliveries. Investigate overdue webhook retries. |
| 32 | `privi_pat_scope` | `scopes`, `allowed_scopes`, `expires_days` | Remove unnecessary token scopes. Use a token lifetime no longer than 90 days. |
| 33 | `privi_package_publish` | `version_exists`, `provenance`, `two_factor` | Choose an unpublished version. Attach package provenance. Protect package publishing with strong authentication. |
| 34 | `privi_monorepo_impact` | `affected_packages`, `tested_packages` | Test every affected package. |
| 35 | `privi_release_asset_integrity` | `expected_sha256`, `actual_sha256`, `signature_valid` | Rebuild or recover the mismatched asset. Verify the release asset signature. |

## AI agents — 35 services

| # | Service ID | Inputs | Policy |
| --- | --- | --- | --- |
| 36 | `privi_context_budget` | `input_tokens`, `reserved_output`, `window` | Trim input or reserve less output. |
| 37 | `privi_generation_cost` | `tokens`, `cost_per_token`, `budget` | Select a cheaper model or lower token limit. |
| 38 | `privi_tool_allowlist` | `requested_tools`, `allowed_tools` | Remove tools outside the agent allowlist. |
| 39 | `privi_agent_step_budget` | `steps_used`, `next_steps`, `step_limit` | Stop or request a larger step budget. |
| 40 | `privi_agent_loop` | `recent_action_hashes` | Break repeated tool-call loops. |
| 41 | `privi_delegation_depth` | `current_depth`, `next_depth`, `max_depth` | Stop excessive agent delegation. Correct the reported delegation depth. |
| 42 | `privi_handoff_contract` | `required_fields`, `provided_fields`, `schema_version_matches` | Supply required handoff fields. Use the agreed handoff schema. |
| 43 | `privi_retrieval_freshness` | `oldest_source_hours`, `max_age_hours`, `timestamps_present` | Refresh stale retrieval sources. Record source timestamps. |
| 44 | `privi_citation_coverage` | `supported_claims`, `claims` | Source at least 95% of externally checkable claims. |
| 45 | `privi_retrieval_diversity` | `domains` | Use at least three independent source domains. |
| 46 | `privi_embedding_compatibility` | `query_dimensions`, `index_dimensions`, `query_model`, `index_model` | Use matching embedding dimensions. Use the same embedding model for query and index. |
| 47 | `privi_chunk_overlap` | `chunk_tokens`, `overlap_tokens` | Limit overlap to 25% of chunk size. |
| 48 | `privi_prompt_version` | `expected_digest`, `actual_digest`, `reviewed` | Use the reviewed prompt version. Review the prompt change. |
| 49 | `privi_output_contract` | `required_keys`, `output_keys`, `types_valid` | Provide all required output keys. Validate output value types. |
| 50 | `privi_human_approval` | `irreversible`, `approval_valid`, `approval_matches_action` | Obtain current approval for irreversible actions. Bind approval to the exact action. |
| 51 | `privi_memory_retention` | `retention_days`, `policy_days`, `deletion_supported` | Reduce memory retention to the approved policy. Implement memory deletion. |
| 52 | `privi_tenant_isolation` | `request_tenant`, `memory_tenant`, `cross_tenant_search` | Bind memory to the requesting tenant. Disable cross-tenant retrieval. |
| 53 | `privi_pii_export` | `pii_detected`, `export_requested`, `consent_valid` | Obtain appropriate permission before exporting identified PII. |
| 54 | `privi_eval_regression` | `baseline_pct`, `candidate_pct` | Resolve quality regression before rollout. |
| 55 | `privi_hallucination_budget` | `unsupported`, `evaluated` | Reduce unsupported answers below 2% on your eval set. |
| 56 | `privi_refusal_regression` | `unsafe_accepts`, `safe_refusals`, `safe_cases` | Investigate unsafe accepted requests. Reduce incorrect refusals below 5%. |
| 57 | `privi_model_latency` | `latencies_ms`, `p95_budget_ms` | Reduce p95 model latency. |
| 58 | `privi_fallback_coverage` | `primary_available`, `fallback_available`, `fallback_tested` | Provide an available model route. Test the configured fallback. |
| 59 | `privi_model_route` | `data_region`, `model_region`, `model_approved` | Route within the approved data region. Use an approved model. |
| 60 | `privi_tool_timeout` | `tool_timeout_ms`, `remaining_ms`, `cancellable` | Fit the tool timeout inside the remaining budget. Support cancellation. |
| 61 | `privi_tool_idempotency` | `writes_state`, `retry_enabled`, `idempotency_key` | Use an idempotency key before retrying writes. |
| 62 | `privi_sandbox_policy` | `executes_code`, `sandboxed`, `network_allowlisted` | Sandbox generated code. Restrict generated-code network access. |
| 63 | `privi_agent_identity` | `identity_verified`, `expires_in_seconds`, `revoked` | Verify the agent identity. Renew expired credentials. Reject revoked agents. |
| 64 | `privi_delegated_scope` | `child_scopes`, `parent_scopes` | Do not expand authority through delegation. |
| 65 | `privi_output_size` | `bytes`, `limit_bytes`, `truncated` | Reduce or paginate the output. Do not return a partial result as complete. |
| 66 | `privi_embedding_drift` | `cosine_drift`, `max_drift`, `sample_count` | Re-evaluate the embedding index. Measure at least 100 samples. |
| 67 | `privi_retrieval_precision` | `relevant`, `retrieved` | Improve retrieval precision to at least 80%. |
| 68 | `privi_eval_leakage` | `training_ids`, `evaluation_ids` | Remove overlap between training and evaluation records. |
| 69 | `privi_agent_concurrency` | `active`, `requested`, `limit` | Queue excess agent tasks. |
| 70 | `privi_agent_completion` | `required_outputs`, `produced_outputs`, `tests_passed` | Produce every requested deliverable. Verify the completed work. |

## Call networks — 30 services

| # | Service ID | Inputs | Policy |
| --- | --- | --- | --- |
| 71 | `privi_latency_slo` | `samples_ms`, `budget_ms` | Reduce the slowest call latencies. |
| 72 | `privi_error_budget` | `errors`, `requests`, `allowed_fraction` | Stop the rollout or restore reliability. |
| 73 | `privi_retry_amplification` | `original_calls`, `retry_calls` | Keep retry traffic below 20% of original calls. |
| 74 | `privi_retry_backoff` | `backoff_ms`, `jitter` | Use strictly increasing retry delays. Add retry jitter. |
| 75 | `privi_timeout_cascade` | `downstream_ms`, `upstream_ms`, `overhead_ms` | Leave upstream time for downstream work and overhead. |
| 76 | `privi_circuit_breaker` | `enabled`, `failure_threshold`, `reset_seconds` | Enable a circuit breaker. Trip within ten consecutive failures. Avoid immediate reset loops. |
| 77 | `privi_rate_headroom` | `used`, `limit`, `next_batch` | Wait for rate-limit capacity. |
| 78 | `privi_queue_age` | `oldest_age_seconds`, `deadline_seconds`, `processing_seconds` | Scale consumers or shed expired work. |
| 79 | `privi_queue_capacity` | `queued`, `incoming`, `capacity` | Apply backpressure before capacity is exhausted. |
| 80 | `privi_idempotency_window` | `key_ttl_seconds`, `max_retry_age_seconds`, `scoped_per_customer` | Retain idempotency keys for the full retry window. Scope idempotency keys by customer. |
| 81 | `privi_duplicate_delivery` | `duplicates`, `deliveries`, `dedupe_enabled` | Investigate duplicate delivery above 1%. Enable delivery deduplication. |
| 82 | `privi_webhook_signature` | `signature_valid`, `age_seconds`, `replay_seen` | Reject invalid webhook signatures. Reject stale webhook timestamps. Reject replayed deliveries. |
| 83 | `privi_tls_expiry` | `days_remaining`, `hostname_matches`, `chain_valid` | Renew certificates before two weeks remain. Use a certificate for the target hostname. Repair the certificate chain. |
| 84 | `privi_route_failover` | `healthy_routes`, `independent_regions`, `failover_tested` | Provide two healthy routes. Use independent failure regions. Test route failover. |
| 85 | `privi_region_affinity` | `route_regions`, `allowed_regions` | Remove routes outside approved regions. |
| 86 | `privi_connection_pool` | `active`, `waiting`, `pool_size` | Increase capacity or limit concurrent requests. |
| 87 | `privi_payload_limit` | `payload_bytes`, `limit_bytes`, `decompressed_bytes`, `decompressed_limit` | Reduce request payload size. Bound decompressed payload size. |
| 88 | `privi_pagination_completeness` | `expected_items`, `received_items`, `next_cursor_present` | Fetch all pages before declaring completion. Continue until the final cursor. |
| 89 | `privi_stream_resume` | `resume_supported`, `event_ids_unique`, `checkpoint_durable` | Support stream resumption. Assign unique event IDs. Persist stream checkpoints. |
| 90 | `privi_backpressure` | `bounded_buffer`, `producer_throttled`, `drop_policy_defined` | Bound queue buffers. Throttle producers when consumers lag. Define overload handling. |
| 91 | `privi_fanout_budget` | `branches`, `calls_per_branch`, `max_calls` | Reduce fan-out to fit the call budget. |
| 92 | `privi_call_cost` | `calls`, `cost_per_call`, `budget` | Reduce calls or obtain a higher budget. |
| 93 | `privi_provider_concentration` | `provider_call_counts`, `max_share` | Diversify traffic across providers. |
| 94 | `privi_health_quorum` | `healthy`, `total`, `minimum_fraction` | Restore sufficient healthy backends. |
| 95 | `privi_dns_ttl` | `ttl_seconds`, `recovery_target_seconds` | Reduce DNS TTL to fit the recovery target. |
| 96 | `privi_trace_coverage` | `traced`, `requests`, `required_fraction` | Increase distributed tracing coverage. |
| 97 | `privi_schema_negotiation` | `client_versions`, `server_versions` | Provide at least one common protocol version. |
| 98 | `privi_dead_letter` | `dead_letters`, `with_owner`, `oldest_age_hours` | Assign every dead letter to an owner. Investigate dead letters within 24 hours. |
| 99 | `privi_clock_skew` | `skew_ms`, `tolerance_ms`, `ntp_healthy` | Restore clock synchronization. Repair time synchronization health. |
| 100 | `privi_graceful_shutdown` | `drain_seconds`, `max_inflight_seconds`, `readiness_removed` | Allow in-flight calls to finish. Remove readiness before draining. |
