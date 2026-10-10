extends SceneTree

func _initialize() -> void:
    call_deferred("_test")

func _test() -> void:
    var scene := load("res://scenes/main.tscn") as PackedScene
    assert(scene != null, "Main scene must load")
    var viewer := scene.instantiate()
    root.add_child(viewer)
    await process_frame
    assert(viewer.office_root != null, "GLB must instantiate")
    assert(viewer.bounds_ready, "Mesh bounds must exist")
    assert(viewer._mesh_count(viewer.office_root) > 100, "Office geometry missing")
    assert(viewer.office_bounds.size.x < 20.0, "Studio floor must be excluded")
    assert(viewer.office_camera.current, "Camera must be current")
    assert(viewer.office_camera.projection == Camera3D.PROJECTION_ORTHOGONAL)
    assert(viewer.get_node("WarmBackground").environment != null)
    assert(viewer.get_node("WarmWindowSun").shadow_enabled)
    print("BASIC_SCENE_TEST_PASS")
    quit(0)
