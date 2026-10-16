# CfdOF Extensions

This file documents every modification made to upstream CfdOF files so that
future merges from [jaheyns/cfdof](https://github.com/jaheyns/cfdof) can be
applied cleanly.

---

## MRF (Multiple Reference Frame) support

**Branch:** `feature/mrf-support`  
**Directory:** `extensions/mrf/`

### New files (no upstream conflict)

| File | Purpose |
|---|---|
| `extensions/__init__.py` | Makes `extensions/` a Python package |
| `extensions/mrf/__init__.py` | Makes `extensions/mrf/` a Python package |
| `extensions/mrf/CfdMRFZone.py` | FreeCAD data object + ViewProvider + Command for an MRF zone |
| `extensions/mrf/TaskPanelCfdMRFZone.py` | Task-panel logic (load / accept / reject / closing) |
| `extensions/mrf/Gui/TaskPanelCfdMRFZone.ui` | Qt Designer UI layout for the task panel |
| `extensions/mrf/Icons/mrf_zone.svg` | Toolbar icon (optional — falls back to meanvelocityforce.svg) |
| `extensions/mrf/templates/MRFProperties` | TemplateBuilder template → `constant/MRFProperties` |

### Upstream files modified

#### `CfdOF/CfdTools.py`

After the `getMeanVelocityForceObjects()` function, add:

```python
# MRF extension
def getMRFZoneObjects(analysis_object):
    """Return all CfdMRFZone objects belonging to the analysis."""
    return getModelsOfType(analysis_object, 'CfdMRFZone')
```

*Merge note:* pure addition — no existing lines changed.

---

#### `CfdOF/Solve/CfdCaseWriterFoam.py`

Three additions, all clearly marked with `# MRF extension` comments:

1. **`__init__`** — after `self.zone_objs = …`:
   ```python
   self.mrf_zone_objs = CfdTools.getMRFZoneObjects(analysis_obj)
   ```

2. **`writeCase` → `self.settings` dict** — after `'zonesPresent': …`:
   ```python
   # MRF extension
   'mrfZones': {},
   'mrfZonesPresent': False,
   ```

3. **`writeCase` body** — after the `mean_velocity_force_cellzone_objs` block:
   ```python
   if self.mrf_zone_objs:
       cfdMessage('MRF zone(s) present\n')
       self.processMRFZoneProperties()
   ```

4. **`writeCase` → after `TemplateBuilder(…)`**:
   ```python
   if self.mrf_zone_objs:
       mrf_template_path = os.path.join(CfdTools.getModulePath(),
                                        "extensions", "mrf", "templates")
       TemplateBuilder(self.case_folder, mrf_template_path, self.settings)
   ```

5. **New method `processMRFZoneProperties()`** — inserted before
   `processInitialisationZoneProperties()`.

*Merge note:* all additions; no existing lines removed or reordered.

---

#### `InitGui.py`

1. After `import CfdOF.Solve.CfdMeanVelocityForce`:
   ```python
   # MRF extension
   from extensions.mrf import CfdMRFZone  # registers CfdOF_MRFZone command
   ```

2. In `cmdlst`, after `'CfdOF_MeanVelocityForce'`:
   ```python
   'CfdOF_MRFZone',
   ```

*Merge note:* pure additions.

---

### Design notes

* **No dedicated solver required.** MRF zones work with `simpleFoam` and
  `pimpleFoam`; the `MRFProperties` dictionary is read automatically by
  those solvers when present in `constant/`.
* **Template isolation.** The `MRFProperties` template lives in
  `extensions/mrf/templates/` and is processed by a *second*
  `TemplateBuilder` call only when MRF zones are present. This avoids
  touching the upstream `Data/Templates/` tree.
* **Units.** FreeCAD stores lengths in **mm** internally; the case writer
  converts the rotation origin to **m** before writing the template.
  RPM is converted to **rad/s** (`omega = RPM × 2π / 60`).
* **cellZone registration.** Each MRF zone is also added to
  `settings['zones']` so that `topoSetZonesDict` generates the
  corresponding `cellZoneSet` in the mesh.
