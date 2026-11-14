# -*- coding: ascii -*-
# Diffuser Array - Emperor red & white WPF window (lib/emperor_ui.py)
# Revit 2024 / pyRevit / IronPython 2.7
# Preserves the three existing Grille Alignment Manager buttons.

import math
import clr
import System

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Windows.Markup import XamlReader
from System.Windows import Visibility
from System.Windows.Interop import WindowInteropHelper
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
    """Accept host-model Air Terminals only. Linked elements cannot be copied in the host model."""
    def AllowElement(self, elem):
        try:
            return is_air_terminal(elem)
        except Exception:
            return False

    def AllowReference(self, reference, position):
        return False


def is_air_terminal(elem):
    try:
        return elem is not None and elem.Category is not None and \
            _eid(elem.Category.Id) == int(DB.BuiltInCategory.OST_DuctTerminal)
    except Exception:
        return False


def normalize_xy(vector):
    try:
        length = math.sqrt(vector.X * vector.X + vector.Y * vector.Y)
        if length < 1.0e-9:
            return None
        return DB.XYZ(vector.X / length, vector.Y / length, 0.0)
    except Exception:
        return None


def get_direction(direction_code):
    view = doc.ActiveView
    if not isinstance(view, DB.ViewPlan):
        raise Exception('Open a floor plan, ceiling plan, or engineering plan before using Diffuser Array.')

    if direction_code in ('H_RIGHT', 'H_LEFT'):
        vector = normalize_xy(view.RightDirection)
    else:
        vector = normalize_xy(view.UpDirection)
    if vector is None:
        raise Exception('Could not determine the array direction from the active plan view.')

    if direction_code in ('H_LEFT', 'V_DOWN'):
        vector = vector.Multiply(-1.0)
    return vector


def get_element_center(elem):
    """Return the center of the element bounding extents in model coordinates."""
    bbox = elem.get_BoundingBox(None)
    if bbox is None:
        raise Exception('Could not determine the geometric center of diffuser {0}.'.format(_eid(elem.Id)))
    local_center = DB.XYZ(
        (bbox.Min.X + bbox.Max.X) * 0.5,
        (bbox.Min.Y + bbox.Max.Y) * 0.5,
        (bbox.Min.Z + bbox.Max.Z) * 0.5)
    try:
        return bbox.Transform.OfPoint(local_center)
    except Exception:
        return local_center


def get_preselected_air_terminals():
    found = []
    seen = set()
    try:
        for element_id in list(uidoc.Selection.GetElementIds()):
            elem = doc.GetElement(element_id)
            if is_air_terminal(elem) and _eid(elem.Id) not in seen:
                found.append(elem)
                seen.add(_eid(elem.Id))
    except Exception:
        pass
    return found


def pick_one_diffuser(prompt):
    reference = uidoc.Selection.PickObject(ObjectType.Element, AirTerminalSelectionFilter(), prompt)
    elem = doc.GetElement(reference.ElementId)
    if not is_air_terminal(elem):
        raise Exception('Select a diffuser (Revit Air Terminal) in the active model.')
    return elem


def sort_sources_along_axis(elements, axis):
    # For a two-element preselection, the first instance along the chosen
    # positive direction becomes SD and the second becomes RD.
    return sorted(elements, key=lambda elem: get_element_center(elem).DotProduct(axis))


DIALOG_XAML = u"""<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Emperor - Diffuser Array" Width="440" SizeToContent="Height" ResizeMode="NoResize"
        WindowStartupLocation="CenterScreen" Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5"
        ShowInTaskbar="False">
  <Window.Resources>
    <!--EMPEROR_THEME-->
  </Window.Resources>
  <StackPanel>
    <Border Background="{StaticResource HeaderBrush}" Padding="20,12">
      <StackPanel>
        <TextBlock Text="DIFFUSER ARRAY" Foreground="White" FontSize="19" FontWeight="Bold"/>
        <TextBlock Text="Repeat one diffuser, or alternate supply / return diffusers"
                   Foreground="#F7DDE0" FontSize="11.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border Margin="10" Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1"
            CornerRadius="6" Padding="14,10">
      <StackPanel>
        <TextBlock Text="ARRAY PATTERN" Foreground="{StaticResource Red}" FontWeight="Bold"/>
        <RadioButton x:Name="SingleRadio" GroupName="pat" IsChecked="True" Content="1 diffuser (repeat one type)"/>
        <RadioButton x:Name="DoubleRadio" GroupName="pat" Content="2 diffusers (alternate SD / RD)"/>
        <Border Background="{StaticResource RedTint}" CornerRadius="4" Padding="8,5" Margin="0,6,0,10">
          <TextBlock x:Name="InfoText" Text="Pattern: D - X - D - X - D ..." Foreground="{StaticResource Red}" FontWeight="SemiBold"/>
        </Border>
        <Grid>
          <Grid.ColumnDefinitions>
            <ColumnDefinition Width="*"/>
            <ColumnDefinition Width="170"/>
          </Grid.ColumnDefinitions>
          <Grid.RowDefinitions>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
            <RowDefinition Height="Auto"/>
          </Grid.RowDefinitions>
          <TextBlock Grid.Row="0" Text="Number of additional copies" VerticalAlignment="Center"/>
          <TextBox x:Name="CopiesBox" Grid.Row="0" Grid.Column="1" Text="6" Height="28" Margin="0,3" Padding="6,0" VerticalContentAlignment="Center"
                   TextAlignment="Right" ToolTip="1 to 200"/>
          <TextBlock Grid.Row="1" Text="X = center-to-center distance (mm)" VerticalAlignment="Center"/>
          <TextBox x:Name="DistanceBox" Grid.Row="1" Grid.Column="1" Text="1200" Height="28" Margin="0,3" Padding="6,0" VerticalContentAlignment="Center"
                   TextAlignment="Right" ToolTip="1 to 100000 mm"/>
          <TextBlock Grid.Row="2" Text="Array direction" VerticalAlignment="Center"/>
          <ComboBox x:Name="DirectionCombo" Grid.Row="2" Grid.Column="1" Height="28" Margin="0,3" SelectedIndex="0">
            <ComboBoxItem Content="Horizontal - Right"/>
            <ComboBoxItem Content="Horizontal - Left"/>
            <ComboBoxItem Content="Vertical - Up"/>
            <ComboBoxItem Content="Vertical - Down"/>
          </ComboBox>
        </Grid>
        <TextBlock x:Name="ErrorText" Foreground="{StaticResource RedBright}" FontWeight="SemiBold"
                   Margin="0,6,0,0" TextWrapping="Wrap" Visibility="Collapsed"/>
        <TextBlock Foreground="{StaticResource Muted}" FontSize="11.5" TextWrapping="Wrap" Margin="0,8,0,0"
                   Text="Preselected pair: first along the direction = SD, second = RD. Otherwise you pick SD, then RD. RD is moved to exactly X from SD."/>
      </StackPanel>
    </Border>
    <Border Background="#F3E9EA" BorderBrush="{StaticResource Line}" BorderThickness="0,1,0,0" Padding="14,8">
      <StackPanel Orientation="Horizontal" HorizontalAlignment="Right">
        <Button x:Name="OkButton" Content="Continue" Style="{StaticResource RedBtn}" MinWidth="96" IsDefault="True"/>
        <Button x:Name="CancelButton" Content="Cancel" Style="{StaticResource OutlineBtn}" MinWidth="96" Margin="0,3,0,3" IsCancel="True"/>
      </StackPanel>
    </Border>
  </StackPanel>
</Window>"""


def _parse_number(text):
    try:
        return float(u'{0}'.format(text).strip().replace(',', '.'))
    except Exception:
        return None


class ArraySettingsDialog(object):
    """Emperor-style settings window. show() returns True when the user pressed Continue."""

    def __init__(self):
        import emperor_ui
        self.window = XamlReader.Parse(emperor_ui.inject(DIALOG_XAML))
        emperor_ui.enable_mouse_glow(self.window)
        try:
            WindowInteropHelper(self.window).Owner = uidoc.Application.MainWindowHandle
        except Exception:
            pass
        f = self.window.FindName
        self.single_radio = f('SingleRadio')
        self.double_radio = f('DoubleRadio')
        self.info_text = f('InfoText')
        self.copies_box = f('CopiesBox')
        self.distance_box = f('DistanceBox')
        self.direction_combo = f('DirectionCombo')
        self.error_text = f('ErrorText')
        self.accepted = False
        self.values = None
        self.single_radio.Checked += self.on_mode_changed
        self.double_radio.Checked += self.on_mode_changed
        f('OkButton').Click += self.on_ok
        f('CancelButton').Click += self.on_cancel

    def on_mode_changed(self, sender, args):
        if self.double_radio.IsChecked:
            self.info_text.Text = 'Pattern: SD - X - RD - X - SD - X - RD ...'
        else:
            self.info_text.Text = 'Pattern: D - X - D - X - D ...'

    def _error(self, message):
        self.error_text.Text = message
        self.error_text.Visibility = Visibility.Visible

    def on_ok(self, sender, args):
        copies = _parse_number(self.copies_box.Text)
        if copies is None or copies != int(copies) or copies < 1 or copies > 200:
            self._error('Number of copies must be a whole number from 1 to 200.')
            return
        distance = _parse_number(self.distance_box.Text)
        if distance is None or distance < 1 or distance > 100000:
            self._error('Distance must be a number from 1 to 100000 mm.')
            return
        self.values = {
            'mode': 'double' if self.double_radio.IsChecked else 'single',
            'copies': int(copies),
            'distance_mm': float(distance),
            'direction_index': max(0, int(self.direction_combo.SelectedIndex))
        }
        self.accepted = True
        self.window.Close()

    def on_cancel(self, sender, args):
        self.accepted = False
        self.window.Close()

    def show(self):
        self.window.ShowDialog()
        return self.accepted

    def get_settings(self):
        return self.values


def get_sources(mode, axis, preselected):
    """Use a matching preselection, otherwise pick the template diffuser(s) explicitly."""
    if mode == 'single':
        if len(preselected) == 1:
            return [preselected[0]]
        return [pick_one_diffuser('Select the MAIN diffuser to use as the array source.')]

    if len(preselected) == 2:
        return sort_sources_along_axis(preselected, axis)
    if len(preselected) == 1:
        sd = preselected[0]
        rd = pick_one_diffuser('Select the SECOND diffuser to use as RD (return diffuser).')
        if _eid(rd.Id) == _eid(sd.Id):
            raise Exception('Select two different diffuser instances for SD and RD.')
        return [sd, rd]

    sd = pick_one_diffuser('Select the FIRST diffuser: SD (supply diffuser).')
    rd = pick_one_diffuser('Select the SECOND diffuser: RD (return diffuser).')
    if _eid(rd.Id) == _eid(sd.Id):
        raise Exception('Select two different diffuser instances for SD and RD.')
    return [sd, rd]


def set_pinned(elem, pinned):
    try:
        if elem is not None and bool(elem.Pinned) != bool(pinned):
            elem.Pinned = bool(pinned)
    except Exception:
        pass


def run_array():
    transaction = None
    try:
        view = doc.ActiveView
        if not isinstance(view, DB.ViewPlan):
            raise Exception('Open a floor plan, ceiling plan, or engineering plan before using Diffuser Array.')

        preselected = get_preselected_air_terminals()
        dialog = ArraySettingsDialog()
        if not dialog.show():
            return
        settings = dialog.get_settings()

        direction_codes = ['H_RIGHT', 'H_LEFT', 'V_UP', 'V_DOWN']
        axis = get_direction(direction_codes[settings['direction_index']])
        sources = get_sources(settings['mode'], axis, preselected)
        for elem in sources:
            if elem is None or not is_air_terminal(elem):
                raise Exception('Array sources must be Air Terminal instances in the active model. Linked-model diffusers cannot be copied into the host model.')

        if len(set([_eid(elem.Id) for elem in sources])) != len(sources):
            raise Exception('Select different diffuser instances for the array sources.')

        distance = settings['distance_mm'] / 304.8
        copies_count = settings['copies']
        source_centers = [get_element_center(elem) for elem in sources]
        sd_center = source_centers[0]
        original_pin_states = {}
        for elem in sources:
            original_pin_states[_eid(elem.Id)] = bool(elem.Pinned)

        # In two-source mode, the selected RD is moved into the second array position.
        rd_move = None
        if settings['mode'] == 'double':
            rd_center = source_centers[1]
            target_rd_center = sd_center + axis.Multiply(distance)
            rd_move = DB.XYZ(target_rd_center.X - rd_center.X,
                             target_rd_center.Y - rd_center.Y,
                             0.0)

        copied_items = []
        transaction = DB.Transaction(doc, 'Diffuser Array')
        transaction.Start()
        try:
            # Temporarily unpin source instances so they can be repositioned/copied reliably.
            for elem in sources:
                if elem.Pinned:
                    elem.Pinned = False

            if settings['mode'] == 'double':
                if rd_move.GetLength() > (0.1 / 304.8):
                    DB.ElementTransformUtils.MoveElement(doc, sources[1].Id, rd_move)
                doc.Regenerate()

                # Each additional copy continues after the SD/RD seed pair.
                # Array position 0 = SD, 1 = RD, 2 = SD, 3 = RD, etc.
                for copy_number in range(1, copies_count + 1):
                    array_index = copy_number + 1
                    if array_index % 2 == 0:
                        source = sources[0]
                        offset_steps = array_index
                        source_was_pinned = original_pin_states[_eid(sources[0].Id)]
                    else:
                        source = sources[1]
                        offset_steps = array_index - 1
                        source_was_pinned = original_pin_states[_eid(sources[1].Id)]
                    displacement = axis.Multiply(distance * offset_steps)
                    new_ids = list(DB.ElementTransformUtils.CopyElement(doc, source.Id, displacement))
                    if not new_ids:
                        raise Exception('Revit did not create a copy of diffuser {0}.'.format(_eid(source.Id)))
                    for new_id in new_ids:
                        copied_items.append((new_id, source_was_pinned))
            else:
                source = sources[0]
                source_was_pinned = original_pin_states[_eid(source.Id)]
                for copy_number in range(1, copies_count + 1):
                    displacement = axis.Multiply(distance * copy_number)
                    new_ids = list(DB.ElementTransformUtils.CopyElement(doc, source.Id, displacement))
                    if not new_ids:
                        raise Exception('Revit did not create a copy of diffuser {0}.'.format(_eid(source.Id)))
                    for new_id in new_ids:
                        copied_items.append((new_id, source_was_pinned))

            doc.Regenerate()

            # Restore original source pinning, then match each copied element to its source pin state.
            for elem in sources:
                set_pinned(doc.GetElement(elem.Id), original_pin_states[_eid(elem.Id)])
            for element_id, should_pin in copied_items:
                copied_elem = doc.GetElement(element_id)
                if copied_elem is not None and is_air_terminal(copied_elem):
                    set_pinned(copied_elem, should_pin)

            transaction.Commit()
        except Exception:
            try:
                if transaction.GetStatus() == DB.TransactionStatus.Started:
                    transaction.RollBack()
            except Exception:
                pass
            raise

        logger.info('Diffuser Array completed. Mode=%s, sources=%s, additional copies=%s, spacing_mm=%s, direction=%s.',
                    settings['mode'], len(sources), copies_count, settings['distance_mm'], direction_codes[settings['direction_index']])

    except Exception as ex:
        if ex.__class__.__name__ == 'OperationCanceledException':
            return
        emperor_ui.alert('Diffuser Array could not complete. The operation was rolled back where possible.\n\nError: {0}'.format(ex),
                    title='Diffuser Array')


run_array()
