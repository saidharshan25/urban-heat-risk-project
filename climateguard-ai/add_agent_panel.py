from pathlib import Path

path = Path("src/dashboard/static/index.html")
html = path.read_text(encoding="utf-8")

marker = "    <!-- Alert Tier Distribution Cards -->"

if 'id="agent-panel"' in html:
    raise SystemExit("Agent panel already exists; no changes made.")

if html.count(marker) != 1:
    raise SystemExit("Expected insertion marker not found exactly once; no changes made.")

panel = r"""
    <!-- ClimateGuard Agent Panel -->
    <section class="table-card" id="agent-panel" style="margin-bottom: 24px; padding: 24px;">
      <h2>ClimateGuard AI — Agent Control Panel</h2>
      <p style="color: var(--text-secondary); margin-bottom: 18px;">
        Run illustrative heat scenarios, review precautionary advisories, and inspect local planning outputs.
      </p>

      <div class="controls-card" style="margin-bottom: 18px;">
        <div class="filter-group">
          <label class="filter-label" for="agent-scenario">Scenario:</label>
          <select id="agent-scenario">
            <option value="baseline">Baseline</option>
            <option value="heatwave" selected>Heatwave</option>
            <option value="extreme_heat">Extreme heat</option>
          </select>
          <label class="filter-label" for="agent-count">Priorities to show:</label>
          <select id="agent-count">
            <option value="3" selected>3</option>
            <option value="5">5</option>
          </select>
          <button class="btn-reset" id="agent-run">Run scenario</button>
          <button class="btn-reset" id="agent-advisory">Generate advisory</button>
        </div>
      </div>

      <div id="agent-status" role="status" aria-live="polite">
        Agent API status: checking...
      </div>

      <div id="agent-results" style="margin-top: 18px;">
        <p>Run a scenario to view priority areas.</p>
      </div>

      <div style="margin-top: 20px;">
        <h3>Precautionary advisory</h3>
        <p id="agent-advisory-result">No advisory generated yet.</p>
      </div>

      <div style="margin-top: 20px;">
        <h3>Optional planning outputs</h3>
        <button class="btn-reset" id="agent-outputs">Check output files</button>
        <div id="agent-output-result" style="margin-top: 10px;"></div>
      </div>

      <div style="margin-top: 20px;">
        <h3>Simulated response-team alert</h3>
        <p style="color: var(--text-secondary);">
          This only appends a local demonstration record. It never sends an external notification.
        </p>
        <button class="btn-reset" id="agent-alert">Log simulated alert</button>
        <div id="agent-alert-result" role="status" style="margin-top: 10px;"></div>
      </div>

      <p style="margin-top: 18px; font-size: 0.85rem; color: var(--text-secondary);">
        Limitations: scenario multipliers are illustrative, risk scores are preliminary screening indicators,
        and candidate facilities are not confirmed operational cooling centres. This panel is not an official warning.
      </p>
    </section>

"""

path.write_text(html.replace(marker, panel + marker), encoding="utf-8")
print("Inserted Agent Control Panel. Existing forecast content was retained.")
