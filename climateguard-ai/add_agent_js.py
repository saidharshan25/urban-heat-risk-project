from pathlib import Path
import shutil

path = Path("src/dashboard/static/index.html")
backup = Path("src/dashboard/static/index.html.before-agent-js-backup")

html = path.read_text(encoding="utf-8")
marker = "</script>"

if '/* CLIMATEGUARD_AGENT_API_INTEGRATION */' in html:
    raise SystemExit("Agent JavaScript already exists; no changes made.")

if html.count(marker) != 1:
    raise SystemExit("Expected one closing script tag; no changes made.")

if 'id="agent-panel"' not in html:
    raise SystemExit("Agent panel is missing; no changes made.")

if not backup.exists():
    shutil.copy2(path, backup)

js = r"""
/* CLIMATEGUARD_AGENT_API_INTEGRATION */
(() => {
  const API = "http://127.0.0.1:8081";
  const $ = (id) => document.getElementById(id);

  const status = $("agent-status");
  const results = $("agent-results");
  const advisoryResult = $("agent-advisory-result");
  const outputResult = $("agent-output-result");
  const alertResult = $("agent-alert-result");

  if (!status || !results || !advisoryResult || !outputResult || !alertResult) {
    return;
  }

  const selectedScenario = () => $("agent-scenario").value;
  const selectedCount = () => Number($("agent-count").value);

  function addText(parent, tag, text, className) {
    const element = document.createElement(tag);
    element.textContent = text == null ? "" : String(text);
    if (className) element.className = className;
    parent.appendChild(element);
    return element;
  }

  async function request(path, options = {}) {
    const response = await fetch(API + path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {})
      }
    });

    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error("The Agent API returned an unreadable response.");
    }

    if (!response.ok) {
      throw new Error(
        typeof payload.detail === "string"
          ? payload.detail
          : "Request failed with HTTP " + response.status
      );
    }
    return payload;
  }

  function showError(target, error) {
    target.replaceChildren();
    addText(target, "p", error.message || String(error));
  }

  function formatNumber(value, digits = 1) {
    if (value === null || value === undefined || value === "") return "Unknown";
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "Unknown";
  }

  function renderPriorities(container, title, items, count) {
    addText(container, "h3", title);
    if (!Array.isArray(items) || items.length === 0) {
      addText(container, "p", "No priority records were returned.");
      return;
    }

    const list = document.createElement("div");
    list.style.display = "grid";
    list.style.gap = "12px";

    items.slice(0, count).forEach((item, index) => {
      const card = document.createElement("article");
      card.style.padding = "14px";
      card.style.border = "1px solid var(--border-color, #777)";
      card.style.borderRadius = "10px";

      addText(card, "h4", (index + 1) + ". " + (item.h3_id || "Area ID unavailable"));
      addText(card, "p", "Risk category: " + (item.risk_category ?? "Unknown"));
      addText(card, "p", "Risk score: " + formatNumber(item.risk_score, 2));
      addText(card, "p", "Vulnerable population: " + formatNumber(item.vulnerable_population, 0));
      addText(card, "p", "Nearest cooling walk distance: " + formatNumber(item.nearest_cooling_walk_m, 0) + " m");
      addText(card, "p", "Access status: " + (item.access_status ?? "Unknown"));

      list.appendChild(card);
    });

    container.appendChild(list);
  }

  async function checkHealth() {
    try {
      const data = await request("/api/agent/health");
      status.textContent = "Agent API: " + data.status +
        " — external notifications: " +
        (data.external_notifications ? "enabled" : "disabled");
    } catch {
      status.textContent =
        "Agent API unavailable. Start agent_api.py with Uvicorn on port 8081.";
    }
  }

  async function runScenario() {
    results.replaceChildren();
    addText(results, "p", "Running scenario...");
    try {
      const data = await request("/api/agent/scenario", {
        method: "POST",
        body: JSON.stringify({
          scenario: selectedScenario(),
          cooling_centres: selectedCount(),
          water_points: selectedCount()
        })
      });

      results.replaceChildren();
      addText(results, "h3", "Scenario: " + (data.scenario || selectedScenario()));
      addText(results, "p", "Scenario multiplier: " + formatNumber(data.scenario_multiplier, 2));
      addText(results, "p", "Hexagons analysed: " + formatNumber(data.total_hexagons, 0));
      addText(results, "p", "Underserved hexagons: " + formatNumber(data.underserved_hexagons, 0));
      if (data.assumption) addText(results, "p", "Assumption: " + data.assumption);

      renderPriorities(
        results, "Cooling-centre priorities",
        data.cooling_centre_priorities, selectedCount()
      );
      renderPriorities(
        results, "Water-point priorities",
        data.water_point_priorities, selectedCount()
      );

      if (Array.isArray(data.warnings) && data.warnings.length) {
        addText(results, "h4", "Warnings and limitations");
        data.warnings.forEach((warning) => addText(results, "p", warning));
      }
    } catch (error) {
      showError(results, error);
    }
  }

  async function generateAdvisory() {
    advisoryResult.textContent = "Generating preliminary advisory...";
    try {
      const data = await request("/api/agent/advisory", {
        method: "POST",
        body: JSON.stringify({ scenario: selectedScenario() })
      });
      advisoryResult.textContent =
        (data.status ? "[" + data.status + "] " : "") +
        (data.advisory || "No advisory text returned.");
    } catch (error) {
      advisoryResult.textContent = error.message || String(error);
    }
  }

  async function checkOutputs() {
    outputResult.replaceChildren();
    addText(outputResult, "p", "Checking output files...");
    try {
      const data = await request("/api/agent/outputs");
      outputResult.replaceChildren();
      const outputs = Array.isArray(data.outputs) ? data.outputs : [];
      outputs.forEach((entry) => {
        String(entry).split(/\r?\n/).forEach((line) => {
          if (line.trim()) addText(outputResult, "p", line);
        });
      });
    } catch (error) {
      showError(outputResult, error);
    }
  }

  async function logAlert() {
    alertResult.textContent = "Logging simulated alert...";
    try {
      const data = await request("/api/agent/alert", {
        method: "POST",
        body: JSON.stringify({
          scenario: selectedScenario(),
          audience: "response_team"
        })
      });
      alertResult.textContent =
        "Status: " + (data.status || "unknown") +
        ". External notification sent: " +
        (data.external_notification_sent ? "Yes" : "No") +
        (data.log_file ? ". Local log: " + data.log_file : "");
    } catch (error) {
      alertResult.textContent = error.message || String(error);
    }
  }

  $("agent-run").addEventListener("click", runScenario);
  $("agent-advisory").addEventListener("click", generateAdvisory);
  $("agent-outputs").addEventListener("click", checkOutputs);
  $("agent-alert").addEventListener("click", logAlert);

  checkHealth();
})();
"""

path.write_text(html.replace(marker, js + "\n" + marker), encoding="utf-8")
print("Agent API JavaScript inserted.")
print("Backup:", backup)
