# Requirements: headroom

> Populated during grill phase. New milestones append to the top, completed milestones remain as history.
> Format: `## M<number>-<name> [CURRENT | COMPLETED]` — one section per milestone.

---

## M1-OMP-Wrap [CURRENT]

### Functional Requirements

#### FR-1: headroom wrap omp 命令
- **Description**: 新增 `headroom wrap omp` 命令，启动 Headroom proxy、配置 OMP（Oh My Pi）使用代理、注册 MCP 服务器、修改 models.yml 路由提供商流量，最后启动 `omp` CLI。
- **Priority**: critical
- **Acceptance criteria**: 运行 `headroom wrap omp` 后，OMP 的 LLM 请求通过 Headroom proxy 路由，压缩生效

#### FR-2: headroom unwrap omp 命令
- **Description**: 新增 `headroom unwrap omp` 命令，恢复 OMP 配置到 wrap 前的状态：恢复 models.yml 备份、移除 MCP 注册、清理 `.omp/config.yml` Headroom 配置。
- **Priority**: critical
- **Acceptance criteria**: 运行 `headroom unwrap omp` 后，OMP 恢复到 wrap 前的配置状态

#### FR-3: OMP MCP 服务器注册
- **Description**: 创建 `OmpRegistrar` 将 Headroom MCP 服务器注册到 `.omp/mcp.json`，使 OMP 能调用 `headroom_retrieve` 获取原始内容。
- **Priority**: high
- **Acceptance criteria**: wrap 后 `.omp/mcp.json` 包含 headroom MCP 服务器配置；unwrap 后移除

#### FR-4: models.yml 注入和恢复
- **Description**: 备份当前 `models.yml`，修改所有提供商的 `baseUrl` 指向 Headroom proxy。unwrap 时从备份恢复。
- **Priority**: high
- **Acceptance criteria**: wrap 后 OMP 流量通过 proxy 路由；unwrap 后原始 models.yml 完全恢复

#### FR-5: OMP 配置注入
- **Description**: 将 Headroom provider 配置写入 `.omp/config.yml`，并注册 MCP 到 `.omp/mcp.json`。
- **Priority**: medium
- **Acceptance criteria**: `.omp/config.yml` 包含 Headroom 相关配置；`.omp/mcp.json` 包含 headroom MCP 服务器

### Non-Functional Requirements

#### NFR-1: 可逆性
- **Description**: wrap/unwrap 必须完全可逆，不留下 Headroom 配置残留
- **Priority**: high

#### NFR-2: 幂等性
- **Description**: 重复 wrap 是安全的（替换已有配置），重复 unwrap 是安全的（无操作）
- **Priority**: medium

### Constraints
- 使用 `headroom/providers/opencode/` 相同的模式实现
- MCP 注册使用 `headroom/mcp_registry/` 模式
- 项目级配置写入 `.omp/` 目录（非用户级 `~/.omp/agent/`）
- OMP 二进制名为 `omp`
- 代理端口默认 8787

### Success Criteria
- [ ] `headroom wrap omp` 启动 proxy + 配置 OMP + 启动 omp
- [ ] Headroom MCP 注册在 `.omp/mcp.json`
- [ ] models.yml 备份后注入 proxy 路由
- [ ] `.omp/config.yml` 包含 Headroom 配置标记
- [ ] `headroom unwrap omp` 完全恢复原始配置
