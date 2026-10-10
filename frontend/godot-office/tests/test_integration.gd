extends SceneTree
var done := false
var failed := false

func _initialize() -> void:
    call_deferred("_test")

func _test() -> void:
    var packed := load("res://scenes/main.tscn") as PackedScene
    var office := packed.instantiate()
    root.add_child(office)
    await process_frame
    var client: Node = office.get_node("AgentClient")
    client.job_finished.connect(func(result: Dictionary):
        assert(result.get("data_mode") == "fixture")
        assert(result.get("counts", {}).get("records") == 12)
        done = true
    )
    client.job_failed.connect(func(message: String):
        push_error(message)
        failed = true
    )
    assert(client.start_fixture("Close out September"))
    assert(not client.start_fixture("duplicate request"))
    for frame in range(4000):
        if done or failed:
            break
        await process_frame
    assert(done and not failed, "Real bridge integration did not complete")
    var store: Node = office.get_node("AgentState")
    for agent in store.AGENTS:
        assert(store.get_agent_state(agent).get("status") == "done")
    assert(client.events_seen >= 8)
    print("GODOT_REAL_AGENT_INTEGRATION_PASS ", client.last_result.get("counts"))
    if DisplayServer.get_name() != "headless":
        await RenderingServer.frame_post_draw
        var path := ProjectSettings.globalize_path("res://../godot-office-connected-preview.png")
        assert(root.get_texture().get_image().save_png(path) == OK)
        print("CONNECTED_RENDER_CAPTURED ", path)
    quit(0)
