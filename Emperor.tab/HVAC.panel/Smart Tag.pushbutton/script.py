# -*- coding: ascii -*-
"""Smart Tag - tag MEP elements in the active view, skipping tagged ones and avoiding overlaps."""
from Autodesk.Revit import DB
from pyrevit import revit

from System.Windows import Thickness, GridLength, GridUnitType, VerticalAlignment
from System.Windows.Controls import Grid, ColumnDefinition, RowDefinition, CheckBox, ComboBox, TextBlock
from System.Windows.Markup import XamlReader

import emperor_ui
from emperor_mep import tagging, tag_learn
from emperor_mep.common import begin, type_label, load_json, save_json, project_key, eid_int

TITLE = 'Emperor - Smart Tag'
doc = revit.doc
uidoc = revit.uidoc
STORE = 'smart_tag.json'
ORIENT = ['auto', 'horizontal', 'vertical']
DEFAULT_ON = ('ducts', 'pipes', 'terminals', 'equipment')

XAML = u'''<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        Title="Emperor - Smart Tag" Width="720" Height="600" MinWidth="620" MinHeight="460"
        WindowStartupLocation="CenterScreen" Background="#F8F8F8" FontFamily="Segoe UI" FontSize="12.5"
        ShowInTaskbar="False">
  <Window.Resources><!--EMPEROR_THEME--></Window.Resources>
  <DockPanel>
    <Border DockPanel.Dock="Top" Background="{StaticResource HeaderBrush}" Padding="18,10">
      <StackPanel>
        <TextBlock Text="SMART TAG" Foreground="White" FontSize="18" FontWeight="Bold"/>
        <TextBlock x:Name="ViewText" Foreground="#F7DDE0" FontSize="11.5" Margin="0,2,0,0"/>
      </StackPanel>
    </Border>
    <Border DockPanel.Dock="Bottom" Background="#F3E9EA" BorderBrush="{StaticResource Line}" BorderThickness="0,1,0,0" Padding="12,7">
      <DockPanel>
        <Button x:Name="CloseBtn" DockPanel.Dock="Right" Content="Close" Style="{StaticResource OutlineBtn}" MinWidth="86" Margin="0,3,0,3" IsCancel="True"/>
        <Button x:Name="TagBtn" DockPanel.Dock="Right" Content="Tag" Style="{StaticResource RedBtn}" MinWidth="96"/>
        <Button x:Name="RemoveBtn" DockPanel.Dock="Right" Content="Remove tags" Style="{StaticResource OutlineBtn}" MinWidth="110"/>
        <Button x:Name="LearnBtn" DockPanel.Dock="Right" Content="Learn from my changes" Style="{StaticResource OutlineBtn}" MinWidth="150"
                ToolTip="Move the tags Smart Tag placed to where you want them, then press this: Smart Tag learns your spots"/>
        <Button x:Name="ForgetBtn" DockPanel.Dock="Right" Content="Learned..." Style="{StaticResource OutlineBtn}" MinWidth="90"
                ToolTip="See what Smart Tag learned, or forget it"/>
        <TextBlock x:Name="Status" VerticalAlignment="Center" Foreground="{StaticResource Muted}" TextTrimming="CharacterEllipsis"/>
      </DockPanel>
    </Border>
    <Border DockPanel.Dock="Top" Margin="10,10,10,0" Background="White" BorderBrush="{StaticResource Line}"
            BorderThickness="1" CornerRadius="6" Padding="12,8">
      <WrapPanel>
        <StackPanel Margin="0,0,18,4">
          <TextBlock Text="TAG" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <ComboBox x:Name="Scope" Width="220" Height="27" Margin="0,4,0,0">
            <ComboBoxItem Content="Everything visible in the view"/>
            <ComboBoxItem Content="Selected elements only"/>
          </ComboBox>
        </StackPanel>
        <StackPanel Margin="0,0,18,4">
          <TextBlock Text="SKIP DUCTS / PIPES SHORTER THAN (mm)" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <TextBox x:Name="MinLength" Width="120" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,4,0,0" HorizontalAlignment="Left" Text="1000"/>
        </StackPanel>
        <StackPanel Margin="0,0,0,4">
          <TextBlock Text="GAP FROM ELEMENT EDGE (paper mm)" Foreground="{StaticResource Red}" FontWeight="Bold" FontSize="11"/>
          <TextBox x:Name="Offset" Width="120" Height="28" Padding="6,0" VerticalContentAlignment="Center" Margin="0,4,0,0" HorizontalAlignment="Left" Text="2"
                   ToolTip="Gap between the duct / pipe edge and the tag, in paper mm"/>
        </StackPanel>
        <WrapPanel Margin="0,8,0,0" Width="640">
          <CheckBox x:Name="SkipTagged" Content="Skip elements that already have a tag" IsChecked="True" Margin="0,0,18,0"/>
          <CheckBox x:Name="AvoidOverlap" Content="Avoid overlapping tags" IsChecked="True" Margin="0,0,18,0"/>
          <CheckBox x:Name="Leader" Content="Leader" Margin="0,0,18,0"
                    ToolTip="The leader leaves the left or right side of the text, then goes to the element"/>
          <CheckBox x:Name="AlwaysHorizontal" Content="Always horizontal" ToolTip="Every tag horizontal, also on vertical ducts / pipes"/>
          <CheckBox x:Name="SkipZero" Content="Skip ducts with 0 L/s flow" IsChecked="True" Margin="0,8,18,0"
                    ToolTip="Also skips ducts whose flow is not calculated or is below 0.5 L/s"/>
          <CheckBox x:Name="PlaceAnyway" Content="Place even without a free spot" Margin="0,8,18,0"
                    ToolTip="Off: a tag that would overlap another tag or text is not placed (it is counted in the report)"/>
          <CheckBox x:Name="UseLearned" Content="Use the spots learned from me" IsChecked="True" Margin="0,8,0,0"
                    ToolTip="Try the spots learned from your corrections first, then the built-in ones"/>
        </WrapPanel>
      </WrapPanel>
    </Border>
    <Border Margin="10" Background="White" BorderBrush="{StaticResource Line}" BorderThickness="1" CornerRadius="6">
      <ScrollViewer VerticalScrollBarVisibility="Auto">
        <StackPanel Margin="12,8,12,10">
          <TextBlock Text="CATEGORIES AND TAG TYPES" Foreground="{StaticResource Red}" FontWeight="Bold"/>
          <Grid x:Name="Rows" Margin="0,4,0,0"/>
        </StackPanel>
      </ScrollViewer>
    </Border>
  </DockPanel>
</Window>'''


def _num(text, default):
    try:
        return float(u'%s' % text)
    except Exception:
        return default


class Window(object):
    def __init__(self, view):
        self.view = view
        self.win = XamlReader.Parse(emperor_ui.inject(XAML))
        emperor_ui.enable_mouse_glow(self.win)
        f = self.win.FindName
        f('ViewText').Text = u'Active view: %s   (1 : %s)' % (view.Name, view.Scale)
        self.scope, self.min_len, self.offset = f('Scope'), f('MinLength'), f('Offset')
        self.skip, self.avoid, self.leader = f('SkipTagged'), f('AvoidOverlap'), f('Leader')
        self.skip_zero, self.anyway = f('SkipZero'), f('PlaceAnyway')
        self.always_h = f('AlwaysHorizontal')
        self.use_learned = f('UseLearned')
        self.status = f('Status')
        self.store = load_json(STORE, {})
        saved = self.store.get(project_key(doc), {})
        self.scope.SelectedIndex = 1 if (saved.get('scope') == 1 and uidoc.Selection.GetElementIds().Count) else 0
        self.min_len.Text = u'%s' % saved.get('min_length', 1000)
        self.offset.Text = u'%s' % saved.get('offset', 2)
        self.skip_zero.IsChecked = saved.get('skip_zero', True)
        self.anyway.IsChecked = saved.get('place_anyway', False)
        self.always_h.IsChecked = saved.get('always_horizontal', False)
        self.use_learned.IsChecked = saved.get('use_learned', True)
        self.skip.IsChecked = saved.get('skip', True)
        self.avoid.IsChecked = saved.get('avoid', True)
        self.leader.IsChecked = saved.get('leader', False)
        self.rows = []
        self._build(f('Rows'), saved.get('rules', {}))
        f('TagBtn').Click += lambda s, a: self.tag()
        f('RemoveBtn').Click += lambda s, a: self.remove()
        f('LearnBtn').Click += lambda s, a: self.learn()
        f('ForgetBtn').Click += lambda s, a: self.learned()
        f('CloseBtn').Click += lambda s, a: self.win.Close()
        try:
            from System.Windows.Interop import WindowInteropHelper
            WindowInteropHelper(self.win).Owner = uidoc.Application.MainWindowHandle
        except Exception:
            pass

    def _build(self, grid, saved):
        for w in (28, 170, None, 120):
            cd = ColumnDefinition()
            cd.Width = GridLength(1, GridUnitType.Star) if w is None else GridLength(w)
            grid.ColumnDefinitions.Add(cd)
        for r, (key, label, _cat, _tagcat, is_curve) in enumerate(tagging.CATEGORIES):
            prev = saved.get(key, {})
            types = tagging.tag_types(doc, key)
            rd = RowDefinition()
            rd.Height = GridLength(34)
            grid.RowDefinitions.Add(rd)
            cb = CheckBox()
            cb.IsChecked = bool(prev.get('on', key in DEFAULT_ON)) and bool(types)
            cb.IsEnabled = bool(types)
            cb.VerticalAlignment = VerticalAlignment.Center
            name = TextBlock()
            name.Text = label
            name.VerticalAlignment = VerticalAlignment.Center
            name.Margin = Thickness(4, 0, 8, 0)
            combo = ComboBox()
            combo.Height = 28
            combo.Margin = Thickness(0, 0, 8, 0)
            labels = [type_label(t) for t in types]
            for n in labels:
                combo.Items.Add(n)
            if not labels:
                combo.Items.Add(u'(no tag family loaded for this category)')
                combo.IsEnabled = False
            combo.SelectedIndex = labels.index(prev['type']) if prev.get('type') in labels else 0
            orient = ComboBox()
            orient.Height = 28
            for o in (u'Auto', u'Horizontal', u'Vertical'):
                orient.Items.Add(o)
            orient.SelectedIndex = ORIENT.index(prev.get('orientation', 'auto')) if prev.get('orientation') in ORIENT else 0
            orient.ToolTip = u'Auto = along the duct / pipe (horizontal or vertical)'
            for c, el in enumerate((cb, name, combo, orient)):
                Grid.SetRow(el, r)
                Grid.SetColumn(el, c)
                grid.Children.Add(el)
            self.rows.append({'key': key, 'check': cb, 'combo': combo, 'orient': orient, 'types': types, 'labels': labels})

    def _save(self):
        rules = {}
        for row in self.rows:
            rules[row['key']] = {'on': bool(row['check'].IsChecked),
                                 'type': row['labels'][row['combo'].SelectedIndex] if row['labels'] else u'',
                                 'orientation': ORIENT[max(0, row['orient'].SelectedIndex)]}
        self.store[project_key(doc)] = {
            'scope': self.scope.SelectedIndex, 'min_length': _num(self.min_len.Text, 1000),
            'offset': _num(self.offset.Text, 3), 'skip': bool(self.skip.IsChecked),
            'avoid': bool(self.avoid.IsChecked), 'leader': bool(self.leader.IsChecked),
            'skip_zero': bool(self.skip_zero.IsChecked), 'place_anyway': bool(self.anyway.IsChecked),
            'always_horizontal': bool(self.always_h.IsChecked),
            'use_learned': bool(self.use_learned.IsChecked), 'rules': rules}
        save_json(STORE, self.store)

    def _active_rows(self):
        return [r for r in self.rows if r['check'].IsChecked and r['types']]

    def tag(self):
        self._save()
        rows = self._active_rows()
        if not rows:
            emperor_ui.alert('Tick at least one category.', TITLE, owner=self.win)
            return
        ids = None
        if self.scope.SelectedIndex == 1:
            ids = list(uidoc.Selection.GetElementIds())
            if not ids:
                emperor_ui.alert('Nothing is selected in Revit.', TITLE, owner=self.win)
                return
        rules = [{'key': r['key'], 'tag_type_id': r['types'][max(0, r['combo'].SelectedIndex)].Id,
                  'orientation': ORIENT[max(0, r['orient'].SelectedIndex)]} for r in rows]
        t, warnings = begin(doc, 'Emperor - Smart Tag')
        try:
            report = tagging.run(doc, self.view, rules, skip_tagged=bool(self.skip.IsChecked),
                                 leader=bool(self.leader.IsChecked), avoid_overlap=bool(self.avoid.IsChecked),
                                 min_length_mm=_num(self.min_len.Text, 1000), offset_mm=_num(self.offset.Text, 2),
                                 ids=ids, skip_zero_flow=bool(self.skip_zero.IsChecked),
                                 place_anyway=bool(self.anyway.IsChecked),
                                 always_horizontal=bool(self.always_h.IsChecked),
                                 use_learned=bool(self.use_learned.IsChecked))
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            emperor_ui.alert(u'Smart Tag failed and nothing was changed.\n\n%s' % ex, TITLE, owner=self.win, warn=True)
            return
        self.status.Text = u'Tagged %d elements' % report['tagged']
        emperor_ui.alert(tagging.describe(report), TITLE, owner=self.win)

    def learn(self):
        hand = emperor_ui.alert(
            u'Smart Tag will learn from the tags it placed in "%s" that you moved (strong vote) or left '
            u'where they were (small vote).\n\nAlso learn from the tags in this view that were placed by hand '
            u'(not by Smart Tag)?' % self.view.Name, TITLE, yes=True, no=True, owner=self.win)
        try:
            cats = [r['key'] for r in self._active_rows()] or None
            rep = tag_learn.learn(doc, self.view, include_hand_placed=bool(hand), categories=cats)
        except Exception as ex:
            emperor_ui.alert(u'Could not learn.\n\n%s' % ex, TITLE, owner=self.win, warn=True)
            return
        lines = [u'Moved by you: %d' % rep['moved'], u'Left where they were: %d' % rep['kept'],
                 u'Placed by hand: %d' % rep['hand'], u'Deleted by you (ignored): %d' % rep['deleted'], u'']
        for sit, n in sorted(rep['situations'].items()):
            lines.append(u'  %s: %d tag(s)' % (sit, n))
        lines.append(u'')
        lines.append(u'Next time Smart Tag tries these spots first (tick "Use the spots learned from me").')
        self.status.Text = u'Learned from %d tags' % (rep['moved'] + rep['kept'] + rep['hand'])
        emperor_ui.alert(u'\n'.join(lines), TITLE, owner=self.win)

    def learned(self):
        text = tag_learn.summary()
        if not emperor_ui.alert(text + u'\n\nForget everything Smart Tag learned?', TITLE, yes=True, no=True,
                                owner=self.win):
            return
        tag_learn.forget()
        self.status.Text = u'Learned spots cleared'

    def remove(self):
        self._save()
        rows = self._active_rows()
        if not rows:
            emperor_ui.alert('Tick the categories whose tags should be removed.', TITLE, owner=self.win)
            return
        if not emperor_ui.alert(u'Delete every tag of the ticked categories in "%s"?' % self.view.Name,
                                TITLE, yes=True, no=True, owner=self.win, warn=True):
            return
        t, _w = begin(doc, 'Emperor - Remove tags')
        try:
            n = tagging.remove_tags(doc, self.view, [r['key'] for r in rows])
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            emperor_ui.alert(u'Could not remove the tags.\n\n%s' % ex, TITLE, owner=self.win, warn=True)
            return
        self.status.Text = u'Removed %d tags' % n


TAGGABLE = (DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan,
            DB.ViewType.Section, DB.ViewType.Elevation, DB.ViewType.Detail)

view = doc.ActiveView if doc is not None else None
if view is None or doc.IsFamilyDocument:
    emperor_ui.alert('Open a project view to use Smart Tag.', TITLE, warn=True)
elif view.ViewType not in TAGGABLE:
    emperor_ui.alert('Open a plan, section or elevation view first (tags cannot be placed in "%s").' % view.Name,
                     TITLE, warn=True)
else:
    try:
        Window(view).win.ShowDialog()
    except Exception:
        import traceback
        emperor_ui.alert(u'Smart Tag stopped unexpectedly.\n\n%s' % traceback.format_exc(), TITLE, warn=True)
