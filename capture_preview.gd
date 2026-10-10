extends SceneTree
## Capture one actual rendered Godot frame. Requires a graphical renderer, not --headless.
func _initialize() -> void:
    call_deferred("_capture")

func _capture() -> void:
    var packed := load("res://scenes/main.tscn") as PackedScene
    var office := packed.instantiate()
    root.add_child(office)
    for frame in range(40):
        await process_frame
    await RenderingServer.frame_post_draw
    var image := root.get_texture().get_image()
    var args := OS.get_cmdline_user_args()
    var path := ProjectSettings.globalize_path("res://../godot-office-preview.png")
    if args.size() > 0:
        path = args[0]
    assert(image != null and image.get_width() > 0)
    var error := image.save_png(path)
    assert(error == OK, "Screenshot failed")
    print("GODOT_RENDER_CAPTURED ", path, " size=", image.get_size())
    quit(0)
