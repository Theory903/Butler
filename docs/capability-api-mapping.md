# Butler Super Agent - Capability to API/Feature Mapping

> **Status:** Production Implementation Guide  
> **Created:** 2026-04-20  
> **Purpose:** Map all 18 capabilities to existing Butler services, APIs, native tools, and external integrations

---

## Overview

This document provides a **complete mapping** of:
1. Each of the 18 Butler capabilities
2. Existing Butler services that provide it
3. Native tools already available in the codebase
4. External APIs to integrate
5. Implementation status and production readiness

---

## Capability Matrix Summary

| # | Capability | Butler Service | Native Tools | External APIs | Status |
|---|------------|---------------|--------------|---------------|--------|
| 1 | Core Chat + Planning | `orchestrator` | hermes_agent, subagent_runtime | OpenAI, Anthropic | ✅ Ready |
| 2 | Web Research | `search` | web_provider, deep_research | SearXNG, Brave | ✅ Ready |
| 3 | Memory + Personalization | `memory` | retrieval, digital_twin | PostgreSQL, Neo4j, Qdrant | ✅ Ready |
| 4 | Reminders + Calendar | `calendar` | - | Google Calendar, Microsoft Graph | ⚠️ Stub |
| 5 | Coding + Terminal | `tools` | executor, browser_tool | GitHub, GitLab | ⚠️ Partial |
| 6 | Weather | `search` | web_provider | OpenWeatherMap | ✅ Ready |
| 7 | Finance + Stocks | `search`, `ml` | - | Alpha Vantage | ⚠️ Add |
| 8 | STT + TTS | `audio` | stt.py, tts.py, faster-whisper | OpenAI, ElevenLabs | ✅ Ready |
| 9 | Push Notifications | `realtime` | ws_mux, stream_dispatcher | FCM, APNs | ⚠️ Partial |
| 10 | MCP Tool Federation | `tools` | mcp_bridge, skill_marketplace | MCP Servers | ✅ Ready |
| 11 | Food + Grocery | `communication` | channel_registry | Swiggy, Zomato, ONDC | ⚠️ Add |
| 12 | Ride + Mobility | `device` | adapters | Uber, Ola | ⚠️ Add |
| 13 | Call Assistant | `audio` | - | Twilio Voice | ⚠️ Add |
| 14 | Smart Home | `device` | environment, adapters | Home Assistant, Matter | ✅ Ready |
| 15 | Health + Wearables | `device` | - | Health Connect | ⚠️ Add |
| 16 | Vision + OCR | `vision` | models.py | Grounding DINO, SAM 3 | ⚠️ Stub |
| 17 | Image Generation | `ml` | media_processor | DALL-E, Stability AI | ⚠️ Add |
| 18 | Robotics | `workflow` | engine | ROS 2, Nav2, MoveIt | ⚠️ Add |

---

## Detailed Capability Mapping

---

### 1. Core Chat + Planning

**What it does:** Understand user requests, plan steps, coordinate tools, maintain context across sessions

**Butler Services:**
- `services/orchestrator/service.py` - Main orchestration
- `services/orchestrator/executor.py` - Tool execution
- `services/orchestrator/planner.py` - Planning
- `services/orchestrator/blender.py` - Multi-model blending
- `services/orchestrator/subagent_runtime.py` - Subagent execution

**Native Tools (in `integrations/hermes/tools/`):**
```
hermes/tools/delegate_tool.py      # Subagent delegation
hermes/tools/session_search_tool.py # Context retrieval
hermes/tools/web.py                # Web search
```

**External APIs:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| OpenAI | LLM reasoning | `OPENAI_API_KEY` |
| Anthropic | LLM reasoning | `ANTHROPIC_API_KEY` |
| Gemini | LLM reasoning | `GEMINI_API_KEY` |
| Groq | Fast LLM | `GROQ_API_KEY` |

**Production Status:** ✅ Ready

---

### 2. Web Research

**What it does:** Search the web, compare sources, synthesize answers with citations

**Butler Services:**
- `services/search/service.py` - Main search service
- `services/search/answering_engine.py` - Answer synthesis
- `services/search/deep_research.py` - Deep research mode
- `services/search/web_provider.py` - Web search abstraction
- `services/search/extraction.py` - Content extraction

**Native Tools:**
```
integrations/hermes/tools/web.py                    # Web search
integrations/hermes/tools/browser_tool.py           # Browser automation
integrations/hermes/tools/browser_providers/        # Multiple browser backends
  - browser_use.py
  - firecrawl.py
  - browserbase.py
  - camofox.py
```

**External APIs:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| SearXNG | Self-hosted search | `SEARXNG_URL` |
| Brave Search | Web search | `BRAVE_API_KEY` |
| Firecrawl | Scraper API | `FIRECRAWL_API_KEY` |
| BrowserBase | Browser infrastructure | `BROWSERBASE_API_KEY` |

**Production Status:** ✅ Ready (need to configure providers)

---

### 3. Memory + Personalization

**What it does:** Remember preferences, habits, relationships, context over time

**Butler Services:**
- `services/memory/service.py` - Main memory service
- `services/memory/retrieval.py` - Retrieval engine
- `services/memory/digital_twin.py` - User behavior modeling
- `services/memory/session_store.py` - Session memory
- `services/memory/episodic_engine.py` - Episode tracking
- `services/memory/evolution_engine.py` - Memory evolution

**Native Tools:**
```
services/memory/mcp_server.py           # MCP memory tools
integrations/hermes/plugins/memory/   # Memory plugins
```

**Infrastructure:**
| Store | Purpose | Config |
|-------|---------|--------|
| PostgreSQL | Structured memory | `DATABASE_URL` |
| Redis | Hot cache | `REDIS_URL` |
| Neo4j | Graph relationships | `NEO4J_URI` |
| Qdrant | Vector embeddings | `QDRANT_HOST` |

**Production Status:** ✅ Ready

---

### 4. Reminders + Calendar

**What it does:** Create reminders, manage calendar, schedule events, time-aware notifications

**Butler Services:**
- `services/calendar/service.py` - Calendar abstraction
- `services/cron/cron_service.py` - Scheduled jobs

**Native Tools:** None yet

**External APIs to Integrate:**
| API | Purpose | Priority |
|-----|---------|----------|
| Google Calendar API | Calendar sync | High |
| Google Tasks API | Reminders/todos | High |
| Microsoft Graph API | Outlook calendar | Medium |
| Cal.com API | Scheduling | Low |

**Config to Add:**
```python
# infrastructure/config.py
GOOGLE_CALENDAR_CLIENT_ID: Optional[str] = None
GOOGLE_CALENDAR_CLIENT_SECRET: Optional[str] = None
MICROSOFT_GRAPH_CLIENT_ID: Optional[str] = None
MICROSOFT_GRAPH_CLIENT_SECRET: Optional[str] = None
```

**Production Status:** ⚠️ Stub - needs API integration

---

### 5. Coding + Terminal

**What it does:** Write code, run terminal commands, use desktop apps, automate software

**Butler Services:**
- `services/tools/executor.py` - Tool execution
- `services/tools/verification.py` - Tool verification

**Native Tools:**
```
integrations/hermes/tools/browser_tool.py      # Computer use
integrations/hermes/tools/mcp_tool.py         # MCP tools
integrations/hermes/tools/delegate_tool.py     # Code execution
integrations/hermes/tools/image_generation_tool.py  # Code from images
```

**External APIs:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| GitHub API | Code, issues, PRs | `GITHUB_TOKEN` |
| GitLab API | Code, issues | `GITLAB_TOKEN` |
| CircleCI | CI/CD | `CIRCLECI_TOKEN` |

**Production Status:** ⚠️ Partial - browser automation needs enhancement

---

### 6. Weather

**What it does:** Current conditions, forecasts, weather-aware planning

**Butler Services:**
- `services/search/web_provider.py` - Uses web search for weather

**Native Tools:** Uses `web.py` tool

**External APIs:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| OpenWeatherMap | Weather data | `OPENWEATHER_API_KEY` |

**Config to Add:**
```python
OPENWEATHER_API_KEY: Optional[str] = None
```

**Production Status:** ✅ Ready via web search

---

### 7. Finance + Stocks

**What it does:** Watch markets, analyze stocks, financial modeling, news correlation

**Butler Services:**
- `services/search/service.py` - Research capability
- `services/ml/features.py` - Feature extraction
- `services/ml/ranking.py` - Signal ranking

**Native Tools:** None yet

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Alpha Vantage | Stocks, forex, crypto | `ALPHA_VANTAGE_API_KEY` |
| NewsAPI | Financial news | `NEWS_API_KEY` |
| Finnhub | Real-time quotes | `FINNHUB_API_KEY` |

**Config to Add:**
```python
ALPHA_VANTAGE_API_KEY: Optional[str] = None
NEWS_API_KEY: Optional[str] = None
FINNHUB_API_KEY: Optional[str] = None
```

**Production Status:** ⚠️ Add - integrate Alpha Vantage MCP server

---

### 8. Speech (STT + TTS)

**What it does:** Listen, transcribe, identify speakers, speak back, clone voices

**Butler Services:**
- `services/audio/service.py` - Main audio service
- `services/audio/stt.py` - Speech-to-text
- `services/audio/tts.py` - Text-to-speech
- `services/audio/diarization.py` - Speaker diarization
- `services/audio/ambient_runtime.py` - Ambient audio

**Native Tools:**
```
services/audio/stt.py            # faster-whisper integration
services/audio/tts.py           # Coqui TTS, XTTS
services/audio/diarization.py    # pyannote.audio
```

**Infrastructure:**
| Service | Model | Config |
|---------|-------|--------|
| STT Primary | Parakeet TDT 0.6B | `STT_PRIMARY_MODEL` |
| STT Secondary | Whisper Large V3 | `STT_SECONDARY_MODEL` |
| STT Local | whisper.cpp | `STT_LOCAL_MODEL` |
| Diarization | pyannote/heartbeat | `DIARIZATION_MODEL` |
| TTS | XTTS-v2 | `TTS_DEFAULT_VOICE` |

**External APIs:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| OpenAI Whisper API | Cloud STT | `OPENAI_API_KEY` |
| ElevenLabs | Premium TTS | `ELEVENLABS_API_KEY` |

**Production Status:** ✅ Ready (local-first, cloud fallback)

---

### 9. Push Notifications

**What it does:** Notify right device at right moment, cross-device continuity

**Butler Services:**
- `services/realtime/listener.py` - Real-time listener
- `services/realtime/ws_mux.py` - WebSocket multiplexing
- `services/realtime/stream_dispatcher.py` - Event dispatch

**Native Tools:** WebSocket connections

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Firebase Cloud Messaging | Android push | `FCM_SERVER_KEY` |
| Apple APNs | iOS push | `APNS_KEY_PATH` |

**Config to Add:**
```python
FCM_SERVER_KEY: Optional[str] = None
APNS_KEY_PATH: Optional[str] = None
APNS_TEAM_ID: Optional[str] = None
```

**Production Status:** ⚠️ Partial - WebSocket ready, push needs FCM/APNs

---

### 10. MCP Tool Federation

**What it does:** Talk to external agents, tool servers, data systems via MCP

**Butler Services:**
- `services/tools/mcp_bridge.py` - MCP client
- `services/tools/skill_marketplace.py` - Skill marketplace
- `services/tools/skills_hub.py` - Skills hub
- `services/tools/executor.py` - Tool execution

**Native Tools:**
```
integrations/hermes/tools/mcp_tool.py        # MCP client tool
integrations/hermes/tools/mcp_oauth.py       # OAuth for MCP
integrations/hermes/optional-skills/mcp/    # MCP templates
```

**Infrastructure:**
- MCP manifest at `BUTLER_DATA_DIR/mcp/manifest.json`
- MCP server in `services/tools/mcp_bridge.py`

**Production Status:** ✅ Ready

---

### 11. Food + Grocery

**What it does:** Order food, groceries, track deliveries, compare prices

**Butler Services:**
- `services/communication/channel_registry.py` - Multi-channel
- `services/communication/delivery.py` - Delivery tracking
- `services/communication/policy.py` - Policy layer

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Swiggy API | Food delivery (India) | `SWIGGY_API_KEY` |
| Zomato API | Food delivery | `ZOMATO_API_KEY` |
| ONDC | Open network | `ONDC_CLIENT_ID` |
| Instacart | Grocery (US) | `INSTACART_API_KEY` |

**Config to Add:**
```python
SWIGGY_API_KEY: Optional[str] = None
ZOMATO_API_KEY: Optional[str] = None
ONDC_CLIENT_ID: Optional[str] = None
ONDC_CLIENT_SECRET: Optional[str] = None
INSTACART_API_KEY: Optional[str] = None
```

**Production Strategy:**
1. Official APIs where available (Swiggy, ONDC)
2. Browser automation fallback for apps without APIs

**Production Status:** ⚠️ Add - create adapters in `services/communication/adapters/`

---

### 12. Ride + Mobility

**What it does:** Book rides, compare ETAs, route-aware planning

**Butler Services:**
- `services/device/adapters.py` - Device adapters
- `services/device/environment.py` - Environment awareness

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Uber Rides API | Ride booking | `UBER_CLIENT_ID` |
| Uber Riders API | Fare estimates | `UBER_CLIENT_SECRET` |
| Ola Maps | Maps, geocoding | `OLA_API_KEY` |
| Google Maps | Directions | `GOOGLE_MAPS_API_KEY` |

**Config to Add:**
```python
UBER_CLIENT_ID: Optional[str] = None
UBER_CLIENT_SECRET: Optional[str] = None
OLA_API_KEY: Optional[str] = None
GOOGLE_MAPS_API_KEY: Optional[str] = None
```

**Production Status:** ⚠️ Add - extend `services/device/adapters.py`

---

### 13. Call Assistant

**What it does:** Answer/screen calls, summarize, route spam, handle voice

**Butler Services:**
- `services/audio/service.py` - Already has audio capabilities

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Twilio Voice | Make/receive calls | `TWILIO_ACCOUNT_SID` |
| Twilio Programmable Voice | IVR, screening | `TWILIO_AUTH_TOKEN` |

**Config to Add:**
```python
TWILIO_ACCOUNT_SID: Optional[str] = None
TWILIO_AUTH_TOKEN: Optional[str] = None
TWILIO_PHONE_NUMBER: Optional[str] = None
```

**Integration Points:**
- `services/audio/service.py` - Add voice call handling
- `integrations/hermes/optional-skills/productivity/telephony/` - Existing telephony scripts

**Production Status:** ⚠️ Add - wire Twilio to audio service

---

### 14. Smart Home

**What it does:** Control devices, room presence, scene automation, Matter devices

**Butler Services:**
- `services/device/service.py` - Main device service
- `services/device/environment.py` - Environment awareness
- `services/device/adapters.py` - Device adapters
- `services/device/capabilities.py` - Capability definitions

**Native Tools:**
```
services/device/environment.py    # Home Assistant integration
services/device/adapters.py      # Matter, Bluetooth adapters
```

**Infrastructure:**
| Service | Purpose | Config |
|---------|---------|--------|
| Home Assistant | Hub | `HOME_ASSISTANT_URL` |
| Matter | Protocol | Built-in |
| MQTT | Device events | `MQTT_BROKER_URL` |

**Config to Add:**
```python
HOME_ASSISTANT_URL: Optional[str] = None
HOME_ASSISTANT_TOKEN: Optional[str] = None
MQTT_BROKER_URL: Optional[str] = None
MQTT_USERNAME: Optional[str] = None
MQTT_PASSWORD: Optional[str] = None
```

**Production Status:** ✅ Ready - Home Assistant already integrated

---

### 15. Health + Wearables

**What it does:** Ingest health signals, adapt based on routines, consent-based

**Butler Services:**
- `services/device/environment.py` - Environment context
- `services/device/service.py` - Device service

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| Health Connect | Android health data | Android SDK |
| Apple HealthKit | iOS health data | iOS SDK |
| Fitbit API | Wearable data | `FITBIT_CLIENT_ID` |
| Oura API | Sleep/activity | `OURA_CLIENT_ID` |

**Config to Add:**
```python
FITBIT_CLIENT_ID: Optional[str] = None
FITBIT_CLIENT_SECRET: Optional[str] = None
OURA_CLIENT_ID: Optional[str] = None
OURA_CLIENT_SECRET: Optional[str] = None
```

**Production Strategy:**
- Android: Health Connect SDK via companion app
- iOS: HealthKit via companion app
- Wearables: REST APIs

**Production Status:** ⚠️ Add - companion app integration

---

### 16. Vision + OCR

**What it does:** Object detection, segmentation, OCR, screen understanding

**Butler Services:**
- `services/vision/service.py` - Main vision service
- `services/vision/models.py` - Model definitions

**Native Tools:**
```
services/vision/models.py              # Model interfaces
integrations/hermes/tools/vision_tools.py  # Vision tools
integrations/hermes/tools/browser_tool.py   # Screen understanding
```

**External APIs/Models to Integrate:**
| Model | Purpose | Integration |
|-------|---------|-------------|
| Grounding DINO | Object detection | Local GPU |
| SAM 3 | Segmentation | Local GPU |
| EasyOCR | Fast OCR | Local |
| Tesseract | OCR fallback | Local |

**Config to Add:**
```python
GROUNDING_DINO_MODEL_PATH: Optional[str] = None
SAM_MODEL_PATH: Optional[str] = None
VISION_GPU_ENDPOINT: str = "http://vision-gpu:8010"
```

**Production Status:** ⚠️ Stub - service exists, needs model integration

---

### 17. Image Generation

**What it does:** Create images, edit, style transfer

**Butler Services:**
- `services/ml/media_processor.py` - Media processing
- `services/vision/service.py` - Vision capabilities

**Native Tools:**
```
integrations/hermes/tools/image_generation_tool.py  # Image gen
```

**External APIs to Integrate:**
| API | Purpose | Config Variable |
|-----|---------|-----------------|
| OpenAI DALL-E | Image generation | `OPENAI_API_KEY` |
| Stability AI | Image generation | `STABILITY_API_KEY` |
| Replicate | Run any model | `REPLICATE_API_KEY` |

**Config to Add:**
```python
STABILITY_API_KEY: Optional[str] = None
REPLICATE_API_KEY: Optional[str] = None
```

**Production Status:** ⚠️ Partial - tool exists, needs provider integration

---

### 18. Robotics

**What it does:** Control robots, navigation, manipulation, embodied AI

**Butler Services:**
- `services/workflow/engine.py` - Workflow automation
- `services/workflow/acp_server.py` - ACP protocol

**External APIs to Integrate:**
| API | Purpose | Config |
|-----|---------|--------|
| ROS 2 | Robot middleware | Native |
| Nav2 | Navigation | Native |
| MoveIt 2 | Manipulation | Native |

**Production Strategy:**
1. ACP (Agent Communication Protocol) for Butler↔ROS bridge
2. `services/workflow/acp_server.py` already exists
3. Create ROS2 adapter in `services/robotics/`

**Config to Add:**
```python
ROS_BRIDGE_URL: str = "http://ros-bridge:9090"
NAV2_HOST: str = "localhost"
MOVEIT_HOST: str = "localhost"
```

**Production Status:** ⚠️ Add - Phase 6 (requires hardware)

---

## Native Tools Reference

### Hermes Tools (in `integrations/hermes/tools/`)

| Tool | Purpose | Butler Service |
|------|---------|---------------|
| `web.py` | Web search | search |
| `browser_tool.py` | Computer use | tools |
| `delegate_tool.py` | Subagent | orchestrator |
| `mcp_tool.py` | MCP tools | tools |
| `vision_tools.py` | Image understanding | vision |
| `image_generation_tool.py` | Create images | ml |
| `tts_tool.py` | Text to speech | audio |
| `send_message_tool.py` | Send messages | communication |
| `session_search_tool.py` | Memory search | memory |

### Browser Providers

| Provider | File | Purpose |
|----------|------|---------|
| BrowserUse | `browser_providers/browser_use.py` | AI browser automation |
| Firecrawl | `browser_providers/firecrawl.py` | Web scraping |
| BrowserBase | `browser_providers/browserbase.py` | Browser infrastructure |
| Camofox | `browser_providers/camofox.py` | Stealth browser |

---

## Environment Variables Summary

### Already Configured

```bash
# Core
OPENAI_API_KEY
ANTHROPIC_API_KEY
GEMINI_API_KEY
GROQ_API_KEY

# Database
DATABASE_URL
REDIS_URL
NEO4J_URI
NEO4J_USER
NEO4J_PASSWORD
QDRANT_HOST
QDRANT_PORT

# Audio
STT_PRIMARY_MODEL
DIARIZATION_MODEL
TTS_DEFAULT_VOICE
HUGGINGFACE_TOKEN

# Auth
JWT_PRIVATE_KEY_PATH
JWT_PUBLIC_KEY_PATH
WEBAUTHN_RP_ID
```

### Need to Add

```bash
# Calendar
GOOGLE_CALENDAR_CLIENT_ID
GOOGLE_CALENDAR_CLIENT_SECRET
MICROSOFT_GRAPH_CLIENT_ID

# Finance
ALPHA_VANTAGE_API_KEY
NEWS_API_KEY
FINNHUB_API_KEY

# Push
FCM_SERVER_KEY
APNS_KEY_PATH

# Commerce
SWIGGY_API_KEY
ZOMATO_API_KEY
ONDC_CLIENT_ID
INSTACART_API_KEY

# Mobility
UBER_CLIENT_ID
UBER_CLIENT_SECRET
OLA_API_KEY
GOOGLE_MAPS_API_KEY

# Telephony
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN

# Smart Home
HOME_ASSISTANT_URL
HOME_ASSISTANT_TOKEN
MQTT_BROKER_URL

# Wearables
FITBIT_CLIENT_ID
OURA_CLIENT_ID

# Media
STABILITY_API_KEY
REPLICATE_API_KEY

# Vision
VISION_GPU_ENDPOINT
GROUNDING_DINO_MODEL_PATH
SAM_MODEL_PATH

# Weather
OPENWEATHER_API_KEY
```

---

## Implementation Priority

### Phase 1: Core (Week 1-2)
1. ✅ Already working: Chat, Search, Memory, Audio, Device
2. Add: Calendar integration (Google)
3. Add: Computer-use browser tool enhancement
4. Add: Alpha Vantage finance data

### Phase 2: Communication (Week 3-4)
5. Add: Twilio voice calling
6. Add: Push notifications (FCM/APNs)
7. Add: WhatsApp Business

### Phase 3: Commerce (Week 5-6)
8. Add: Swiggy/Zomato food ordering
9. Add: Uber ride booking
10. Add: ONDC adapter

### Phase 4: Smart Home + Health (Week 7-8)
11. Enhance: Home Assistant
12. Add: Health Connect
13. Add: Wearable APIs

### Phase 5: Advanced AI (Week 9-12)
14. Add: Vision models (Grounding DINO, SAM)
15. Add: Image generation
16. Add: Robotics ROS2 bridge

---

*Generated: 2026-04-20*