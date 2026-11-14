# -*- coding: ascii -*-
"""View Manager - plan views per level (create / rename) and view templates for views."""
from pyrevit import revit

from System.Windows import Thickness, GridLength, GridUnitType, VerticalAlignment, Visibility
from System.Windows.Controls import Grid, ColumnDefinition, RowDefinition, CheckBox, ComboBox, TextBlock
from System.Windows.Markup import XamlReader

import emperor_ui
from emperor_views import manager as vm
from emperor_mep.common import begin, name_of, load_json, save_json, project_key, eid_int, ft_to_mm

TITLE = 'Emperor - View Manager'
doc = revit.doc
uidoc = revit.uidoc
STORE = 'view_manager.json'
NONE_TEMPLATE = u'(no template)'

XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Emperor - View Manager" Width="900" Height="640" MinWidth="780" MinHeight="520"
        WindowStartupLocation="CenterScreen" Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5"
        ShowInTaskbar="False">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="18,10">
      <StackPanel>
        <TextBlock Text="VIEW MANAGER" Foreground="White" FontSize="18" FontWeight="Bold"/>
        <TextBlock Text="Plan views for every level, named from the level - and view templates for your views"
                   Foreground="#F7DDE0" FontSize="11.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="{StaticResource Line}" BorderThickness="0,1,0,0" Padding="12,7">
      <DockPanel>
        <Button x:Name="CloseBtn" DockPanel.Dock="Right" Content="Close" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
        <Button x:Name="CreateBtn" DockPanel.Dock="Right" Content="Create" Style="{StaticResource RedBtn}" MinWidth="96"/>
        <Button x:Name="PreviewBtn" DockPanel.Dock="Right" Content="Preview" Style="{StaticResource OutlineBtn}" MinWidth="96"/>
        <Button x:Name="TemplateBtn" DockPanel.Dock="Left" Content="Template for views..." Style="{StaticResource OutlineBtn}" MinWidth="150"
                ToolTip="Give a view template to the views you tick (or remove their template)"/>
        <TextBlock x:Name="Status" VerticalAlignment="Center" Foreground="{StaticResource Muted}" TextTrimming="CharacterEllipsis" Margin="12,0,8,0"/>
      </DockPanel>
    </Border>
    <Grid Margin="10">
      <Grid.ColumnDefinitions>
        <ColumnDefinition Width="270"/>
        <ColumnDefinition Width="10"/>
        <ColumnDefinition Width="*"/>
      </Grid.ColumnDefinitions>
      <Border Grid.Column="0" Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6">
        <DockPanel Margin="12,8,8,10">
          <DockPanel DockPanel.Dock="Top" Margin="0,0,4,6">
            <Button x:Name="NoneBtn" DockPanel.Dock="Right" Content="None" Style="{StaticResource OutlineBtn}" MinWidth="52" Padding="6,2" Margin="4,0,0,0"/>
            <Button x:Name="AllBtn" DockPanel.Dock="Right" Content="All" Style="{StaticResource OutlineBtn}" MinWidth="52" Padding="6,2" Margin="4,0,0,0"/>
            <TextBlock Text="LEVELS" Foreground="{StaticResource Red}" FontWeight="Bold" VerticalAlignment="Center"/>
          </DockPanel>
          <ScrollViewer VerticalScrollBarVisibility="Auto">
            <StackPanel x:Name="LevelList"/>
          </ScrollViewer>
        </DockPanel>
      </Border>
      <ScrollViewer Grid.Column="2" VerticalScrollBarVisibility="Auto">
        <StackPanel>
          <Border Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6" Padding="12,8,12,10">
            <StackPanel>
              <TextBlock Text="VIEW TYPES" Foreground="{StaticResource Red}" FontWeight="Bold"/>
              <TextBlock Text="Tick one or more. New views use the view type and the template chosen on the row."
                         Foreground="{StaticResource Muted}" FontSize="11.5" Margin="0,2,0,4" TextWrapping="Wrap"/>
              <Grid x:Name="KindRows"/>
            </StackPanel>
          </Border>
          <Border Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6" Padding="12,8,12,10" Margin="0,10,0,0">
            <StackPanel>
              <TextBlock Text="VIEW NAME" Foreground="{StaticResource Red}" FontWeight="Bold"/>
              <WrapPanel Margin="0,6,0,0">
                <StackPanel>
                  <TextBlock Text="Prefix" Foreground="{StaticResource Muted}" FontSize="11.5"/>
                  <TextBox x:Name="Prefix" Width="150" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,2,0,0"/>
                </StackPanel>
                <StackPanel Margin="10,0,0,0">
                  <TextBlock Text="Separator" Foreground="{StaticResource Muted}" FontSize="11.5"/>
                  <TextBox x:Name="Sep" Width="70" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,2,0,0"
                           ToolTip="Put between the prefix and the level name, and between the level name and the suffix (only where there is a prefix / suffix). Spaces count."/>
                </StackPanel>
                <TextBlock Text="level name" VerticalAlignment="Bottom" Margin="10,0,10,6" Foreground="{StaticResource Ink}"/>
                <StackPanel>
                  <TextBlock Text="Suffix" Foreground="{StaticResource Muted}" FontSize="11.5"/>
                  <TextBox x:Name="Suffix" Width="150" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,2,0,0"/>
                </StackPanel>
              </WrapPanel>
              <TextBlock x:Name="Example" Margin="0,8,0,0" Foreground="{StaticResource Ink}" TextWrapping="Wrap"/>
            </StackPanel>
          </Border>
          <Border Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6" Padding="12,8,12,10" Margin="0,10,0,0">
            <StackPanel>
              <TextBlock Text="LEVELS THAT ALREADY HAVE A VIEW OF THAT TYPE" Foreground="{StaticResource Red}" FontWeight="Bold"/>
              <CheckBox x:Name="SkipBox" Margin="0,8,0,0" Content="Skip - leave those levels as they are"/>
              <CheckBox x:Name="RenameBox" Margin="0,8,0,0" Content="Rename the existing view to the new name"/>
              <CheckBox x:Name="CreateNewBox" Margin="0,8,0,0" Content="Create a new view - one more view on that level"/>
              <TextBlock Foreground="{StaticResource Muted}" FontSize="11.5" TextWrapping="Wrap" Margin="0,8,0,0"
                         Text="One choice at a time. Rename: a level with several views of that type is skipped (it is not clear which one to rename). A level that already has a view with exactly the new name is always left as it is."/>
            </StackPanel>
          </Border>
        </StackPanel>
      </ScrollViewer>
    </Grid>
  </DockPanel>
</Window>'''

TEMPLATE_XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Emperor - View Manager" Width="640" Height="620" MinWidth="520" MinHeight="420"
        WindowStartupLocation="CenterOwner" Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5"
        ShowInTaskbar="False">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="18,10">
      <StackPanel>
        <TextBlock Text="TEMPLATE FOR VIEWS" Foreground="White" FontSize="16" FontWeight="Bold"/>
        <TextBlock Text="Tick the views, choose the view template, press Apply"
                   Foreground="#F7DDE0" FontSize="11.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="{StaticResource Line}" BorderThickness="0,1,0,0" Padding="12,7">
      <DockPanel>
        <Button x:Name="CloseBtn" DockPanel.Dock="Right" Content="Close" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
        <Button x:Name="ApplyBtn" DockPanel.Dock="Right" Content="Apply" Style="{StaticResource RedBtn}" MinWidth="96"/>
        <TextBlock x:Name="Status" VerticalAlignment="Center" Foreground="{StaticResource Muted}" TextTrimming="CharacterEllipsis"/>
      </DockPanel>
    </Border>
    <Border DockPanel.Dock="Bottom" Margin="10,0,10,10" Background="White" BorderBrush="{StaticResource Line}"
            BorderThickness="1" CornerRadius="6" Padding="12,8">
      <DockPanel>
        <TextBlock DockPanel.Dock="Left" Text="VIEW TEMPLATE" Foreground="{StaticResource Red}" FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,12,0"/>
        <ComboBox x:Name="Template" Height="28"/>
      </DockPanel>
    </Border>
    <Border Margin="10" Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6">
      <DockPanel Margin="12,8,8,10">
        <DockPanel DockPanel.Dock="Top" Margin="0,0,4,6">
          <Button x:Name="NoneBtn" DockPanel.Dock="Right" Content="None" Style="{StaticResource OutlineBtn}" MinWidth="52" Padding="6,2" Margin="4,0,0,0"/>
          <Button x:Name="AllBtn" DockPanel.Dock="Right" Content="All shown" Style="{StaticResource OutlineBtn}" MinWidth="76" Padding="6,2" Margin="4,0,0,0"/>
          <TextBlock DockPanel.Dock="Left" Text="VIEWS" Foreground="{StaticResource Red}" FontWeight="Bold" VerticalAlignment="Center" Margin="0,0,12,0"/>
          <TextBox x:Name="Filter" Height="28" Padding="6,0" VerticalContentAlignment="Center"
                   ToolTip="Type part of a view name, view type or template name to shorten the list"/>
        </DockPanel>
        <ScrollViewer VerticalScrollBarVisibility="Auto">
          <StackPanel x:Name="ViewList"/>
        </ScrollViewer>
      </DockPanel>
    </Border>
  </DockPanel>
</Window>'''


def _owner(win):
    try:
        from System.Windows.Interop import WindowInteropHelper
        WindowInteropHelper(win).Owner = uidoc.Application.MainWindowHandle
    except Exception:
        pass


def _saved_mode(saved):
    """What to do with levels that already have a view - also reads the settings of View Manager 1.0
    ('rename' / 'ask' booleans; 'ask' no longer exists and becomes Skip)."""
    mode = saved.get('existing')
    if mode in vm.MODES:
        return mode
    if saved.get('rename'):
        return vm.RENAME
    return vm.SKIP


def _level_text(lv):
    try:
        return u'%s    (%+.2f m)' % (lv.Name, ft_to_mm(lv.Elevation) / 1000.0)
    except Exception:
        return lv.Name


# ---------------------------------------------------------------- template for views
class TemplateWindow(object):
    def __init__(self, owner):
        self.win = XamlReader.Parse(emperor_ui.inject(TEMPLATE_XAML))
        emperor_ui.enable_mouse_glow(self.win)
        try:
            self.win.Owner = owner
        except Exception:
            _owner(self.win)
        f = self.win.FindName
        self.status, self.filter, self.combo, self.panel = f('Status'), f('Filter'), f('Template'), f('ViewList')
        self.templates = vm.templates(doc)
        self.combo.Items.Add(u'(no template - remove it from the views)')
        for t in self.templates:
            self.combo.Items.Add(u'%s    [%s]' % (t.Name, vm.view_type_label(t)))
        self.combo.SelectedIndex = 0
        selected = set()
        for i in uidoc.Selection.GetElementIds():
            selected.add(eid_int(i))
        self.rows = []
        self.busy = True                 # no recount while the list is filled / ticked in bulk
        for v in vm.template_views(doc):
            cb = CheckBox()
            cb.Margin = Thickness(0, 3, 0, 3)
            cb.IsChecked = eid_int(v.Id) in selected
            cb.Checked += lambda s, a: self._count()
            cb.Unchecked += lambda s, a: self._count()
            row = {'id': eid_int(v.Id), 'check': cb, 'type': vm.view_type_label(v), 'name': v.Name}
            self._label(row, vm.template_name(doc, v))
            self.panel.Children.Add(cb)
            self.rows.append(row)
        f('AllBtn').Click += lambda s, a: self._tick(True)
        f('NoneBtn').Click += lambda s, a: self._tick(False)
        f('ApplyBtn').Click += lambda s, a: self.apply()
        f('CloseBtn').Click += lambda s, a: self.win.Close()
        self.filter.TextChanged += lambda s, a: self._filter()
        self.busy = False
        self._count()

    @staticmethod
    def _label(row, template):
        row['template'] = template
        text = u'%s:  %s' % (row['type'], row['name'])
        if template:
            text += u'      [%s]' % template
        row['text'] = text.lower()
        row['check'].Content = text

    def _shown(self, row):
        return row['check'].Visibility == Visibility.Visible

    def _filter(self):
        words = (u'%s' % self.filter.Text).lower().split()
        for row in self.rows:
            ok = all(w in row['text'] for w in words)
            row['check'].Visibility = Visibility.Visible if ok else Visibility.Collapsed
        self._count()

    def _tick(self, value):
        self.busy = True
        try:
            for row in self.rows:
                if self._shown(row) or not value:
                    row['check'].IsChecked = value
        finally:
            self.busy = False
        self._count()

    def _count(self):
        if self.busy:
            return
        ticked = len([r for r in self.rows if r['check'].IsChecked])
        shown = len([r for r in self.rows if self._shown(r)])
        self.status.Text = u'%d ticked  -  %d of %d views shown' % (ticked, shown, len(self.rows))

    def apply(self):
        ids = [r['id'] for r in self.rows if r['check'].IsChecked]
        if not ids:
            emperor_ui.alert('Tick at least one view.', TITLE, owner=self.win)
            return
        index = self.combo.SelectedIndex
        template = self.templates[index - 1] if index > 0 else None
        if template is None and not emperor_ui.alert(
                'Remove the view template from the %d ticked view(s)?' % len(ids),
                TITLE, yes=True, no=True, owner=self.win, warn=True):
            return
        t, _warnings = begin(doc, 'Emperor - View Manager: view template')
        try:
            report = vm.assign_template(doc, ids, eid_int(template.Id) if template is not None else None)
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            emperor_ui.alert(u'The template could not be applied and nothing was changed.\n\n%s' % ex, TITLE,
                             owner=self.win, warn=True)
            return
        for row in self.rows:                       # show the new template beside each view
            if row['check'].IsChecked:
                view = doc.GetElement(vm.make_eid(row['id']))
                if view is not None:
                    self._label(row, vm.template_name(doc, view))
        lines = [u'Changed: %d view(s)' % report['changed']]
        if report['same']:
            lines.append(u'Already had it: %d' % report['same'])
        if report['unfit']:
            lines.append(u'')
            lines.append(u'The template does not fit these views (other view type) - left as they are:')
            lines.extend(u'  ' + n for n in report['unfit'][:15])
            if len(report['unfit']) > 15:
                lines.append(u'  ... and %d more' % (len(report['unfit']) - 15))
        if report['failed']:
            lines.append(u'')
            lines.append(u'Problems:')
            lines.extend(u'  ' + n for n in report['failed'][:10])
        self._count()
        emperor_ui.alert(u'\n'.join(lines), TITLE, owner=self.win)


# ---------------------------------------------------------------- main window
class Window(object):
    def __init__(self):
        self.win = XamlReader.Parse(emperor_ui.inject(XAML))
        emperor_ui.enable_mouse_glow(self.win)
        f = self.win.FindName
        self.status, self.example = f('Status'), f('Example')
        self.prefix, self.suffix, self.sep = f('Prefix'), f('Suffix'), f('Sep')
        self.mode_boxes = {vm.SKIP: f('SkipBox'), vm.RENAME: f('RenameBox'), vm.CREATE: f('CreateNewBox')}
        self.store = load_json(STORE, {})
        saved = self.store.get(project_key(doc), {})
        self.prefix.Text = saved.get('prefix', u'')
        self.suffix.Text = saved.get('suffix', u'')
        self.sep.Text = saved.get('sep', vm.DEFAULT_SEP)
        self._set_mode(_saved_mode(saved))

        self.levels = []
        panel = f('LevelList')
        unticked = set(saved.get('levels_off', []))
        for lv in vm.levels(doc):
            cb = CheckBox()
            cb.Content = _level_text(lv)
            cb.Margin = Thickness(0, 3, 0, 3)
            cb.IsChecked = lv.Name not in unticked
            panel.Children.Add(cb)
            self.levels.append({'id': eid_int(lv.Id), 'name': lv.Name, 'check': cb})
        self.kinds = []
        self._build_kinds(f('KindRows'), saved.get('kinds', {}))

        f('AllBtn').Click += lambda s, a: self._tick_levels(True)
        f('NoneBtn').Click += lambda s, a: self._tick_levels(False)
        f('PreviewBtn').Click += lambda s, a: self.run(True)
        f('CreateBtn').Click += lambda s, a: self.run(False)
        f('TemplateBtn').Click += lambda s, a: self.templates()
        f('CloseBtn').Click += lambda s, a: self.win.Close()
        for box in (self.prefix, self.suffix, self.sep):
            box.TextChanged += lambda s, a: self._example()
        for key, box in self.mode_boxes.items():
            box.Checked += lambda s, a, key=key: self._set_mode(key)
            box.Unchecked += lambda s, a: self._keep_one()
        for lv in self.levels:
            lv['check'].Checked += lambda s, a: self._example()
            lv['check'].Unchecked += lambda s, a: self._example()
        self._example()
        _owner(self.win)

    def _set_mode(self, mode):
        """The three boxes answer one question: exactly one of them is ticked."""
        if getattr(self, '_busy_mode', False):
            return
        self._busy_mode = True
        try:
            for key, box in self.mode_boxes.items():
                box.IsChecked = key == mode
        finally:
            self._busy_mode = False

    def _keep_one(self):
        """Unticking the ticked box would leave none ticked: Skip (the default) is ticked instead."""
        if getattr(self, '_busy_mode', False):
            return
        if not any(box.IsChecked for box in self.mode_boxes.values()):
            self._set_mode(vm.SKIP)

    def _mode(self):
        for key in vm.MODES:
            if self.mode_boxes[key].IsChecked:
                return key
        return vm.SKIP

    def _name_parts(self):
        return u'%s' % self.prefix.Text, u'%s' % self.suffix.Text, u'%s' % self.sep.Text

    def _build_kinds(self, grid, saved):
        for w in (130, None, None):
            cd = ColumnDefinition()
            cd.Width = GridLength(1, GridUnitType.Star) if w is None else GridLength(w)
            grid.ColumnDefinitions.Add(cd)
        rd = RowDefinition()
        rd.Height = GridLength(22)
        grid.RowDefinitions.Add(rd)
        for c, text in enumerate((u'', u'View type for new views', u'Template for new views')):
            tb = TextBlock()
            tb.Text = text
            tb.FontSize = 11.5
            tb.Foreground = self.win.FindResource('Muted')
            tb.VerticalAlignment = VerticalAlignment.Center
            Grid.SetColumn(tb, c)
            grid.Children.Add(tb)
        for r, (key, label, _fam, _vt) in enumerate(vm.KINDS):
            prev = saved.get(key, {})
            rd = RowDefinition()
            rd.Height = GridLength(36)
            grid.RowDefinitions.Add(rd)
            types = vm.view_family_types(doc, key)
            temps = vm.templates(doc, key)
            cb = CheckBox()
            cb.Content = label
            cb.VerticalAlignment = VerticalAlignment.Center
            cb.IsChecked = bool(prev.get('on', key == 'floor')) and bool(types)
            type_combo = ComboBox()
            type_combo.Height = 28
            type_combo.Margin = Thickness(0, 0, 8, 0)
            names = [name_of(t) for t in types]
            for n in names:
                type_combo.Items.Add(n)
            if not types:
                type_combo.Items.Add(u'(no %s type in this project)' % label.lower())
                type_combo.IsEnabled = False
                cb.IsEnabled = False
            type_combo.SelectedIndex = names.index(prev['type']) if prev.get('type') in names else 0
            temp_combo = ComboBox()
            temp_combo.Height = 28
            temp_combo.Items.Add(NONE_TEMPLATE)
            tnames = [t.Name for t in temps]
            for n in tnames:
                temp_combo.Items.Add(n)
            temp_combo.SelectedIndex = tnames.index(prev['template']) + 1 if prev.get('template') in tnames else 0
            for c, el in enumerate((cb, type_combo, temp_combo)):
                Grid.SetRow(el, r + 1)
                Grid.SetColumn(el, c)
                grid.Children.Add(el)
            self.kinds.append({'key': key, 'label': label, 'check': cb, 'types': types, 'templates': temps,
                               'type_combo': type_combo, 'temp_combo': temp_combo})

    def _tick_levels(self, value):
        for lv in self.levels:
            lv['check'].IsChecked = value

    def _example(self):
        sample = self.levels[0]['name'] if self.levels else u'Level 1'
        for lv in self.levels:
            if lv['check'].IsChecked:
                sample = lv['name']
                break
        prefix, suffix, sep = self._name_parts()
        name = vm.make_name(prefix, sample, suffix, sep)
        bad = vm.bad_chars(prefix + suffix + sep)
        if bad:
            self.example.Text = u'Revit does not accept these characters in a view name:  %s' % u'  '.join(bad)
            self.example.Foreground = self.win.FindResource('Red')
        else:
            self.example.Text = u'Example:  level "%s"  ->  view "%s"' % (sample, name)
            self.example.Foreground = self.win.FindResource('Ink')

    def _kind_state(self):
        out = {}
        for k in self.kinds:
            has_type = bool(k['types'])
            ti = k['temp_combo'].SelectedIndex
            out[k['key']] = {
                'on': bool(k['check'].IsChecked) and has_type,
                'type': u'%s' % k['type_combo'].SelectedItem if has_type else u'',
                'template': k['templates'][ti - 1].Name if ti > 0 else u'',
                'type_id': eid_int(k['types'][max(0, k['type_combo'].SelectedIndex)].Id) if has_type else None,
                'template_id': eid_int(k['templates'][ti - 1].Id) if ti > 0 else None,
            }
        return out

    def _save(self, kinds):
        self.store[project_key(doc)] = {
            'prefix': u'%s' % self.prefix.Text, 'suffix': u'%s' % self.suffix.Text, 'sep': u'%s' % self.sep.Text,
            'existing': self._mode(),
            'levels_off': [lv['name'] for lv in self.levels if not lv['check'].IsChecked],
            'kinds': dict((k, {'on': v['on'], 'type': v['type'], 'template': v['template']})
                          for k, v in kinds.items())}
        save_json(STORE, self.store)

    def templates(self):
        TemplateWindow(self.win).win.ShowDialog()

    def run(self, dry):
        kinds = self._kind_state()
        self._save(kinds)
        active = [k[0] for k in vm.KINDS if kinds[k[0]]['on']]
        level_ids = [lv['id'] for lv in self.levels if lv['check'].IsChecked]
        if not level_ids:
            emperor_ui.alert('Tick at least one level.', TITLE, owner=self.win)
            return
        if not active:
            emperor_ui.alert('Tick at least one view type.', TITLE, owner=self.win)
            return
        prefix, suffix, sep = self._name_parts()
        bad = vm.bad_chars(prefix + suffix + sep)
        if bad:
            emperor_ui.alert(u'Revit does not accept these characters in a view name:  %s\n\n'
                             u'Remove them from the prefix / separator / suffix.' % u'  '.join(bad),
                             TITLE, owner=self.win, warn=True)
            return
        plan = vm.build_plan(doc, level_ids, active, prefix, suffix, self._mode(), sep)
        if dry:
            emperor_ui.alert(u'PREVIEW - nothing changed yet\n\n' + vm.describe_plan(plan), TITLE, owner=self.win)
            return
        todo = [a for a in plan if a['action'] in ('create', 'rename')]
        if not todo:
            emperor_ui.alert(u'Nothing to do.\n\n' + vm.describe_plan(plan), TITLE, owner=self.win)
            return
        t, warnings = begin(doc, 'Emperor - View Manager')
        try:
            report = vm.apply_plan(doc, todo, kinds)
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            emperor_ui.alert(u'View Manager failed and nothing was changed.\n\n%s' % ex, TITLE,
                             owner=self.win, warn=True)
            return
        self.status.Text = u'Done: %d created, %d renamed' % (len(report['created']), report['renamed'])
        lines = [u'Created: %d    Renamed: %d    Template applied: %d'
                 % (len(report['created']), report['renamed'], report['templated'])]
        skipped = [a for a in plan if a['action'] == 'skip']
        if skipped:
            lines.append(u'')
            lines.append(u'Skipped: %d' % len(skipped))
            lines.extend(u'  %s  %s - %s' % (vm.KIND_LABEL[a['kind']], a['level'], a['note']) for a in skipped[:12])
            if len(skipped) > 12:
                lines.append(u'  ... and %d more' % (len(skipped) - 12))
        if report['failed']:
            lines.append(u'')
            lines.append(u'Problems:')
            lines.extend(u'  ' + x for x in report['failed'][:12])
        if warnings:
            lines.append(u'')
            lines.append(u'Revit warnings answered automatically: %d' % len(warnings))
        emperor_ui.alert(u'\n'.join(lines), TITLE, owner=self.win)


if doc is None or doc.IsFamilyDocument:
    emperor_ui.alert('Open a project (not a family) to use View Manager.', TITLE, warn=True)
else:
    try:
        Window().win.ShowDialog()
    except Exception:
        import traceback
        emperor_ui.alert(u'View Manager stopped unexpectedly.\n\n%s' % traceback.format_exc(), TITLE, warn=True)
