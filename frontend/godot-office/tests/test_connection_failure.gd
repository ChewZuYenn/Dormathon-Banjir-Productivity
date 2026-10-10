extends SceneTree
var failed := false

func _initialize() -> void:
    call_deferred("_test")

func _test() -> void:
    var packed := load("res://scenes/main.tscn") as PackedScene
    var office := packed.instantiate()
    root.add_child(office)
    await process_frame
    var client: Node = office.get_node("AgentClient")
    client.bridge_url = "http://127.0.0.1:1"
    client.job_failed.connect(func(_message: String): failed = true)
    assert(client.start_fixture("Connection failure test"))
    for i in range(10):
        if failed:
            break
        await create_timer(0.15).timeout
    assert(failed, "Missing bridge must report failure")
    for state in office.get_node("AgentState").states.values():
        assert(state["status"] != "done", "Missing bridge must not fake success")
    client.job_id = "accepted-job-test"
    client._fail("test interrupted poll")
    assert(client.job_id == "accepted-job-test", "Accepted job id must survive network failure")
    print("CONNECTION_FAILURE_TEST_PASS")
    quit(0)
