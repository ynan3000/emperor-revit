# -*- coding: ascii -*-
"""Smart Insulation - add / update / remove duct and pipe insulation by system type."""
from Autodesk.Revit import DB
from pyrevit import revit

import System
from System.Windows import Thickness, GridLength, GridUnitType, VerticalAlignment
from System.Windows.Controls import Grid, ColumnDefinition, RowDefinition, CheckBox, ComboBox, TextBox, TextBlock
from System.Windows.Markup import XamlReader

import emperor_ui
from emperor_mep import insulation as ins
from emperor_mep.common import begin, name_of, load_json, save_json, project_key, eid_int

TITLE = 'Emperor - Smart Insulation'
doc = revit.doc
uidoc = revit.uidoc
STORE = 'smart_insulation.json'

XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Emperor - Smart Insulation" Width="760" Height="640" MinWidth="640" MinHeight="460"
        WindowStartupLocation="CenterScreen" Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5"
        ShowInTaskbar="False">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="18,10">
      <StackPanel>
        <TextBlock Text="SMART INSULATION" Foreground="White" FontSize="18" FontWeight="Bold"/>
        <TextBlock Text="Insulation for ducts and pipes by system type - fixed thickness or by size"
                   Foreground="#F7DDE0" FontSize="11.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="{StaticResource Line}" BorderThickness="0,1,0,0" Padding="12,7">
      <DockPanel>
        <Button x:Name="CloseBtn" DockPanel.Dock="Right" Content="Close" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
        <Button x:Name="ApplyBtn" DockPanel.Dock="Right" Content="Apply" Style="{StaticResource RedBtn}" MinWidth="96"/>
        <Button x:Name="PreviewBtn" DockPanel.Dock="Right" Content="Preview" Style="{StaticResource OutlineBtn}" MinWidth="96"/>
        <TextBlock x:Name="Status" VerticalAlignment="Center" Foreground="{StaticResource Muted}" TextTrimming="CharacterEllipsis"/>
      </DockPanel>
    </Border>
    <Border DockPanel.Dock="Top" Margin="10,10,10,0" Background="White" BorderBrush="{StaticResource Line}"
            BorderThickness="1" CornerRadius="6" Padding="12,8">
      <WrapPanel>
        <StackPanel Margin="0,0,18,4">
          <TextBlock Text="APPLY TO" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <ComboBox x:Name="Scope" Width="190" Height="27" Margin="0,4,0,0">
            <ComboBoxItem Content="Whole model"/>
            <ComboBoxItem Content="Elements in the active view"/>
            <ComboBoxItem Content="Selected elements"/>
          </ComboBox>
        </StackPanel>
        <StackPanel Margin="0,0,18,4">
          <TextBlock Text="MODE" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <ComboBox x:Name="Mode" Width="230" Height="27" Margin="0,4,0,0">
            <ComboBoxItem Content="Add missing + update existing"/>
            <ComboBoxItem Content="Add missing only"/>
            <ComboBoxItem Content="Remove insulation"/>
          </ComboBox>
        </StackPanel>
        <StackPanel Margin="0,0,0,4">
          <TextBlock Text="INCLUDE" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <WrapPanel Margin="0,8,0,0">
            <CheckBox x:Name="IncFittings" Content="Fittings" IsChecked="True" Margin="0,0,14,0"/>
            <CheckBox x:Name="IncAccessories" Content="Accessories" Margin="0,0,14,0"/>
            <CheckBox x:Name="IncFlex" Content="Flex"/>
          </WrapPanel>
        </StackPanel>
      </WrapPanel>
    </Border>
    <Border Margin="10" Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6">
      <ScrollViewer VerticalScrollBarVisibility="Auto">
        <StackPanel Margin="12,8,12,10">
          <TextBlock Text="DUCT SYSTEMS" Foreground="{StaticResource Red}" FontWeight="Bold"/>
          <Grid x:Name="DuctRows" Margin="0,4,0,12"/>
          <TextBlock Text="PIPE SYSTEMS" Foreground="{StaticResource Red}" FontWeight="Bold"/>
          <Grid x:Name="PipeRows" Margin="0,4,0,8"/>
          <TextBlock Foreground="{StaticResource Muted}" FontSize="11.5" TextWrapping="Wrap" Margin="0,6,0,0"
                     Text="Thickness in mm. A single number is used for every size. By size: 'limit:thickness' pairs and a last value for bigger sizes, e.g. 50:25, 150:40, 50 = up to 50 mm -> 25, up to 150 mm -> 40, bigger -> 50. Size = diameter, or the larger side of a rectangular duct."/>
        </StackPanel>
      </ScrollViewer>
    </Border>
  </DockPanel>
</Window>'''

MODES = ['update', 'add', 'remove']


class Window(object):
    def __init__(self):
        self.win = XamlReader.Parse(emperor_ui.inject(XAML))
        emperor_ui.enable_mouse_glow(self.win)
        f = self.win.FindName
        self.scope, self.mode = f('Scope'), f('Mode')
        self.inc_fit, self.inc_acc, self.inc_flex = f('IncFittings'), f('IncAccessories'), f('IncFlex')
        self.status = f('Status')
        self.store = load_json(STORE, {})
        saved = self.store.get(project_key(doc), {})
        self.scope.SelectedIndex = saved.get('scope', 0)
        self.mode.SelectedIndex = saved.get('mode', 0)
        self.inc_fit.IsChecked = saved.get('fittings', True)
        self.inc_acc.IsChecked = saved.get('accessories', False)
        self.inc_flex.IsChecked = saved.get('flex', False)
        rules = dict(((r['kind'], r['system']), r) for r in saved.get('rules', []))
        self.rows = []
        self._build(f('DuctRows'), 'duct', rules)
        self._build(f('PipeRows'), 'pipe', rules)
        f('PreviewBtn').Click += lambda s, a: self.run(True)
        f('ApplyBtn').Click += lambda s, a: self.run(False)
        f('CloseBtn').Click += lambda s, a: self.win.Close()
        try:
            from System.Windows.Interop import WindowInteropHelper
            WindowInteropHelper(self.win).Owner = uidoc.Application.MainWindowHandle
        except Exception:
            pass

    def _build(self, grid, kind, saved):
        for w in (28, None, 210, 150):
            cd = ColumnDefinition()
            cd.Width = GridLength(1, GridUnitType.Star) if w is None else GridLength(w)
            grid.ColumnDefinitions.Add(cd)
        types = ins.insulation_types(doc, kind)
        type_names = [name_of(t) for t in types]
        systems = ins.system_types(doc, kind)
        if not systems:
            rd = RowDefinition()
            grid.RowDefinitions.Add(rd)
            tb = TextBlock()
            tb.Text = u'No %s system types in this project.' % kind
            tb.Foreground = emperor_ui_brush('#77777D')
            Grid.SetColumnSpan(tb, 4)
            grid.Children.Add(tb)
            return
        for r, st in enumerate(systems):
            sname = name_of(st)
            prev = saved.get((kind, sname), {})
            rd = RowDefinition()
            rd.Height = GridLength(36)
            grid.RowDefinitions.Add(rd)
            cb = CheckBox()
            cb.IsChecked = bool(prev.get('on', False))
            cb.VerticalAlignment = VerticalAlignment.Center
            label = TextBlock()
            label.Text = sname
            label.VerticalAlignment = VerticalAlignment.Center
            label.Margin = Thickness(4, 0, 8, 0)
            combo = ComboBox()
            combo.Height = 28
            combo.Margin = Thickness(0, 0, 8, 0)
            for n in type_names:
                combo.Items.Add(n)
            if not type_names:
                combo.Items.Add(u'(no %s insulation types loaded)' % kind)
                combo.IsEnabled = False
            idx = type_names.index(prev['insulation']) if prev.get('insulation') in type_names else 0
            combo.SelectedIndex = idx if combo.Items.Count else -1
            box = TextBox()
            box.Height = 28
            box.Padding = Thickness(6, 0, 6, 0)
            box.FontSize = 12
            box.VerticalContentAlignment = VerticalAlignment.Center
            box.Text = prev.get('thickness', u'25')
            box.ToolTip = u'25  or  50:25, 150:40, 50'
            for c, el in enumerate((cb, label, combo, box)):
                Grid.SetRow(el, r)
                Grid.SetColumn(el, c)
                grid.Children.Add(el)
            self.rows.append({'kind': kind, 'system': sname, 'check': cb, 'combo': combo, 'box': box,
                              'has_types': bool(type_names)})

    def _rules(self):
        out = []
        for row in self.rows:
            out.append({'kind': row['kind'], 'system': row['system'], 'on': bool(row['check'].IsChecked),
                        'insulation': u'%s' % row['combo'].SelectedItem if row['has_types'] else u'',
                        'thickness': u'%s' % row['box'].Text})
        return out

    def _save(self, rules):
        self.store[project_key(doc)] = {
            'scope': self.scope.SelectedIndex, 'mode': self.mode.SelectedIndex,
            'fittings': bool(self.inc_fit.IsChecked), 'accessories': bool(self.inc_acc.IsChecked),
            'flex': bool(self.inc_flex.IsChecked), 'rules': rules}
        save_json(STORE, self.store)

    def run(self, dry):
        rules = self._rules()
        self._save(rules)
        active = [r for r in rules if r['on']]
        if not active:
            emperor_ui.alert('Tick at least one system type.', TITLE, owner=self.win)
            return
        parts = ['curves']
        if self.inc_fit.IsChecked:
            parts.append('fittings')
        if self.inc_acc.IsChecked:
            parts.append('accessories')
        if self.inc_flex.IsChecked:
            parts.append('flex')
        view, ids = None, None
        if self.scope.SelectedIndex == 1:
            view = doc.ActiveView
        elif self.scope.SelectedIndex == 2:
            ids = list(uidoc.Selection.GetElementIds())
            if not ids:
                emperor_ui.alert('Nothing is selected in Revit. Select elements first or change "Apply to".',
                                 TITLE, owner=self.win)
                return
        mode = MODES[max(0, self.mode.SelectedIndex)]
        if dry:
            report = ins.run(doc, active, mode, parts, view, ids, dry_run=True)
            emperor_ui.alert(u'PREVIEW - nothing changed yet\n\n' + ins.describe(report), TITLE, owner=self.win)
            return
        if mode == 'remove' and not emperor_ui.alert(
                'Remove the insulation of the ticked system types (%s)?' % self.scope.SelectedItem.Content,
                TITLE, yes=True, no=True, owner=self.win, warn=True):
            return
        t, warnings = begin(doc, 'Emperor - Smart Insulation')
        try:
            report = ins.run(doc, active, mode, parts, view, ids)
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            emperor_ui.alert(u'Smart Insulation failed and nothing was changed.\n\n%s' % ex, TITLE,
                             owner=self.win, warn=True)
            return
        self.status.Text = u'Done: +%d added, %d updated, %d removed' % (report['added'], report['updated'], report['removed'])
        text = ins.describe(report)
        if warnings:
            text += u'\n\nRevit warnings answered automatically: %d' % len(warnings)
        emperor_ui.alert(text, TITLE, owner=self.win)


def emperor_ui_brush(hex_color):
    from System.Windows.Media import BrushConverter
    return BrushConverter().ConvertFromString(hex_color)


if doc is None or doc.IsFamilyDocument:
    emperor_ui.alert('Open a project (not a family) to use Smart Insulation.', TITLE, warn=True)
else:
    try:
        Window().win.ShowDialog()
    except Exception as ex:
        import traceback
        emperor_ui.alert(u'Smart Insulation stopped unexpectedly.\n\n%s' % traceback.format_exc(), TITLE, warn=True)
