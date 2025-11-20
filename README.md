ALOE (Adaptive Log Orchestration Engine)

ALOE is a multi-agent system that helps teams review backend logs more intelligently.
It uses LLM agents that work together guided by an Orchestrator that decides what should happen during each run.

**Components:**
1. Log Preprocessor
- Collects raw logs from ElasticSearch via API
- Normalizes fields (service, class, message, timestamp)
- Clusters similar logs together

2. Triage Agent (LLM-based)
- Classifies each cluster (internal error, timeout, noise, etc.)
- Assigns severity, priority, and confidence
- Extracts service name, Java class, and stack excerpt

3. Summary Builder
- Aggregates triage results
- Counts errors by type, priority, and severity
- Creates a compact summary for the orchestrator

4. Orchestrator Agent (LLM-based)
- Reads full triage, summary, past feedback
- Decides which agents to run
- Selects which clusters deserve Jira tickets
- Optimizes between ticketing, filtering, and documentation

5. JiraDrafts Agent (LLM-based)
- Takes clusters selected by the orchestrator
- Generates clean Jira ticket drafts using the template

6. FilterSuggestions Agent (LLM-based)
- Proposes KQL filters for recurring noise or external-service issues

7. ConfluenceDraft Agent (LLM-based)
- Produces a Markdown summary of the log review session to include on teams's Confluence page (includes key findings, tickets, and suggested filters)

8. Feedback Review Tool
- Lets humans approve/reject Jira drafts
- Saves feedback linked by stable cluster signature
- Guides future orchestrator decisions

  run  ```python app.py review_jira```


Example:
```Running full ALOE pipeline with LLM orchestration...

Step 1: Log Preprocessor Agent
Preprocessing logs from output/logs.json
Saved 100 normalized logs → output/raw_logs.json
Saved 38 clusters → output/clusters.json
Preprocessed 100 logs

Step 2: LLM Triage Agent
Triaged 38 clusters

Step 3: Build summary for Orchestrator
Summary: {'log_count': 100, 'cluster_count': 38, 'triaged_cluster_count': 38, 'by_label': {'internal_error': 24, 'noise': 1, 'external_service': 13}, 'by_priority': 
{'high': 13, 'low': 1, 'medium': 24}, 'internal_high_count': 13}

Step 4: LLM Orchestrator Agent
Orchestrator plan: {'actions': [{'agent': 'JiraDrafts', 'run': False, 'cluster_indices': []}, {'agent': 'FilterSuggestions', 'run': False, 'for_labels': ['timeout', 
'external_service', 'noise'], 'min_count': None}, {'agent': 'ConfluenceDraft', 'run': False, 'include_sections': ['summary']}], 'global_policy': {}, 'reason': 'no reason 
provided'}

Step 5: Executing plan
Skipping JiraDrafts as per orchestrator plan
Skipping FilterSuggestions as per orchestrator plan
Skipping ConfluenceDraft as per orchestrator plan
Pipeline finished.
{
    'summary': {
        'log_count': 100,
        'cluster_count': 38,
        'triaged_cluster_count': 38,
        'by_label': {'internal_error': 24, 'noise': 1, 'external_service': 13},
        'by_priority': {'high': 13, 'low': 1, 'medium': 24},
        'internal_high_count': 13
    },
    'plan': {
        'actions': [
            {'agent': 'JiraDrafts', 'run': False, 'cluster_indices': []},
            {'agent': 'FilterSuggestions', 'run': False, 'for_labels': ['timeout', 'external_service', 'noise'], 'min_count': None},
            {'agent': 'ConfluenceDraft', 'run': False, 'include_sections': ['summary']}
        ],
        'global_policy': {},
        'reason': 'no reason provided'
    },
    'results': {}
}
```

