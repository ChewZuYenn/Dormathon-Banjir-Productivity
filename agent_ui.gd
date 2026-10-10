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
const STATE_LABELS := {"idle": "等待 · idle", "working": "执行中 · working", "done": "代码完成 · done", "error": "失败 · error"}

func _ready() -> void:
    store = get_node("../AgentState")
    client = get_node("../AgentClient")
    _build()
    store.agent_changed.connect(_update_card)
    store.current_step_changed.connect(func(step: String): current_label.text = "当前步骤  ·  " + step)
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
    var heading := _label("小小办公室  /  月末结账 Agent", 25)
    heading.position = Vector2(38, 22)
    root_control.add_child(heading)
    var caption := _label("本地 3D 场景  ·  结构化测试数据  ·  无自动付款 / 无邮件发送", 15, MUTED)
    caption.position = Vector2(38, 59)
    root_control.add_child(caption)
    connection_label = _label("桥接未连接 · 可先运行界面模拟", 15, MUTED)
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
    goal_input.placeholder_text = "输入结账任务目标"
    goal_input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
    goal_input.add_theme_font_size_override("font_size", 17)
    goal_input.add_theme_color_override("font_color", INK)
    goal_input.add_theme_stylebox_override("normal", _style(Color("fffdf5"), 9))
    row.add_child(goal_input)
    connect_button = _button("连接本机桥接")
    connect_button.pressed.connect(client.connect_bridge)
    row.add_child(connect_button)
    run_button = _button("运行仓库测试")
    run_button.pressed.connect(_start_real)
    row.add_child(run_button)
    mock_button = _button("界面模拟")
    mock_button.pressed.connect(_start_mock)
    row.add_child(mock_button)

    var bottom := VBoxContainer.new()
    bottom.name = "BottomArea"
    bottom.add_theme_constant_override("separation", 9)
    root_control.add_child(bottom)
    current_label = _label("当前步骤  ·  等待任务", 16)
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
        var status := _label("等待 · idle", 14, MUTED)
        top.add_child(status)
        var detail := _label("等待执行", 14, MUTED)
        detail.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
        detail.custom_minimum_size.y = 39
        body.add_child(detail)
        cards[name] = {"status": status, "detail": detail}
    result_label = _label("完成指模块返回成功，不代表账务准确或异常已解决。", 14, MUTED)
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
        store.set_current_step("请先输入任务目标")
        return
    _set_busy(true)
    result_label.text = "真实调用仓库 Python 模块；使用预抽取样例，不处理你的真实文件。"
    if not client.start_fixture(goal_input.text):
        _set_busy(false)

func _finished(result: Dictionary) -> void:
    _set_busy(false)
    connection_label.text = "本机桥接已连接 · 本次调用真实模块/结构化测试数据"
    var counts: Dictionary = result.get("counts", {})
    var warnings: Array = result.get("warnings", [])
    result_label.text = "测试完成：%d 条记录 / %d 个异常 / %d 个待办 / %d 封草稿（未发送）；%d 条警告，详见任务 result.json（悬停查看）。" % [int(counts.get("records", 0)), int(counts.get("exceptions", 0)), int(counts.get("tasks", 0)), int(counts.get("email_drafts", 0)), warnings.size()]
    result_label.tooltip_text = "\n".join(PackedStringArray(warnings))

func _failed(message: String) -> void:
    _set_busy(false)
    result_label.text = "未完成真实执行：" + message

func _start_mock() -> void:
    if demo_running:
        return
    demo_running = true
    _set_busy(true)
    store.reset_agents()
    connection_label.text = "界面模拟 · 不调用 Agent，不生成账本"
    result_label.text = "此按钮只验证 idle → working → done 的界面变化。"
    for name in store.AGENTS:
        store.set_current_step("[模拟] " + name + " 执行中")
        store.set_agent_status(name, "working", "[模拟] 演示状态变化")
        await get_tree().create_timer(1.0).timeout
        store.set_agent_status(name, "done", "[模拟] 演示完成")
    store.set_current_step("界面模拟结束；未执行账务")
    demo_running = false
    _set_busy(false)
