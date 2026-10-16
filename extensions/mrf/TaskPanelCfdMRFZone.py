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
TaskPanelCfdMRFZone — FreeCAD task panel for CfdMRFZone objects.

Allows the user to:
  - Select the solid(s) that define the rotating cell zone (via CfdFaceSelectWidget)
  - Set the rotation origin (point on the axis) in mm
  - Set the rotation axis (unit vector, dimensionless)
  - Set the rotational speed in RPM
  - Optionally list non-rotating patches (comma-separated names)

On accept(), all values are written back to the object via storeIfChanged().
On reject(), the original ShapeRefs and NeedsCaseRewrite flag are restored.
"""

import os

import FreeCAD
from FreeCAD import Units
from CfdOF import CfdTools, CfdFaceSelectWidget
from CfdOF.CfdTools import setQuantity, getQuantity, storeIfChanged

if FreeCAD.GuiUp:
    import FreeCADGui
    from PySide import QtGui


class TaskPanelCfdMRFZone:
    """Task panel for creating and editing a CfdMRFZone object."""

    def __init__(self, obj):
        self.obj = obj
        self.analysis_obj = CfdTools.getParentAnalysisObject(obj)

        # Save originals so reject() can restore them
        self.ShapeRefsOrig = list(self.obj.ShapeRefs)
        self.NeedsCaseRewriteOrig = self.analysis_obj.NeedsCaseRewrite

        # Load the .ui file from extensions/mrf/Gui/
        ui_path = os.path.join(
            CfdTools.getModulePath(),
            "extensions", "mrf", "Gui", "TaskPanelCfdMRFZone.ui"
        )
        self.form = FreeCADGui.PySideUic.loadUi(ui_path)

        # Embed the solid-selection widget
        # allowFaces=False, allowSolids=True — we want cell zones (solids)
        self.form.faceSelectWidget.setLayout(QtGui.QVBoxLayout())
        self.faceSelector = CfdFaceSelectWidget.CfdFaceSelectWidget(
            self.form.faceSelectWidget,
            self.obj,
            False,   # allowFaces
            False,   # allowSolids (volume selection, not surface patches)
            True,    # allowCellZones — selects named cellZone volumes
        )

        self.load()

    # ------------------------------------------------------------------
    # load / accept / reject / closing
    # ------------------------------------------------------------------

    def load(self):
        """Populate all widgets from the current object properties."""
        obj = self.obj

        # Rotation origin — stored in mm (FreeCAD internal units)
        setQuantity(self.form.inputOriginX, Units.Quantity("{} mm".format(obj.RotationOrigin.x)))
        setQuantity(self.form.inputOriginY, Units.Quantity("{} mm".format(obj.RotationOrigin.y)))
        setQuantity(self.form.inputOriginZ, Units.Quantity("{} mm".format(obj.RotationOrigin.z)))

        # Rotation axis — dimensionless unit vector
        setQuantity(self.form.inputAxisX, Units.Quantity(float(obj.RotationAxis.x)))
        setQuantity(self.form.inputAxisY, Units.Quantity(float(obj.RotationAxis.y)))
        setQuantity(self.form.inputAxisZ, Units.Quantity(float(obj.RotationAxis.z)))

        # Rotational speed — RPM (stored as plain float in the object)
        setQuantity(self.form.inputRPM, Units.Quantity("{} 1/min".format(obj.RPM)))

        # Non-rotating patches — plain string
        self.form.inputNonRotatingPatches.setText(obj.NonRotatingPatches)

    def accept(self):
        """Validate inputs, write back to the object, and close the panel."""
        obj = self.obj

        # --- Validate: at least one solid must be selected ---
        if not obj.ShapeRefs:
            CfdTools.cfdErrorBox(
                "Please select at least one solid to define the MRF cell zone."
            )
            return

        # --- Validate: rotation axis must be non-zero ---
        ax = self.form.inputAxisX.property("quantity").Value
        ay = self.form.inputAxisY.property("quantity").Value
        az = self.form.inputAxisZ.property("quantity").Value
        if ax == 0.0 and ay == 0.0 and az == 0.0:
            CfdTools.cfdErrorBox("Rotation axis cannot be the zero vector.")
            return

        # --- Build values ---
        origin = FreeCAD.Vector(
            self.form.inputOriginX.property("quantity").Value,   # mm
            self.form.inputOriginY.property("quantity").Value,
            self.form.inputOriginZ.property("quantity").Value,
        )
        axis = FreeCAD.Vector(ax, ay, az)

        try:
            rpm = Units.Quantity(getQuantity(self.form.inputRPM)).getValueAs('1/min')
        except Exception:
            CfdTools.cfdErrorBox("RPM must be a valid rotational speed value.")
            return

        non_rotating = self.form.inputNonRotatingPatches.text().strip()

        # --- Close the panel first (matches CfdOF pattern) ---
        doc = FreeCADGui.getDocument(obj.Document)
        doc.resetEdit()

        # --- Persist changes ---
        storeIfChanged(obj, 'RotationOrigin', origin)
        storeIfChanged(obj, 'RotationAxis', axis)
        storeIfChanged(obj, 'RPM', float(rpm))
        storeIfChanged(obj, 'NonRotatingPatches', non_rotating)
        # ShapeRefs is mutated in-place by CfdFaceSelectWidget — no explicit store needed

        FreeCADGui.doCommand("FreeCAD.ActiveDocument.recompute()")

    def reject(self):
        """Restore the original ShapeRefs and NeedsCaseRewrite, then close."""
        self.obj.ShapeRefs = self.ShapeRefsOrig
        self.analysis_obj.NeedsCaseRewrite = self.NeedsCaseRewriteOrig
        doc = FreeCADGui.getDocument(self.obj.Document)
        doc.resetEdit()

    def closing(self):
        """Called by the view provider when the panel is being closed."""
        FreeCADGui.Selection.removeObserver(self.faceSelector)
