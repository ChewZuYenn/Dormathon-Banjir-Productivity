extends Node
## Shared display contract. This node never performs accounting itself.
signal agent_changed(agent_name: String, state: Dictionary)
signal current_step_changed(step: String)

const AGENTS := ["Secretary", "Logistics", "Financial"]
const VALID_STATUSES := ["idle", "working", "done", "error"]
var states: Dictionary = {}
var current_step: String = "等待任务"

func _ready() -> void:
    reset_agents()

func set_agent_status(agent_name: String, status: String, step: String = "") -> bool:
    if agent_name not in AGENTS or status not in VALID_STATUSES:
        return false
    states[agent_name] = {"status": status, "step": step}
    agent_changed.emit(agent_name, states[agent_name].duplicate())
    return true

func set_current_step(step: String) -> void:
    current_step = step
    current_step_changed.emit(step)

func get_agent_state(agent_name: String) -> Dictionary:
    return states.get(agent_name, {}).duplicate()

func reset_agents() -> void:
    for agent in AGENTS:
        set_agent_status(agent, "idle", "等待执行")
    set_current_step("等待任务")

func apply_snapshot(snapshot: Dictionary) -> bool:
    var agents: Variant = snapshot.get("agents")
    if not agents is Dictionary:
        return false
    # Validate before changing anything, so malformed data cannot partly update UI.
    for agent in AGENTS:
        var item: Variant = agents.get(agent)
        if not item is Dictionary or item.get("status", "") not in VALID_STATUSES or not item.get("step", "") is String:
            return false
    for agent in AGENTS:
        set_agent_status(agent, str(agents[agent]["status"]), str(agents[agent].get("step", "")))
    set_current_step(str(snapshot.get("current_step", "")))
    return true
