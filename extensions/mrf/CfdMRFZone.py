# SPDX-License-Identifier: LGPL-3.0-or-later
# SPDX-FileNotice: Extension for CfdOF — MRF (Multiple Reference Frame) support.

################################################################################
#                                                                              #
#   This program is free software; you can redistribute it and/or              #
#   modify it under the terms of the GNU Lesser General Public                 #
#   License as published by the Free Software Foundation; either               #
#   version 3 of the License, or (at your option) any later version.           #
#                                                                              #
#   This program is distributed in the hope that it will be useful,            #
#   but WITHOUT ANY WARRANTY; without even the implied warranty of             #
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                       #
#                                                                              #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public License   #
#   along with this program; if not, write to the Free Software Foundation,    #
#   Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.        #
#                                                                              #
################################################################################

"""
CfdMRFZone — FreeCAD object representing a Multiple Reference Frame (MRF) zone
for OpenFOAM simulations.

An MRF zone maps to a named cellZone in the mesh and generates the corresponding
entry in constant/MRFProperties.  Unlike SRF (which rotates the entire domain),
MRF allows multiple independent rotating regions within the same mesh, which is
the standard approach for fan / impeller simulations with stationary surroundings.

Each CfdMRFZone object stores:
    ShapeRefs       — solid(s) in the FreeCAD document that define the rotating region
    RotationOrigin  — a point on the rotation axis (mm, FreeCAD internal units)
    RotationAxis    — unit vector of the rotation axis (dimensionless)
    RPM             — rotational speed (rev/min, positive = right-hand rule w.r.t. axis)

The object is compatible with simpleFoam and pimpleFoam; no dedicated solver
is required (unlike SRFSimpleFoam).
"""

import os

import FreeCAD
import FreeCADGui
import Part
from pivy import coin

from CfdOF import CfdTools
from CfdOF.CfdTools import addObjectProperty

QT_TRANSLATE_NOOP = FreeCAD.Qt.QT_TRANSLATE_NOOP

# Default values ---------------------------------------------------------------
_DEFAULT_ORIGIN = FreeCAD.Vector(0.0, 0.0, 0.0)
_DEFAULT_AXIS   = FreeCAD.Vector(0.0, 0.0, 1.0)   # Z axis — common for fans
_DEFAULT_RPM    = 0.0

# Visual appearance in the 3D view
_SHAPE_COLOR       = (0.2, 0.6, 1.0)   # light blue — distinct from porous zones (orange)
_TRANSPARENCY      = 70                 # percent


# ------------------------------------------------------------------------------
# Factory function
# ------------------------------------------------------------------------------

def makeCfdMRFZone(name="MRFZone"):
    """
    Create a new CfdMRFZone object and add it to the active document.
    The object is automatically added to the active CfdOF analysis.
    """
    obj = FreeCAD.ActiveDocument.addObject("Part::FeaturePython", name)
    CfdMRFZone(obj)
    if FreeCAD.GuiUp:
        ViewProviderCfdMRFZone(obj.ViewObject)
    return obj


# ------------------------------------------------------------------------------
# Toolbar / menu command
# ------------------------------------------------------------------------------

class CommandCfdMRFZone:
    """FreeCAD command that creates a new CfdMRFZone and opens its task panel."""

    def __init__(self):
        pass

    def GetResources(self):
        icon_path = os.path.join(
            CfdTools.getModulePath(), "extensions", "mrf", "Icons", "mrf_zone.svg"
        )
        # Graceful fallback: use the generic mean-velocity-force icon if ours is missing
        if not os.path.isfile(icon_path):
            icon_path = os.path.join(
                CfdTools.getModulePath(), "Gui", "Icons", "meanvelocityforce.svg"
            )
        return {
            'Pixmap':   icon_path,
            'MenuText': QT_TRANSLATE_NOOP("CfdOF_MRFZone", "MRF Zone"),
            'ToolTip':  QT_TRANSLATE_NOOP(
                "CfdOF_MRFZone",
                "Add a Multiple Reference Frame (MRF) rotating zone to the analysis"
            ),
        }

    def IsActive(self):
        return CfdTools.getActiveAnalysis() is not None

    def Activated(self):
        FreeCAD.ActiveDocument.openTransaction("Create MRF Zone")
        FreeCADGui.doCommand("")
        FreeCADGui.doCommand("from extensions.mrf import CfdMRFZone")
        FreeCADGui.doCommand("from CfdOF import CfdTools")
        FreeCADGui.doCommand(
            "CfdTools.getActiveAnalysis().addObject(CfdMRFZone.makeCfdMRFZone())"
        )
        FreeCADGui.ActiveDocument.setEdit(FreeCAD.ActiveDocument.ActiveObject.Name)


# ------------------------------------------------------------------------------
# Data object (proxy stored in Part::FeaturePython)
# ------------------------------------------------------------------------------

class CfdMRFZone:
    """
    Data proxy for an MRF zone object.

    Properties are registered via addObjectProperty so that:
      - they survive document save/load (onDocumentRestored calls initProperties again)
      - adding a new property in a future version does not break existing files
        (addObjectProperty is idempotent when the property already exists)
    """

    def __init__(self, obj):
        self.Object = obj
        self.initProperties(obj)

    def initProperties(self, obj):
        obj.Proxy = self
        self.Type = 'CfdMRFZone'

        # --- Solid reference(s) that define the rotating cell zone in the mesh ---
        addObjectProperty(
            obj,
            "ShapeRefs",
            [],
            "App::PropertyLinkSubListGlobal",
            "MRF Zone",
            QT_TRANSLATE_NOOP(
                "App::Property",
                "Solid(s) in the document that define the MRF cell zone. "
                "The mesh must contain a cellZone with the same name."
            ),
        )

        # --- Rotation geometry ---
        if addObjectProperty(
            obj,
            "RotationOrigin",
            _DEFAULT_ORIGIN,
            "App::PropertyVector",
            "MRF Zone",
            QT_TRANSLATE_NOOP(
                "App::Property",
                "A point on the rotation axis (FreeCAD internal units: mm). "
                "Corresponds to 'origin' in MRFProperties."
            ),
        ):
            obj.RotationOrigin = _DEFAULT_ORIGIN

        if addObjectProperty(
            obj,
            "RotationAxis",
            _DEFAULT_AXIS,
            "App::PropertyVector",
            "MRF Zone",
            QT_TRANSLATE_NOOP(
                "App::Property",
                "Unit vector of the rotation axis. "
                "Positive RPM follows the right-hand rule around this vector. "
                "Corresponds to 'axis' in MRFProperties."
            ),
        ):
            obj.RotationAxis = _DEFAULT_AXIS

        # --- Rotational speed ---
        if addObjectProperty(
            obj,
            "RPM",
            _DEFAULT_RPM,
            "App::PropertyFloat",
            "MRF Zone",
            QT_TRANSLATE_NOOP(
                "App::Property",
                "Rotational speed in rev/min (RPM). "
                "Sign follows the right-hand rule w.r.t. RotationAxis."
            ),
        ):
            obj.RPM = _DEFAULT_RPM

        # --- NonRotatingPatches ---
        # Patches inside the MRF zone that should NOT rotate (e.g. stationary shaft).
        # Stored as a list of patch names (strings), comma-separated.
        if addObjectProperty(
            obj,
            "NonRotatingPatches",
            "",
            "App::PropertyString",
            "MRF Zone",
            QT_TRANSLATE_NOOP(
                "App::Property",
                "Comma-separated list of patch names inside the MRF zone "
                "that must remain stationary (e.g. a shaft face). "
                "Leave empty if not needed."
            ),
        ):
            obj.NonRotatingPatches = ""

    def onDocumentRestored(self, obj):
        """Called when an existing .FCStd file is opened. Re-registers properties."""
        self.initProperties(obj)

    def execute(self, obj):
        """
        Recompute the visual shape from the referenced solids.
        Called automatically by FreeCAD when any property changes.
        """
        if obj.ShapeRefs:
            shapes = []
            for ref in obj.ShapeRefs:
                try:
                    shapes.append(ref[0].Shape)
                except Part.OCCError:
                    pass
            if shapes:
                obj.Shape = Part.makeCompound(shapes)
                return
        obj.Shape = Part.Shape()

    # Serialisation — required for FreeCAD >= 0.21.2 and for backward compat
    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


# ------------------------------------------------------------------------------
# View provider
# ------------------------------------------------------------------------------

class ViewProviderCfdMRFZone:
    """
    View provider: controls the 3D appearance of the zone and opens the task panel
    when the user double-clicks or edits the object.
    """

    def __init__(self, vobj):
        vobj.Proxy = self
        self.taskd = None

    def getIcon(self):
        icon_path = os.path.join(
            CfdTools.getModulePath(), "extensions", "mrf", "Icons", "mrf_zone.svg"
        )
        if not os.path.isfile(icon_path):
            icon_path = os.path.join(
                CfdTools.getModulePath(), "Gui", "Icons", "meanvelocityforce.svg"
            )
        return icon_path

    def attach(self, vobj):
        self.ViewObject = vobj
        self.Object = vobj.Object
        self.standard = coin.SoGroup()
        vobj.addDisplayMode(self.standard, "Standard")
        vobj.ShapeColor    = _SHAPE_COLOR
        vobj.Transparency  = _TRANSPARENCY

    def updateData(self, obj, prop):
        """Mark the case as needing a rewrite whenever any property changes."""
        analysis_obj = CfdTools.getParentAnalysisObject(obj)
        if analysis_obj and not analysis_obj.Proxy.loading:
            analysis_obj.NeedsCaseRewrite = True

    def onChanged(self, vobj, prop):
        return

    def doubleClicked(self, vobj):
        doc = FreeCADGui.getDocument(vobj.Object.Document)
        if not doc.getInEdit():
            doc.setEdit(vobj.Object.Name)
        else:
            FreeCAD.Console.PrintError('Task dialog already active\n')
            FreeCADGui.Control.showTaskView()
        return True

    def setEdit(self, vobj, mode):
        analysis_object = CfdTools.getParentAnalysisObject(self.Object)
        if analysis_object is None:
            CfdTools.cfdErrorBox("MRF Zone object must have a parent analysis object.")
            return False

        from extensions.mrf import TaskPanelCfdMRFZone
        import importlib
        importlib.reload(TaskPanelCfdMRFZone)
        self.taskd = TaskPanelCfdMRFZone.TaskPanelCfdMRFZone(self.Object)
        self.taskd.obj = vobj.Object
        FreeCADGui.Control.showDialog(self.taskd)
        return True

    def unsetEdit(self, vobj, mode):
        if self.taskd:
            self.taskd.closing()
            self.taskd = None
        FreeCADGui.Control.closeDialog()

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


# Backward-compat shim: if the view provider class is renamed in a future version,
# FreeCAD can still deserialise old files by calling attach() on this stub.
class _ViewProviderCfdMRFZone:
    def attach(self, vobj):
        new_proxy = ViewProviderCfdMRFZone(vobj)
        new_proxy.attach(vobj)

    def __getstate__(self):
        return None

    def __setstate__(self, state):
        return None

    def dumps(self):
        return None

    def loads(self, state):
        return None


# Register the command so FreeCAD can find it by name
FreeCADGui.addCommand('CfdOF_MRFZone', CommandCfdMRFZone())
