# Vision Service - Technical Specification

> **For:** Engineering  
> **Status:** Stub-Wired (v3.1) — Model proxy endpoints exist; GPU workers not yet deployed
> **Version:** 3.1  
> **Reference:** Butler stacked perception system for multi-modal grounding and spatial reasoning  
> **Last Updated:** 2026-04-19

---

## 0. Implementation Status

| Phase | Component | Status | Description |
|-------|-----------|--------|-------------|
| 1 | **VisionModelProxy** | ⚪ STUB-WIRED | Endpoint structure complete; GPU worker returns mock data |
| 2 | **OCR / Detection** | ⚪ STUB-WIRED | YOLOv8 + PaddleOCR POSTs wired; GPU node not deployed |
| 3 | **Segmentation** | ⚪ STUB-WIRED | SAM2 endpoint wired; compute-expensive, gated on explicit request |
| 4 | **Spatial Reasoning** | ⚪ STUB-WIRED | Qwen2.5-VL multimodal reasoner wired; GPU node not deployed |
| 5 | **Intake Pipeline** | 🔲 PLANNED | Multi-modal file routing (image/video/screen) — not yet implemented |
| 6 | **Video Analysis** | 🔲 PLANNED | Temporal frame processing — not yet implemented |
| 7 | **Active Perception** | 🔲 PLANNED | Proactive visual cues and change detection |

---

## 0.1 v3.1 Notes

> **Current state as of 2026-04-19**

### What exists
`VisionModelProxy` (`services/vision/models.py`) is a GPU-endpoint router with four methods:

| Method | Model | GPU Endpoint | Dev Behaviour |
|--------|-------|-------------|---------------|
| `run_yolov8()` | YOLOv8s | `POST /vision-gpu:8008/detect` | Returns mock 1-object detection |
| `run_paddleocr()` | PaddleOCR | `POST /vision-gpu:8008/ocr` | Returns mock login-form text |
| `run_sam2()` | SAM2-small | `POST /vision-gpu:8008/segment` | Returns mock 1-mask; **expensive — only on explicit call** |
| `run_qwen_vl()` | Qwen2.5-VL-7B | `POST /vision-gpu:8008/reason` | Returns mock reasoning result |

`VisionService` (`services/vision/service.py`) exposes:`detect()`, `ocr()`, `reason()`, `segment()` — thin delegation to the proxy.

### What is NOT yet implemented
- HTTP client calls to the GPU node (currently returns hardcoded dicts)
- `httpx.AsyncClient` transport + GPU worker deployment
- Intake pipeline for routing image/video/screenshot bytes
- Video temporal frame analysis
- Active/proactive perception signals

### Upgrade path
Replace each mock return block in `models.py` with an `httpx.AsyncClient.post()` call to the GPU worker, with the same three-tier fallback pattern as `AudioModelProxy`.

### Key Files
| File | Role |
|------|------|
| `services/vision/models.py` | `VisionModelProxy` — GPU endpoint stubs |
| `services/vision/service.py` | `VisionService` — thin facade |

---

## 1. Service Overview

### 1.1 Purpose
The Vision service handles **visual understanding** via a stacked perception system:
- Android screen automation
- Object/icon detection
- OCR and text extraction
- Segmentation for precision tasks
- Multimodal reasoning over fused outputs

This is NOT "upload screenshot to LLM." It's a structured pipeline where each layer does one job well, then Butler fuses outputs better than a single model.

### 1.2 Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  Butler Stacked Vision Perception                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  INPUT: Screen / Camera / Image                                          │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 1: Structured Inputs (Always First)                         │   │
│  │  • Android AccessibilityNodeInfo tree                            │   │
│  │  • MediaProjection screen capture                              │   │
│  │  • Camera metadata (EXIF, dimensions)                        │   │
│  │  • Device state                                                   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 2: Specialized Perception Models                       │   │
│  │                                                                  │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐               │   │
│  │  │  YOLOv8[ST]│  │ PaddleOCR[S]│  │ SAM 2 [ST] │               │   │
│  │  │ Detection │  │   OCR    │  │  Segment  │               │   │
│  │  └────────────┘  └────────────┘  └────────────┘               │   │
│  │                                                                  │   │
│  │  ┌────────────┐  ┌────────────┐                             │   │
│  │  │InsightFaceS│  │ Qwen2.5-VL S│                             │   │
│  │  │   Face    │  │ Reasoner │                             │   │
│  │  └────────────┘  └────────────┘                             │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ LAYER 3: Multimodal Fusion + Reasoning                            │   │
│  │  • Qwen2.5-VL-7B (default)                                      │   │
│  │  • InternVL3.5-8B (heavy fallback)                              │   │
│  │  • Verifies actions before execution                              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│     │                                                                    │
│     ▼                                                                    │
│  OUTPUT: Structured understanding + verified actions                     │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.3 Boundaries

| Service | Boundary |
|---------|-----------|
| Vision | Perception only - never executes UI actions |
| Tools | Executes actions based on Vision output |
| Memory | Stores derived insights, not raw images |
| Device | Handles Android accessibility + MediaProjection |

### 1.4 Hermes Library Integration
Vision does NOT consume Hermes directly. All perception models are Butler-owned for operational control.

---

## 2. Stacked Perception Pipeline

### 2.1 Task-Specific Routing

**Screen/UI Automation:**
1. Android AccessibilityService tree → structured DOM
2. OCR for missing text → PaddleOCR
3. YOLOv8 for non-semantic visuals → icons/buttons
4. SAM 2 only for precise region grounding
5. Qwen2.5-VL to reason over fused result

**Camera/Security:**
1. YOLOv8 for object detection
2. SAM 2 for precision masks
3. InsightFace (opt-in, closed-world only)
4. Qwen2.5-VL / InternVL for scene reasoning

**Document/Forms:**
1. PaddleOCR for text extraction
2. Document parser for structure
3. Qwen2.5-VL for semantic interpretation
4. Strict schema extraction

### 2.2 Verification Beats Confidence

Every perception must verify:
- **Action target exists** before reporting found
- **Text was actually extracted** with confidence threshold
- **Button tap target changed screen** after action
- **OCR confidence is sufficient** (>0.85 threshold)
- **Detection confidence is sufficient** (>0.7 threshold)

Models love being confident. Butler verifies.

---

## 3. Model Stack

### 3.1 Multimodal Reasoning

| Model | Use Case | Latency | Hardware |
|-------|----------|---------|----------|
| **Qwen2.5-VL-7B** | Fast default | <500ms | ~8GB VRAM |
| **Qwen2.5-VL-72B** | Premium only | <2s | ~80GB VRAM |
| **InternVL3.5-8B** | Heavy fallback | <800ms | ~10GB VRAM |

**Rule:** Smallest model that can do the job.

### 3.2 Detection Models (YOLOv8)

| Model | Use Case | Latency | mAP | Memory |
|-------|----------|---------|-----|-------|
| **YOLOv8n** | Edge/fast | <30ms | 37% | ~6MB |
| **YOLOv8s** | Balanced | <50ms | 45% | ~20MB |
| **YOLOv8m** | Camera/security | <80ms | 50% | ~50MB |

### 3.3 Segmentation Models (SAM 2)

| Model | Use Case | Latency | Trigger |
|-------|----------|---------|---------|
| **SAM2-tiny** | Precision when needed | <80ms | Explicit request only |
| **SAM2-small** | Balanced | <120ms | Region refinement |
| **SAM2-base** | High-precision | <200ms | Hard cases |

**CRITICAL:** Do NOT run SAM2 on every frame. That's how you heat rooms with inference.

### 3.4 OCR Models

| Model | Use Case | Latency | Languages |
|-------|----------|---------|-----------|
| **PaddleOCR** | Primary | <50ms | 80+ |
| **EasyOCR** | Light fallback | <100ms | 80+ |

### 3.5 Face Recognition (InsightFace)

**LEGAL NOTE:**
- Library: MIT licensed
- **Pretrained models: Non-commercial research use only**
- Commercial use → requires separate license

**Butler rules:**
- Opt-in only
- Closed-world personal graph only
- "This is probablyMom/colleague" not mass surveillance

---

## 4. API Contracts

### 4.1 Screen Parse (Android)

```yaml
POST /vision/screen-parse
  Request:
    {
      "source": "android",
      "package": "com.example.app",
      "include_tree": true,
      "fallback_images": true
    }
  Response:
    {
      "elements": [
        {
          "id": "username_input",
          "type": "input",
          "text": "Username",
          "bbox": [20, 100, 300, 40],
          "input_type": "text",
          "editable": true,
          "accessibility_id": "com.example:id/username"
        }
      ],
      "screen_type": "login",
      "accessibility_tree": {...},
      "ocr_fallback": {...},
      "processing_time_ms": 85
    }
  Errors:
    - 400: Invalid source
    - 503: Service unavailable
```

### 4.2 Detection Endpoint

```yaml
POST /vision/detect
  Request:
    {
      "image_data": "base64",
      "classes": ["button", "text", "icon", "input", "image", "person", "vehicle"],
      "threshold": 0.5,
      "max_detections": 50,
      "model": "yolov8m"  # Explicit model selection
    }
  Response:
    {
      "objects": [
        {
          "class": "button",
          "bbox": [0, 0, 100, 50],
          "confidence": 0.92,
          "text": "Submit"
        }
      ],
      "objects_count": 5,
      "model_used": "yolov8m",
      "processing_time_ms": 45,
      "verified": true  # Verification check passed
    }
```

### 4.3 OCR Endpoint

```yaml
POST /vision/ocr
  Request:
    {
      "image_data": "base64",
      "languages": ["en"],
      "paragraphs": true,
      "digits": true,
      "mode": "accurate"  # fast, accurate
    }
  Response:
    {
      "text": "User login\nUsername\nPassword",
      "blocks": [
        {
          "text": "User login",
          "bbox": [10, 10, 200, 50],
          "confidence": 0.95,
          "reading_order": 1
        }
      ],
      "language": "en",
      "model_used": "paddleocr",
      "processing_time_ms": 35,
      "verified": true
    }
```

### 4.4 Multimodal Reason

```yaml
POST /vision/reason
  Request:
    {
      "image_data": "base64",
      "context": {
        "task": "find_login_button",
        "screen_state": "login_screen"
      },
      "model": "qwen2.5-vl-7b"  # Optional override
    }
  Response:
    {
      "reasoning": "The login button is the rightmost button with primary styling...",
      "target": {
        "bbox": [250, 400, 350, 460],
        "class": "button",
        "text": "Login"
      },
      "confidence": 0.94,
      "alternatives": [...],
      "model_used": "qwen2.5-vl-7b",
      "verification": {
        "exists": true,
        "verified_bbox": [248, 398, 352, 462]
      }
    }
```

### 4.5 Segment (SAM 2)

```yaml
POST /vision/segment
  Request:
    {
      "image_data": "base64",
      "points": [[100, 50]],
      "mode": "point",
      "model": "sam2_small"
    }
  Response:
    {
      "masks": [
        {
          "segmentation": [1, 0, 1, ...],
          "bbox": [80, 30, 250, 150],
          "score": 0.94
        }
      ],
      "count": 1,
      "model_used": "sam2_small",
      "warning": "SAM2 latency applies"
    }
```

### 4.6 Face Recognition (Opt-in)

```yaml
POST /vision/face/recognize
  Request:
    {
      "image_data": "base64",
      "graph": "personal",
      "return_embeddings": false
    }
  Response:
    {
      "faces": [
        {
          "bbox": [100, 50, 200, 150],
          "identity": "mom",
          "confidence": 0.92
        }
      ]
      # Opt-in flag must be true, returns empty if not enabled
    }
  Errors:
    - 403: Face recognition not enabled by user
```

---

## 5. Android Integration

### 5.1 AccessibilityService (Primary)

```python
class AndroidScreenSource:
    """Primary structured input for Android"""
    
    async def get_accessibility_tree(self, package: str) -> AccessibilityTree:
        # AccessibilityService provides real DOM
        return await self.service.get_window_root_node(package)
    
    async def get_node_info(self, node_id: str) -> AccessibilityNodeInfo:
        # Query specific elements
        return await self.service.find_node(node_id)
    
    async def perform_action(self, node_id: str, action: str) -> bool:
        # Execute tap, scroll, type actions
        return await self.service.performAction(node_id, action)
```

### 5.2 MediaProjection (Fallback)

```python
class MediaProjectionCapture:
    """Pixel capture when accessibility unavailable"""
    
    async def capture_screen(self) -> bytes:
        # MediaProjection API screen capture
        return await self.projection.capture_frame()
    
    async def capture_region(self, bbox: List[int]) -> bytes:
        # Crop to specific region
        return await self.projection.capture_region(bbox)
```

### 5.3 Perception Order (Enforced)

```
1. Try AccessibilityService first
   ↓
2. If missing text → PaddleOCR
   ↓
3. If missing icons → YOLOv8
   ↓
4. If precision needed → SAM 2 (explicit request)
   ↓
5. If reasoning needed → Qwen2.5-VL
   ↓
6. VERIFY before reporting success
```

---

## 6. Configuration

### 6.1 Model Selection

```yaml
service:
  name: vision
  port: 8008
  workers: 4

detection:
  default_model: yolov8s
  confidence_threshold: 0.5
  classes:
    - button
    - text
    - icon
    - input
    - image

ocr:
  enabled: true
  engine: paddleocr
  confidence_threshold: 0.85
  languages:
    - en

segmentation:
  enabled: true
  default_model: sam2_small
  # WARNING: Don't auto-trigger on every frame

reasoning:
  default_model: qwen2.5-vl-7b
  fallback_model: internvl3.5-8b
  confidence_threshold: 0.7

face:
  enabled: false  # Opt-in only
  model: insightface
  # Commercial use requires license review

android:
  accessibility_enabled: true
  projection_fallback: true
```

### 6.2 Routing Rules

```python
VISION_ROUTING = {
    "android_ui": ["accessibility", "ocr", "yolo", "sam2"],
    "camera_objects": ["yolo", "sam2", "face"],
    "document": ["ocr", "reasoning"],
    "screenshot_reasoning": ["ocr", "yolo", "reasoning"]
}
```

---

## 7. Error Codes (RFC 9457)

| Code | Error | HTTP | Cause |
|------|-------|------|-------|
| V001 | invalid-image | 400 | Unsupported format |
| V002 | image-too-large | 413 | Exceeds 5MB |
| V003 | no-content-detected | 422 | Below confidence threshold |
| V004 | model-unavailable | 503 | GPU required |
| V005 | verification-failed | 422 | Action target not verified |
| V006 | face-disabled | 403 | Not opt-in |

---

## 8. Observability

### 8.1 Key Metrics

| Metric | Type | Alert Threshold |
|--------|------|-----------------|
| detection_latency_p99 | histogram | >80ms |
| ocr_latency_p99 | histogram | >60ms |
| reason_latency_p99 | histogram | >1500ms |
| detection_confidence_avg | gauge | <0.7 |
| ocr_confidence_avg | gauge | <0.85 |
| verification_success_rate | gauge | <0.95 |
| sam2_auto_trigger_rate | gauge | Track for cost |

### 8.2 Per-Task Metrics

| Task | Target Latency | Min Confidence |
|------|----------------|-----------------|
| android_screen_parse | <100ms | 0.9 |
| detection | <50ms | 0.7 |
| ocr | <50ms | 0.85 |
| reason | <1000ms | 0.7 |
| segment | <150ms | 0.8 |

---

## 9. Runbook

### 9.1 High Latency

```bash
# Check model in use
curl http://vision:8008/metrics/model

# Switch to faster models
curl -X POST http://vision:8008/config -d '{
  "detection": "yolov8n",
  "reasoning": "qwen2.5-vl-7b"
}'

# Check GPU memory
nvidia-smi
```

### 9.2 Low Detection Confidence

```bash
# Check threshold
curl http://vision:8008/config/detection

# Lower threshold (with warning)
curl -X POST http://vision:8008/config/detection -d '{"threshold": 0.4}'

# Switch to more accurate model
curl -X POST http://vision:8008/config -d '{"detection": "yolov8m"}'
```

### 9.3 SAM2 Overuse

```bash
# Check auto-trigger rate
curl http://vision:8008/metrics/sam2触发

# SAM2 should only trigger on explicit request
# Find services auto-triggering and disable
```

---

## 10. Stack Summary

| Layer | Default | Fallback | Trigger |
|-------|---------|----------|---------|
| **Detection** | YOLOv8s | YOLOv8m | Always |
| **OCR** | PaddleOCR | EasyOCR | Text missing from tree |
| **Segmentation** | None | SAM2-small | Explicit request |
| **Reasoning** | Qwen2.5-VL-7B | InternVL3.5-8B | Reasoning needed |
| **Face** | Disabled | - | Opt-in only |

**Gold rule:** Structured signals first, specialist models second, multimodal reasoning third, verification always.

---

*Document owner: Vision Team*  
*Last updated: 2026-04-18*  
*Version: 2.0 (Stub)*