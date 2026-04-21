# Butler Vision Identity + Human-Vehicle Relation Specification

**Version:** 2.0 (SOTA Full Stack)  
**Status:** Production Ready  
**Last Updated:** 2026-04-20

## SOTA Stack Overview

| Layer | SOTA Choice | Notes |
|-------|-----------|-------|
| Open-world detection | GroundingDINO 1.5/1.6 | Language-guided detection |
| Segmentation + tracking | SAM 2 / Grounded SAM 2 | Open-set segmentation |
| Face recognition | InsightFace / ArcFace | 512-d embeddings |
| Tracking | ByteTrack | Production MOT baseline |
| Person ReID | OSNet / FastReID | Cross-view matching |
| Vehicle ReID | Dedicated vehicle-ReID | Not generic tracking |
| Multi-camera | DeepStream MV3DT | Calibrated fusion |
| Relation engine | Butler-native | Temporal graph reasoning |

---

## 1. Executive Summary

This specification defines Butler's computer vision identity system for recognizing people, vehicles, and inferring human-vehicle relations. The system models identity and relations separately, using confidence-aware outputs to avoid false certainty.

### Core Capabilities

- **Known-person recognition**: Face-based identification for enrolled identities
- **Unknown-person tracking**: Track persistent person identities across frames
- **Vehicle identity**: ReID-based vehicle recognition
- **Human-vehicle relation inference**: Infer ownership, usage, arrival patterns
- **Event understanding**: High-level activity recognition

### SOTA Stack (v2.0)

Butler's vision stack is built as a multi-stage identity and relation engine:

| Layer | SOTA Component | Purpose |
|-------|---------------|---------|
| **Perception** | GroundingDINO + SAM 2 | Open-set detection, segmentation, tracking |
| **Tracking** | ByteTrack | Per-camera multi-object tracking |
| **Identity** | InsightFace + OSNet + Vehicle-ReID | Face, person, vehicle recognition |
| **Relation** | Butler-native temporal graph | Evidence-backed relation inference |
| **Memory** | Evidence-weighted graph | Soft claims with supersession |

### Hard Boundaries

- **Consent-first**: No biometric storage without explicit consent
- **Local-processing**: Face embeddings stay on device
- **Soft claims**: Confidence-aware output, no hallucinated certainty
- **Evidence requirements**: Ownership inference only after repeated evidence
- **Audit logging**: All identity operations logged

### Target Deployment

| Tier | Use Case | Cost |
|------|----------|------|
| Tier A | Home/office/robot | $150-500 |
| Tier B | Multi-room/robotics | $1.5K-5K |
| Tier C | Campus/research | $15K+ |

---

## 2. Component Architecture

### 2.1 Detection Layer

| Component | Model | Purpose |
|-----------|-------|---------|
| Person Detector | YOLOv8-Person / MMDetection | Detect all people in frame |
| Face Detector | RetinaFace / MediaPipe | Detect faces |
| Vehicle Detector | YOLOv8-Vehicle | Detect cars, bikes, trucks |
| Plate Detector | YOLOv8-Plate | Detect license plates |
| Keypoint Detector | HRNet / ViTPose | Body/vehicle pose estimation |

### 2.2 Tracking Layer

| Component | Tracker Type | Purpose |
|-----------|-----------|---------|
| Camera Tracker | ByteTrack / BoT-SORT | Per-camera object tracks |
| Multi-Camera Tracker | Spatial fusion | Cross-camera track association |

### 2.3 Recognition Layer

| Component | Model | Purpose |
|-----------|-------|---------|
| Face Recognizer | InsightFace / ArcFace | Face embedding + identification |
| Person ReID | OSNet / FastReID | Person re-identification |
| Vehicle ReID | FastReID-Vehicle | Vehicle re-identification |
| Plate OCR | CRNN / EasyOCR | License plate reading |

### 2.4 Association Layer

Logic to attach tracks across modalities:
- Face track → Person track (via head region overlap)
- Person track → Vehicle track (via proximity, mounting, movement)
- Multi-camera person/vehicle linking

### 2.5 Graph Layer

Stores evolving identity relations with:
- Temporal persistence
- Confidence scoring
- Contradiction resolution

---

## 3. Model Specifications

### 3.1 Face Recognition

```
Model: InsightFace (ArcFace)
Architecture: ResNet-100 + Additive Angular Margin Loss
Embedding: 512-dimensional
Inference: ~15ms per face on CUDA
Threshold: 0.68 (cosine similarity)
```

### 3.2 Person ReID

```
Model: OSNet (Omniscale Feature Learning)
Architecture: OSNet-1.0
Embedding: 512-dimensional
Input: 256x128 person crop
Augmentation: Random erasing, horizontal flip
Inference: ~8ms per crop
```

### 3.3 Vehicle ReID

```
Model: FastReID Vehicle Pipeline
Backbone: ResNet-50
Embedding: 2048-dimensional
Input: 224x224 vehicle crop
Variants: Car ReID, Bike ReID
Augmentation: Color jitter, random crop
```

### 3.4 Tracking

```
Primary: ByteTrack
- Detection confidence threshold: 0.3
- Track buffer: 30 frames
- Match threshold: 0.7 (IoU) / 0.5 (embedding)

Multi-camera: Camera geometry + appearance fusion
- Epipolar constraints
- Time synchronization window: 10 seconds
```

---

## 4. Identity Node Schema

### 4.1 Core Identity Types

```python
class IdentityType(Enum):
    PERSON = "person"
    FACE = "face_identity"
    VEHICLE = "vehicle"
    BIKE = "bike"
    PLATE = "plate"
    HELMET = "helmet"
    PHONE = "phone"
    LOCATION = "location"
```

### 4.2 Identity Node

```python
class IdentityNode:
    id: str                          # Unique ID (person_17, bike_04)
    identity_type: IdentityType
    embeddings: List[float]          # Stored embeddings
    features: Dict[str, Any]          # Visual features, attributes
    first_seen: datetime
    last_seen: datetime
    encounter_count: int
    confidence: float                # Identity confidence score
    
    # For persons
    known_face_id: Optional[str]       # Linked face record
    display_name: Optional[str]       # For known persons
    
    # For vehicles
    plate_number: Optional[str]
    make_model: Optional[str]
    color: Optional[str]
```

### 4.3 Relation Types

```python
class RelationType(Enum):
    OWNS = "owns"                    # Strong ownership claim
    USES = "uses"                   # Regular usage
    ARRIVED_ON = "arrived_on"         # Arrived on vehicle
    ENTERED = "entered"              # Entered location
    PARKED = "parked"               # Parked vehicle
    CO_OCCURS_WITH = "co_occurs_with"# Same time/place
    LIKELY_SAME_ENTITY = "likely_same_entity"  # ReID match
```

### 4.4 Relation Edge

```python
class RelationEdge:
    id: str                        # Unique relation ID
    source_id: str                  # Source identity ID
    target_id: str                 # Target identity ID
    relation_type: RelationType
    
    # Evidence
    evidence: Dict[str, Any]        # Supporting evidence
    confidence: float              # 0.0 - 1.0
    
    # Metadata
    first_observed: datetime
    last_observed: datetime
    occurrence_count: int
    location_ids: List[str]        # Where observed
    
    # Provenance
    evidence_sources: List[str]     # Camera IDs
    notes: Optional[str]
```

---

## 5. Event Schema

### 5.1 Core Events

```python
class VisionEvent:
    event_id: str
    event_type: EventType          # See below
    timestamp: datetime
    location_id: str
    
    # Actors
    primary_identity: str          # person_17
    secondary_identities: List[str] # bike_04
    
    # Context
    camera_ids: List[str]
    track_ids: List[str]           # Source tracks
    embeddings: Dict[str, List[float]]
    
    # Bounding boxes
    bboxes: Dict[str, List[int]]   # camera_id -> [x1,y1,x2,y2]
    
    # Confidence
    confidence: float
    
    # Derived
    relation_id: Optional[str]
```

### 5.2 Event Types

```python
class EventType(Enum):
    PERSON_DETECTED = "person_detected"
    FACE_RECOGNIZED = "face_recognized"
    VEHICLE_DETECTED = "vehicle_detected"
    PLATE_DETECTED = "plate_detected"
    PERSON_ENTERED = "person_entered"
    PERSON_EXITED = "person_exited"
    VEHICLE_PARKED = "vehicle_parked"
    VEHICLE_DEPARTED = "vehicle_departed"
    RELATION_INFERRED = "relation_inferred"
    IDENTITY_RESOLVED = "identity_resolved"
```

---

## 6. Confidence Rules

### 6.1 Identity Confidence

| Scenario | Confidence | Formula |
|----------|------------|---------|
| Known face match | High | 0.94 if similarity > 0.68 |
| Person ReID match | Medium | 0.81 if cosine > 0.75 |
| Vehicle ReID match | Medium | 0.77 if cosine > 0.70 |
| Unknown new person | Low | 0.5 initially |
| First encounter | Low | 0.3 - grows with encounters |

### 6.2 Relation Confidence

```
Relation Confidence Rules:

ARRIVED_ON(person, vehicle):
  - Attach face to person when face box overlaps head region for N frames: conf += 0.2
  - Person approaches vehicle: conf += 0.15
  - Person mounts vehicle: conf += 0.25
  - Both tracks move together: conf += 0.2
  - Maximum: 0.81

OWNS(person, vehicle):
  - Single encounter: NOT ASSERTED (requires repeated evidence)
  - 2-3 encounters: 0.42 (possible_owner)
  - 4+ encounters across days: 0.68 (likely_owner)
  - 10+ encounters across locations: 0.85 (owner)

USES(person, vehicle):
  - Weekly co-occurrence: 0.72
  - Daily co-occurrence: 0.85
  
LIKELY_SAME_ENTITY:
  - ReID cosine > 0.75: 0.77
  - ReID cosine > 0.82: 0.88
  - Plus temporal continuity: +0.05
```

### 6.3 Confidence Thresholds

```python
class ConfidenceThresholds:
    # Display thresholds
    RECOGNIZED_CERTAIN = 0.90   # "Abhishek Jha (0.94)"
    RECOGNIZED_LIKELY = 0.70   # "likely Abhishek Jha"
    RECOGNIZED_POSSIBLE = 0.50 # "possibly Abhishek Jha"
    
    # Relation thresholds
    RELATION_CONFIRMED = 0.85
    RELATION_LIKELY = 0.70
    RELATION_POSSIBLE = 0.50
    
    # Minimum for storage
    MIN_IDENTITY_CONFIDENCE = 0.30
    MIN_RELATION_CONFIDENCE = 0.42
```

---

## 7. Association Logic

### 7.1 Face to Person Attachment

```
Rule: attach_face_to_person(face_track, person_track) -> confidence

1. Check overlap:
   - face_box overlaps head_region(person_track) for N frames
   - N >= 5 frames: confidence += 0.3
   
2. Check temporal:
   - Duration > 2 seconds: confidence += 0.2
   
3. Check position:
   - Face directly above body: confidence += 0.25
   
4. Check quality:
   - Face clarity > 0.7: confidence += 0.15
   - Face illumination > 0.5: confidence += 0.1
   
5. Apply threshold:
   - If confidence > 0.6: attach
   - Store with confidence score
```

### 7.2 Person to Vehicle Linking

```
Rule: link_person_to_vehicle(person_track, vehicle_track, camera_id) -> confidence

1. Spatial approach:
   - Person moves toward vehicle: +0.15
   - Distance < 2m at closest: +0.2
   
2. Behavioral:
   - Person adjacent to vehicle (standing): +0.15
   - Person mounts vehicle: +0.25
   - Both move together: +0.2
   
3. Temporal:
   - Sequential within 10s: +0.1
   
4. Entry/Exit:
   - Person enters vehicle: +0.2
   - Person exits vehicle: +0.15
   
5. History bonus:
   - Previously linked: +0.1
   
6. Apply threshold:
   - confidence > 0.65: link
   - Store as ARRIVED_ON or USES
```

### 7.3 Ownership Inference

```
Rule: infer_ownership(person_id, vehicle_id) -> ownership_confidence

DO NOT assert from single encounter.

1. Count encounters:
   - co_occurrence_count = count co-occurrences(person_id, vehicle_id)
   
2. Time span:
   - days_observed = unique days with co-occurrence
   
3. Location diversity:
   - locations_observed = unique locations
   
4. Compute:
   if co_occurrence_count >= 10 AND days_observed >= 3:
     ownership_confidence = min(0.85, 0.42 + co_occurrence_count * 0.04)
   elif co_occurrence_count >= 4:
     ownership_confidence = 0.42
   else:
     ownership_confidence = 0.0  # Do not assert
     
5. Store as OWNS only when confidence >= 0.68
```

### 7.4 Multi-Camera Track Resolution

```
Rule: resolve_cross_camera_tracks(track_a, track_b) -> same_entity_confidence

1. Appearance:
   - ReID cosine similarity: +0.5 weight
   
2. Spatial:
   - Camera geometry consistent: +0.2 weight
   - Epipolar check passes: +0.1 weight
   
3. Temporal:
   - Within sync window (10s): +0.15 weight
   - Direction of travel: +0.05 weight
   
4. Combine:
   same_entity_confidence = weighted_sum(evidence)
   
5. Threshold:
   - If confidence > 0.70: resolve as same entity
```

---

## 8. Output Format

### 8.1 System Output (Production)

The Butler Identity System outputs confidence-aware JSON:

```json
{
  "timestamp": "2026-04-20T07:15:00Z",
  "frame_id": 157234,
  "location_id": "office_garage",
  "detections": [
    {
      "track_id": "person_17",
      "type": "person",
      "bbox": [120, 45, 180, 320],
      "motion": "standing"
    },
    {
      "track_id": "face_23",
      "type": "face",
      "bbox": [135, 55, 165, 85],
      "recognized_face": "Abhishek Jha",
      "face_confidence": 0.94
    },
    {
      "track_id": "bike_04",
      "type": "vehicle",
      "bbox": [200, 180, 340, 380],
      "vehicle_type": "bike"
    }
  ],
  "identities": {
    "person_17": {
      "display_name": "Abhishek Jha",
      "confidence": 0.94,
      "known": true
    },
    "bike_04": {
      "display_name": "Bike_04",
      "confidence": 0.81,
      "known": false
    }
  },
  "relations": [
    {
      "type": "likely_arrived_on",
      "source": "person_17",
      "target": "bike_04",
      "confidence": 0.81,
      "evidence": ["approach", "mount", "move_together"]
    }
  ],
  "events": [
    {
      "event_type": "vehicle_parked",
      "identity": "bike_04",
      "location": "office_garage",
      "timestamp": "2026-04-20T07:12:00Z"
    },
    {
      "event_type": "person_entered",
      "identity": "person_17",
      "location": "office_entrance",
      "timestamp": "2026-04-20T07:15:00Z"
    }
  ]
}
```

### 8.2 Low-Confidence Output

For uncertain identities:

```json
{
  "track_id": "person_17",
  "identities": [],
  "relations": [
    {
      "type": "possible_owner",
      "source": "person_17",
      "target": "bike_04",
      "confidence": 0.42,
      "note": "Single encounter - requires more evidence"
    }
  ]
}
```

---

## 9. Database Schema

### 9.1 Identity Table

```sql
CREATE TABLE identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identity_type VARCHAR(50) NOT NULL,
    display_name VARCHAR(255),
    
    -- Embeddings (stored as vector)
    face_embedding_vector VECTOR(512),
    person_reid_vector VECTOR(512),
    vehicle_reid_vector VECTOR(2048),
    
    -- Attributes
    attributes JSONB,
    plate_number VARCHAR(20),
    make_model VARCHAR(100),
    color VARCHAR(50),
    
    -- Tracking
    first_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    encounter_count INTEGER DEFAULT 0,
    
    -- Confidence
    confidence_score FLOAT DEFAULT 0.5,
    is_known BOOLEAN DEFAULT FALSE,
    
    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_identities_type ON identities(identity_type);
CREATE INDEX idx_identities_last_seen ON identities(last_seen DESC);
CREATE INDEX idx_identities_face_embedding ON identities USING ivfflat (face_embedding_vector vector_cosine_ops);
CREATE INDEX idx_identities_reid_embedding ON identities USING ivfflat (person_reid_vector vector_cosine_ops);
```

### 9.2 Relations Table

```sql
CREATE TABLE relations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES identities(id),
    target_id UUID NOT NULL REFERENCES identities(id),
    relation_type VARCHAR(50) NOT NULL,
    
    -- Evidence
    evidence JSONB,
    confidence_score FLOAT NOT NULL,
    
    -- Metadata
    first_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_observed TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    occurrence_count INTEGER DEFAULT 1,
    location_ids TEXT[],
    
    -- Provenance
    evidence_sources TEXT[],
    notes TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    CONSTRAINT unique_source_target_type UNIQUE (source_id, target_id, relation_type)
);

CREATE INDEX idx_relations_source ON relations(source_id);
CREATE INDEX idx_relations_target ON relations(target_id);
CREATE INDEX idx_relations_confidence ON relations(confidence_score DESC);
```

### 9.3 Events Table

```sql
CREATE TABLE vision_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    location_id VARCHAR(100) NOT NULL,
    
    -- Actors
    primary_identity_id UUID REFERENCES identities(id),
    secondary_identity_ids UUID[],
    
    -- Context
    camera_ids TEXT[],
    track_ids TEXT[],
    embeddings JSONB,
    
    -- Bounding boxes
    bboxes JSONB,
    
    -- Confidence
    confidence_score FLOAT,
    
    -- Derived
    relation_id UUID REFERENCES relations(id),
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_vision_events_timestamp ON vision_events(timestamp DESC);
CREATE INDEX idx_vision_events_location ON vision_events(location_id);
CREATE INDEX idx_vision_events_type ON vision_events(event_type);
CREATE INDEX idx_vision_events_primary ON vision_events(primary_identity_id);
```

### 9.4 Known Faces Table (Consent-Controlled)

```sql
CREATE TABLE known_faces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    person_name VARCHAR(255) NOT NULL,
    face_embedding_vector VECTOR(512) NOT NULL,
    
    -- Consent
    consent_given BOOLEAN DEFAULT FALSE,
    consent_timestamp TIMESTAMP WITH TIME ZONE,
    retention_policy VARCHAR(50),
    
    -- Metadata
    photo_source VARCHAR(255),
    enrollment_date TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_verified TIMESTAMP WITH TIME ZONE,
    
    -- Access
    access_level VARCHAR(50) DEFAULT 'self',
    
    UNIQUE (person_name)
);

CREATE INDEX idx_known_faces_embedding ON known_faces USING ivfflat (face_embedding_vector vector_cosine_ops);
CREATE INDEX idx_known_faces_consent ON known_faces(consent_given) WHERE consent_given = TRUE;
```

---

## 10. Safety Policy

### 10.1 Legal Requirements

| Requirement | Implementation |
|-------------|----------------|
| **Consent** | Explicit consent required before storing face embeddings |
| **Retention Policy** | Configurable auto-expiration (30/90/365 days) |
| **Access Control** | Role-based: self, family, none |
| **Audit Logs** | All identity access logged with timestamp, accessor |
| **Data Export** | GDPR/CCPA compliant export capability |
| **Right to Delete** | Must honor deletion requests within 72 hours |

### 10.2 Consent Categories

```python
class ConsentLevel(Enum):
    NONE = "none"                      # No recognition
    SELF = "self"                      # Only show to subject
    FAMILY = "family"                 # Show to household members
    VISITORS = "visitors"              # Show to visitors
    PUBLIC = "public"                 # Anyone (not recommended)
```

### 10.3 Retention Policies

```python
class RetentionPolicy(Enum):
    SESSION_ONLY = "session"           # Not stored
    DAILY = "daily"                  # Auto-delete after 24 hours
    WEEKLY = "weekly"                # Auto-delete after 7 days
    MONTHLY = "monthly"              # Auto-delete after 30 days
    YEARLY = "yearly"                # Auto-delete after 365 days
    FOREVER = "forever"              # Never auto-delete
```

### 10.4 Safety Rules

```
RULE 1: Never store biometric data without explicit consent

RULE 2: Face embeddings are encrypted at rest
        - Use AES-256-GCM for embeddings
        - Separate encryption keys from data

RULE 3: Do not assert ownership from single encounter
        - Minimum 4 encounters for "possible_owner"
        - Minimum 10 encounters for ownership claim

RULE 4: Confidence-aware output
        - Always include confidence scores
        - Use natural language qualifiers:
          * 0.90+ = "[Name] detected"
          * 0.70-0.89 = "likely [Name]"
          * 0.50-0.69 = "possibly [Name]"
          * < 0.50 = "unknown person"

RULE 5: Audit everything
        - Log all identity lookups
        - Log all confidence thresholds
        - Retain logs for 1 year minimum

RULE 6: No surveillance mode defaults
        - Default to "smart assistant" not "CCTV"
        - No tracking across public spaces without explicit opt-in
        - Local processing preferred over cloud
```

### 10.5 Deployment Tiers and Consent

| Tier | Processing | Data Retention | Consent Required |
|------|-----------|----------------|------------------|
| **Local (Personal)** | On-device | Local only | Self consent |
| **Edge (Home)** | Home hub | 30 days default | All household members |
| **Cloud (Enterprise)** | Cloud | Policy-based | All users + disclosure |

---

## 11. Deployment Tiers

### 11.1 Tier 1: Local (Personal Device)

```
Use Case: Single-user personal assistant
Processing: On-device (no network)
Models: Lightweight (MobileNet, ShuffleNet)
Latency: < 50ms local inference
Storage: Local SSD/NVMe only
Privacy: 100% local - no data leaves device

Capabilities:
- Face recognition (self only)
- Person tracking (local)
- Basic vehicle detection
- No cloud connectivity required

Hardware: Raspberry Pi 5 / Apple Neural Engine / Google EdgeTPU
```

### 11.2 Tier 2: Edge (Home/Office)

```
Use Case: Home or small office
Processing: Local edge server
Models: Full accuracy (ResNet, YOLOv8)
Latency: < 100ms end-to-end
Storage: Local NAS with encryption
Privacy: Local processing, optional cloud backup

Capabilities:
- Known face recognition (household members)
- Person ReID (multiple cameras)
- Vehicle ReID
- Basic relation inference
- Multi-camera tracking

Hardware: NVIDIA Jetson AGX / Intel NCS2 / Custom build
```

### 11.3 Tier 3: Cloud (Enterprise)

```
Use Case: Large property / campus
Processing: Cloud or on-prem server cluster
Models: Full accuracy + ensemble
Latency: < 200ms end-to-end
Storage: Distributed database with replication
Privacy: Full audit, consent management, GDPR compliant

Capabilities:
- Full identity graph
- Cross-location tracking
- Historical analysis
- Advanced relation inference
- Real-time alerts

Hardware: NVIDIA A100 GPU cluster / DeepStream deployment
```

### 11.4 Tier Comparison

| Feature | Local | Edge | Cloud |
|---------|-------|------|-------|
| Face Recognition | Self only | 50 faces | Unlimited |
| Person Tracking | Single cam | 10 cameras | 100+ cameras |
| Vehicle ReID | Basic | Full | Full + ensemble |
| Relation Inference | None | Basic | Advanced |
| Storage | 7 days | 90 days | 1+ year |
| Latency | <50ms | <100ms | <200ms |
| Cost | $150 | $1,500 | $15,000+ |
| Privacy | Highest | High | Configurable |

---

## 12. API Reference

### 12.1 Identity API

```python
# Enroll a known face
POST /api/v1/vision/faces/enroll
{
    "person_name": "Abhishek Jha",
    "image": "base64_encoded_image",
    "consent_given": true,
    "retention_policy": "yearly"
}

# Recognize faces
POST /api/v1/vision/faces/recognize
{
    "frame": "base64_encoded_frame",
    "return_identities": true
}

# Query identity
GET /api/v1/vision/identities/{identity_id}

# Query relations
GET /api/v1/vision/identities/{identity_id}/relations
```

### 12.2 Event API

```python
# Get recent events
GET /api/v1/vision/events?location_id=office&limit=50

# Query by identity
GET /api/v1/vision/events?identity_id={id}&from=2026-04-01

# Get entry/exit events
GET /api/v1/vision/events?type=person_entered&location_id=office
```

### 12.3 Configuration API

```python
# Update confidence thresholds
PUT /api/v1/vision/config/thresholds
{
    "recognized_certain": 0.90,
    "recognized_likely": 0.70,
    "relation_confirmed": 0.85
}

# Export data (GDPR)
POST /api/v1/vision/export
{
    "identity_id": "person_17",
    "include_embeddings": false
}
```

---

## 13. Error Handling

### 13.1 RFC 9457 Error Response

All errors follow RFC 9457 Problem Details format:

```json
{
  "type": "https://butler.local/v1/problems/identity-not-found",
  "title": "Identity Not Found",
  "status": 404,
  "detail": "No identity found for track_id 'person_999'",
  "instance": "/api/v1/vision/identities/person_999"
}
```

### 13.2 Error Types

| Type | HTTP Code | Description |
|------|----------|-------------|
| `identity-not-found` | 404 | Identity ID not found |
| `no-faces-detected` | 200 | No faces in frame (success with empty) |
| `embedding-failed` | 500 | Model inference failed |
| `consent-required` | 403 | Consent needed for operation |
| `storage-full` | 507 | Local storage exhausted |
| `camera-offline` | 503 | Camera stream unavailable |

---

## 14. Implementation Notes

### 14.1 Recommended Stack

| Component | Recommendation | Notes |
|-----------|--------------|-------|
| Face Detection | RetinaFace | Best accuracy/speed balance |
| Face Recognition | InsightFace (ArcFace) | 512-d embeddings |
| Person Detection | YOLOv8-Person | Lightweight |
| Person ReID | OSNet | Efficient |
| Vehicle Detection | YOLOv8-Vehicle | Car, bike, truck |
| Vehicle ReID | FastReID | Vehicle variants |
| Tracking | ByteTrack | Best for crowded scenes |
| Plate OCR | CRNN + CTC | Lightweight OCR |
| Database | PostgreSQL + pgvector | For embeddings |

### 14.2 Performance Targets

| Metric | Local | Edge | Cloud |
|--------|-------|------|-------|
| FPS | 15+ | 25+ | 30+ |
| Latency P95 | 80ms | 50ms | 30ms |
| Memory | 2GB | 4GB | 8GB |
| GPU Required | Optional | Required | Required |

### 14.3 Known Issues

- **Occlusion**: Person ReID degrades with partial occlusion
- **Lighting**: Face recognition requires adequate lighting (>100 lux)
- **Camera Quality**: Minimum 1080p, 15fps recommended
- **Angle**: Face recognition degrades >45° from frontal
- **Multi-camera**: Requires temporal sync <1s between cameras

---

## 15. Appendix

### 15.1 Confidence Qualifier Mapping

| Confidence | Display | API Field |
|------------|---------|----------|
| 0.90+ | "Abhishek Jha detected" | `recognized` |
| 0.70-0.89 | "likely Abhishek Jha" | `likely` |
| 0.50-0.69 | "possibly Abhishek Jha" | `possible` |
| <0.50 | "unknown person" | `unknown` |

### 15.2 Relation Type Qualifiers

| Confidence | Display |
|------------|---------|
| 0.85+ | "owns" |
| 0.70-0.84 | "likely owns" |
| 0.50-0.69 | "possibly owns" |
| <0.50 | Not displayed |

### 15.3 SOTA Model References

| Model | Repository | Purpose |
|-------|-----------|---------|
| GroundingDINO | https://github.com/IDEA-Research/GroundingDINO | Open-set detection |
| Grounded SAM 2 | https://github.com/IDEA-Research/Grounded-SAM-2 | Segmentation + tracking |
| InsightFace | https://github.com/InsightFace | Face detection + recognition |
| ByteTrack | https://github.com/ifzhang/ByteTrack | Multi-object tracking |
| OSNet | https://github.com/KaiyangZhou/OSNet | Person ReID |
| FastReID | https://github.com/JDAI-CV/FastReID | ReID toolbox |
| OpenVINO vehicle-reid | https://github.com/openvinotoolkit/model_zoo | Vehicle ReID |
| DeepStream | https://github.com/NVIDIA-AI-IOT/deepstream | Multi-camera fusion |

---

## 16. SOTA Full Stack Architecture (v2.0)

### 16.1 Layer 1: Perception

```
┌─────────────────────────────────────────────────────────────┐
│                    PERCEPTION LAYER                        │
├─────────────────────────────────────────────────────────────┤
│ Component              │ Model              │ Purpose          │
├───────────────────────┼───────────────────┼─────────────────┤
│ Open-world detector    │ GroundingDINO 1.6  │ Language-guided │
│ Segmentation         │ SAM 2 / Grounded   │ Open-set seg    │
│ Face detector       │ InsightFace       │ Face + align   │
│ Face recognizer      │ ArcFace           │ 512-d embed   │
│ Vehicle detector    │ YOLOv8-Vehicle   │ Car, bike    │
│ Plate detector     │ YOLOv8-Plate     │ License plate│
│ Keypoints          │ ViTPose           │ Body pose    │
└───────────────────────┴───────────────────┴─────────────────┘
```

### 16.2 Layer 2: Tracking

```
┌─────────────────────────────────────────────────────────────┐
│                    TRACKING LAYER                          │
├─────────────────────────────────────────────────────────────┤
│ Per-Camera Tracker: ByteTrack                             │
│   - Detection confidence threshold: 0.3                 │
│   - Track buffer: 30 frames                                │
│   - Match threshold: 0.7 (IoU) / 0.5 (embedding)      │
│                                                             │
│ Multi-Camera Tracker (Tier B/C):                           │
│   - Calibrated camera geometry                              │
│   - Temporal sync window: 10 seconds                    │
│   - Epipolar constraints                                 │
└─────────────────────────────────────────────────────────────┘
```

### 16.3 Layer 3: Identity

```
┌─────────────────────────────────────────────────────────────┐
│                    IDENTITY LAYER                         │
├─────────────────────────────────────────────────────────────┤
│ Face Identity (known):                                    │
│   - InsightFace embeddings (512-d)                        │
│   - Only for enrolled users                              │
│   - Unknown face → person track only                    │
│                                                             │
│ Person ReID:                                             │
│   - OSNet backbone                                      │
│   - Cross-view matching without face                    │
│   - Embedding + appearance fusion                     │
│                                                             │
│ Vehicle ReID:                                            │
│   - Dedicated vehicle-ReID model                       │
│   - Not generic tracking IDs                          │
│   - Context: plate, location, color                     │
└─────────────────────────────────────────────────────────────┘
```

### 16.4 Layer 4: Relation Reasoning

```
┌─────────────────────────────────────────────────────────────┐
│                  RELATION REASONING LAYER                │
├─────────────────────────────────────────────────────────────┤
│ Temporal Rules (evidence-backed):                         │
│                                                             │
│ face_track → person_track                               │
│   IF face spatially consistent with head region          │
│   FOR several frames                                   │
│   THEN attach with confidence                          │
│                                                             │
│ person_track → vehicle_track                            │
│   IF person approaches, stops near, mounts             │
│   AND motion becomes coupled                           │
│   THEN link with confidence                            │
│                                                             │
│ ARRIVED_ON condition:                                   │
│   IF person + vehicle enter scene separately             │
│   AND couple, terminate at same destination            │
│   THEN infer arrived_on                                 │
│                                                             │
│ LIKELY_OWNER_OF condition:                              │
│   IF repeated co-occurrence over days + locations     │
│   THEN infer with accumulated confidence                 │
│                                                             │
│ DRIVES condition:                                      │
│   IF car-enter sequence + co-motion                    │
│   THEN infer drives (stronger than just proximity)       │
└─────────────────────────────────────────────────────────────┘
```

### 16.5 Layer 5: Memory Graph

```
┌───────��─────────────────────────────────────────────────────┐
│                    MEMORY GRAPH LAYER                     │
├─────────────────────────────────────────────────────────────┤
│ Entities: person, face_id, vehicle, plate, helmet,         │
│          bag, device, location                             │
│                                                             │
│ Relations (weighted evidence):                           │
│   - USES                (person ↔ device)                │
│   - ARRIVED_ON          (person ↔ vehicle)                │
│   - DRIVES             (person ↔ vehicle)                 │
│   - PARKED             (person/vehicle ↔ location)       │
│   - CO_OCCURS_WITH     (entity ↔ entity)                  │
│   - LIKELY_OWNER_OF   (person ↔ vehicle)                │
│   - ENTERED            (person ↔ location)               │
│   - LEFT_WITH         (person ↔ entity)                  │
│                                                             │
│ Confidence: stored per rule, evidence累积               │
│ Supersession: contradictions resolved over time             │
└─────────────────────────────────────────────────────────────┘
```

---

## 17. SOTA Deployment Tiers

### 17.1 Tier A: Local Edge ($150-500)

```
Use Case: Home, office, robot, smart glasses
─────────────────────────────────────────
Perception:
  - GroundingDINO small (yolo-s path)
  - InsightFace embeddings only
  - Lightweight plate OCR

Tracking:
  - ByteTrack single-camera

Identity:
  - Face identity (self + household)
  - Basic person ReID (OSNet-light)

Relation:
  - Simple mount/dismount detection
  - Basic co-occurrence counts

Memory:
  - Local graph cache (7 days)
  - SQLite + embeddings

Hardware:
  - Raspberry Pi 5 + GPU hat
  - NVIDIA Jetson Nano
  - Google EdgeTPU

Latency: <100ms
Storage: 32GB SSD
```

### 17.2 Tier B: Premium Edge Server ($1.5K-5K)

```
Use Case: Multi-room smart space, robotics lab
─────────────────────────────────────────
Perception:
  - GroundingDINO base
  - Grounded SAM 2
  - InsightFace full

Tracking:
  - ByteTrack multi-camera
  - Calibrated geometry

Identity:
  - Person ReID (OSNet-full)
  - Vehicle ReID (dedicated)
  - Plate OCR

Relation:
  - Full event reasoning
  - Multi-camera fusion
  - Entry/exit detection

Memory:
  - PostgreSQL + pgvector
  - 90-day retention

Hardware:
  - NVIDIA Jetson AGX
  - Intel NCS2
  - Custom build (RTX 3060)

Latency: <50ms
Storage: 1TB NVMe
```

### 17.3 Tier C: Research / SOTA Premium ($15K+)

```
Use Case: Campus, research, production
─────────────────────────────────────────
Perception:
  - GroundingDINO 1.6
  - Full Grounded SAM 2
  - Ensemble face models

Tracking:
  - MOTRv2 (research path)
  - DeepStream MV3DT
  - Multi-camera 3D fusion

Identity:
  - Person ReID (ensemble)
  - Vehicle ReID (dedicated)
  - Plate + contextual

Relation:
  - Semantic tracking summaries
  - Graph-memory relations
  - Active learning loop

Memory:
  - Distributed PostgreSQL
  - 1+ year retention
  - Human verification

Hardware:
  - NVIDIA A100 cluster
  - DeepStream deployment
  - Enterprise networking

Latency: <30ms
Storage: 10TB+ RAID
```

### 17.4 Tier Comparison

| Feature | Tier A | Tier B | Tier C |
|---------|-------|-------|-------|
| Detection | YOLO-small | GroundingDINO | DINO 1.6 |
| Segmentation | None | SAM 2 | SAM 2 full |
| Face Rec | Basic | Full | Ensemble |
| ReID | OSNet-light | OSNet-full | Ensemble |
| Multi-cam | No | Yes | Yes |
| Relations | Basic | Full | +semantic |
| Storage | 7 days | 90 days | 1+ year |
| Latency | <100ms | <50ms | <30ms |
| Cost | $150 | $1.5K | $15K |

---

## 18. Entity Graph Schema (v2.0)

### 18.1 Full Entity Record

```json
{
  "person_id": "prs_017",
  "display_name": "Abhishek Jha",
  "identity_type": "person",
  "face_identity": {
    "label": "Abhishek Jha",
    "confidence": 0.96,
    "embedding_model": "insightface_arcface",
    "embedding": [0.12, -0.34, ...]
  },
  "person_reid": {
    "embedding_model": "osnet",
    "embedding": [0.45, 0.23, ...],
    "last_updated": "2026-04-20T08:12:00Z"
  },
  "attributes": {
    "age_range": "adult",
    "clothing_color": "black",
    "has_bag": true
  },
  "first_seen": "2026-04-01T08:00:00Z",
  "last_seen": "2026-04-20T08:12:00Z",
  "encounter_count": 47
}
```

### 18.2 Vehicle Entity

```json
{
  "vehicle_id": "veh_bike_004",
  "identity_type": "vehicle",
  "vehicle_type": "motorbike",
  "vehicle_reid": {
    "embedding_model": "vehicle-reid-0001",
    "embedding": [0.67, -0.12, ...],
    "last_updated": "2026-04-20T08:12:00Z"
  },
  "plate": {
    "text": "CG04XX1234",
    "confidence": 0.88,
    "ocr_model": "crnn_plate"
  },
  "attributes": {
    "color": "black",
    "make": "Unknown",
    "model": "Unknown"
  },
  "first_seen": "2026-04-15T07:30:00Z",
  "last_seen": "2026-04-20T08:12:00Z",
  "encounter_count": 23
}
```

### 18.3 Relation Record

```json
{
  "relation_id": "rel_001",
  "type": "ARRIVED_ON",
  "subject": "prs_017",
  "object": "veh_bike_004",
  "confidence": 0.84,
  "evidence": [
    {"type": "track_coupling", "confidence": 0.88},
    {"type": "mount_event", "confidence": 0.91},
    {"type": "co_exit", "confidence": 0.82}
  ],
  "first_observed": "2026-04-15T08:00:00Z",
  "last_observed": "2026-04-20T08:12:00Z",
  "occurrence_count": 12,
  "location_ids": ["office_garage", "home_driveway"]
}
```

### 18.4 Complete Event

```json
{
  "event_id": "evt_20260420_081200",
  "type": "RELATION_INFERRED",
  "timestamp": "2026-04-20T08:12:00Z",
  "location_id": "office_garage",
  "primary_entity": {
    "id": "prs_017",
    "display_name": "Abhishek Jha",
    "confidence": 0.96
  },
  "secondary_entities": [
    {
      "id": "veh_bike_004",
      "type": "vehicle",
      "vehicle_type": "motorbike"
    }
  ],
  "relation": {
    "type": "ARRIVED_ON",
    "confidence": 0.84,
    "evidence": ["track_coupling", "mount_event", "co_exit"]
  },
  "source_cameras": ["cam_garage_01", "cam_entrance_01"],
  "confidence": 0.84
}
```

---

## 19. Hard Boundaries

### 19.1 Consent Requirements

| Action | Consent Required |
|--------|---------------|
| Store face embedding | Explicit yes |
| Recognize by name | Enrolled + consent |
| Track across cameras | Opt-in |
| Infer ownership | Repeated evidence |
| Share with 3rd party | Explicit no by default |

### 19.2 Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    HARD BOUNDARIES                       │
├─────────────────────────────────────────────────────────────┤
│ ❌ Biometric storage without consent                     │
│ ❌ Covert surveillance mode                           │
│ ❌ Random person identification                      │
│ ❌ Ownership claims from single encounter              │
│ ❌ Retention without policy                         │
│ ❌ Cloud sync without encryption                     │
│ ❌ Sharing with 3rd parties without consent      │
└─────────────────────────────────────────────────────────────┘
```

### 19.3 Local-First Principles

1. **Process locally** - face embeddings never leave device
2. **Retention limits** - auto-expire after policy duration
3. **Consent-first** - no face stored without explicit consent
4. **Audit everything** - log all identity operations
5. **Soft claims** - confidence-aware with qualifiers

---

**End of Specification (v2.0)**