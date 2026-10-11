\# ClimateGuard AI



ClimateGuard AI is a project for exploring urban heat risk, forecast-based risk classification, and cooling-centre accessibility.



\## Features



\- Heat-hazard and forecast-risk calculations

\- Weather data ingestion and quality checks

\- Dashboard for displaying project results

\- Cooling-centre accessibility analysis, where supported by the available data

\- Agent-assisted advisory features, subject to the configured API integration



\## Requirements



\- Python installed

\- Project dependencies listed in `requirements.txt`



\## Local Setup



1\. Open a terminal in the project directory.

2\. Create and activate a Python virtual environment if you do not already have one.

3\. Install dependencies:



&#x20;  ```powershell

&#x20;  python -m pip install -r requirements.txt

&#x20;  ```



4\. Run the project's tests:



&#x20;  ```powershell

&#x20;  python -m unittest discover -s tests -t . -v

&#x20;  ```



\## Testing



The test suite includes tests for the dashboard, forecast risk service, heat-hazard engine, ingestion integration, and ingestion quality.



\## Configuration and Security



\- Keep API keys and credentials out of source control.

\- Store secrets in environment variables or a suitable secrets manager.

\- Document required configuration variables before running external integrations.

\- Do not commit `.env` files containing real secrets.



\## Risk Classification Disclaimer



Risk categories and thresholds must be documented with their sources. Project-defined thresholds should not be represented as official meteorological warnings unless independently validated against an authoritative source.



\## Deployment Status



Deployment has not been approved as part of this preparation process. Verify configuration, security, tests, and rollback procedures before any deployment.



