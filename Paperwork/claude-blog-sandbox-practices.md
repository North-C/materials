# Claude Blog Sandbox Practices: Initial Summary

Date: 2026-06-01

This note summarizes sandbox-related practices found in Claude Blog and adjacent Claude Code documentation. It focuses on the underlying scenarios, workload/risk segmentation, selection rationale, and technical capabilities of the sandbox stacks mentioned by Anthropic.

## Scope and Sources

Primary blog and documentation sources:

- Claude Managed Agents updates: self-hosted sandboxes and MCP tunnels
  https://claude.com/blog/claude-managed-agents-updates
- Claude Managed Agents product/runtime background
  https://claude.com/blog/claude-managed-agents
- Beyond permission prompts: making Claude Code more secure and autonomous
  https://claude.com/blog/beyond-permission-prompts-making-claude-code-more-secure-and-autonomous
- Claude Code sandboxing documentation
  https://code.claude.com/docs/en/sandboxing
- Claude Code sandbox environments documentation
  https://code.claude.com/docs/en/sandbox-environments
- Using LLMs to secure source code
  https://claude.com/blog/using-llms-to-secure-source-code
- Claude Code on the web
  https://claude.com/blog/claude-code-on-the-web

The common thread is that Anthropic does not describe one universal sandbox design. Instead, it segments sandbox choices by workload duration, trust boundary, data sensitivity, network requirements, and exploit risk.

## Executive Summary

Claude Blog presents sandboxes as execution boundaries for AI agents, not merely as developer convenience. The sandbox choice is shaped by three questions:

1. Where should code and tools execute: Anthropic-managed runtime, local developer machine, cloud VM, self-hosted enterprise infrastructure, or specialized provider?
2. What risk is being contained: accidental tool misuse, malicious prompt injection, credential exposure, untrusted code execution, exploit PoC execution, or enterprise data leakage?
3. What workload properties matter: fast startup, long-lived state, GPU/CPU elasticity, private network access, auditability, VPC/BYOC deployment, or reproducible security testing?

The resulting pattern is layered:

- Low to medium-risk developer automation: OS-level sandboxing such as macOS Seatbelt or Linux bubblewrap around Bash commands.
- Browser/web coding tasks: isolated cloud sandboxes with scoped credentials and network/file-system constraints.
- Production enterprise agents: self-hosted or provider-hosted sandboxes connected to Claude Managed Agents through MCP tunnels.
- Long-running engineering agents: stateful cloud development environments such as Daytona.
- High-concurrency AI workloads: elastic container/sandbox infrastructure such as Modal.
- Enterprise perimeter and regulated-data workloads: VPC/BYOC/network-boundary patterns such as Cloudflare or Vercel Sandbox.
- Vulnerability validation and exploit testing: containers for discovery, then microVMs or full VMs for PoC execution and target validation.

## Scenario-Based Analysis

### 1. Managed Production Agents

Scenario goal:

Teams want to ship production agents without building the entire agent runtime: orchestration loop, tool execution, checkpoints, scoped permissions, credentials, tracing, and observability.

Selected sandbox approach:

Anthropic-managed agent runtime with sandboxed execution, plus optional self-hosted sandboxes when the execution boundary must remain under customer control.

Judgment basis:

- If the goal is speed to production and lower platform burden, a managed runtime is attractive.
- If code, data, internal services, or security controls must remain inside the customer's environment, self-hosted sandboxes are preferred.
- The split lets Anthropic manage the agent loop while enterprise users control tool execution.

Technical support characteristics:

- Agent loop managed by Claude infrastructure.
- Sandboxed code/tool execution.
- Scoped permissions and credential handling.
- Checkpointing and traceability for production operations.
- MCP tunnels for connecting Claude-managed orchestration to customer-controlled execution environments.

### 2. Self-Hosted Enterprise Sandboxes

Scenario goal:

Enterprises want AI agents to operate on internal systems, repositories, files, and tools while keeping execution, network access, audit surfaces, and security controls inside their own perimeter.

Selected sandbox approach:

Self-hosted sandboxes on customer infrastructure, or provider-backed sandboxes such as Cloudflare, Daytona, Modal, and Vercel.

Judgment basis:

- Internal data and tools often cannot be copied into third-party managed execution environments.
- Enterprises need policy enforcement around network egress, package access, secrets, logging, and artifact retention.
- Different workloads need different sandbox properties, so Anthropic presents provider choice as workload-dependent rather than one-size-fits-all.

Technical support characteristics:

- Customer-controlled runtime boundary.
- Access to internal package registries, source repositories, file systems, and private services.
- Integration with existing security monitoring and audit tooling.
- MCP tunnel pattern for connecting remote tool execution to managed agent orchestration.
- Provider selection based on startup latency, statefulness, compute elasticity, VPC support, and credential model.

### 3. Cloudflare-Based Sandboxes

Scenario goal:

Run enterprise agents at scale while maintaining strong network control, observability, and secure access to internal services.

Selected sandbox technology:

Cloudflare stack using microVMs, lighter-weight isolates, egress control, zero-trust-style secrets injection, and internal connectivity.

Judgment basis:

- Chosen when the team needs both scale and control.
- Useful when the agent must reach internal services but outbound traffic must be mediated.
- Fits teams that already use Cloudflare as part of their perimeter, observability, and access-control layer.

Technical support characteristics:

- microVM isolation for stronger execution boundaries than ordinary in-process isolation.
- Lightweight isolates for faster or lower-overhead execution where appropriate.
- Egress proxy/control to restrict external network access.
- Secrets injection outside normal sandbox persistence paths.
- Private connectivity to internal resources.
- Operational observability and centralized network policy enforcement.

### 4. Daytona Long-Running Development Sandboxes

Scenario goal:

Support long-running engineering agents that need a full development environment, durable state, previews, debugging, and workflow continuity.

Selected sandbox technology:

Daytona-style stateful, composable cloud development environments.

Judgment basis:

- Long-running agents need more than a short-lived command sandbox.
- They need file-system durability, installed packages, SSH/debug access, preview URLs, and pause/resume.
- Stateful environments are a better fit when the agent builds, tests, monitors, and iterates across many steps.

Technical support characteristics:

- Full development environment abstraction.
- Long-lived state and file system persistence.
- SSH access for inspection and debugging.
- Preview URLs for web app or service validation.
- Pause/restore capability.
- External file-store mounting or persistent workspaces.

### 5. Modal Elastic AI Workload Sandboxes

Scenario goal:

Run many concurrent AI or compute-heavy sandboxed workloads with fast startup and elastic CPU/GPU resources.

Selected sandbox technology:

Modal cloud execution platform with custom container runtimes, fast startup, elastic compute, and high concurrency.

Judgment basis:

- Best fit when the bottleneck is compute elasticity, startup latency, and concurrent execution volume.
- Useful for AI workloads that need GPU/CPU on demand rather than a fixed long-lived workspace.
- More appropriate for ephemeral compute tasks than for state-heavy developer sessions.

Technical support characteristics:

- Custom container images/runtimes.
- Rapid sandbox startup.
- CPU/GPU provisioning on demand.
- High-concurrency execution model.
- Suitable for batch-like or parallel AI workloads.

### 6. Vercel Sandbox for Enterprise and Financial Data

Scenario goal:

Run agent workflows close to enterprise applications and proprietary data while preserving network boundaries and credential control.

Selected sandbox technology:

Vercel Sandbox with VM security, VPC peering, BYOC patterns, fast startup, and network-boundary credential injection.

Judgment basis:

- Suitable when sensitive data access must stay inside enterprise network boundaries.
- Useful when agents need to interact with production-adjacent applications but credentials should not live inside the sandbox.
- Strong fit for regulated or proprietary-data workloads where VPC/BYOC and network boundary controls matter.

Technical support characteristics:

- VM-backed security boundary.
- VPC peering and private network access.
- Bring-your-own-cloud deployment patterns.
- Millisecond-class startup goals.
- Credential injection through firewall/proxy/network boundary rather than persistent sandbox storage.

### 7. Claude Code Local Sandboxed Bash

Scenario goal:

Let Claude Code execute local development commands with fewer permission prompts while limiting the blast radius of shell commands.

Selected sandbox technology:

- macOS: Seatbelt-based sandboxing.
- Linux/WSL2: bubblewrap-based sandboxing.
- Network: external proxy/Unix socket patterns for network mediation.
- File system: allow/deny rules around command access.

Judgment basis:

- The local development use case needs low latency and direct access to the user's workspace.
- A full VM would be heavier than needed for many command executions.
- OS-level sandboxing is enough for many routine file and build commands, but it is not equivalent to a complete VM security boundary.

Technical support characteristics:

- Restricts file-system access for Bash and child processes.
- Can limit writes outside allowed directories.
- Can mediate or disable network access.
- Keeps command execution close to the user's local repo and tools.
- Better suited to trusted or semi-trusted development automation than adversarial exploit execution.

### 8. Claude Code on the Web

Scenario goal:

Run coding tasks from a browser in isolated cloud environments, especially when tasks can be parallelized or delegated without tying up a local machine.

Selected sandbox technology:

Anthropic-managed isolated cloud sandboxes or VMs for web-based Claude Code tasks.

Judgment basis:

- Removes local setup burden.
- Enables multiple coding tasks to run in parallel.
- Lets the platform scope repository access, credentials, network, and file-system behavior.
- More appropriate when the user wants convenience and isolation, but not necessarily full enterprise-owned infrastructure.

Technical support characteristics:

- Cloud-hosted isolated workspace.
- Scoped repository credentials.
- Network and file-system restrictions.
- Git access through controlled proxy patterns.
- Separation from local developer signing keys and other sensitive local credentials.

### 9. Security Scanning and Vulnerability Validation

Scenario goal:

Use LLM agents to find and validate vulnerabilities while reducing false positives and containing malicious or fragile exploit execution.

Selected sandbox technology:

- Containers for lower-risk discovery and static/dynamic analysis.
- microVMs, such as Firecracker-style isolation, or full VMs for target execution and exploit PoC validation.
- Locked-down networking and reproducible snapshots.

Judgment basis:

- Discovery agents mostly read and analyze source code, so container isolation can be acceptable.
- PoC validation executes untrusted or adversarial code, so the isolation boundary must be stronger.
- Exploit validation needs reproducibility, network restrictions, dependency pinning, and rollback.
- The threat model is stronger than ordinary developer automation.

Technical support characteristics:

- Separate discovery and validation environments.
- microVM/VM boundary for exploit execution.
- Network egress lockdown.
- No ambient credentials in the target runtime.
- Snapshot/restore for reproducibility.
- Fixed dependencies and deterministic build/test environments.
- Evidence-producing validation to distinguish exploitable issues from static false positives.

## Cross-Cutting Selection Dimensions

The blog examples imply the following selection matrix.

| Dimension | Lower-risk choice | Higher-risk or enterprise choice |
|---|---|---|
| Isolation strength | OS sandbox, container | microVM, VM, provider-managed VM, self-hosted VM |
| Startup latency | isolates, OS sandbox, fast containers | VM/microVM with warm pool or provider optimization |
| Runtime duration | ephemeral sandbox | stateful development environment |
| Data sensitivity | managed cloud sandbox | self-hosted, VPC, BYOC, private network |
| Credential exposure | environment variables or scoped tokens | boundary injection, proxy-mediated credentials, no persistent secrets |
| Network access | open or lightly restricted egress | egress proxy, allowlists, private connectivity |
| Observability | command logs and traces | enterprise audit, network logs, provider observability |
| Workload type | coding command, build, simple tool call | exploit validation, regulated-data workflow, long-running agent |

## Technical Stack Comparison

| Stack | Strengths | Tradeoffs |
|---|---|---|
| macOS Seatbelt | Native OS sandboxing, low overhead, good local fit | Platform-specific, not a VM boundary |
| bubblewrap | Lightweight Linux namespace sandboxing, good for local command containment | Requires Linux/WSL2 support, not equivalent to microVM isolation |
| Containers | Portable packaging, fast startup, easy dependency control | Weaker boundary than VM/microVM for adversarial code |
| microVMs | Stronger isolation with better density than full VMs | More operational complexity than containers |
| Full VMs | Strong isolation and mature security model | Heavier startup and resource overhead |
| Cloudflare | Strong network/perimeter controls, observability, microVM/isolate mix | Best fit when Cloudflare already fits enterprise architecture |
| Daytona | Long-running stateful development environment | Heavier than ephemeral task sandboxes |
| Modal | Fast elastic compute, GPU/CPU scaling, high concurrency | Less focused on durable developer state |
| Vercel Sandbox | VM security, VPC/BYOC, app-platform proximity, credential boundary model | Best aligned with Vercel/app workloads and enterprise network patterns |
| Anthropic-managed cloud sandbox | Convenient, integrated with Claude Code/Managed Agents | Less direct customer control than self-hosted environments |

## Preliminary Takeaways

1. Sandbox choice follows workload and risk, not vendor preference.
2. Agent execution should be separated into orchestration and tool execution boundaries.
3. Credentials should increasingly move out of the sandbox and into boundary-mediated access paths.
4. Network egress control is as important as file-system isolation for agent safety.
5. Security validation workloads require stronger isolation than normal coding workloads.
6. Stateful sandboxes are useful for engineering agents, while ephemeral sandboxes fit high-concurrency AI tasks.
7. Enterprise adoption depends on bringing the sandbox into the customer's existing perimeter, audit, and compliance model.

## Open Questions for Deeper Follow-Up

- What concrete isolation guarantees do each provider's sandboxes expose: namespace/container, microVM, VM, or hybrid?
- How are MCP tunnels authenticated, authorized, and audited across enterprise boundaries?
- What is the recommended policy model for package installation and dependency cache reuse in long-running agent sandboxes?
- How should teams score sandbox escape risk versus productivity gains for Claude Code local sandboxing?
- What operational model works best for rotating credentials when boundary injection is used?
- How should snapshots be signed, retained, and invalidated for security validation environments?
