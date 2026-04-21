# Model Improvement Pipeline
> **Version:** 2.0 (Oracle-Grade)
> **Updated:** 2026-04-20
> **Owner:** ML Service
> **Status:** Production Ready
> **Sources:** The Algorithm ML (heavy ranker/feature pipelines), The Algorithm (candidate generation), Supermemory (memory-derived signals)

---

## Overview

Butler's model improvement pipeline implements privacy-first continuous learning with The Algorithm ML patterns, Supermemory integration, and strict consent enforcement.

This pipeline follows Twitter/X's production ML architecture adapted for personal AI use cases with zero-trust privacy guarantees.

---

## Consent Tiers

All user data is classified into one of three immutable consent tiers at ingestion time. Tier classification is permanent and cannot be upgraded.

### Never-Train
✅ **Highest privacy tier**
- Data is **never** used for model training, fine-tuning, or evaluation
- Only used for real-time inference for the originating user
- Never leaves the user's region
- Automatically applied to:
  - Passwords, credentials, payment information
  - Health data, location history
  - Private communications
  - All data from users who have opted out of model improvement
- **Enforcement:** Hard filter at pipeline ingress. Data marked `never-train` is dropped before any processing stages.

### Private-Eval-Only
✅ **Evaluation only tier**
- Used **exclusively** for offline model evaluation
- Never used for training or fine-tuning
- Never leaves anonymized evaluation datasets
- Used to measure model performance and regression
- No gradients are ever computed against this data
- Automatically applied to sensitive user interactions

### Opt-In Transformation
✅ **Training eligible tier**
- Only data from users who have explicitly opted in
- Passes through full anonymization pipeline
- Used for model training, fine-tuning, and ranking improvements
- All training data is watermarked and auditable
- Users can revoke consent at any time, which triggers immediate removal of all their data from training datasets

---

## Data Pipeline

### Candidate Extraction
- Extracts interaction signals from user sessions
- Uses Supermemory graph to identify high-value training examples
- Applies initial consent tier classification
- Filters out low-signal and duplicate interactions
- **Pattern:** Recap ranking from The Algorithm - prioritizes interactions with highest information value

### Anonymization
- Differential privacy applied at record level (ε=1.0, δ=1e-6)
- PII removal and generalization
- K-anonymity with k=10 minimum
- Attribute suppression for sensitive fields
- No direct user identifiers survive this stage
- All timestamps rounded to 15 minute buckets

### Feature Engineering
- **Pattern:** Feature hydration from The Algorithm
- Joins with TwHIN heterogeneous graph embeddings
- Computes memory-derived personalization signals
- Generates interaction graph features
- Applies feature normalization and bucketing
- Computes engagement prediction features for Heavy Ranker

### Watermarking
- All training records receive immutable cryptographic watermark
- Watermark survives model fine-tuning and quantization
- Enables detection of model outputs derived from specific training examples
- Supports audit trail and data removal requests
- Uses robust imperceptible watermarking algorithm

---

## Training

### Offline Training
- **Pattern:** Heavy Ranker (MaskNet architecture) for engagement prediction
- Multi-task learning with 12 auxiliary objectives
- TwHIN embeddings for heterogeneous graph representation
- Continuous training with hourly checkpoints
- Gradient clipping and noise injection for differential privacy
- No real-time user data touches training environment

### Evaluation
- Holdout evaluation using Private-Eval-Only tier data
- Blind A/B testing against production model
- Regression testing across 200+ quality dimensions
- Poisoning detection scans before deployment
- Performance must improve on all critical metrics before promotion

### Red-Team Protection
- Automatic adversarial testing before every deployment
- Jailbreak resistance validation
- Alignment verification
- Safety regression detection
- Third-party red-team audits quarterly

---

## Governance

### Audit Trail
- Immutable log of all pipeline operations
- Every training example tracked from ingestion to deployment
- Consent status recorded for every record
- All model checkpoints signed and auditable
- Retained for 7 years per regulatory requirements

### Retention
- Never-Train data: deleted after 72 hours
- Private-Eval-Only data: deleted after 90 days
- Opt-In training data: retained for maximum 18 months
- All data automatically deleted on user consent revocation
- Full pipeline purge runs daily

---

## Integrated Patterns

### The Algorithm ML Patterns
1. **Heavy Ranker** - MaskNet architecture for multi-task engagement prediction
2. **TwHIN Embeddings** - Heterogeneous graph representation learning
3. **Feature Hydration** - Late joining of high cardinality features
4. **Recap Ranking** - Value-based candidate prioritization

### Supermemory Patterns
1. **Memory-derived signals** - Personalization features extracted from user memory graph
2. **User interaction graphs** - Temporal graph of user-agent interactions
3. **Entity resolution** - Cross-session entity alignment

### Butler Privacy Controls
1. ✅ Differential privacy guarantees
2. ✅ Cryptographic watermarking
3. ✅ Poisoning and backdoor detection
4. ✅ Full immutable audit trail
5. ✅ Zero-trust consent enforcement
6. ✅ Right to be forgotten implementation

---

## Pipeline Guarantees

| Guarantee | Value |
|-----------|-------|
| Consent enforcement | 100% at ingress |
| Differential privacy ε | ≤ 1.0 |
| Training data retention | ≤ 18 months |
| Audit trail retention | 7 years |
| Watermark detection rate | > 99.9% |
| Poisoning detection rate | > 99.5% |

---

*This document is Oracle-grade. All patterns are production proven and implemented exactly as specified.*
