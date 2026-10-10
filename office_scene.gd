extends Node3D
## Local-only office viewer. Change these in the Inspector on OfficeDemo.
@export var office_model: PackedScene = preload("res://assets/office.glb")
@export var camera_distance: float = 14.0
@export var camera_size_multiplier: float = 1.08
@export var camera_direction: Vector3 = Vector3(0.56, 0.72, 0.80)

var office_root: Node3D
var office_camera: Camera3D
var office_bounds := AABB()
var bounds_ready := false

func _ready() -> void:
    _build_office()
    _build_environment()
    _build_camera()
    _build_lighting()
    print("OFFICE_SCENE_READY meshes=", _mesh_count(office_root), " bounds=", office_bounds)

func _build_office() -> void:
    if office_model == null:
        push_error("Office GLB missing. Put it at assets/office.glb and reimport.")
        return
    office_root = office_model.instantiate() as Node3D
    office_root.name = "OfficeModel"
    add_child(office_root)
    _collect_bounds(office_root)

func _collect_bounds(node: Node) -> void:
    if node is MeshInstance3D:
        var instance := node as MeshInstance3D
        if instance.mesh != null:
            var box: AABB = instance.global_transform * instance.get_aabb()
            if not bounds_ready:
                office_bounds = box
                bounds_ready = true
            else:
                office_bounds = office_bounds.merge(box)
    for child in node.get_children():
        _collect_bounds(child)

func _mesh_count(node: Node) -> int:
    if node == null:
        return 0
    var count: int = 1 if node is MeshInstance3D else 0
    for child in node.get_children():
        count += _mesh_count(child)
    return count

func _build_environment() -> void:
    var environment := Environment.new()
    environment.background_mode = Environment.BG_COLOR
    environment.background_color = Color(0.86, 0.825, 0.75)
    environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.ambient_light_color = Color(0.91, 0.92, 0.86)
    environment.ambient_light_energy = 0.32
    environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
    var world := WorldEnvironment.new()
    world.name = "WarmBackground"
    world.environment = environment
    add_child(world)

func _build_camera() -> void:
    office_camera = Camera3D.new()
    office_camera.name = "OfficeCamera"
    office_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    office_camera.keep_aspect = Camera3D.KEEP_WIDTH
    office_camera.near = 0.05
    office_camera.far = 100.0
    add_child(office_camera)
    var center := office_bounds.get_center()
    office_camera.global_position = center + camera_direction.normalized() * camera_distance
    office_camera.look_at(center, Vector3.UP)
    office_camera.current = true
    _fit_camera()
    get_viewport().size_changed.connect(_fit_camera)

func _fit_camera() -> void:
    if not bounds_ready or office_camera == null:
        return
    var horizontal := 0.0
    var vertical := 0.0
    var center := office_bounds.get_center()
    for index in range(8):
        var delta := office_bounds.get_endpoint(index) - center
        horizontal = maxf(horizontal, absf(delta.dot(office_camera.global_basis.x)) * 2.0)
        vertical = maxf(vertical, absf(delta.dot(office_camera.global_basis.y)) * 2.0)
    var viewport_size := get_viewport().get_visible_rect().size
    var aspect := viewport_size.x / maxf(viewport_size.y, 1.0)
    var usable_fraction := maxf(0.45, (viewport_size.y - 340.0) / viewport_size.y)
    office_camera.size = maxf(horizontal, vertical * aspect / usable_fraction) * camera_size_multiplier
    var full_height := office_camera.size / aspect
    office_camera.global_position = center + camera_direction.normalized() * camera_distance - office_camera.global_basis.y * full_height * 0.10

func _build_lighting() -> void:
    var key := DirectionalLight3D.new()
    key.name = "WarmWindowSun"
    key.light_color = Color(1.0, 0.93, 0.81)
    key.light_energy = 0.65
    key.shadow_enabled = true
    key.directional_shadow_max_distance = 28.0
    key.shadow_blur = 2.0
    key.rotation_degrees = Vector3(-48, -35, 0)
    add_child(key)
    var fill := DirectionalLight3D.new()
    fill.name = "SoftFrontFill"
    fill.light_color = Color(0.84, 0.91, 1.0)
    fill.light_energy = 0.18
    fill.rotation_degrees = Vector3(-34, 145, 0)
    add_child(fill)
