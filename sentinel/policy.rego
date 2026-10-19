package sentinel.security.guardrails

# ==============================================================================
# Project Sentinel — Enterprise Open Policy Agent (OPA) Rego Guardrails
# Top 0.1% Cloud Infrastructure & Deployment Security Policy
# Enforces Zero-Trust, Minimal Blast Radius, and Hardened Container Environments.
# ==============================================================================

default allow = false
default compliance_score = 0

# Rule 1: Allow only if all strict security guardrails pass without violations
allow {
    count(violations) == 0
}

# Collect all policy violations
violations[msg] {
    container := input.containers[_]
    not container.resources.limits.cpu
    msg := sprintf("Container '%v' is missing authoritative CPU resource limits", [container.name])
}

violations[msg] {
    container := input.containers[_]
    not container.resources.limits.memory
    msg := sprintf("Container '%v' is missing authoritative Memory resource limits", [container.name])
}

violations[msg] {
    container := input.containers[_]
    container.security_context.run_as_root == true
    msg := sprintf("Container '%v' violates Least Privilege: Root execution is strictly prohibited", [container.name])
}

violations[msg] {
    container := input.containers[_]
    container.security_context.read_only_root_filesystem != true
    msg := sprintf("Container '%v' must have a read-only root filesystem to prevent runtime payload persistence", [container.name])
}

violations[msg] {
    input.deployment.strategy == "direct_recreate"
    msg := "Deployment strategy 'direct_recreate' violates High Availability SLO: Zero-downtime required"
}

violations[msg] {
    input.deployment.canary_initial_traffic > 10
    msg := sprintf("Initial canary traffic split (%v%%) exceeds maximum blast radius tolerance of 10%%", [input.deployment.canary_initial_traffic])
}

violations[msg] {
    input.network.cloud_armor_waf_enabled != true
    msg := "Ingress service is missing Google Cloud Armor Layer 7 WAF policy binding"
}

violations[msg] {
    input.supply_chain.slsa_level != "SLSA_BUILD_LEVEL_3"
    msg := sprintf("Supply chain attestation '%v' does not meet required SLSA_BUILD_LEVEL_3 standard", [input.supply_chain.slsa_level])
}

# Calculate compliance score (0 - 100)
compliance_score = score {
    total_checks := 8
    violation_count := count(violations)
    passed_checks := max([0, total_checks - violation_count])
    score := round((passed_checks / total_checks) * 100)
}
