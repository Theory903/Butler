# Butler Infrastructure Architecture Specification

**Version:** 1.0  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## Executive Summary

This specification defines Butler's infrastructure architecture using proven systems from Kubernetes, NGINX, Redis, Kafka, Cassandra, and Netflix-style recommendation systems. Butler is designed as a cloud-first AI OS with local companion runtimes.

### Architecture Vision

> Butler is a programmable distributed operating system for people, places, and machines - combining cloud intelligence with local execution across all platforms.

### Core Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Edge | NGINX | Reverse proxy, caching, rate limiting |
| Orchestration | Kubernetes | Service deployment, scaling, isolation |
| Hot State | Redis | Sessions, streams, semantic cache |
| Event Bus | Kafka | Durable events, replay, workflow |
| Global Storage | Cassandra | Write-heavy, multi-region history |
| Personalization | Netflix-style | Multi-stage ranking |

---

## Part 1: Infrastructure Match Matrix

### 1.1 Butler Concern → Technology Mapping

| Butler Concern | Best-Fit Tech | Role in Butler | Fit Score |
|---------------|---------------|---------------|-----------|
| Edge ingress | NGINX | Reverse proxy, TLS, caching, rate limits | 10/10 |
| Service orchestration | Kubernetes | Deployment, scaling, service discovery | 10/10 |
| Realtime state | Redis | Sessions, locks, hot memory, streams | 10/10 |
| Workflow/events | Kafka | Durable events, replay, stream processing | 10/10 |
| Global write-heavy | Cassandra | Device telemetry, audit logs, timelines | 9/10 |
| Personalization | Netflix-style | Ranking, recommendations, proactive actions | 9/10 |
| Search | Elasticsearch | Full-text, log analysis | 8/10 |
| Vector similarity | pgvector | Memory embeddings | 9/10 |
| SQL transactions | PostgreSQL | Workflow truth, user data | 10/10 |

### 1.2 Technology Fit Scores

| Technology | Fit Score | Operational Risk | Cost | Use Now |
|-----------|-----------|------------------|------|---------|
| Kubernetes | 10/10 | Medium | High | ✅ |
| NGINX | 10/10 | Low | Low | ✅ |
| Redis | 10/10 | Low | Medium | ✅ |
| Kafka | 10/10 | Medium | High | ✅ |
| Cassandra | 9/10 | Medium | High | ✅ |
| PostgreSQL | 10/10 | Low | Low | ✅ |
| Elasticsearch | 8/10 | Medium | Medium | ✅ |
| pgvector | 9/10 | Low | Low | ✅ |
| etcd | 9/10 | Low | Low | ✅ |
| Prometheus | 10/10 | Low | Low | ✅ |
| Grafana | 10/10 | Low | Low | ✅ |
| OpenTelemetry | 10/10 | Low | Low | ✅ |
| Tailscale | 9/10 | Low | Medium | ✅ |
| Matter | 9/10 | Medium | Medium | ✅ |
| ROS 2 | 8/10 | High | Medium | ✅ |

---

## Part 2: Layer Architecture

### 2.1 Five-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUTLER FIVE-LAYER ARCHITECTURE             │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LAYER 1: EDGE GATEWAY                               │    │
│  │  NGINX: Reverse proxy, TLS, caching, rate limiting   │    │
│  │  - Public API termination                             │    │
│  │  - Request filtering                                  │    │
│  │  - DDoS protection                                   │    │
│  │  - Geographic routing                                 │    │
│  └───────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LAYER 2: CONTROL PLANE (Kubernetes)                │    │
│  │  - Service orchestration                              │    │
│  │  - Pod management                                     │    │
│  │  - Autoscaling                                       │    │
│  │  - Service discovery                                  │    │
│  │  - Network policies                                   │    │
│  └───────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LAYER 3: HOT-PATH RUNTIME (Redis)                  │    │
│  │  - Session state                                      │    │
│  │  - Conversation context                               │    │
│  │  - Rate limiting                                      │    │
│  │  - Semantic cache                                     │    │
│  │  - Realtime streams                                   │    │
│  │  - Presence/proximity                                 │    │
│  │  - Vector search                                      │    │
│  └───────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LAYER 4: EVENT BACKBONE (Kafka)                      │    │
│  │  - Workflow transitions                               │    │
│  │  - Tool execution events                              │    │
│  │  - Memory write streams                               │    │
│  │  - Device telemetry                                   │    │
│  │  - Audit logs                                         │    │
│  │  - Feature pipelines                                  │    │
│  └───────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌───────────────────────────────────────────────────────┐    │
│  │  LAYER 5: GLOBAL OPERATIONAL (Cassandra + Postgres)  │    │
│  │  - User data (Postgres)                               │    │
│  │  - Interaction history (Cassandra)                    │    │
│  │  - Device telemetry (Cassandra)                       │    │
│  │  - Feature stores (Cassandra)                         │    │
│  │  - Workflow definitions (Postgres)                     │    │
│  └───────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 3: NGINX Edge Layer

### 3.1 NGINX Responsibilities

```
┌─────────────────────────────────────────────────────────────────┐
│                    NGINX EDGE RESPONSIBILITIES                 │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Reverse Proxy                                            │
│     • All public API traffic terminates here                  │
│     • TLS termination                                         │
│     • Header manipulation                                     │
│                                                              │
│  2. Caching                                                  │
│     • Repeated read-heavy responses                          │
│     • Static assets                                          │
│     • Search results                                          │
│     • Health check responses                                  │
│                                                              │
│  3. Load Balancing                                           │
│     • Round-robin across Gateway pods                        │
│     • Least connections for WebSocket                         │
│     • Health-aware routing                                    │
│                                                              │
│  4. Rate Limiting                                            │
│     • Per-user rate limits                                    │
│     • Per-IP abuse prevention                                 │
│     • Burst handling                                          │
│                                                              │
│  5. Request Filtering                                        │
│     • Block known attack patterns                             │
│     • Header sanitization                                     │
│     • Bot detection                                           │
│                                                              │
│  6. TCP/UDP Proxying                                         │
│     • WebRTC media streams                                     │
│     • MQTT for IoT                                            │
│     • Custom protocol gateways                                 │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 NGINX Configuration

```nginx
# Butler NGINX Configuration

events {
    worker_connections 10240;
}

http {
    # Upstream services
    upstream gateway {
        least_conn;
        server gateway-1:8000;
        server gateway-2:8000;
        server gateway-3:8000;
    }
    
    upstream websocket {
        server gateway-1:8001;
        server gateway-2:8001;
    }
    
    # Rate limiting zones
    limit_req_zone $binary_remote_addr zone=general:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=api:10m rate=100r/s;
    limit_req_zone $jwt_claims.sub zone=premium:10m rate=500r/s;
    
    # Caching
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=butler:100m
                     max_size=10g inactive=60m use_temp_path=off;
    
    server {
        listen 443 ssl http2;
        server_name api.butler.ai;
        
        # TLS configuration
        ssl_certificate /etc/nginx/certs/butler.crt;
        ssl_certificate_key /etc/nginx/certs/butler.key;
        ssl_protocols TLSv1.3 TLSv1.2;
        ssl_ciphers HIGH:!aNULL:!MD5;
        
        # Rate limiting
        limit_req zone=api burst=20 nodelay;
        
        # Caching for GET requests
        proxy_cache butler;
        proxy_cache_valid 200 60s;
        proxy_cache_key "$scheme$request_method$host$request_uri";
        
        # Gateway routing
        location / {
            proxy_pass http://gateway;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
        
        # WebSocket support
        location /ws {
            proxy_pass http://websocket;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_read_timeout 86400;
        }
    }
}
```

---

## Part 4: Kubernetes Control Plane

### 4.1 Kubernetes Services

| Service | Type | Replicas | Purpose |
|---------|------|----------|---------|
| gateway | Deployment | 3+ | API entry point |
| orchestrator | Deployment | 2+ | Workflow execution |
| memory | Deployment | 2+ | Memory/graph service |
| ml-runtime | Deployment | GPU | LLM inference |
| vision-runtime | Deployment | GPU | Vision inference |
| audio-runtime | Deployment | GPU | Audio processing |
| device-service | Deployment | 2+ | Device control |
| home-service | Deployment | 2+ | Smart home |
| search-service | Deployment | 2+ | Search/retrieval |
| meeting-service | Deployment | 2+ | Meeting copilot |
| health-service | Deployment | 2+ | Health data |

### 4.2 GPU Node Pools

```yaml
# GPU node pool for ML workloads
apiVersion: node.k8s.io/v1
kind: RuntimeClass
handler: nvidia
---
apiVersion: v1
kind: Pod
metadata:
  name: ml-inference-pod
spec:
  containers:
  - name: ml-runtime
    image: butler/ml-runtime:v1.0
    resources:
      limits:
        nvidia.com/gpu: "1"
        memory: "16Gi"
        cpu: "8"
      requests:
        memory: "8Gi"
        cpu: "4"
  runtimeClassName: nvidia
```

### 4.3 Network Policies

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: butler-internal
spec:
  podSelector:
    matchLabels:
      app: butler
  policyTypes:
    - Ingress
    - Egress
  ingress:
    # Allow from NGINX ingress
    - from:
        - namespaceSelector:
            matchLabels:
              name: ingress-nginx
      ports:
        - protocol: TCP
          port: 8000
    # Allow from same namespace
    - from:
        - podSelector: {}
  egress:
    # Allow DNS
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
    # Allow to Redis
    - to:
        - podSelector:
            matchLabels:
              app: redis
      ports:
        - protocol: TCP
          port: 6379
    # Allow to Kafka
    - to:
        - podSelector:
            matchLabels:
              app: kafka
      ports:
        - protocol: TCP
          port: 9092
```

---

## Part 5: Redis Hot-Path Runtime

### 5.1 Redis Data Structures

| Key Pattern | Type | TTL | Purpose |
|-------------|------|-----|---------|
| session:{user_id} | Hash | 24h | Active session state |
| conv:{session_id} | JSON | 30m | Conversation context |
| wake:{device_id} | String | 10s | Wake word state |
| presence:{user_id} | String | 30s | User presence |
| proximity:{device_id} | JSON | 5s | Ranging data |
| rate_limit:{user_id} | String | 1m | Rate bucket |
| idempotency:{key} | String | 24h | Idempotency cache |
| cache:search:{hash} | String | 1h | Semantic cache |
| stream:workflow | Stream | 7d | Workflow events |
| stream:device | Stream | 7d | Device events |
| stream:audit | Stream | 30d | Audit logs |

### 5.2 Redis Configuration

```conf
# Butler Redis Configuration

# Memory
maxmemory 16gb
maxmemory-policy allkeys-lru

# Persistence
save 900 1
save 300 10
save 60 10000

# Replication
replica-read-only yes
repl-diskless-sync yes

# Clustering
cluster-enabled yes
cluster-config-file nodes.conf
cluster-node-timeout 15000

# Streams
stream-node-max-entries 10000
stream-group-max-entries 5000

# Lua
lua-time-limit 5000
```

---

## Part 6: Kafka Event Backbone

### 6.1 Topics

| Topic | Partitions | Retention | Purpose |
|-------|-----------|-----------|---------|
| workflow.transitions | 32 | 7 days | State machine events |
| tool.executions | 64 | 30 days | Tool call history |
| memory.writes | 32 | 30 days | Memory mutations |
| device.telemetry | 64 | 7 days | Device signals |
| user.interactions | 32 | 90 days | Interaction timeline |
| audit.events | 16 | 1 year | Compliance logs |
| recommendation.signals | 32 | 90 days | Feedback for ranking |
| meeting.events | 16 | 30 days | Meeting transcriptions |

### 6.2 Event Schema

```json
{
  "event_id": "evt_001",
  "event_type": "workflow.transition",
  "timestamp": "2026-04-20T08:12:00Z",
  "source_service": "orchestrator",
  "payload": {
    "workflow_id": "wf_123",
    "from_state": "pending",
    "to_state": "running",
    "trigger": "user_approval"
  },
  "metadata": {
    "user_id": "usr_456",
    "correlation_id": "corr_789",
    "trace_id": "trace_abc"
  }
}
```

---

## Part 7: Cassandra Global Storage

### 7.1 Keyspaces

| Keyspace | Replication | Purpose |
|----------|-------------|---------|
| butler_users | RF=3 | User profiles, settings |
| butler_interactions | RF=3 | Full interaction history |
| butler_telemetry | RF=3 | Device telemetry |
| butler_audit | RF=5 | Audit trail (critical) |

### 7.2 Tables

```sql
-- User interactions timeline (high write)
CREATE TABLE butler_interactions.user_timeline (
    user_id uuid,
    timestamp timestamp,
    interaction_id timeuuid,
    interaction_type text,
    session_id uuid,
    device_id text,
    input text,
    output text,
    confidence float,
    PRIMARY KEY ((user_id), timestamp, interaction_id)
) WITH CLUSTERING ORDER BY (timestamp DESC)
    AND compaction = {'class': 'TimeWindowCompactionStrategy'}
    AND default_time_to_live = 7776000;  -- 90 days

-- Device telemetry (high write)
CREATE TABLE butler_telemetry.device_events (
    device_id text,
    timestamp timestamp,
    event_id timeuuid,
    event_type text,
    payload frozen<map<text, text>>,
    location text,
    battery float,
    PRIMARY KEY ((device_id), timestamp, event_id)
) WITH CLUSTERING ORDER BY (timestamp DESC)
    AND compaction = {'class': 'TimeWindowCompactionStrategy'}
    AND default_time_to_live = 604800;  -- 7 days

-- Audit log (append-only)
CREATE TABLE butler_audit.audit_log (
    partition_id int,
    audit_id timeuuid,
    timestamp timestamp,
    service text,
    action text,
    user_id uuid,
    resource text,
    outcome text,
    details frozen<map<text, text>>,
    PRIMARY KEY ((partition_id), timestamp, audit_id)
) WITH CLUSTERING ORDER BY (timestamp DESC)
    AND compaction = {'class': 'TimeWindowCompactionStrategy'}
    AND default_time_to_lime = 31536000;  -- 1 year
```

---

## Part 8: Network Control Matrix

### 8.1 Layer Responsibilities

| Layer | Butler Role | Best Primitives |
|-------|-------------|-----------------|
| Physical/Radio | Device discovery, proximity, local link | Device adapters, ranging, drivers |
| Link/LAN | LAN discovery, VLAN, smart-device reach | mDNS, DHCP, local brokers |
| Network | Route awareness, namespace isolation | Linux netns, Netfilter, eBPF |
| Transport | Multiplexed sessions, migration | QUIC, WebRTC |
| Session | Stable identity, discovery, retries | Kubernetes Services |
| Stream | Durable ordered events, fanout | Kafka, Redis Streams |
| Workflow | Deterministic orchestration | DAG engine, checkpoints |

### 8.2 Network Brain Components

```
┌─────────────────────────────────────────────────────────────────┐
│                    NETWORK BRAIN                               │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Observability                                      │    │
│  │  • Host network observer                            │    │
│  │  • LAN topology map                                 │    │
│  │  • Service discovery graph                          │    │
│  │  • Traffic classifier                               │    │
│  │  • Outage detector                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Control                                            │    │
│  │  • eBPF programs                                   │    │
│  │  • XDP fastpath hooks                              │    │
│  │  • Netfilter rule manager                           │    │
│  │  • tc policy profiles                               │    │
│  │  • Namespace isolation                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Multiplex Runtime                                  │    │
│  │  • QUIC session manager                             │    │
│  │  • WebRTC bridge                                    │    │
│  │  • Stream prioritizer                               │    │
│  │  • Congestion-aware mode selector                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Safety                                            │    │
│  │  • Immutable audit logs                            │    │
│  │  • Break-glass shutdown                             │    │
│  │  • Human override priority                          │    │
│  │  • Local-only fallback mode                         │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 9: Butler OS Specification

### 9.1 OS Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUTLER OS LAYERS                           │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  APPLICATION LAYER                                   │    │
│  │  • Butler apps, skills, workflows                    │    │
│  │  • Local automation                                  │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ORCHESTRATION LAYER                                │    │
│  │  • Supervisor daemon                                │    │
│  │  • Policy engine                                    │    │
│  │  • Workflow runtime                                  │    │
│  │  • Audit logger                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  ISOLATION LAYER                                    │    │
│  │  • Namespaces                                       │    │
│  │  • cgroups                                          │    │
│  │  • seccomp                                          │    │
│  │  • AppArmor/SELinux                                 │    │
│  │  • Sandboxed workers                                │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  KERNEL CONTROL LAYER                               │    │
│  │  • eBPF/XDP programs                                │    │
│  │  • Netfilter rules                                  │    │
│  │  • tc qdiscs                                        │    │
│  │  • Device model                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                            │                                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  BASE OS (Yocto-built Butler Linux)                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Language Stack

| Language | Use Case | Rationale |
|----------|---------|-----------|
| Rust | Kernel-adjacent daemons, packet agents | Memory safety, performance |
| C/C++ | Driver interfaces | Kernel forcing |
| Python | Orchestration, ML glue, workflows | Productivity |
| TypeScript | UI, dashboards | Web team familiarity |
| Go | Kubernetes operators | Cloud-native ecosystem |

---

## Part 10: Cross-Platform Deployment

### 10.1 Platform Capability Matrix

| Capability | Android | iOS | macOS | Windows | Linux | Web |
|-----------|---------|-----|-------|--------|-------|-----|
| Voice input | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Voice output | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Notifications | ✅ | ✅ | ✅ | ✅ | ❌ | ⚠️ |
| Camera | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| Microphone | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠️ |
| File system | ✅ | ⚠️ | ✅ | ✅ | ✅ | ⚠️ |
| Terminal | ❌ | ❌ | ✅ | ✅ | ✅ | ❌ |
| Browser control | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| Health data | ✅ (HC) | ✅ (HK) | ❌ | ❌ | ❌ | ❌ |
| BLE/UWB | ✅ | ✅ | ✅ | ⚠️ | ⚠️ | ❌ |
| Background tasks | ⚠️ | ⚠️ | ✅ | ✅ | ✅ | ❌ |
| Local automation | ✅ | ⚠️ | ✅ | ✅ | ✅ | ❌ |

**Legend**: ✅ Full | ⚠️ Limited | ❌ Not available

### 10.2 Butler Cloud Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    BUTLER CLOUD + LOCAL ARCHITECTURE           │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│                    ┌──────────────────────┐                   │
│                    │   BUTLER CLOUD      │                   │
│                    │                      │                   │
│                    │  • Identity         │                   │
│                    │  • Policy Engine    │                   │
│                    │  • Memory Graph     │                   │
│                    │  • Orchestrator     │                   │
│                    │  • Recommendations │                   │
│                    │  • LLM Routing     │                   │
│                    │  • Event History   │                   │
│                    │  • Observability   │                   │
│                    └──────────┬───────────┘                   │
│                               │                                │
│          ┌────────────────────┼────────────────────┐         │
│          │                    │                    │         │
│          ▼                    ▼                    ▼         │
│  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐   │
│  │   ANDROID    │   │     iOS       │   │    macOS     │   │
│  │    NODE      │   │    NODE       │   │    NODE      │   │
│  │               │   │               │   │               │   │
│  │ • Sensors    │   │ • Sensors     │   │ • Terminal   │   │
│  │ • BLE/UWB    │   │ • HealthKit   │   │ • Files      │   │
│  │ • HealthConn │   │ • Background  │   │ • Browser    │   │
│  │ • Camera     │   │ • Camera      │   │ • Camera     │   │
│  │ • Local auto │   │ • Local auto  │   │ • Local auto │   │
│  └───────────────┘   └───────────────┘   └───────────────┘   │
│          │                    │                    │         │
│          └────────────────────┼────────────────────┘         │
│                               │                                │
│          ┌────────────────────┼────────────────────┐         │
│          │                    │                    │         │
│          ▼                    ▼                    ▼         │
│  ┌───────────────┐   ┌───────────────┐   ┌───────────────┐   │
│  │   WINDOWS    │   │    LINUX     │   │    BROWSER   │   │
│  │    NODE      │   │    NODE      │   │    NODE      │   │
│  │               │   │               │   │               │   │
│  │ • Terminal    │   │ • Terminal    │   │ • Web API    │   │
│  │ • Browser     │   │ • Browser     │   │ • WASM       │   │
│  │ • Files       │   │ • Files       │   │ • Extension  │   │
│  │ • Camera      │   │ • Camera      │   │               │   │
│  │ • Local auto  │   │ • Local auto  │   │               │   │
│  └───────────────┘   └───────────────┘   └───────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

### 10.3 Capability Classes

| Class | Cloud-Only | Local-Only | Hybrid |
|-------|-----------|-------------|--------|
| **Intelligence** | LLM reasoning | - | Voice assistant |
| **Memory** | Memory graph | - | Context carryover |
| **Recommendations** | Ranking engine | - | Proactive actions |
| **Orchestration** | Workflow engine | - | Local automation |
| **Sensors** | - | Android/iOS sensors | Location |
| **Terminal** | - | macOS/Windows/Linux | - |
| **Files** | - | Desktop nodes | - |
| **Bluetooth** | - | Mobile + desktop | BLE proximity |
| **Health** | - | Mobile platforms | Health assist |
| **Network** | - | Linux | Device control |

---

## Part 11: Production Rules

### 11.1 Infrastructure Rules

```
RULE 1: Never let the agent directly "own the network stack"
        Butler issues intents. Kernel/network controller executes.

RULE 2: Separate observation, policy, and actuation
        Observe traffic. Decide with policy. Apply with actuators.

RULE 3: Every side effect must be reversible or bounded
        Network changes, routing, firewall rules - all bounded.

RULE 4: Build around deterministic state machines
        Agent proposes. Workflow commits. Event log records.

RULE 5: Use multiplexing intentionally
        One session: voice + control + telemetry + UI updates
```

### 11.2 Safety Rules

```
┌─────────────────────────────────────────────────────────────────┐
│                    NON-NEGOTIABLE SAFETY RULES                 │
├─────────────────────────────────────────────────────────────────┤
│                                                              │
│ 1. Deny-by-default capabilities                               │
│                                                              │
│ 2. Per-device and per-domain approval classes                │
│                                                              │
│ 3. Immutable audit logs                                       │
│                                                              │
│ 4. Break-glass shutdown                                       │
│                                                              │
│ 5. Local-only fallback mode                                   │
│                                                              │
│ 6. Human override priority                                     │
│                                                              │
│ 7. No hidden privilege escalation from subagents             │
│                                                              │
│ 8. No uncontrolled self-modification of kernel/network policy│
│                                                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 12: Data Path Matrix

### 12.1 Data Type → Storage Mapping

| Data Type | Primary Store | Secondary | Why |
|-----------|--------------|-----------|-----|
| Active session | Redis | - | Lowest latency |
| Conversation context | Redis | - | Hot path |
| Workflow history | Kafka | Postgres | Replay + truth |
| User profiles | Postgres | - | ACID transactions |
| Interaction history | Cassandra | - | High write |
| Device telemetry | Cassandra | - | Time-series |
| Audit logs | Cassandra | - | Append-heavy |
| Memory embeddings | pgvector | Redis cache | Similarity search |
| Search index | Elasticsearch | - | Full-text |
| Recommendation features | Redis | Cassandra | Online/offline |

---

## Part 13: Implementation Order

### Phase 1: Foundation (Weeks 1-4)

| Task | Technology |
|------|------------|
| Cluster setup | Kubernetes |
| Gateway deployment | NGINX + Gateway |
| Database setup | PostgreSQL + Redis |
| Event backbone | Kafka |
| Observability | Prometheus + Grafana + OTel |

### Phase 2: Core Services (Weeks 5-8)

| Task | Technology |
|------|------------|
| Orchestrator | Custom |
| Memory service | PostgreSQL + pgvector |
| ML runtime | GPU pods |
| Authentication | JWT + OAuth |

### Phase 3: Platform Nodes (Weeks 9-12)

| Task | Technology |
|------|------------|
| Android node | Tauri + Android |
| iOS node | Tauri + iOS |
| Desktop nodes | Tauri |
| Web node | Tauri + WASM |

### Phase 4: Advanced (Weeks 13-20)

| Task | Technology |
|------|------------|
| Cassandra | Multi-region |
| Network brain | eBPF/XDP |
| Butler OS | Yocto |
| Matter integration | Smart home |

---

**End of Specification**