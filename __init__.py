# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####


bl_info = {
    "name": "Smashing",
    "author": "Sean Dunn",
    "version": (0, 1),
    "blender": (2, 91, 0),
    "location": "Viewport Object Menu -> Quick Effects",
    "description": "Smash selected target with active object",
    "warning": "",
    "doc_url": "",
    "support": "COMMUNITY",
    "category": "Object",
}

import sys
import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    EnumProperty,
)

from bpy.types import Operator
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from timeit import default_timer as timer
from sys import float_info


# Logging

def infoPrint(msg):
    print("Smashing: " + msg)


def errorPrint(msg):
    print("Smashing: Error: " + msg)


def debugPrint(msg):
    #print("Smashing: Debug: " + msg)        
    pass


# Geometry utilities

class GeoUtil:    

    @staticmethod
    def computeBoxWorld(piece):
        if piece == None:
            return None
        
        min = Vector((float_info.max, float_info.max, float_info.max))
        max = Vector((-float_info.max, -float_info.max, -float_info.max))
        for v in piece.bound_box:
            b = piece.matrix_world @ Vector(v)

            if b.x < min.x:
                min.x = b.x
            if b.y < min.y:
                min.y = b.y
            if b.z < min.z:
                min.z = b.z
                
            if b.x > max.x:
                max.x = b.x
            if b.y > max.y:
                max.y = b.y
            if b.z > max.z:
                max.z = b.z

        return (min, max)
        

    @staticmethod
    def countCommonVerts(objA, objB, tolerance=0.00001, max=-1):
        minA, maxA = GeoUtil.computeBoxWorld(objA)
        minB, maxB = GeoUtil.computeBoxWorld(objB)
                
        if minA.x > maxB.x or minA.y > maxB.y or minA.z > maxB.z:
            return 0
        
        objABmesh = bmesh.new()
        objABmesh.from_mesh(objA.data)
        objABmesh.transform(objA.matrix_world)
        objABmesh.verts.ensure_lookup_table()        

        objBBmesh = bmesh.new()
        objBBmesh.from_mesh(objB.data)
        objBBmesh.transform(objB.matrix_world)
        objBBmesh.verts.ensure_lookup_table()

        tolSq = tolerance * tolerance
        count = 0    

        for u in objABmesh.verts:
            for v in objBBmesh.verts:
                diff = u.co - v.co
                if diff.dot(diff) < tolSq:
                    count += 1                    
                    if count == max:
                        return max

        return count
        

    @staticmethod
    def objectsOverlap(objA, objB):
        objABmesh = bmesh.new()
        objABmesh.from_mesh(objA.data)
        objABmesh.transform(objA.matrix_world)
        objABvhTree = BVHTree.FromBMesh(objABmesh)
            
        objBBmesh = bmesh.new()
        objBBmesh.from_mesh(objB.data)
        objBBmesh.transform(objB.matrix_world)
        objBBvhTree = BVHTree.FromBMesh(objBBmesh)
        
        inter = objABvhTree.overlap(objBBvhTree)                
        if inter:
            objBBmesh.faces.ensure_lookup_table()        
            centerLocal = Vector((0,0,0))
            for p in inter:
                centerLocal = centerLocal + objBBmesh.faces[p[1]].calc_center_bounds()

            centerLocal /= len(inter)
            return centerLocal
        
        return None


    @staticmethod
    def computeMeshMinZ(p):
        pBmesh = bmesh.new()
        pBmesh.from_mesh(p.data)
        pBmesh.transform(p.matrix_world)
        
        minZ = sys.float_info.max
        for u in pBmesh.verts:
            if u.co.z < minZ:
                minZ = u.co.z
                
        return minZ


class DebrisGraph:
    def __init__(self, detectDiscon):
        self.detectDisconnected = detectDiscon

        self.pieceList = []
        self.pieceGraph = {}
        self.bottomPieces = set()
        self.crumbleSet = set()


    # Public Methods
    
    def addList(self, list):
        for item in list:
            self.pieceList.append(item)
        
        
    def compute(self):
        if self.detectDisconnected:        
            # find bottommost pieces and compute connection graph
            def minZSorter(p):
                return p[1]

            # by sorting by height, we will search downward first, which should get us to a
            # base piece sooner        
            heightSorted = []
            for piece in self.pieceList:
                heightSorted.append((piece, GeoUtil.computeMeshMinZ(piece)))
            heightSorted.sort(key=minZSorter)

            for sortPiece in heightSorted:
                debugPrint("HeightSorted:" + sortPiece[0].name)
            
            bottomZ = heightSorted[0][1]
            for sortPiece in heightSorted:
                if sortPiece[1] - bottomZ > 0.001:
                    break
                else:
                    self.bottomPieces.add(sortPiece[0])

            debugPrint("Bottom piece count: " + str(len(self.bottomPieces)))
                    
            infoPrint("Computing connection graph...")
            start = timer()
            index = 0            
            for piecePair in heightSorted:
                piece = piecePair[0]

                index += 1
                debugPrint ("  Piece:" + piece.name + " progress:" + str(index) + "/" + str(len(heightSorted)))

                touching = []
                for otherPair in heightSorted:
                    other = otherPair[0]
                    if piece != other:
                        found = False

                        # optimization: we can use previous computations to cut our time
                        if other in self.pieceGraph:
                            otherList = self.pieceGraph[other]
                            if piece in otherList:
                                found = True
                                
                        if not found:
                            max = 4
                            tolerance = 0.01
                            common = GeoUtil.countCommonVerts(piece, other, tolerance, max)
                            debugPrint ("    Testing:" + other.name + " Common:" + str(common));
                            if common >= max:
                                found = True

                        if found:
                            debugPrint ("    Touching!");
                            touching.append(other)

                self.pieceGraph[piece] = touching
                
            # given this data structure, we can query whether the touching pieces are still
            # in the same place, and try to find a path from the current piece to a member 
            # of the bottom pieces set
            end = timer()
            infoPrint("Computing connection graph took %f seconds." % (end - start))

    
    def isConnectedToBase(self, obj):
        if self.detectDisconnected:        
            return self._isConnectedToBase_r(obj, set(), 0)
        else:
            return not self.isCrumbled(obj)


    def isCrumbled(self, piece):
        return piece in self.crumbleSet

    
    def setCrumbled(self, piece):
        self.crumbleSet.add(piece)        


    # Private Methods

    def _isConnectedToBase_r(self, obj, visited, level):
        debugPrint(("  " * level) + "ICTB: " + obj.name)
        if self._isBottomPiece(obj):
            debugPrint(("  " * level) + "ICTB: BS: T")
            return True

        if self.isCrumbled(obj) or obj in visited:
            debugPrint(("  " * level) + "ICTB: CRV: F")
            return False

        visited.add(obj)    

        connList = self._getConnected(obj)
        for connObj in connList:
            debugPrint(("  " * level) + "ICTB: TST: " + obj.name + " > " + connObj.name)
            if self._isConnectedToBase_r(connObj, visited, level + 1):
                debugPrint(("  " * level) + "ICTB: IC!: T")
                return True
            
        debugPrint(("  " * level) + "ICTB: F")
        return False

        
    
    def _getConnected(self, obj):
        return self.pieceGraph[obj]
    
    
    def _isBottomPiece(self, obj):
        return obj in self.bottomPieces

                    
class SmashingMain(Operator):
    bl_idname = "object.exec_smashing"
    bl_label = "Run Smashing"
    bl_options = {'PRESET', 'UNDO'}


    # Properties

    # Shatter
        
    source_limit: IntProperty(
        name="Source Limit",
        description="Limit the number of input points, 0 for unlimited (count)",
        min=0, max=10000,
        default=32
    )

    crack_gap: FloatProperty(
        name="Crack Gap",
        description="How large the gaps between pieces are. Small gaps may cause explosions. (units)",
        min=0, max=1,
        default=0.001
    )
    
    # Shockwave

    shock_speed: FloatProperty(
        name="Shock Speed",
        description="How fast shockwave propagates through target (units/second)",
        min=0, max=1000,
        default=343
    )

    shock_duration: FloatProperty(
        name="Shock Duration",
        description="How long we allow shockwave to propagate once hit (seconds)",
        min=0, max=1000,
        default=1
    )

    # Structure
    
    detect_disconnected: BoolProperty(
        name="Detect Disconnected Pieces (!)",
        description="Disconnect pieces that don't connect to the ground (expensive!)",
        default=False
    )

    
    # Methods
    
    @classmethod
    def poll(cls, context):
        return bpy.ops.object.add_fracture_cell_objects != None
    

    def main(self, context, **kw):
        mainStart = timer()
        infoPrint("Smash in progress...")

        objects_context = context.selected_editable_objects
        kw_copy = kw.copy()


        '''
            Todo:
                Easy to use interface for creating smash patterns
                    Curve that lets you edit fragment size as distance from hit point
                    Aspect ratio of smash pattern in space of hit proxy
                    Spokes
                    Levels
                    Curve that lets you edit randomness of crack distribution as distance from hit point                    
                    
        '''

        sourceLimit = kw_copy.pop("source_limit")
        shockSpeed = kw_copy.pop("shock_speed")
        shockDuration = kw_copy.pop("shock_duration")
        crackGap = kw_copy.pop("crack_gap")
        detectDisconnected = kw_copy.pop("detect_disconnected")


        frameTime = 1 / bpy.context.scene.render.fps
        
        hitProxy = bpy.context.active_object
        target = None
        pieces = []
        
        for obj in bpy.context.selected_objects:
            if obj != hitProxy:
                target = obj
                # take first selected non-active object as target
                break
            
        if target == None:
            errorPrint("Script requires a target.")  
            return
        
        if target.rigid_body == None:
            errorPrint("Script requires a target with rigid body enabled.")  
            return

        # clear all selected
        bpy.ops.object.select_all(action='DESELECT')

        relativeMatrices = {}
        
        hitPointLocal = None
        hitPointGlobal = None
        hitFrame = None

        scene = bpy.data.scenes['Scene']

        targsMatrices = []
        pieceGraph = DebrisGraph(detectDisconnected)
                                
        for frame in range(scene.frame_start, scene.frame_end, 1):
            debugPrint("Hit Detection Frame:" + str(frame))

            scene.frame_set(frame)
            bpy.context.view_layer.update()
                
            # track the target matrix so we can use it to animate the pieces later            
            targsMatrices.append(target.matrix_world.copy())
            
            if hitFrame == None:            
                centerLocal = GeoUtil.objectsOverlap(hitProxy, target)                
                if centerLocal != None:
                    centerGlobal = target.matrix_world @ centerLocal
                                    
                    # run cell fracture on object
                    target.select_set(True)
                    bpy.context.view_layer.objects.active = target
                    
                    infoPrint("Computing fracture...");
                    start = timer()
                    bpy.ops.object.add_fracture_cell_objects(
                        #source={'PARTICLE_OWN'},
                        source_limit=sourceLimit, # 100
                        #source_noise=0,
                        #cell_scale=(1,1,1),
                        #recursion=0,
                        #recursion_source_limit=8,
                        #recursion_clamp=250,
                        #recursion_chance=0.25,
                        #recursion_chance_select='SIZE_MIN',
                        #use_smooth_faces=False,
                        #use_sharp_edges=True,
                        #use_sharp_edges_apply=True,
                        #use_data_match=True,
                        #use_island_split=True,
                        margin=crackGap, #0.001
                        #material_index=0,
                        #use_interior_vgroup=False,
                        #mass_mode='VOLUME',
                        #mass=1,
                        #use_recenter=True,
                        #use_remove_original=True,
                        #collection_name="",
                        #use_debug_points=False,
                        use_debug_redraw=False, # True
                        #use_debug_bool=False
                        )
                    end = timer()
                    infoPrint("Computing fracture took %f seconds." % (end - start))
                    
                    newPieces = bpy.context.selected_objects                    
                    pieceGraph.addList(newPieces)
                                            
                    # center origins of new pieces
                    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME')                
                                        
                    # re-add target as active, add to selecton list, and copy basic rigidbody attributes to new objects
                    target.select_set(True)
                    bpy.context.view_layer.objects.active = target
                    bpy.ops.rigidbody.object_settings_copy()
                                
                    # hide original object from view and render
                    target.keyframe_insert(data_path="hide_viewport", frame=frame-1)
                    target.hide_viewport = True
                    target.keyframe_insert(data_path="hide_viewport", frame=frame)

                    target.keyframe_insert(data_path="hide_render", frame=frame-1)
                    target.hide_render = True
                    target.keyframe_insert(data_path="hide_render", frame=frame)
                    
                    # use the inv matrix at the time of piece creation
                    targMatWorldInv = target.matrix_world.inverted_safe()

                    # Do not change the animation behavior of the primary. Just disappear it, and turn off its collision collections.

                    start = timer()
                    infoPrint("Hiding target and showing pieces...")

                    for piece in newPieces:
                        piece.hide_viewport = True
                        piece.keyframe_insert(data_path="hide_viewport", frame=frame-1)
                        piece.hide_viewport = False
                        piece.keyframe_insert(data_path="hide_viewport", frame=frame)

                        piece.hide_render = True
                        piece.keyframe_insert(data_path="hide_render", frame=frame-1)
                        piece.hide_render = False
                        piece.keyframe_insert(data_path="hide_render", frame=frame)
                        
                        relativeMatrices[piece] = targMatWorldInv @ piece.matrix_world                        

                    hitPointLocal = centerLocal
                    hitPointGlobal = centerGlobal
                    hitFrame = frame                
                    debugPrint("Found hit point: local:" + str(hitPointLocal) + " global:" + str(hitPointGlobal) + " at frame:" + str(hitFrame))

                        
                    # determine what collision collections are active for the initial target
                    activeCCs = set()
                    if target.rigid_body != None:
                        for cc in range(0, 20, 1):
                            if target.rigid_body.collision_collections[cc]:
                                activeCCs.add(cc)

                    # turn off all active collision collections on the next frame for the initial target
                    # then turn on the same collision collections on the same frame
                    for cc in activeCCs:
                        target.keyframe_insert(data_path="rigid_body.collision_collections", frame=frame-1, index=cc)
                        target.rigid_body.collision_collections[cc] = False
                        target.keyframe_insert(data_path="rigid_body.collision_collections", frame=frame, index=cc)
                        
                    for piece in newPieces:
                        for cc in activeCCs:
                            piece.rigid_body.collision_collections[cc] = False
                            piece.keyframe_insert(data_path="rigid_body.collision_collections", frame=frame-1, index=cc)
                            piece.rigid_body.collision_collections[cc] = True
                            piece.keyframe_insert(data_path="rigid_body.collision_collections", frame=frame, index=cc)
                            
                    end = timer()
                    infoPrint("Hiding target and showing pieces took %f seconds." % (end - start))
                                                                    
                    # from here on, we'll consider the newPieces the targets
                    pieces = newPieces

        if hitPointLocal != None and hitFrame != None:

            pieceGraph.compute()
            shockTime = 0
            shockRadius = 0    

            start = timer()
            infoPrint("Animating smithereens...")                        
                
            for frame in range(scene.frame_start, scene.frame_end, 1):
                debugPrint("Shock Animation Frame:" + str(frame))
            
                scene.frame_set(frame)
                bpy.context.view_layer.update()
                
                curHitPointGlobal = target.matrix_world @ hitPointLocal
                
                inHitSequence = frame > hitFrame

                if inHitSequence and shockTime < shockDuration:
                    shockRadius += shockSpeed * frameTime
                    shockTime += frameTime
                    debugPrint("ShockRadius: " + str(shockRadius))

                closestDistance = 999999
                            
                for piece in pieces:
                    # position pieces relative to moving target
                    matIndex = frame - scene.frame_start
                    relMat = relativeMatrices[piece]
                    pieceMat = targsMatrices[matIndex] @ relMat
                    
                    pieceLocal = sum((Vector(b) for b in piece.bound_box), Vector()) * (1.0 / 8.0)
                    pieceGlobal = pieceMat @ pieceLocal
                    distance = (curHitPointGlobal - pieceGlobal).length
                    
                    if distance < closestDistance:
                        closestDistance = distance
                                        
                    localOverlapPos = GeoUtil.objectsOverlap(hitProxy, piece)
                    
                    connToBase = pieceGraph.isConnectedToBase(piece)
                    if inHitSequence and not pieceGraph.isCrumbled(piece) and (not connToBase or distance < shockRadius or localOverlapPos != None):
                        # turn off kinematic and add to crumbleSet
                        piece.rigid_body.kinematic = True
                        piece.keyframe_insert(data_path="rigid_body.kinematic", frame=frame-1)
                        piece.rigid_body.kinematic = False
                        piece.keyframe_insert(data_path="rigid_body.kinematic", frame=frame)
                        pieceGraph.setCrumbled(piece)
                        debugPrint("Including:" + piece.name)
                        if not connToBase:
                            debugPrint("  not connected")
                    
                    if not pieceGraph.isCrumbled(piece):
                        # store animation for pre-hit pieces
                        loc, rot, sca = pieceMat.decompose()
                        
                        if piece == pieces[0]:
                            debugPrint("  pieceMat: " + str(pieceMat) + " loc:" + str(loc))
                        
                        piece.location = loc
                        piece.keyframe_insert(data_path="location", frame=frame)
                        piece.rotation_quaternion = rot
                        piece.keyframe_insert(data_path="rotation_quaternion", frame=frame)
                        piece.scale = sca
                        piece.keyframe_insert(data_path="scale", frame=frame)

            # go back to beginning, ready to play
            scene.frame_set(scene.frame_start)
            bpy.context.view_layer.update()
                    
            end = timer()
            infoPrint("Animating smithereens took %f seconds." % (end - start))                        

        mainEnd = timer()
        infoPrint("Smashed in %f seconds." % (mainEnd - mainStart))
 

    def execute(self, context):
        keywords = self.as_keywords()

        self.main(context, **keywords)

        return {'FINISHED'}


    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=600)


    def draw(self, context):
        layout = self.layout
        
        box = layout.box()
        col = box.column()
        col.label(text="Shockwave")
        rowsub = col.row()
        rowsub.prop(self, "shock_speed")
        rowsub.prop(self, "shock_duration")

        box = layout.box()
        col = box.column()
        col.label(text="Shatter Pattern")
        rowsub = col.row()
        rowsub.prop(self, "source_limit")
        rowsub.prop(self, "crack_gap")

        box = layout.box()
        col = box.column()
        col.label(text="Behavior")
        rowsub = col.row()
        rowsub.prop(self, "detect_disconnected")


def menu_func(self, context):
    layout = self.layout
    layout.separator()
    layout.operator("object.exec_smashing", text="Smashing")


def register():
    bpy.utils.register_class(SmashingMain)
    bpy.types.VIEW3D_MT_object_quick_effects.append(menu_func)


def unregister():
    bpy.utils.unregister_class(SmashingMain)
    bpy.types.VIEW3D_MT_object_quick_effects.remove(menu_func)


if __name__ == "__main__":
    try:
        unregister()
    except:
        infoPrint("Skipping first unregister()")
        
    register()
