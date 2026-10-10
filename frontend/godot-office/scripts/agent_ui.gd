extends CanvasLayer
## Three status cards below the office; task bar stays over the scene's lower edge.
var store: Node
var client: Node
var cards: Dictionary = {}
var current_label: Label
var connection_label: Label
var result_label: Label
var goal_input: LineEdit
var run_button: Button
var mock_button: Button
var connect_button: Button
var demo_running := false
var root_control: Control

const INK := Color("343e34")
const MUTED := Color("6e7567")
const STATE_COLORS := {"idle": Color("7f8978"), "working": Color("b87932"), "done": Color("3e795d"), "error": Color("b85550")}
const STATE_LABELS := {"idle": "Idle", "working": "Working", "done": "Done (code)", "error": "Error"}

func _ready() -> void:
    store = get_node("../AgentState")
    client = get_node("../AgentClient")
    _build()
    store.agent_changed.connect(_update_card)
    store.current_step_changed.connect(func(step: String): current_label.text = "Current step  ·  " + step)
    client.connection_changed.connect(_connection)
    client.job_finished.connect(_finished)
    client.job_failed.connect(_failed)
    for name in store.AGENTS:
        _update_card(name, store.get_agent_state(name))
    get_viewport().size_changed.connect(_layout)
    _layout()

func _style(color: Color, radius: int = 14) -> StyleBoxFlat:
    var box := StyleBoxFlat.new()
    box.bg_color = color
    box.corner_radius_top_left = radius
    box.corner_radius_top_right = radius
    box.corner_radius_bottom_left = radius
    box.corner_radius_bottom_right = radius
    box.content_margin_left = 16
    box.content_margin_right = 16
    box.content_margin_top = 12
    box.content_margin_bottom = 12
    return box

func _label(text: String, size: int, color: Color = INK) -> Label:
    var node := Label.new()
    node.text = text
    node.add_theme_font_size_override("font_size", size)
    node.add_theme_color_override("font_color", color)
    return node

func _button(text: String) -> Button:
    var node := Button.new()
    node.text = text
    node.add_theme_font_size_override("font_size", 16)
    node.add_theme_color_override("font_color", INK)
    node.add_theme_stylebox_override("normal", _style(Color("e8e8d9"), 10))
    node.add_theme_stylebox_override("hover", _style(Color("f6f4e8"), 10))
    node.add_theme_stylebox_override("pressed", _style(Color("d9dfcc"), 10))
    return node

func _build() -> void:
    root_control = Control.new()
    root_control.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    root_control.mouse_filter = Control.MOUSE_FILTER_IGNORE
    add_child(root_control)
    var heading := _label("Little Office  /  Month-end close agents", 25)
    heading.position = Vector2(38, 22)
    root_control.add_child(heading)
    var caption := _label("Local 3D scene  ·  structured test data  ·  no auto-payment / no email sending", 15, MUTED)
    caption.position = Vector2(38, 59)
    root_control.add_child(caption)
    connection_label = _label("Bridge not connected · try the UI simulation", 15, MUTED)
    connection_label.name = "ConnectionLabel"
    root_control.add_child(connection_label)

    var bar := PanelContainer.new()
    bar.name = "TaskBar"
    bar.add_theme_stylebox_override("panel", _style(Color("f6f3e9")))
    root_control.add_child(bar)
    var row := HBoxContainer.new()
    row.add_theme_constant_override("separation", 10)
    bar.add_child(row)
    goal_input = LineEdit.new()
    goal_input.text = "Close out September"
    goal_input.placeholder_text = "Enter a closing goal"
    goal_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    goal_input.add_theme_font_size_override("font_size", 17)
    goal_input.add_theme_color_override("font_color", INK)
    goal_input.add_theme_stylebox_override("normal", _style(Color("fffdf5"), 9))
    row.add_child(goal_input)
    connect_button = _button("Connect bridge")
    connect_button.pressed.connect(client.connect_bridge)
    row.add_child(connect_button)
    run_button = _button("Run repo test")
    run_button.pressed.connect(_start_real)
    row.add_child(run_button)
    mock_button = _button("UI simulation")
    mock_button.pressed.connect(_start_mock)
    row.add_child(mock_button)

    var bottom := VBoxContainer.new()
    bottom.name = "BottomArea"
    bottom.add_theme_constant_override("separation", 9)
    root_control.add_child(bottom)
    current_label = _label("Current step  ·  Waiting for a task", 16)
    current_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
    bottom.add_child(current_label)
    var grid := HBoxContainer.new()
    grid.add_theme_constant_override("separation", 14)
    bottom.add_child(grid)
    for name in ["Secretary", "Logistics", "Financial"]:
        var card := PanelContainer.new()
        card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        card.custom_minimum_size.y = 103
        card.add_theme_stylebox_override("panel", _style(Color("f7f4ea")))
        grid.add_child(card)
        var body := VBoxContainer.new()
        body.add_theme_constant_override("separation", 6)
        card.add_child(body)
        var top := HBoxContainer.new()
        body.add_child(top)
        var title := _label(name, 19)
        title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
        top.add_child(title)
        var status := _label("Idle", 14, MUTED)
        top.add_child(status)
        var detail := _label("Waiting", 14, MUTED)
        detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
        detail.custom_minimum_size.y = 39
        body.add_child(detail)
        cards[name] = {"status": status, "detail": detail}
    result_label = _label("Done means the module returned successfully, not that the books are correct or exceptions resolved.", 14, MUTED)
    result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
    bottom.add_child(result_label)

func _layout() -> void:
    var size := get_viewport().get_visible_rect().size
    var width := maxf(600, size.x - 76)
    root_control.get_node("TaskBar").position = Vector2(38, size.y - 265)
    root_control.get_node("TaskBar").size = Vector2(width, 58)
    root_control.get_node("BottomArea").position = Vector2(38, size.y - 194)
    root_control.get_node("BottomArea").size = Vector2(width, 178)
    connection_label.position = Vector2(38, size.y - 296)

func _update_card(name: String, state: Dictionary) -> void:
    if not cards.has(name):
        return
    var status: String = state.get("status", "idle")
    cards[name]["status"].text = STATE_LABELS.get(status, status)
    cards[name]["status"].add_theme_color_override("font_color", STATE_COLORS.get(status, MUTED))
    cards[name]["detail"].text = state.get("step", "")

func _connection(connected: bool, message: String) -> void:
    connection_label.text = message
    connection_label.add_theme_color_override("font_color", STATE_COLORS["done"] if connected else MUTED)

func _set_busy(value: bool) -> void:
    run_button.disabled = value
    mock_button.disabled = value
    connect_button.disabled = value

func _start_real() -> void:
    if goal_input.text.strip_edges().is_empty():
        store.set_current_step("Enter a task goal first")
        return
    _set_busy(true)
    result_label.text = "Calls the real repo Python modules on pre-extracted samples; your own files are not processed."
    if not client.start_fixture(goal_input.text):
        _set_busy(false)

func _finished(result: Dictionary) -> void:
    _set_busy(false)
    connection_label.text = "Local bridge connected · this run uses real modules / structured test data"
    var counts: Dictionary = result.get("counts", {})
    var warnings: Array = result.get("warnings", [])
    result_label.text = "Test done: %d records / %d exceptions / %d tasks / %d drafts (not sent); %d warnings, see the job's result.json (hover to view)." % [int(counts.get("records", 0)), int(counts.get("exceptions", 0)), int(counts.get("tasks", 0)), int(counts.get("email_drafts", 0)), warnings.size()]
    result_label.tooltip_text = "\n".join(PackedStringArray(warnings))

func _failed(message: String) -> void:
    _set_busy(false)
    result_label.text = "Real run did not finish: " + message

func _start_mock() -> void:
    if demo_running:
        return
    demo_running = true
    _set_busy(true)
    store.reset_agents()
    connection_label.text = "UI simulation · no agents called, no ledger produced"
    result_label.text = "This button only checks the idle → working → done UI changes."
    for name in store.AGENTS:
        store.set_current_step("[Simulated] " + name + " working")
        store.set_agent_status(name, "working", "[Simulated] demo state change")
        await get_tree().create_timer(1.0).timeout
        store.set_agent_status(name, "done", "[Simulated] demo done")
    store.set_current_step("UI simulation finished; no accounting performed")
    demo_running = false
    _set_busy(false)
