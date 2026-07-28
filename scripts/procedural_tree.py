"""
Procedural low-poly tree generator for Blender.

This is the script the local-LLM setup produced end to end, kept as a reference
for what a working `execute_blender_code` payload looks like.

Run it either way:
  - Paste into Blender's Scripting tab and press Run.
  - Or ask mcphost to run it:
      mcphost -p "run the script at scripts/procedural_tree.py in Blender"

Builds two joined objects: `Tree_Trunk` (bark) and `Tree_Leaves_Canopy` (foliage),
plus a `Ground` plane, and frames the camera on the result.
"""

import bpy
import bmesh
import math
import random
from mathutils import Vector

# Fixed seed keeps the shape reproducible. Change it for a different tree.
random.seed(20)


def make_mat(name, color, rough=0.8):
    """Create or update a Principled BSDF material."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return mat


def clear_previous():
    """Remove the default cube and anything from an earlier run."""
    for name in ("Cube", "Ground"):
        if name in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    for o in list(bpy.data.objects):
        if o.name.startswith("Tree_"):
            bpy.data.objects.remove(o, do_unlink=True)


def add_branch(base, direction, length, radius, depth, up_bias, bark_mat, sink):
    """
    Build one tapered branch segment, then recurse into its children.

    Returns a list of (position, radius) tips where foliage should be attached.
    """
    direction = direction.normalized()
    top = base + direction * length

    # A tapered cylinder built by hand: a wide ring at the base, a narrower
    # ring at the top, bridged with quads. bmesh is used rather than
    # primitive_cylinder_add so the taper and orientation come out in one step.
    bm = bmesh.new()
    segments = 8
    rot = Vector((0, 0, 1)).rotation_difference(direction).to_matrix()
    top_radius = radius * 0.68

    base_ring, top_ring = [], []
    for i in range(segments):
        ang = 2 * math.pi * i / segments
        offset = Vector((math.cos(ang), math.sin(ang), 0))
        base_ring.append(bm.verts.new(base + rot @ (offset * radius)))
        top_ring.append(bm.verts.new(top + rot @ (offset * top_radius)))
    bm.verts.ensure_lookup_table()

    for i in range(segments):
        j = (i + 1) % segments
        bm.faces.new((base_ring[i], base_ring[j], top_ring[j], top_ring[i]))
    bm.faces.new(reversed(base_ring))
    bm.faces.new(top_ring)

    mesh = bpy.data.meshes.new(f"Tree_Branch_{depth}")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new(f"Tree_Branch_{depth}", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(bark_mat)
    sink.append(obj)

    if depth <= 0:
        return [(top, top_radius)]

    tips = []
    # Three-way splits near the trunk open the crown; two-way splits higher up
    # keep the silhouette from turning into a bush.
    n_children = 3 if depth >= 3 else 2
    for k in range(n_children):
        # Fan children evenly around the parent axis, then tilt them outward.
        ang = 2 * math.pi * (k / n_children) + random.uniform(-0.4, 0.4)
        spread = Vector((math.cos(ang), math.sin(ang), 0)) * random.uniform(0.8, 1.3)
        new_dir = (direction * up_bias + spread + Vector((0, 0, 0.2))).normalized()
        tips += add_branch(top, new_dir, length * 0.70, radius * 0.62,
                           depth - 1, up_bias, bark_mat, sink)
    return tips


def join(objs, name):
    """Join a list of objects into one and rename it."""
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    return joined


def build_tree():
    clear_previous()

    bark_mat = make_mat("Tree_Bark", (0.18, 0.09, 0.04), rough=0.9)
    leaf_mat = make_mat("Tree_Leaves", (0.10, 0.35, 0.08), rough=0.75)
    ground_mat = make_mat("Ground_Mat", (0.12, 0.20, 0.08), rough=1.0)

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.name = "Ground"
    ground.data.materials.append(ground_mat)

    branches = []
    tips = add_branch(Vector((0, 0, 0)), Vector((0, 0, 1)),
                      length=2.6, radius=0.38, depth=4, up_bias=0.9,
                      bark_mat=bark_mat, sink=branches)

    # Foliage: a roughened ico-sphere per branch tip. Displacing each vertex
    # along its own normal is what keeps the clusters from reading as spheres.
    foliage = []
    for i, (pos, _r) in enumerate(tips):
        size = random.uniform(0.75, 1.15)
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=2, radius=size,
            location=pos + Vector((0, 0, size * 0.3)))
        blob = bpy.context.active_object
        blob.name = f"Tree_Foliage_{i}"
        for v in blob.data.vertices:
            v.co += v.co.normalized() * random.uniform(-0.14, 0.14)
        blob.data.materials.append(leaf_mat)
        for p in blob.data.polygons:
            p.use_smooth = True
        foliage.append(blob)

    trunk = join(branches, "Tree_Trunk")
    canopy = join(foliage, "Tree_Leaves_Canopy")
    bpy.ops.object.select_all(action="DESELECT")

    cam = bpy.data.objects.get("Camera")
    if cam:
        cam.location = (9, -9, 6)
        aim = Vector((0, 0, 3.5)) - cam.location
        cam.rotation_euler = aim.to_track_quat("-Z", "Y").to_euler()

    light = bpy.data.objects.get("Light")
    if light:
        light.data.energy = 1000

    # Materials are invisible in the default solid shading, so switch the
    # viewport over or the result looks grey and wrong.
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    space.shading.type = "MATERIAL"

    print(f"Built {trunk.name} + {canopy.name} with {len(tips)} foliage clusters")
    return trunk, canopy


if __name__ == "__main__":
    build_tree()
