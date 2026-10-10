extends SceneTree

func _initialize() -> void:
    call_deferred("_test")

func _test() -> void:
    var packed := load("res://scenes/main.tscn") as PackedScene
    var office := packed.instantiate()
    root.add_child(office)
    await process_frame
    var store: Node = office.get_node("AgentState")
    var ui: Node = office.get_node("AgentUI")
    assert(store.states.size() == 3)
    assert(store.set_agent_status("Secretary", "working", "Test plan generation"))
    assert(store.get_agent_state("Secretary")["status"] == "working")
    assert(ui.cards["Secretary"]["detail"].text == "Test plan generation")
    assert(not store.set_agent_status("Unknown", "done"))
    assert(not store.set_agent_status("Financial", "invalid"))
    store.set_current_step("Step 2: reconcile")
    assert(ui.current_label.text.contains("Step 2: reconcile"))
    var before: Dictionary = store.states.duplicate(true)
    assert(not store.apply_snapshot({"agents": {"Secretary": {"status": "done"}}}))
    assert(store.states == before)
    store.reset_agents()
    assert(store.get_agent_state("Secretary")["status"] == "idle")
    ui._start_mock()
    assert(ui.demo_running)
    assert(ui.run_button.disabled)
    await create_timer(3.3).timeout
    assert(not ui.demo_running)
    assert(not ui.run_button.disabled)
    for agent in store.AGENTS:
        assert(store.get_agent_state(agent)["status"] == "done")
        assert(ui.cards[agent]["detail"].text.contains("Simulated"))
    print("AGENT_STATE_UI_TEST_PASS")
    quit(0)
