# Smashing

Smashing: A rigid body destruction addon for Blender

## About

This addon presents an easy to use interface for creating rigid body collision effects. 

## Installation

Smashing is compatible with Blender 2.91.

> Requirement: Smashing makes use of the Cell Fracture addon. You will also need to have it installed and enabled.

To use, place the source files of this project into a .zip, and install this archive as an addon in Blender.

## Usage

Once installed, Smashing can be invoked as follows:

1. Set the range of the animation timeline that Smashing should simulate over.
2. Select the object to be smashed (*the smashee*). This object must be a mesh with rigid body enabled and configured on it. These rigid body settings will be copied to the rigid body settings of each newly created broken piece.
3. Shift-select the object to smash it with (*the smasher*). This can be an invisible proxy object, or a real object in the scene.
4. Invoke Smashing through *Object -> Quick Effects -> Smashing*.
5. Set the properties for the plugin (see below), and press OK.

Smashing will then compute the point in time at which the *smasher* collides with the *smashee*, by testing whether any of their polygons intersect each other.

> Warning: Be conscious of rigid body limitations, and what Rigid Body Types you use in the simulation. For example, if your created fragments need to collide against a surrounding static concave surface, you shouldn't set that surface to be a Convex Hull, or the fragments will explode out of it. The safest type to use is Mesh, and then optimize with more efficient types once that works.

> Warning: because they must intersect faces, if the animation is so fast that the smasher is inside the smashee without intersecting, it will not register as a hit.

> Tip: Use an invisible proxy object as the smasher, so you can guarantee a hit the frame before the visibly smashing object actually collides with it.

Once a hit is detected, the smashee will be fragmented using the Cell Fracture addon. All new fragments will have the smashee's rigid body options copied to it.

Smashing also manages the animation of visibility between the original smashee mesh, and the new fragments, ensuring they don't appear until the smash happens.

### Addon Properties

| Group | Property | Description |
| --- | --- | --- |
| *Shockwave* |||
|| **Shock Speed** | This is the speed (units/s) that pieces will be considered "loose". Set this slower to create an object that falls apart over time. |
|| **Shock Duration** | This is how long (seconds) we allow the shockwave to propagate through the object. |
| *Shatter Pattern* |||
|| **Source Limit** | Limit the number of inputs in the underlying Cell Fracture. |
|| **Crack Gap** | The gap in between the edges of the underlying Cell Fracture. |
| *Behavior* |||
|| **Detect Disconnected Pieces** | This keeps objects from hanging in the air when their bottom gets knocked out, at the expense of taking longer to compute. It creates a simple internal connection graph of what pieces are connected to the ground. If an intermediary piece is knocked out, the dependent chain of pieces will fall. |

## Changes

#### v0.1

- Initial commit, allowing simple smashing of a mesh object by another mesh object.

## Future Work

* Resolve issues.
* Provide a popup if the Cell Fracture addon is not installed and enabled. This is a common issue with new installations.
* Create an intuitive interface for designing the smashing pattern. Should be better than using the grease pencil alone, and reusable.

## Contributors

* @hanoixan (Sean Dunn)
