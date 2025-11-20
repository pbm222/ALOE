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
