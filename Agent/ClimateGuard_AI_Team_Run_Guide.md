# ClimateGuard AI
## Team Setup and Run Guide

### 1. What this project does

ClimateGuard AI is a prototype for heat-risk screening and response support. It runs a selected scenario, uses existing project data to produce priority lists for cooling centres and water points, generates an English precautionary advisory, and can record a simulated alert locally.

**Important limitations**
- Scenario multipliers are illustrative assumptions, not calibrated weather forecasts.
- The advisory is preliminary guidance, not an official warning or a substitute for local authorities.
- Alerts are only written to a local log file. No SMS, email, or external alert is sent.
- The workflow evaluation checks software behaviour. It does not prove real-world prediction accuracy.

### 2. Requirements

Install these on the computer that will run the project:

- Windows 10/11
- Python 3.13 (or a compatible version used by the project)
- Git is optional if the project is already downloaded as a ZIP
- Ollama, required only for the AI agent
- The local Ollama model `qwen2.5:1.5b`, required only for the AI agent

The ZIP should include the project source files and required data files, especially the `data` folder. Do not include secrets, API keys, or personal credentials.

### 3. Extract and open the project

1. Extract the ZIP file to a folder, for example `G:\AWS_Hacks\AWS`.
2. Open that extracted folder in VS Code.
3. In VS Code, choose **Terminal → New Terminal**.
4. Confirm the terminal is in the project root, where `climateguard_workflow.py`, `climateguard_agent.py`, and `requirements.txt` are located.

All commands below should be run from this project root.

### 4. Create a virtual environment

In PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation, use this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

If Python 3.13 is not installed, install a Python version compatible with the dependencies, then create the environment with that version.

### 5. Install dependencies

If `requirements.txt` lists all project dependencies:

```powershell
python -m pip install -r requirements.txt
```

If that file does not include the required packages, install the packages actually used by the project. The current agent uses Strands Agents and its Ollama model integration; the workflow also uses the project's optimizer dependencies.

### 6. Run the workflow

Run the workflow evaluation first:

```powershell
python -m py_compile climateguard_workflow.py
python evaluate_climateguard.py
```

Expected result on a correctly configured project: **7 tests pass**. The report is written to:

```text
data\processed\climateguard_evaluation_report.json
```

To run the interactive workflow:

```powershell
python climateguard_workflow.py
```

Enter `baseline`, `heatwave`, or `extreme_heat` when prompted. Press Enter to use the default heatwave scenario.

### 7. Run the AI agent (optional)

Install Ollama from its official website and make sure its local service is running. Then download the model:

```powershell
ollama pull qwen2.5:1.5b
ollama list
```

If Ollama is not running, start the Ollama application or service. Then, in the project virtual environment:

```powershell
python -m pip install "strands-agents[ollama]"
python -m py_compile climateguard_agent.py
python climateguard_agent.py
```

Try prompts such as:
- `Run a heatwave scenario and show the priority areas.`
- `Create an English heatwave safety advisory.`
- `Log a simulated heatwave alert for the response team.`
- `Inspect the optional CSV outputs.`

Type `exit` to close the interactive agent.

**Note:** The agent depends on a local Ollama model, so its first response may take longer. It does not require AWS credentials for the local Ollama configuration.

### 8. Current completed work

- Scenario handling for `baseline`, `heatwave`, and `extreme_heat`.
- Input validation for unsupported scenarios and invalid centre/point counts.
- Priority-output integration through the existing optimizer.
- English-only precautionary advisory generation.
- Local simulated alert logging with explicit `SIMULATED_NOT_SENT` status.
- Optional inspection of processed `T26.csv` and `T27.csv` outputs.
- Workflow evaluation script with 7 functional checks and response-time measurements.
- Local Strands/Ollama agent setup and tool-call counters for four tools, if `climateguard_agent.py` is included and configured as described.

### 9. Evaluation and troubleshooting

**If `ModuleNotFoundError` appears**
- Activate `.venv`.
- Run `python -m pip install -r requirements.txt`.
- Install any missing dependency that is actually used by the failing module.

**If the optimizer cannot find its data**
- Confirm the ZIP includes the required `data` folder and processed input CSV files.
- Run commands from the project root.

**If the agent cannot connect to Ollama**
- Confirm Ollama is installed and running.
- Run `ollama list`.
- Confirm `qwen2.5:1.5b` appears in the model list.
- Check the configured local address: `http://localhost:11434`.

**If a test fails**
- Read the full `[FAIL]` line and traceback/error details.
- Do not edit the test to force a pass; fix the input or implementation issue first.

### 10. Suggested team handoff

1. One team member verifies setup from a clean ZIP extraction.
2. Run `python evaluate_climateguard.py` and save the evaluation report.
3. Test the workflow with all three scenarios.
4. Test each agent prompt and record any wrong tool selections or failures.
5. Keep the README and dependency list updated as the code changes.

---
ClimateGuard AI is a prototype. Validate its data, assumptions, and outputs before any real-world operational use.
