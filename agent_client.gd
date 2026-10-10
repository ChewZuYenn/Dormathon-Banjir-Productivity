extends Node
## Async local bridge client. HTTP errors never become a fake "done".
signal connection_changed(connected: bool, message: String)
signal job_finished(result: Dictionary)
signal job_failed(message: String)

@export var bridge_url: String = "http://127.0.0.1:8765"
var store: Node
var request_node: HTTPRequest
var poll_timer: Timer
var operation := ""
var job_id := ""
var busy := false
var connected := false
var events_seen := 0
var last_result: Dictionary = {}

func _ready() -> void:
    store = get_node("../AgentState")
    request_node = HTTPRequest.new()
    request_node.timeout = 6.0
    add_child(request_node)
    request_node.request_completed.connect(_completed)
    poll_timer = Timer.new()
    poll_timer.wait_time = 0.4
    add_child(poll_timer)
    poll_timer.timeout.connect(_poll)

func connect_bridge() -> void:
    if not busy:
        _request("health", "/health")

func start_fixture(goal: String) -> bool:
    return start_job({"mode": "fixture", "goal": goal})

func start_records(goal: String, period: String, records: Array) -> bool:
    return start_job({"mode": "records", "goal": goal, "period": period, "records": records})

func start_job(payload: Dictionary) -> bool:
    if busy or not job_id.is_empty():
        return false
    store.reset_agents()
    events_seen = 0
    last_result = {}
    return _request("submit", "/jobs", HTTPClient.METHOD_POST, JSON.stringify(payload))

func _request(kind: String, path: String, method: int = HTTPClient.METHOD_GET, body: String = "") -> bool:
    # Local-only default. Never attach API keys or invoke external services.
    if not bridge_url.begins_with("http://127.0.0.1:") and not bridge_url.begins_with("http://localhost:"):
        _fail("只允许本机桥接地址")
        return false
    operation = kind
    busy = true
    var headers := PackedStringArray(["Content-Type: application/json"])
    var error := request_node.request(bridge_url + path, headers, method, body)
    if error != OK:
        _fail("无法发起本机请求：" + str(error))
        return false
    return true

func _poll() -> void:
    if not busy and not job_id.is_empty():
        _request("poll", "/jobs/" + job_id)

func _completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
    busy = false
    if result != HTTPRequest.RESULT_SUCCESS:
        _fail("桥接未连接或请求超时；先启动 bridge/server.py")
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if not parsed is Dictionary:
        _fail("桥接返回了无效 JSON")
        return
    var data: Dictionary = parsed
    if code < 200 or code >= 300:
        if operation == "poll" and code == 404:
            job_id = ""
        _fail(str(data.get("error", "HTTP " + str(code))))
        return
    match operation:
        "health":
            connected = data.get("service", "") == "office-agent-bridge"
            connection_changed.emit(connected, "本机桥接已连接 · 真实模块/测试数据" if connected else "不是预期桥接服务")
            if connected and not job_id.is_empty():
                poll_timer.start()
                _poll()
        "submit":
            job_id = str(data.get("job_id", ""))
            if job_id.is_empty():
                _fail("桥接没有返回任务编号")
                return
            store.set_current_step("本地任务已提交")
            poll_timer.start()
            _poll()
        "poll":
            # Replay observed actual events; no invented timer-based progress.
            var events: Array = data.get("events", [])
            for index in range(events_seen, events.size()):
                var event: Dictionary = events[index]
                store.set_agent_status(str(event.get("agent", "")), str(event.get("status", "")), str(event.get("step", "")))
            events_seen = events.size()
            if not store.apply_snapshot(data):
                _fail("桥接状态字段不符合约定")
                return
            if data.get("status") == "error":
                job_id = ""
                _fail(str(data.get("error", "Agent 执行失败")))
            elif data.get("status") == "done":
                poll_timer.stop()
                _request("result", "/jobs/" + job_id + "/result")
        "result":
            last_result = data
            job_id = ""
            connected = true
            job_finished.emit(data)

func _fail(message: String) -> void:
    busy = false
    poll_timer.stop()
    connected = false
    # Retain an accepted task id so an interrupted poll can be resumed safely.
    if not job_id.is_empty():
        message += "（任务编号已保留，可点击连接本机桥接恢复）"
    store.set_current_step(message)
    connection_changed.emit(false, message)
    job_failed.emit(message)
