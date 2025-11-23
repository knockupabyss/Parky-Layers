bl_info = {
    "name": "Parky Layers",
    "author": "KnockupAbyss",
    "version": (1, 0),
    "blender": (3, 0, 0),
    "description": "Alight Motion, but for Blender",
    "category": "Paint",
}

import bpy
import bmesh
import os

# ------------------------------------------------------------------------
#   Global Settings & Functions
# ------------------------------------------------------------------------
LAYER_COLLECTION_NAME = "Layers"
LAYER_GAP = 0.05  # Distance between layers on Y axis
IMG_RES = 1024    # Default texture resolution

# this scales uvs so textures don't overlap weirdly like they do in the first demo, it's incredibly janky but it works
def scale_uvs(obj, scale_factor):
    # validation
    if obj is None or obj.type != 'MESH':
        print("Error: Object is not a valid mesh.")
        return

    mesh = obj.data
    
    # create new mesh
    bm = bmesh.new()
    bm.from_mesh(mesh)

    # get uv layer
    uv_layer = bm.loops.layers.uv.verify()

    # calculate scale factors
    if isinstance(scale_factor, (int, float)):
        scale_u = scale_factor
        scale_v = scale_factor
    else:
        scale_u = scale_factor[0]
        scale_v = scale_factor[1]

    # iterate faces to scale
    for face in bm.faces:
        for loop in face.loops:
            loop_uv = loop[uv_layer]
            
            # Apply scaling (Pivot is 0,0)
            loop_uv.uv.x *= scale_u
            loop_uv.uv.y *= scale_v

    # write bmesh data
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()


# ------------------------------------------------------------------------
#   Material & Shader Logic
# ------------------------------------------------------------------------

# make the texture material
def get_or_create_layer_material(obj):
    wm = bpy.context.window_manager
    
    mat_name = f"{obj.name}_Mat"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    mat.blend_method = 'BLEND' # essential for transparency!!!
    
    nodes.clear()

    tex_image = nodes.new(type='ShaderNodeTexImage')
    tex_image.location = (-600, 200)
    tex_image.label = "Image Texture"

    tex_image.image = bpy.data.images.new(f"{obj.name}_Txt", width=2160, height=2160, alpha=True)
    tex_image.image.generated_color = (0,0,0,0)

    trans_bsdf = nodes.new(type='ShaderNodeBsdfTransparent')
    trans_bsdf.location = (-600, -100)

    mix_shader = nodes.new(type='ShaderNodeMixShader')
    mix_shader.location = (-300, 200)

    mat_output = nodes.new(type='ShaderNodeOutputMaterial')
    mat_output.location = (-100, 200)

    links.new(tex_image.outputs['Alpha'], mix_shader.inputs['Fac'])

    links.new(trans_bsdf.outputs['BSDF'], mix_shader.inputs[1])

    links.new(tex_image.outputs['Color'], mix_shader.inputs[2])

    links.new(mix_shader.outputs['Shader'], mat_output.inputs['Surface'])

    return mat, None

# ------------------------------------------------------------------------
#   Core Logic
# ------------------------------------------------------------------------

def update_layer_transforms(context):
    """
    Loops through the UI list order and positions the actual 3D planes
    along the Y axis so visual order matches list order.
    """
    scene = context.scene
    
    # front view looks along Y+
    # bottom layer (index 0) is furthest back
    # top layer (last index) is closest to camera (negative Y)
    
    for i, item in enumerate(scene.layer_stack):
        obj = item.obj_ptr
        if obj:
            new_y = -(i * LAYER_GAP)
            obj.location.y = new_y

def set_active_layer(context, index):
    """Sets the active object and switches mode based on list selection"""
    scene = context.scene
    if index < 0 or index >= len(scene.layer_stack):
        return

    item = scene.layer_stack[index]
    obj = item.obj_ptr
    
    if obj:
        bpy.ops.object.select_all(action='DESELECT')
        
        obj.select_set(True)
        context.view_layer.objects.active = obj
        
        if context.mode != 'PAINT_TEXTURE':
            try:
                bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
            except:
                pass # context might be wrong during init

# ------------------------------------------------------------------------
#   Data Structures
# ------------------------------------------------------------------------

def update_layer_name(self, context):
    """
    Callback: Updates the actual 3D object name when the 
    UI list item name is changed by the user.
    """
    if self.obj_ptr:
        # apply ui name
        self.obj_ptr.name = self.name
        
        # sync check
        if self.name != self.obj_ptr.name:
            self.name = self.obj_ptr.name

class LayerItem(bpy.types.PropertyGroup):
    # pointer to the actual object
    obj_ptr: bpy.props.PointerProperty(type=bpy.types.Object)
    
    # name prop
    name: bpy.props.StringProperty(update=update_layer_name)

# ------------------------------------------------------------------------
#   Operators
# ------------------------------------------------------------------------

class LAYER_OT_add(bpy.types.Operator):
    """Add a new drawing layer"""
    bl_idname = "layers.add_layer"
    bl_label = "Add Layer"
    
    def execute(self, context):
        scene = context.scene
        
        col = bpy.data.collections.get(LAYER_COLLECTION_NAME)
        if not col:
            col = bpy.data.collections.new(LAYER_COLLECTION_NAME)
            context.scene.collection.children.link(col)
        
        bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=False, align='WORLD', location=(0, 0, 0))
        obj = context.active_object
        obj.rotation_euler = (1.5708, 0, 0)
        
        layer_count = len(scene.layer_stack) + 1
        obj.name = f"Layer_{layer_count}"
        
        for old_col in obj.users_collection:
            old_col.objects.unlink(obj)
        col.objects.link(obj)
        
        mat, img = get_or_create_layer_material(obj)
        if len(obj.data.materials) == 0:
            obj.data.materials.append(mat)
        else:
            obj.data.materials[0] = mat
            
        item = scene.layer_stack.add()
        item.name = obj.name
        item.obj_ptr = obj
        for i,iitem in enumerate(scene.layer_stack):
            if iitem.name == item.name:
                scene.layer_stack.move(i,0)
        
        
        scene.layer_index = len(scene.layer_stack) - 1
        
        update_layer_transforms(context)

        scale_uvs(obj=obj, scale_factor=0.997)
        
        bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        
        return {'FINISHED'}

class LAYER_OT_remove(bpy.types.Operator):
    """Remove the selected layer"""
    bl_idname = "layers.remove_layer"
    bl_label = "Remove Layer"
    
    def execute(self, context):
        scene = context.scene
        idx = scene.layer_index
        
        if 0 <= idx < len(scene.layer_stack):
            item = scene.layer_stack[idx]
            obj = item.obj_ptr
            
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
            
            scene.layer_stack.remove(idx)
            
            scene.layer_index = max(0, idx - 1)
            
            update_layer_transforms(context)
            
        return {'FINISHED'}

class LAYER_OT_move(bpy.types.Operator):
    """Move layer up or down"""
    bl_idname = "layers.move_layer"
    bl_label = "Move Layer"
    
    direction: bpy.props.EnumProperty(items=(('UP', 'Up', ""), ('DOWN', 'Down', "")))
    
    def execute(self, context):
        scene = context.scene
        idx = scene.layer_index
        l = len(scene.layer_stack)
        
        if self.direction == 'UP' and idx < l - 1:
            scene.layer_stack.move(idx, idx + 1)
            scene.layer_index -= 1
            update_layer_transforms(context)
            
        elif self.direction == 'DOWN' and idx > 0:
            scene.layer_stack.move(idx, idx - 1)
            scene.layer_index += 1
            update_layer_transforms(context)
            
        return {'FINISHED'}

# ------------------------------------------------------------------------
#   UI Panel & List
# ------------------------------------------------------------------------

class LAYER_UL_list(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        # show warning when obj missing
        if not item.obj_ptr:
            layout.label(text=f"{item.name} (Deleted)", icon="ERROR")
        else:
            layout.prop(item, "name", text="", emboss=False, icon="MESH_PLANE")

class LAYER_PT_panel(bpy.types.Panel):
    bl_label = "Parky Layers"
    bl_idname = "LAYER_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Parky Layers"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        row = layout.row()
        row.template_list("LAYER_UL_list", "", scene, "layer_stack", scene, "layer_index")
        
        col = row.column(align=True)
        col.operator("layers.move_layer", icon='TRIA_UP', text="").direction = 'UP'
        col.operator("layers.move_layer", icon='TRIA_DOWN', text="").direction = 'DOWN'
        
        row = layout.row(align=True)
        row.operator("layers.add_layer", icon='ADD')
        row.operator("layers.remove_layer", icon='REMOVE')

# ------------------------------------------------------------------------
#   Registration & Hooks
# ------------------------------------------------------------------------

def on_layer_index_change(self, context):
    set_active_layer(context, self.layer_index)

def register():
    bpy.utils.register_class(LayerItem)
    bpy.utils.register_class(LAYER_OT_add)
    bpy.utils.register_class(LAYER_OT_remove)
    bpy.utils.register_class(LAYER_OT_move)
    bpy.utils.register_class(LAYER_UL_list)
    bpy.utils.register_class(LAYER_PT_panel)
    
    bpy.types.Scene.layer_stack = bpy.props.CollectionProperty(type=LayerItem)
    bpy.types.Scene.layer_index = bpy.props.IntProperty(update=on_layer_index_change)

def unregister():
    del bpy.types.Scene.layer_stack
    del bpy.types.Scene.layer_index
    
    bpy.utils.unregister_class(LayerItem)
    bpy.utils.unregister_class(LAYER_OT_add)
    bpy.utils.unregister_class(LAYER_OT_remove)
    bpy.utils.unregister_class(LAYER_OT_move)
    bpy.utils.unregister_class(LAYER_UL_list)
    bpy.utils.unregister_class(LAYER_PT_panel)

def layeritems():
    for v in bpy.types.Scene.layer_stack:
        v.obj_ptr.name = v.name

bpy.app.handlers.frame_change_pre.append(layeritems)

if __name__ == "__main__":
    register()