# -*- coding: ascii -*-
# Vertical Align - single main diffuser centerline alignment
# Grille Alignment Manager v1.2 - Revit 2024 / pyRevit / IronPython 2.7
# Self-contained to avoid import-path failures for grille_align_core.
# Includes host and linked reference handling and preselection support.

# -*- coding: ascii -*-
# Grille Alignment Manager core
# Revit 2024 / pyRevit / IronPython 2.7

import math
from Autodesk.Revit import DB
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import revit, forms, script
import emperor_ui


def _eid(element_id):
    """ElementId -> int on every Revit version (IntegerValue is gone from Revit 2026)."""
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)



uidoc = revit.uidoc
doc = revit.doc
logger = script.get_logger()


class AirTerminalSelectionFilter(ISelectionFilter):
    def AllowElement(self, elem):
        return is_air_terminal(elem)

    def AllowReference(self, reference, position):
        return False


class AnyReferenceSelectionFilter(ISelectionFilter):
    """Accept suitable host-model elements and elements inside loaded RVT links."""
    def AllowElement(self, elem):
        try:
            if isinstance(elem, DB.RevitLinkInstance):
                return elem.GetLinkDocument() is not None
            return is_reference_candidate(elem)
        except Exception:
            return False

    def AllowReference(self, reference, position):
        try:
            return reference_to_target(reference) is not None
        except Exception:
            return False


class ReferenceTarget(object):
    def __init__(self, element, link_instance=None, linked_doc=None):
        self.element = element
        self.link_instance = link_instance
        self.linked_doc = linked_doc
        if link_instance is not None:
            try:
                self.transform = link_instance.GetTotalTransform()
            except Exception:
                self.transform = link_instance.GetTransform()
            self.identity = 'L{0}:E{1}'.format(
                _eid(link_instance.Id), _eid(element.Id))
            self.display_name = '{0} - {1}'.format(
                safe_element_name(link_instance), safe_element_name(element))
        else:
            self.transform = DB.Transform.Identity
            self.identity = 'H:E{0}'.format(_eid(element.Id))
            self.display_name = safe_element_name(element)
        self.name = safe_element_name(element)


def is_air_terminal(elem):
    try:
        return elem is not None and elem.Category is not None and \
            _eid(elem.Category.Id) == int(DB.BuiltInCategory.OST_DuctTerminal)
    except Exception:
        return False


def is_reference_candidate(elem):
    """Any visible model element with usable extents can serve as a reference.

    Air terminals are handled as the moving diffusers, while view/level/link
    container objects are not valid physical reference boundaries.
    """
    try:
        if elem is None:
            return False
        if isinstance(elem, (DB.View, DB.Level, DB.RevitLinkInstance)):
            return False
        if is_air_terminal(elem):
            return False
        bbox = elem.get_BoundingBox(None)
        if bbox is not None:
            return True
        options = DB.Options()
        options.ComputeReferences = False
        options.IncludeNonVisibleObjects = False
        options.DetailLevel = DB.ViewDetailLevel.Fine
        geometry = elem.get_Geometry(options)
        return geometry is not None
    except Exception:
        return False


def reference_to_target(reference):
    """Resolve a picked reference to its host or linked element, not its face."""
    if reference is None:
        return None
    try:
        linked_id = reference.LinkedElementId
        is_linked_reference = linked_id is not None and _eid(linked_id) >= 0
    except Exception:
        is_linked_reference = False

    if is_linked_reference:
        link_instance = doc.GetElement(reference.ElementId)
        if not isinstance(link_instance, DB.RevitLinkInstance):
            return None
        linked_doc = link_instance.GetLinkDocument()
        if linked_doc is None:
            return None
        linked_elem = linked_doc.GetElement(reference.LinkedElementId)
        if not is_reference_candidate(linked_elem):
            return None
        return ReferenceTarget(linked_elem, link_instance, linked_doc)

    host_elem = doc.GetElement(reference.ElementId)
    if isinstance(host_elem, DB.RevitLinkInstance):
        return None
    if not is_reference_candidate(host_elem):
        return None
    return ReferenceTarget(host_elem)


def safe_element_name(elem):
    try:
        if elem.Name:
            return elem.Name
    except Exception:
        pass
    return 'Element'


def normalize_horizontal(vector):
    try:
        length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y)
        if length < 1.0e-9:
            return None
        return DB.XYZ(vector.X / length, vector.Y / length, 0.0)
    except Exception:
        return None


def get_view_axis(mode):
    """Use the active plan view's screen-right or screen-up direction projected to XY."""
    view = doc.ActiveView
    if not isinstance(view, DB.ViewPlan):
        raise Exception('Open a floor plan, ceiling plan, or engineering plan before using this button.')

    if mode == 'horizontal':
        vector = normalize_horizontal(view.RightDirection)
        axis_name = 'horizontal'
    else:
        vector = normalize_horizontal(view.UpDirection)
        axis_name = 'vertical'

    if vector is None:
        raise Exception('Could not determine the {0} direction from the active plan view.'.format(axis_name))
    return vector


def get_bbox_points(elem):
    points = []
    try:
        bbox = elem.get_BoundingBox(None)
        if bbox is None:
            return points
        transform = bbox.Transform
        for x in (bbox.Min.X, bbox.Max.X):
            for y in (bbox.Min.Y, bbox.Max.Y):
                for z in (bbox.Min.Z, bbox.Max.Z):
                    point = DB.XYZ(x, y, z)
                    try:
                        point = transform.OfPoint(point)
                    except Exception:
                        pass
                    points.append(point)
    except Exception:
        return []
    return points


def append_geometry_points(geometry, points):
    try:
        for item in geometry:
            try:
                if isinstance(item, DB.Solid):
                    try:
                        for face in item.Faces:
                            try:
                                mesh = face.Triangulate()
                                for vertex in mesh.Vertices:
                                    points.append(vertex)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        for edge in item.Edges:
                            try:
                                for point in edge.AsCurve().Tessellate():
                                    points.append(point)
                            except Exception:
                                pass
                    except Exception:
                        pass
                elif isinstance(item, DB.GeometryInstance):
                    try:
                        append_geometry_points(item.GetInstanceGeometry(), points)
                    except Exception:
                        pass
                elif isinstance(item, DB.Mesh):
                    try:
                        for vertex in item.Vertices:
                            points.append(vertex)
                    except Exception:
                        pass
                elif isinstance(item, DB.Curve):
                    try:
                        for point in item.Tessellate():
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
        geometry = elem.get_Geometry(options)
        if geometry is not None:
            append_geometry_points(geometry, points)
    except Exception:
        pass

    if len(points) < 2:
        points = get_bbox_points(elem)
    if external_transform is not None:
        transformed = []
        for point in points:
            try:
                transformed.append(external_transform.OfPoint(point))
            except Exception:
                transformed.append(point)
        points = transformed
    return points


def projection_range(elem, axis, external_transform=None):
    points = get_geometry_points(elem, external_transform)
    if not points:
        raise Exception('Could not read geometry or a bounding box for reference element ID {0}.'.format(
            _eid(elem.Id)))
    values = [point.DotProduct(axis) for point in points]
    return min(values), max(values)


def projection_center(elem, axis, external_transform=None):
    """Use the geometric extents center along the alignment axis, not the family origin."""
    lower, upper = projection_range(elem, axis, external_transform)
    return (lower + upper) / 2.0


def append_planar_normals(geometry, normals):
    try:
        for item in geometry:
            try:
                if isinstance(item, DB.Solid):
                    for face in item.Faces:
                        try:
                            if isinstance(face, DB.PlanarFace):
                                normal = normalize_horizontal(face.FaceNormal)
                                if normal is not None:
                                    normals.append(normal)
                        except Exception:
                            pass
                elif isinstance(item, DB.GeometryInstance):
                    try:
                        append_planar_normals(item.GetInstanceGeometry(), normals)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def get_reference_normals(target):
    normals = []
    try:
        options = DB.Options()
        options.ComputeReferences = False
        options.IncludeNonVisibleObjects = False
        options.DetailLevel = DB.ViewDetailLevel.Fine
        geometry = target.element.get_Geometry(options)
        if geometry is not None:
            append_planar_normals(geometry, normals)
    except Exception:
        pass

    try:
        if isinstance(target.element, DB.Wall):
            orientation = normalize_horizontal(target.element.Orientation)
            if orientation is not None:
                normals.append(orientation)
    except Exception:
        pass

    result = []
    for normal in normals:
        try:
            normal = target.transform.OfVector(normal)
            normal = normalize_horizontal(normal)
            if normal is not None:
                result.append(normal)
        except Exception:
            pass
    return result


def validate_reference_direction(target, axis, mode):
    """If planar faces exist, require a face normal parallel to the requested movement axis."""
    normals = get_reference_normals(target)
    if not normals:
        # Curved objects such as circular columns have no single planar side normal.
        return
    best_score = 0.0
    for normal in normals:
        try:
            score = abs(normal.DotProduct(axis))
            if score > best_score:
                best_score = score
        except Exception:
            pass
    if best_score < math.cos(math.radians(10.0)):
        raise Exception(
            'The reference "{0}" does not have a detected vertical face perpendicular to the {1} alignment direction. '
            'Select an element whose near face is perpendicular to this row or column.'.format(
                target.name, mode))


class AirTerminalReferenceSelectionFilter(ISelectionFilter):
    """Allow a single host or linked Air Terminal as the alignment anchor."""
    def AllowElement(self, elem):
        try:
            if isinstance(elem, DB.RevitLinkInstance):
                return elem.GetLinkDocument() is not None
            return is_air_terminal(elem)
        except Exception:
            return False

    def AllowReference(self, reference, position):
        try:
            return reference_to_air_terminal_target(reference) is not None
        except Exception:
            return False


def reference_to_air_terminal_target(reference):
    """Resolve one picked Air Terminal from the host model or a loaded link."""
    if reference is None:
        return None
    try:
        linked_id = reference.LinkedElementId
        is_linked = linked_id is not None and _eid(linked_id) >= 0
    except Exception:
        is_linked = False

    if is_linked:
        link_instance = doc.GetElement(reference.ElementId)
        if not isinstance(link_instance, DB.RevitLinkInstance):
            return None
        linked_doc = link_instance.GetLinkDocument()
        if linked_doc is None:
            return None
        linked_elem = linked_doc.GetElement(reference.LinkedElementId)
        if not is_air_terminal(linked_elem):
            return None
        return ReferenceTarget(linked_elem, link_instance, linked_doc)

    host_elem = doc.GetElement(reference.ElementId)
    if not is_air_terminal(host_elem):
        return None
    return ReferenceTarget(host_elem)


def get_selected_grilles():
    """Support preselection or select moving diffusers after launching the button."""
    grilles = []
    seen = set()
    for element_id in list(uidoc.Selection.GetElementIds()):
        try:
            elem = doc.GetElement(element_id)
            if is_air_terminal(elem) and _eid(elem.Id) not in seen:
                grilles.append(elem)
                seen.add(_eid(elem.Id))
        except Exception:
            pass

    if not grilles:
        try:
            picked = uidoc.Selection.PickObjects(
                ObjectType.Element,
                AirTerminalSelectionFilter(),
                'Select the diffuser(s) to align, then click Finish.')
            for reference in picked:
                try:
                    elem = doc.GetElement(reference.ElementId)
                    if is_air_terminal(elem) and _eid(elem.Id) not in seen:
                        grilles.append(elem)
                        seen.add(_eid(elem.Id))
                except Exception:
                    pass
        except Exception as ex:
            if ex.__class__.__name__ == 'OperationCanceledException':
                return []
            raise
    return grilles


def get_center_alignment_axis(mode):
    """Return the move axis perpendicular to the desired aligned row/column.

    Horizontal Align gives all selected diffuser centers the same screen-up
    coordinate, so movement is along View.UpDirection.
    Vertical Align gives all selected diffuser centers the same screen-right
    coordinate, so movement is along View.RightDirection.
    """
    view = doc.ActiveView
    if not isinstance(view, DB.ViewPlan):
        raise Exception('Open a floor plan, ceiling plan, or engineering plan before using this button.')

    if mode == 'horizontal':
        vector = normalize_horizontal(view.UpDirection)
        description = 'horizontal row'
    else:
        vector = normalize_horizontal(view.RightDirection)
        description = 'vertical column'

    if vector is None:
        raise Exception('Could not determine the movement direction for the {0}.'.format(description))
    return vector


def pick_main_diffuser():
    """Ask for one anchor diffuser, on either the host model or a linked model."""
    reference = uidoc.Selection.PickObject(
        ObjectType.PointOnElement,
        AirTerminalReferenceSelectionFilter(),
        'Select ONE main/reference air diffuser. Click the diffuser body; do not select a face.')
    target = reference_to_air_terminal_target(reference)
    if target is None:
        raise Exception('The main reference must be an Air Terminal in the active model or a loaded Revit link.')
    return target


def safe_unpin_move_pin(elem, move_vector):
    was_pinned = bool(elem.Pinned)
    if was_pinned:
        elem.Pinned = False
    DB.ElementTransformUtils.MoveElement(doc, elem.Id, move_vector)
    if was_pinned:
        elem.Pinned = True


def run_center_align(mode):
    mode_label = 'Horizontal Align' if mode == 'horizontal' else 'Vertical Align'
    try:
        axis = get_center_alignment_axis(mode)
        grilles = get_selected_grilles()
        if not grilles:
            return

        # Only one anchor diffuser is needed. It may also be present in the
        # preselection; it will naturally remain in place when already aligned.
        anchor = pick_main_diffuser()
        target_center = projection_center(anchor.element, axis, anchor.transform)

        tolerance = 0.5 / 304.8  # 0.5 mm
        plan_items = []
        for elem in grilles:
            center = projection_center(elem, axis)
            delta = target_center - center
            if abs(delta) > tolerance:
                plan_items.append({
                    'elem': elem,
                    'delta': delta,
                    'pinned': bool(elem.Pinned)
                })

        if not plan_items:
            logger.info('%s: diffuser centers already align with main diffuser %s.',
                        mode_label, anchor.display_name)
            return

        with revit.Transaction(mode_label):
            for item in plan_items:
                elem = doc.GetElement(item['elem'].Id)
                if elem is None:
                    raise Exception('A selected diffuser no longer exists in the active model.')
                move_vector = axis.Multiply(item['delta'])
                safe_unpin_move_pin(elem, move_vector)

        logger.info('%s completed. Selected=%s; moved=%s; anchor=%s.',
                    mode_label, len(grilles), len(plan_items), anchor.display_name)

    except Exception as ex:
        if ex.__class__.__name__ == 'OperationCanceledException':
            return
        emperor_ui.alert(
            '{0} could not complete. No preview or completion panel is shown.\n\nError: {1}'.format(mode_label, ex),
            title=mode_label)


# Button entry point
run_center_align('vertical')
