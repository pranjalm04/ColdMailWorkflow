# Pranjal Mestry

- Phone: (716) 605-5399
- Location: New York City, NY
- Email: pranjalmestry48@gmail.com
- LinkedIn: https://www.linkedin.com/in/pranjal-mestry
- GitHub: https://github.com/pranjalm04

## Summary

Founding-era Software Engineer at a pre-seed B2B SaaS shipping agentic AI infrastructure for autonomous enterprise ERP workflow execution. 4 years building production backend, distributed systems, and agentic AI infrastructure across fintech, AI/SaaS, and data platforms. Lifted production agentic-workflow success rate from 62% to 88% with a hierarchical FSM and LLM-agent execution engine. IEEE-published on deep-learning network-flow detection. Python, Java, C++, Spark, Kafka, Cassandra, Kubernetes.

## Experience

### Software Engineer II - Happypath (Pre-seed B2B SaaS · 15-engineer team · Agentic AI for autonomous ERP workflow execution)
New York City, NY | Aug 2025 - Present

- Lifted production agentic-workflow success rate from 62% to 88% by architecting a hierarchical FSM (main + sub-FSMs) that orchestrates LLM-driven agents to autonomously navigate enterprise SaaS UIs, decide field values from prior form state, recover from errors via bounded retries with exponential backoff and feedback-loop replay, and enforce role-based stakeholder approval flows.
- Built core modules of the AI-agent execution engine in Python with FastAPI and LLM integration that converts customer natural-language workflow specifications into autonomous browser execution against Microsoft Dynamics 365 and Workday. Team shipped 80% reduction in manual execution effort and 85% scenario completion rate.
- Designed and built a domain-specific language (DSL) over YAML configs that compiles to a DAG, extracting interactable-component metadata from HTML to ground LLM agents during autonomous page execution. Declarative extraction rules drive a DAG runtime that produces structured page representations the agents reason over.
- Owned a custom Chrome DevTools Protocol (CDP) proxy with TCP command multiplexing to Playwright workers, scaling the distributed Chromium cluster to 20+ Chromium instances per node (4x density vs prior architecture) and cutting cluster compute cost by ~60%, with circuit breakers isolating unhealthy workers from the routing pool.
- Built FastAPI REST endpoints for the workflow control plane: a browser-session provisioning API that requests Chromium instances from the cluster manager, a workflow-submission API that enqueues runs onto Celery workers, and a usage-tracking API exposing per-customer compute and session consumption.
- Co-developed the cluster's telemetry and observability service exposing CPU, memory, and session-capacity time-series that drive placement decisions in production and prevent overloaded nodes.

### AI Engineer Intern - PhysicianX
Buffalo, NY | Feb 2025 - May 2025

- Engineered a concurrent web crawler to extract physician jobs from 127k+ healthcare sites, transforming 200k+ pages of unstructured data into structured records stored in DynamoDB; increased platform job inventory by 45k+ and expanded listings by 30%.
- Developed an agentic workflow using LLMs to navigate web pages and convert complex HTML to Markdown; implemented output guardrails to ensure schema accuracy in generated JSON metadata for downstream ingestion.

### Software Engineer - Tata Consultancy Services Pvt. Ltd.
Pune, India | Jul 2021 - Jul 2024

- Cut tax-processing pipeline runtime from 6 hours to 45 minutes (8x speedup) by optimizing SQL query execution plans, introducing geospatial indexing, and implementing batch processing. The reduced pipeline window unlocked real-time integration with GAR partner property data that prior timing made impossible, growing partner-driven revenue by ~25%.
- Built a geocoding ETL pipeline in Apache Airflow with PostGIS, authoring task-level DAGs that ingest GeoJSON polygons and resolve hotel-listing locations to city polygons, tax jurisdictions, regions, and zones, using a KD-tree for point-to-polygon nearest-distance lookups and polygon-shape transformations to handle ambiguous geographic entities.
- Built Jenkins CI/CD pipelines automating full-lifecycle deployment of Apache Airflow DAGs to a GKE-hosted scheduler with quality gates and rollback, enabling continuous, safer pipeline updates.
- Led a 4-engineer team to deliver a green-field GIS platform (TypeScript, React, Spring Boot, PostGIS) from a one-month MVP through production rollout, replacing scheduled batch geographic-entity processing with runtime resolution backed by complex PostGIS queries for analysis and transformation, cutting marketing-offer, regional-discount, and tax-rate reflection latency on Priceline's customer site from scheduled batch windows to real-time, enabling same-day campaign go-live.

## Publications

### Deep Learning-Based Real-Time Malicious Network Traffic Detection for Cyber-Physical Systems
IEEE | Co-author | Python, NumPy, Pandas, CNN, LSTM

- Designed a hybrid 1D CNN + LSTM deep-learning model analyzing network flow in spatial and temporal domains.
- Identified and blocked 85% of malicious traffic attempts in a simulated smart-home cyber-physical-systems environment.

## Projects

### Real-Time Data Ingestion Pipeline (Spark Streaming, Kafka, Cassandra)
PySpark, Spark Structured Streaming, Airflow, Kafka, Docker, Cassandra

- Implemented a real-time ingestion pipeline using Airflow, Kafka, Spark Structured Streaming, and Cassandra.
- Processed 100K+ events per minute with schema validation, replay support, and parallel partition consumption.

### Real-Time Multi-Currency Sales Analytics
Java, Apache Flink, Apache Kafka, Elasticsearch, Docker

- Processed millions of global sales transactions in real-time with Apache Flink, performing asynchronous currency conversion to USD with sub-second latency.
- Populated real-time fact tables (daily, hourly, and individual sales) by transforming high-volume Kafka streams, ensuring data freshness for immediate analysis.
- Integrated real-time sales data into Elasticsearch, enabling interactive Kibana dashboards for instant visualization of KPIs.

### Traffic Monitoring Proxy
C++, TCP/UDP, Prometheus, Grafana

- Built a TCP/UDP proxy in C++ with Prometheus and Grafana monitoring for latency, throughput, and multi-node system-health visualization.
- Systems-level networking and observability owned end-to-end.

## Education

### State University of New York at Buffalo
Master of Science in Information Systems (STEM-Designated) | Buffalo, NY | Jul 2024 - May 2025
Coursework: Distributed Systems, Machine Learning, Data Engineering, Software Architecture, Database Management Systems

### Pune Institute of Computer Technology
Bachelor of Engineering in Electronics and Telecommunications | Pune, India | Aug 2017 - May 2021
Core CS coursework: Data Structures, Algorithms, Operating Systems, Computer Networks, Database Management, Object-Oriented Programming, Computer Architecture

## Skills

- Languages: Python, Java, TypeScript, SQL, C++, Go
- Web Frameworks: FastAPI, Spring Boot, REST APIs
- AI / LLM: Agentic Workflows, RAG, LangChain, LangGraph, FSM Orchestration, Output Guardrails, Schema Validation, Prompt Engineering
- Backend & Distributed Systems: Microservices, Multi-Threading, Concurrent Programming, Performance Optimization, TCP/UDP Networking
- Big Data & Streaming: Apache Spark, Spark Structured Streaming, Apache Flink, Apache Airflow, Apache Kafka, Celery
- Databases: Cassandra, DynamoDB, Redis, Elasticsearch, SQL (Postgres/MySQL)
- DevOps & Cloud: Docker, Kubernetes (GKE), Jenkins CI/CD, Prometheus, Grafana, Linux, AWS (S3, DynamoDB), GCP
- Frontend: React, TypeScript
- AI-Native Tooling: Claude Code, Playwright
