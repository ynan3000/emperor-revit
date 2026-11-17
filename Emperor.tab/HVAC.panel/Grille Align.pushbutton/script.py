# -*- coding: ascii -*-
# Grille Alignment Manager - Automatic Apply, Linked References
# Revit 2024 / pyRevit / IronPython 2.7

import math

from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import revit, forms, script
import emperor_ui


from pyrevit.compat import get_elementid_value_func as _get_eid_value_func
_EID_VALUE = _get_eid_value_func()   # ElementId.Value (2024+) or .IntegerValue (older)


def _eid(element_id):
    """ElementId -> int on every Revit version."""
    return int(_EID_VALUE(element_id))




uidoc = revit.uidoc
doc = revit.doc
logger = script.get_logger()


class AirTerminalSelectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        try:
            return elem.Category is not None and _eid(elem.Category.Id) == int(DB.BuiltInCategory.OST_DuctTerminal)
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return False


class LinkedReferenceSelectionFilter(ISelectionFilter):
    """Filter for selecting an actual model element inside a loaded Revit link."""
    def AllowElement(self, elem):
        try:
            return isinstance(elem, DB.RevitLinkInstance) and elem.GetLinkDocument() is not None
        except Exception:
            return False

    def AllowReference(self, reference, position):
        try:
            link_instance = doc.GetElement(reference.ElementId)
            if not isinstance(link_instance, DB.RevitLinkInstance):
                return False
            linked_doc = link_instance.GetLinkDocument()
            if linked_doc is None:
                return False
            linked_elem = linked_doc.GetElement(reference.LinkedElementId)
            if linked_elem is None:
                return False
            if isinstance(linked_elem, DB.View) or isinstance(linked_elem, DB.Level):
                return False
            return linked_elem.get_BoundingBox(None) is not None
        except Exception:
            return False


class ReferenceTarget(object):
    """A reference element plus the transform needed to read linked geometry in host coordinates."""
    def __init__(self, element, link_instance=None, linked_doc=None):
        self.element = element
        self.link_instance = link_instance
        self.linked_doc = linked_doc
        self.transform = None
        if link_instance is not None:
            try:
                self.transform = link_instance.GetTotalTransform()
            except Exception:
                self.transform = link_instance.GetTransform()
        self.is_linked = link_instance is not None
        self.name = safe_element_name(element)
        self.identity = self._make_identity()
        if self.is_linked:
            self.display_name = '{0} - {1}'.format(safe_element_name(link_instance), self.name)
            self.id_text = 'Link ID {0} / Element ID {1}'.format(
                _eid(link_instance.Id), _eid(element.Id))
        else:
            self.display_name = self.name
            self.id_text = 'Element ID {0}'.format(_eid(element.Id))

    def _make_identity(self):
        if self.link_instance is not None:
            return 'L{0}:E{1}'.format(
                _eid(self.link_instance.Id), _eid(self.element.Id))
        return 'E{0}'.format(_eid(self.element.Id))


def is_air_terminal(elem):
    try:
        return elem is not None and elem.Category is not None and _eid(elem.Category.Id) == int(DB.BuiltInCategory.OST_DuctTerminal)
    except Exception:
        return False


def safe_element_name(elem):
    try:
        name = elem.Name
        if name:
            return name
    except Exception:
        pass
    return 'Element'


def get_bbox_points(elem, external_transform=None):
    points = []
    try:
        bbox = elem.get_BoundingBox(None)
        if bbox is None:
            return points
        transform = bbox.Transform
        xs = [bbox.Min.X, bbox.Max.X]
        ys = [bbox.Min.Y, bbox.Max.Y]
        zs = [bbox.Min.Z, bbox.Max.Z]
        for x in xs:
            for y in ys:
                for z in zs:
                    local_point = DB.XYZ(x, y, z)
                    try:
                        point = transform.OfPoint(local_point)
                    except Exception:
                        point = local_point
                    if external_transform is not None:
                        try:
                            point = external_transform.OfPoint(point)
                        except Exception:
                            pass
                    points.append(point)
    except Exception:
        return []
    return points


def add_geometry_points(geometry, points):
    try:
        for geom_obj in geometry:
            try:
                if isinstance(geom_obj, DB.Solid):
                    if geom_obj.Faces is not None and geom_obj.Faces.Size > 0:
                        for face in geom_obj.Faces:
                            try:
                                mesh = face.Triangulate()
                                for vert in mesh.Vertices:
                                    points.append(vert)
                            except Exception:
                                pass
                    try:
                        for edge in geom_obj.Edges:
                            try:
                                for point in edge.AsCurve().Tessellate():
                                    points.append(point)
                            except Exception:
                                pass
                    except Exception:
                        pass
                elif isinstance(geom_obj, DB.GeometryInstance):
                    try:
                        instance_geometry = geom_obj.GetInstanceGeometry()
                        add_geometry_points(instance_geometry, points)
                    except Exception:
                        pass
                elif isinstance(geom_obj, DB.Mesh):
                    try:
                        for vert in geom_obj.Vertices:
                            points.append(vert)
                    except Exception:
                        pass
                elif isinstance(geom_obj, DB.Curve):
                    try:
                        for point in geom_obj.Tessellate():
                            points.append(point)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def get_geometry_points(elem, external_transform=None):
    points = []
    try:
        options = DB.Options()
        options.ComputeReferences = False
        options.IncludeNonVisibleObjects = False
        options.DetailLevel = DB.ViewDetailLevel.Fine
        geom = elem.get_Geometry(options)
        if geom is not None:
            add_geometry_points(geom, points)
    except Exception:
        pass
    if len(points) < 2:
        return get_bbox_points(elem, external_transform)
    if external_transform is not None:
        transformed_points = []
        for point in points:
            try:
                transformed_points.append(external_transform.OfPoint(point))
            except Exception:
                transformed_points.append(point)
        points = transformed_points
    return points


def get_element_center(elem, external_transform=None):
    points = get_bbox_points(elem, external_transform)
    if not points:
        try:
            loc = elem.Location
            if isinstance(loc, DB.LocationPoint):
                point = loc.Point
                if external_transform is not None:
                    point = external_transform.OfPoint(point)
                return point
        except Exception:
            pass
        raise Exception('Could not determine a bounding box or insertion point for element ID {0}.'.format(_eid(elem.Id)))
    sx = 0.0
    sy = 0.0
    sz = 0.0
    for point in points:
        sx += point.X
        sy += point.Y
        sz += point.Z
    count = float(len(points))
    return DB.XYZ(sx / count, sy / count, sz / count)


def get_projected_range(elem, axis, external_transform=None):
    points = get_geometry_points(elem, external_transform)
    if not points:
        raise Exception('Could not read geometry for reference element ID {0}.'.format(_eid(elem.Id)))
    projections = []
    for point in points:
        projections.append(point.DotProduct(axis))
    return min(projections), max(projections)


def normalize_horizontal(vector):
    """Return a unit XY vector, or None if the vector has no usable XY component."""
    try:
        length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y)
        if length < 1.0e-9:
            return None
        return DB.XYZ(vector.X / length, vector.Y / length, 0.0)
    except Exception:
        return None


def add_planar_face_normals(geometry, normals):
    """Collect candidate horizontal normals from planar faces in element geometry."""
    try:
        for geom_obj in geometry:
            try:
                if isinstance(geom_obj, DB.Solid):
                    try:
                        for face in geom_obj.Faces:
                            if isinstance(face, DB.PlanarFace):
                                normal = normalize_horizontal(face.FaceNormal)
                                if normal is not None:
                                    normals.append(normal)
                    except Exception:
                        pass
                elif isinstance(geom_obj, DB.GeometryInstance):
                    try:
                        add_planar_face_normals(geom_obj.GetInstanceGeometry(), normals)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def get_reference_horizontal_normals(target):
    """Get candidate face normals in host coordinates, including linked transforms."""
    normals = []
    try:
        options = DB.Options()
        options.ComputeReferences = False
        options.IncludeNonVisibleObjects = False
        options.DetailLevel = DB.ViewDetailLevel.Fine
        geometry = target.element.get_Geometry(options)
        if geometry is not None:
            add_planar_face_normals(geometry, normals)
    except Exception:
        pass

    # Wall.Orientation is a useful supplementary normal when planar wall faces
    # are unavailable through the element geometry iterator.
    try:
        if isinstance(target.element, DB.Wall):
            # Leave the vector in the linked document's coordinates here;
            # the shared transform pass below maps every candidate exactly once.
            orientation = normalize_horizontal(target.element.Orientation)
            if orientation is not None:
                normals.append(orientation)
    except Exception:
        pass

    transformed = []
    for normal in normals:
        try:
            if target.transform is not None:
                normal = target.transform.OfVector(normal)
            normal = normalize_horizontal(normal)
            if normal is not None:
                transformed.append(normal)
        except Exception:
            pass
    return transformed


def choose_reference_normal(target, rough_axis):
    """Choose the horizontal face normal most aligned with the reference-to-reference direction."""
    candidates = get_reference_horizontal_normals(target)
    best = None
    best_score = -1.0
    for normal in candidates:
        try:
            score = abs(normal.DotProduct(rough_axis))
            if score > best_score:
                best_score = score
                best = normal
        except Exception:
            pass
    if best is None:
        return None, 0.0
    if best.DotProduct(rough_axis) < 0.0:
        best = best.Multiply(-1.0)
    return best, best_score


def get_perpendicular_movement_axis(ref1, ref2, center1, center2):
    """Derive the movement axis from reference face normals, not arbitrary center offsets."""
    dx = center2.X - center1.X
    dy = center2.Y - center1.Y
    rough_length = math.sqrt(dx * dx + dy * dy)
    if rough_length < (1.0 / 304.8):
        raise Exception('The reference elements have almost the same XY center. Select two references at opposite ends of the grille row.')
    rough_axis = DB.XYZ(dx / rough_length, dy / rough_length, 0.0)

    normal1, score1 = choose_reference_normal(ref1, rough_axis)
    normal2, score2 = choose_reference_normal(ref2, rough_axis)

    if normal1 is not None and normal2 is not None:
        alignment = normal1.DotProduct(normal2)
        # Both references must define a reasonably common perpendicular axis.
        if alignment < math.cos(math.radians(5.0)):
            raise Exception('The selected reference faces do not define a common perpendicular direction. Select two compatible, parallel reference faces at opposite ends of the grille row.')
        combined = normalize_horizontal(normal1.Add(normal2))
        axis = combined if combined is not None else rough_axis
    elif normal1 is not None:
        axis = normal1
    elif normal2 is not None:
        axis = normal2
    else:
        # Curved references (for example circular columns) may have no planar
        # faces. The center-to-center direction is then the practical fallback.
        axis = rough_axis

    if axis.DotProduct(rough_axis) < 0.0:
        axis = axis.Multiply(-1.0)
    return axis


def internal_to_mm(value):
    return DB.UnitUtils.ConvertFromInternalUnits(value, DB.UnitTypeId.Millimeters)


def mm_text(value, decimals):
    try:
        number = internal_to_mm(value)
        return ('{0:,.%df}' % decimals).format(number) + ' mm'
    except Exception:
        return '{0} mm'.format(value)


def signed_mm_text(value):
    number = internal_to_mm(value)
    if abs(number) < 0.05:
        number = 0.0
    return ('+' if number > 0 else '') + '{0:,.1f} mm'.format(number)


def get_selected_grilles():
    selected_ids = list(uidoc.Selection.GetElementIds())
    selected = []
    for element_id in selected_ids:
        elem = doc.GetElement(element_id)
        if is_air_terminal(elem):
            selected.append(elem)
    if selected:
        if len(selected) != len(selected_ids):
            emperor_ui.alert('Using {0} selected Air Terminal(s). Other selected elements will be ignored.'.format(len(selected)), title='Grille Alignment Manager')
        return selected
    try:
        refs = uidoc.Selection.PickObjects(ObjectType.Element, AirTerminalSelectionFilter(), 'Select the grille(s) to align, then click Finish.')
        result = []
        seen = set()
        for reference in refs:
            elem = doc.GetElement(reference.ElementId)
            if elem is not None and _eid(elem.Id) not in seen:
                result.append(elem)
                seen.add(_eid(elem.Id))
        return result
    except Exception as ex:
        if 'OperationCanceledException' in str(type(ex)) or ex.__class__.__name__ == 'OperationCanceledException':
            return []
        raise


def pick_reference(prompt):
    """Pick an actual model element inside a loaded Revit link. No source-choice dialog."""
    reference = uidoc.Selection.PickObject(
        ObjectType.LinkedElement,
        LinkedReferenceSelectionFilter(),
        prompt + ' Pick the element inside the linked model; do not select a face.')
    if reference is None:
        return None

    link_instance = doc.GetElement(reference.ElementId)
    if not isinstance(link_instance, DB.RevitLinkInstance):
        raise Exception('The selected reference could not be resolved to a Revit link instance.')

    linked_doc = link_instance.GetLinkDocument()
    if linked_doc is None:
        raise Exception('The selected Revit link is unloaded or unavailable. Reload the link and try again.')

    linked_elem = linked_doc.GetElement(reference.LinkedElementId)
    if linked_elem is None:
        raise Exception('Could not find the selected element in the linked document.')

    return ReferenceTarget(linked_elem, link_instance, linked_doc)

def run():
    grilles = get_selected_grilles()
    if not grilles:
        return

    try:
        ref1 = pick_reference('Select the FIRST linked reference element (start of the grille row).')
        if ref1 is None:
            return
        ref2 = pick_reference('Select the SECOND linked reference element (end of the grille row).')
        if ref2 is None:
            return
    except Exception as ex:
        if 'OperationCanceledException' in str(type(ex)) or ex.__class__.__name__ == 'OperationCanceledException':
            return
        emperor_ui.alert('Could not complete linked reference selection.\n\n{0}'.format(ex), title='Grille Alignment Manager')
        return

    if ref1.identity == ref2.identity:
        emperor_ui.alert('Please select two different reference elements.', title='Grille Alignment Manager')
        return

    try:
        center1 = get_element_center(ref1.element, ref1.transform)
        center2 = get_element_center(ref2.element, ref2.transform)
        axis = get_perpendicular_movement_axis(ref1, ref2, center1, center2)

        start_min, start_max = get_projected_range(ref1.element, axis, ref1.transform)
        end_min, end_max = get_projected_range(ref2.element, axis, ref2.transform)
        start_face = start_max
        end_face = end_min
        span = end_face - start_face
        if span <= (1.0 / 304.8):
            emperor_ui.alert('The detected near faces do not define a positive span. Select the first reference at one end of the row and the second reference at the opposite end.', title='Grille Alignment Manager')
            return

        spacing = span / float(len(grilles))
        grille_data = []
        for elem in grilles:
            center = get_element_center(elem)
            current_projection = center.DotProduct(axis)
            grille_data.append({'elem': elem, 'current_projection': current_projection})
        grille_data.sort(key=lambda row: row['current_projection'])

        plan_items = []
        for index, row in enumerate(grille_data):
            target_projection = start_face + ((index + 0.5) * spacing)
            delta = target_projection - row['current_projection']
            if abs(delta) > (0.5 / 304.8):
                plan_items.append({
                    'elem': row['elem'],
                    'delta': delta,
                    'was_pinned': bool(row['elem'].Pinned)
                })

        if not plan_items:
            logger.info('Grille Alignment: selected grilles already match target spacing. Grilles=%s; X=%s mm.',
                        len(grilles), internal_to_mm(spacing))
            return

        # Move immediately after both linked references are selected. No preview window.
        with revit.Transaction('Align Grilles - X-2X-X'):
            for item in plan_items:
                elem = doc.GetElement(item['elem'].Id)
                if elem is None:
                    raise Exception('A selected grille no longer exists in the document.')
                originally_pinned = item['was_pinned']
                if originally_pinned:
                    elem.Pinned = False
                move_vector = axis.Multiply(item['delta'])
                DB.ElementTransformUtils.MoveElement(doc, elem.Id, move_vector)
                if originally_pinned:
                    elem.Pinned = True

        logger.info('Grille Alignment completed. Grilles selected=%s; moved=%s; reference span=%s mm; center spacing X=%s mm; end offset X/2=%s mm.',
                    len(grilles), len(plan_items), internal_to_mm(span),
                    internal_to_mm(spacing), internal_to_mm(spacing / 2.0))

    except Exception as ex:
        emperor_ui.alert('Could not calculate or apply the grille layout. The changes are rolled back if Revit could not complete the transaction.\n\nCheck that the linked references are loaded and have readable geometry.\n\nError: {0}'.format(ex), title='Grille Alignment Manager')


try:
    run()
except Exception as ex:
    emperor_ui.alert('Grille Alignment Manager stopped unexpectedly.\n\n{0}'.format(ex), title='Grille Alignment Manager')
