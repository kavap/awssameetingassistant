"""Role descriptions for meeting participants.

Used to enrich the participants context block injected into Sonnet so the model
understands each person's domain expertise and typical contribution in a meeting.
"""

ROLE_DESCRIPTIONS: dict[str, str] = {
    # -----------------------------------------------------------------------
    # AWS — Sales Motions
    # -----------------------------------------------------------------------
    "AWS Account Manager": (
        "Commercial relationship owner for the account. Manages the customer's AWS "
        "spend and opportunity pipeline, co-sells with partners, tracks EDP/MAP "
        "commitments. Understands customer business priorities and budget cycles but "
        "is not deeply technical. Coordinates the broader AWS team engagement."
    ),
    "AWS Domain Sales Specialist": (
        "Sales specialist owning commercial strategy for a specific domain (e.g., "
        "Data & Analytics, GenAI, Security, Migration). Drives the commercial motion "
        "and co-sells with the account team. Deep knowledge of AWS commercial programs "
        "(EDP, MAP, ISV Accelerate) and competitive landscape within their domain."
    ),

    # -----------------------------------------------------------------------
    # AWS — Solutions Architecture
    # -----------------------------------------------------------------------
    "AWS Account SA": (
        "Primary SA owning the technical relationship for the account. Coordinates "
        "specialist SAs, drives Well-Architected reviews, and owns overall solution "
        "architecture breadth. Go-to for connecting customer requirements to the right "
        "AWS services and escalating to specialist or service teams when needed. "
        "Responsible for technical strategy, blockers, and customer technical success."
    ),
    "AWS Analytics Specialist SA": (
        "Deep expertise in data and analytics architectures. Primary services: Amazon "
        "EMR, AWS Glue, Amazon Athena, Amazon Redshift, AWS Lake Formation, Amazon "
        "Kinesis, Amazon MSK, Amazon QuickSight, AWS Clean Rooms. Called in for data "
        "platform modernization, migration from on-premises Hadoop, Teradata, "
        "Informatica, or Cloudera, building data lakes and lakehouses, and real-time "
        "streaming analytics architectures."
    ),
    "AWS ML Specialist SA": (
        "Expert in machine learning, AI, and generative AI workloads. Primary services: "
        "Amazon SageMaker (Studio, Pipelines, Feature Store, Model Monitor), Amazon "
        "Bedrock (foundation models, RAG, Agents), Amazon Rekognition, Amazon "
        "Comprehend, Amazon Forecast, Amazon Personalize. Focuses on MLOps pipelines, "
        "GenAI patterns, foundation model selection and fine-tuning, responsible AI, "
        "and migrating from on-premises ML infrastructure."
    ),
    "AWS Storage Specialist SA": (
        "Focused on storage architecture, performance, and cost optimization. Primary "
        "services: Amazon S3 (Intelligent-Tiering, lifecycle policies, performance "
        "tuning), Amazon EBS, Amazon EFS, Amazon FSx (Lustre, Windows, NetApp ONTAP, "
        "OpenZFS), AWS Storage Gateway, AWS Backup, AWS DataSync. Handles migration "
        "from on-premises NAS/SAN, tiering strategies, and backup/restore architectures."
    ),
    "AWS Database Specialist SA": (
        "Covers relational and NoSQL database modernization and migration. Primary "
        "services: Amazon RDS, Amazon Aurora (PostgreSQL and MySQL), Amazon DynamoDB, "
        "Amazon ElastiCache, Amazon MemoryDB, Amazon DocumentDB, Amazon Keyspaces, "
        "Amazon Neptune, Amazon QLDB. Focus areas: migration from Oracle, SQL Server, "
        "and open-source databases using DMS and SCT, right-sizing, and cost "
        "optimization of database fleets."
    ),
    "AWS Security Specialist SA": (
        "Deep expertise in cloud security architecture, compliance, and threat "
        "detection. Primary services: AWS IAM, AWS Organizations (SCPs, permission "
        "boundaries), Amazon GuardDuty, AWS Security Hub, AWS WAF, AWS Shield, AWS "
        "KMS, AWS Secrets Manager, Amazon Macie, AWS CloudTrail, Amazon Detective, "
        "AWS Config. Focuses on compliance frameworks (HIPAA, PCI-DSS, SOC2, FedRAMP), "
        "zero-trust architectures, data protection, and incident response."
    ),
    "AWS SA Manager / Leader": (
        "SA manager or principal/distinguished SA providing executive oversight or "
        "senior technical leadership. Joins for strategic accounts, escalations, "
        "executive briefings, or Well-Architected leadership reviews. Helps unblock "
        "internal resources, escalate priority feature requests to service teams, "
        "and set the technical vision for large or complex engagements."
    ),
    "AWS Data and AI Strategist": (
        "Executive-level advisor focused on data strategy and AI/ML adoption roadmaps. "
        "Helps customers define their data platform vision, data governance strategy, "
        "organizational data capabilities, and AI transformation journey. Engages at "
        "CDO/CTO level. More strategic and advisory than hands-on technical — bridges "
        "business value and technical architecture at an executive conversation level."
    ),

    # -----------------------------------------------------------------------
    # AWS — Technical Account Management & Customer Success
    # -----------------------------------------------------------------------
    "AWS TAM": (
        "Technical Account Manager — proactive operational advisor for Enterprise "
        "Support customers. Monitors customer environments, drives operational reviews "
        "(Operations, Security, Reliability), helps prioritize and expedite support "
        "cases, and coordinates service team escalations. Acts as the bridge between "
        "the customer's operational teams and AWS Support/Engineering. Knows the "
        "customer's architecture and operational history deeply."
    ),
    "AWS CSM": (
        "Customer Success Manager — focused on value realization and adoption. Tracks "
        "customer progress against committed business goals, monitors usage of key "
        "services, and coordinates AWS programs, training, and enablement. More "
        "commercially and outcomes-focused than the TAM. Helps customers demonstrate "
        "measurable ROI from their AWS investment and expand adoption strategically."
    ),

    # -----------------------------------------------------------------------
    # AWS — Professional Services
    # -----------------------------------------------------------------------
    "AWS Proserve Architect": (
        "Professional Services technical lead who designs and delivers implementation "
        "projects: cloud migrations, application modernization, data platform builds, "
        "and security remediations. Provides hands-on delivery alongside SA advisory. "
        "Brings ProServe delivery methodology, proven accelerators, and the Migration "
        "Acceleration Program (MAP) framework. Accountable for technical quality of "
        "the delivered solution."
    ),
    "AWS Proserve Engagement Manager": (
        "Professional Services project and program manager. Owns delivery timeline, "
        "scope, budget, and customer stakeholder relationship for ProServe engagements. "
        "Coordinates architect and delivery resources, manages delivery risk, tracks "
        "milestones and change requests. Primary point of contact for the customer's "
        "project management office during a ProServe engagement."
    ),

    # -----------------------------------------------------------------------
    # AWS — Service Teams
    # -----------------------------------------------------------------------
    "AWS Service PM": (
        "Product Manager from a specific AWS service team (e.g., Redshift PM, Bedrock "
        "PM, Glue PM). Represents the service roadmap and capabilities. In customer "
        "meetings to listen to feature requests, validate real-world use cases, and "
        "occasionally preview upcoming capabilities under NDA. Less common in standard "
        "customer meetings — typically engaged for strategic accounts or escalations."
    ),
    "AWS Service Engineer/Architect": (
        "Deep technical expert from an AWS service team (L5+ engineering). Joins for "
        "escalations, deep technical dives, or proof-of-concept support for a specific "
        "service. Has internals knowledge of the service that field SAs typically do "
        "not have. Called in when the customer has hit service limits, edge cases, or "
        "requires hands-on guidance beyond standard SA capability."
    ),

    # -----------------------------------------------------------------------
    # Customer — Executive
    # -----------------------------------------------------------------------
    "Customer CDO/CTO": (
        "Executive technology owner. Sets the data and technology strategy, controls "
        "the technology budget, and makes final architectural and vendor decisions. "
        "Focused on business outcomes, competitive differentiation, total cost, "
        "security/compliance risk, and organizational change. Needs to understand "
        "strategic value and risk — not deep implementation details. Their buy-in "
        "is required for major platform decisions."
    ),
    "Customer VP Engineering": (
        "Leads the engineering organization that will implement and operate the AWS "
        "platform. Concerned with team capabilities and upskilling needs, migration "
        "risk and timeline, operational complexity, developer experience, and "
        "long-term maintainability. Translates the CTO's strategy into engineering "
        "execution. Makes resourcing and build-vs-buy decisions."
    ),
    "Customer Director": (
        "Mid-level management stakeholder — typically Director of Data Engineering, "
        "Director of Platform, or Director of Analytics. Translates executive strategy "
        "into team priorities and delivery plans. Focused on project feasibility, "
        "resourcing, dependencies, and delivery risk. Often the day-to-day decision "
        "maker for the engagement scope and timeline."
    ),

    # -----------------------------------------------------------------------
    # Customer — Technical
    # -----------------------------------------------------------------------
    "Customer Technical Lead": (
        "Senior individual contributor owning the technical design on the customer "
        "side. Acts as the primary technical counterpart to the AWS SA. Has deep "
        "knowledge of the existing architecture, its constraints, and the specific "
        "requirements the solution must meet. Key influencer on architectural "
        "decisions — their technical buy-in is critical for adoption. May also be "
        "a Principal Engineer or Staff Engineer."
    ),
    "Customer Data Engineer": (
        "Hands-on builder of data pipelines, ETL/ELT jobs, and data platform "
        "infrastructure. Deep familiarity with existing tools: Apache Spark, Hadoop, "
        "Airflow, dbt, Kafka, Informatica, or Talend. Will be the primary day-to-day "
        "operator of AWS data services after migration. Needs technical depth on "
        "migration paths, operational patterns, and how AWS services map to their "
        "current toolchain."
    ),
    "Customer Data Scientist": (
        "Builds and trains ML models, runs experiments, and consumes data products. "
        "Focused on: model training environment (GPU access, distributed training), "
        "feature engineering workflows, experiment tracking (MLflow equivalents), "
        "SageMaker Studio usability, access to clean and governed data, and "
        "productionizing models. May be new to cloud-native ML tooling — needs "
        "clear migration path from on-premises Jupyter/Spark ML workflows."
    ),
    "Customer Project Manager": (
        "Manages delivery timeline, stakeholders, budget, and scope on the customer "
        "side. Coordinates between customer engineering teams and the AWS team. "
        "Focused on milestones, dependencies, resource availability, and risk "
        "management rather than technical details. Primary liaison to the AWS "
        "Proserve Engagement Manager when ProServe is engaged."
    ),

    # -----------------------------------------------------------------------
    # Partner
    # -----------------------------------------------------------------------
    "Partner Architect": (
        "Technical lead from an AWS partner (Systems Integrator, ISV, or MSP). "
        "Designs the joint solution alongside the AWS SA and may bring proprietary "
        "accelerators, IP, or pre-built integrations from the partner's AWS practice. "
        "Typically AWS certified with prior delivery experience. Key for understanding "
        "the partner's specific capability gaps and technical contributions to the "
        "engagement."
    ),
    "Partner Delivery Lead": (
        "Owns delivery execution for the partner's workstream. Manages the partner's "
        "delivery team resources, timeline, and quality standards. Coordinates with "
        "AWS ProServe or the customer's PM on integration points, dependencies, and "
        "handoff milestones. Accountable for what the partner commits to deliver."
    ),
    "Partner Practice Lead": (
        "Strategic leader of the partner's AWS practice (e.g., Data & Analytics "
        "Practice Lead, Cloud Migration Practice Lead). Sets the partner's go-to-"
        "market strategy, solution offerings, and investment areas on AWS. Engages "
        "in meetings to align on joint opportunities, co-sell motions, and determine "
        "the level of partner commitment to the engagement."
    ),
}
