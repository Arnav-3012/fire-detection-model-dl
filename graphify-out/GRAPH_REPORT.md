# Graph Report - firewatch  (2026-08-18)

## Corpus Check
- 10 files · ~12,974 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 207 nodes · 204 edges · 54 communities (24 shown, 30 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 22 edges (avg confidence: 0.9)
- Token cost: 108,272 input · 0 output

## Community Hubs (Navigation)
- Edge Loop Architecture
- Camera Smoke Test & Env Setup
- Agent Tools & Cut List
- Agent Response Graph (LangGraph)
- Corrected System Architecture
- Conda Env & Setup Scripts
- Model Quality Bars & Datasets
- Sensor Hardware & Pin Map
- MQ Calibration & Safety Framing
- Vision Inference Pipeline
- Sensor Config Thresholds
- Simulated Dispatch & Cloud Upload
- verify_env.py Internals
- Vision Config Thresholds
- Phase 0 Setup Log
- Location Config
- Adversarial Eval Scenarios
- test_camera.py Internals
- Fusion Config
- info.md Session Protocol
- config.yaml Principle
- Evaluation Output
- Hardware Safety Rules
- Offline Test Requirement
- Hardware BOM
- Core Deliverable & Demo
- setup.sh
- Commit Conventions
- Failure Behaviour Table
- logs.md Protocol
- No Fabricated Metrics Rule
- No Secrets Rule
- Quality Bars Overview
- Scope Discipline Rule
- Code Style Standards
- Testing Requirement Rule
- When to Stop and Ask
- Project State Table
- Hardware Primer Appendix
- Arduino Uno
- .env Specification
- FireWatch Plan Title
- Day 0 Action List
- Hardware Order List
- Scope Exclusions
- Sensor Data Collection Plan
- Software Milestones

## God Nodes (most connected - your core abstractions)
1. `Repository Structure` - 14 edges
2. `Corrected Architecture (8 revisions)` - 9 edges
3. `Tool Choices Table` - 9 edges
4. `edge/main.py (full loop)` - 7 edges
5. `LangGraph Nodes (verify/locate/compose/notify_owner/wait/escalate/simulate)` - 7 edges
6. `sensors config section` - 6 edges
7. `vision config section` - 5 edges
8. `main()` - 5 edges
9. `edge/vision.py` - 5 edges
10. `Groq (llama-3.1-8b-instant)` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Fire Recall Prioritised Over Everything Else` --semantically_similar_to--> `Stove Flame Labelled Fire, Fusion Resolves Hazard`  [INFERRED] [semantically similar]
  info.md → plan.md
- `Phase 0b: switch LLM from Claude/anthropic SDK to Groq/llama-3.1-8b-instant` --rationale_for--> `Groq (llama-3.1-8b-instant)`  [EXTRACTED]
  context.md → plan.md
- `MQ Calibration Procedure` --references--> `MQ-2 Burn-in Procedure`  [INFERRED]
  plan.md → context.md
- `Local Alarm Fires Before the Network is Touched` --rationale_for--> `edge/main.py (full loop)`  [INFERRED]
  info.md → plan.md
- `Cut List Authority` --references--> `Cut List`  [INFERRED]
  info.md → plan.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Offline-first Local Detection and Fusion Flow** — info_md_local_alarm_before_network, plan_md_edge_main_py, plan_md_fuse_function, info_md_offline_test, plan_md_demo_moment [INFERRED 0.85]
- **Agent Response Pipeline (verify to simulate)** — plan_md_langgraph_nodes, plan_md_compose_node_impl, plan_md_notify_owner_node, plan_md_wait_node, plan_md_escalate_node, plan_md_simulate_node [EXTRACTED 0.95]
- **Phase 0 Sub-phases (scaffold through camera test)** — logs_md_phase_0_scaffold_config, logs_md_phase_0b_provider_swap, logs_md_phase_0c_env_created, logs_md_phase_0d_verify_env, logs_md_phase_0e_setup_scripts, logs_md_phase_0f_camera_smoke_test [EXTRACTED 0.90]

## Communities (54 total, 30 thin omitted)

### Community 0 - "Edge Loop Architecture"
Cohesion: 0.14
Nodes (20): edge/main.py, Local Alarm Fires Before the Network is Touched, arduino/sensor_node.ino, Build Order H1-H9, Camera class, Claude Code Prompts Per Phase, dashboard/app.py, Day 0 Scaffold Prompt (+12 more)

### Community 1 - "Camera Smoke Test & Env Setup"
Cohesion: 0.11
Nodes (17): Phase 0f: scripts/test_camera.py kept out of edge/, scripts/test_camera.py, Leftover anthropic package, Phase 0c — Project environment created, Phase 0d — verify_env.py written and passed, Phase 0f — Camera smoke test, fastapi, langchain-core (+9 more)

### Community 2 - "Agent Tools & Cut List"
Cohesion: 0.19
Nodes (13): Cut List Authority, agent/tools.py, Cut List, find_nearest_fire_station(), Google Colab (free T4), Groq (llama-3.1-8b-instant), MobileNetV3-Small, OSM Overpass API (+5 more)

### Community 3 - "Agent Response Graph (LangGraph)"
Cohesion: 0.20
Nodes (11): compose node, The LLM Never Decides Whether There Is a Fire, agent/graph.py, agent/server.py, compose node implementation, escalate node, LangGraph, LangGraph Nodes (verify/locate/compose/notify_owner/wait/escalate/simulate) (+3 more)

### Community 4 - "Corrected System Architecture"
Cohesion: 0.20
Nodes (10): Agent Handles Response Only, Never Detection, Camera plus Gas Sensor Fusion, Corrected Architecture (8 revisions), FireWatch, Hardcoded Coordinates, GPS Optional, Laptop as Edge Device (Pi optional stretch), Local Edge Inference (model runs on edge, cloud logs/retrains only), Fine-tune Pretrained MobileNetV3-Small (+2 more)

### Community 5 - "Conda Env & Setup Scripts"
Cohesion: 0.20
Nodes (10): firewatch conda environment, Phase 0c: conda rather than venv for dev environment, Phase 0d: verify_env.py import-name mapping as explicit dict, Phase 0e: setup.sh/setup.ps1 build venv not conda, setup.ps1, setup.sh, verify_env.py, Phase 0e — Portable setup scripts and scripts/verify_env.py (+2 more)

### Community 6 - "Model Quality Bars & Datasets"
Cohesion: 0.24
Nodes (10): Fire Recall Prioritised Over Everything Else, Model Quality Bar (3-class classifier), BoWFire Dataset, 3-Class Design (neutral/smoke/fire), Data Collection Plan, D-Fire Dataset, FIRE Dataset (Kaggle), Hard Negatives (+2 more)

### Community 7 - "Sensor Hardware & Pin Map"
Cohesion: 0.22
Nodes (10): Active Buzzer 5V, Appendix B — Troubleshooting, Burn-in Rationale (24-48h drift), DHT22 (Temp + Humidity), MQ-135 Air Quality Module, MQ-2 Gas/Smoke Module, How an MQ Sensor Actually Works (SnO2 mechanism), Arduino Uno Pin Map (+2 more)

### Community 8 - "MQ Calibration & Safety Framing"
Cohesion: 0.25
Nodes (9): MQ-2 Burn-in Procedure, Live Values Table, Appendix C — Report Checklist, BNS §217 (False Emergency Reporting Offence), What Changed From the Original Idea (8 revisions), eval/calibrate_mq.py, mq2_danger formula, mq2_warn formula (+1 more)

### Community 9 - "Vision Inference Pipeline"
Cohesion: 0.29
Nodes (8): edge/vision.py, eval/run_eval.py, models/fire_mnv3.onnx, ONNX Runtime, Temporal Smoothing Rule (N-of-M voting), TemporalVoter class, train/export_onnx.py, VisionModel class

### Community 10 - "Sensor Config Thresholds"
Cohesion: 0.29
Nodes (7): sensors config section, baud (9600), mq135_warn (PLACEHOLDER 300), mq2_danger (PLACEHOLDER 600), mq2_warn (PLACEHOLDER 300), serial_port (NOT SET), temp_rise_rate (PLACEHOLDER 2.0)

### Community 11 - "Simulated Dispatch & Cloud Upload"
Cohesion: 0.29
Nodes (6): No Real Emergency Dispatch, Ever, AWS S3, cloud/uploader.py, log_incident(), simulate node, boto3

### Community 12 - "verify_env.py Internals"
Cohesion: 0.48
Nodes (6): check_config_yaml(), check_package(), check_python_version(), main(), print_table(), Environment verification for FireWatch. Imports every major dependency from…

### Community 13 - "Vision Config Thresholds"
Cohesion: 0.33
Nodes (6): vision config section, frame_threshold (tau, 0.70), input_size (224), model_path (models/fire_mnv3.onnx), votes_needed (N, 5), window (M, 8 frames)

### Community 14 - "Phase 0 Setup Log"
Cohesion: 0.33
Nodes (6): Phase 0b: switch LLM from Claude/anthropic SDK to Groq/llama-3.1-8b-instant, D-Fire Dataset Not Downloaded, Phase 0 — Project setup, Phase 0 — Scaffold and config, Phase 0b — Provider swap: Anthropic to Groq, Telegram Bot Not Created

### Community 15 - "Location Config"
Cohesion: 0.50
Nodes (4): location config section, address (NOT SET), latitude (PLACEHOLDER 0.0), longitude (PLACEHOLDER 0.0)

### Community 16 - "Adversarial Eval Scenarios"
Cohesion: 0.67
Nodes (3): Adversarial False Positives Quality Bar (Day 5), Candle Known Limitation (fusion resolves, vision alone cannot), Test Videos

## Ambiguous Edges - Review These
- `Phase 0d — verify_env.py written and passed` → `Phase 0f — Camera smoke test`  [AMBIGUOUS]
  logs.md · relation: references

## Knowledge Gaps
- **67 isolated node(s):** `fusion config section`, `input_size (224)`, `frame_threshold (tau, 0.70)`, `model_path (models/fire_mnv3.onnx)`, `votes_needed (N, 5)` (+62 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **30 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Phase 0d — verify_env.py written and passed` and `Phase 0f — Camera smoke test`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **Why does `Repository Structure` connect `Edge Loop Architecture` to `Agent Tools & Cut List`, `Agent Response Graph (LangGraph)`, `Model Quality Bars & Datasets`, `Vision Inference Pipeline`, `Simulated Dispatch & Cloud Upload`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `edge/vision.py` connect `Vision Inference Pipeline` to `Edge Loop Architecture`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `Streamlit` connect `Agent Tools & Cut List` to `Edge Loop Architecture`, `Camera Smoke Test & Env Setup`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **What connects `fusion config section`, `input_size (224)`, `frame_threshold (tau, 0.70)` to the rest of the system?**
  _67 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Edge Loop Architecture` be split into smaller, more focused modules?**
  _Cohesion score 0.1368421052631579 - nodes in this community are weakly interconnected._
- **Should `Camera Smoke Test & Env Setup` be split into smaller, more focused modules?**
  _Cohesion score 0.1111111111111111 - nodes in this community are weakly interconnected._