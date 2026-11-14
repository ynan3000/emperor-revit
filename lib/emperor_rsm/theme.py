# -*- coding: ascii -*-
# Emperor BIM Toolkit - shared look for Room & Space Manager
# Same palette, header, buttons, tabs, check boxes and grid style as Emperor Exporter
# (emperor_common.py v3.1). Kept in its own package so it never shadows the
# Exporter's emperor_common module on the pyRevit search path.
# Author: Yahya Morcy

import os
import time
import codecs
import traceback

import clr
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System')

import System
from System import Uri, UriKind
from System.Windows import Thickness, FontWeights, TextWrapping, VerticalAlignment, CornerRadius
from System.Windows.Media import Color, SolidColorBrush, FontFamily
from System.Windows.Media.Imaging import BitmapImage
from System.Windows.Controls import (StackPanel, Border, TextBlock, TextBox, Button, Image,
                                     ComboBox, CheckBox, Orientation)
from System.Windows.Input import Cursors

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(PKG_DIR, 'assets')
APPDATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')), 'EmperorBIMToolkit')
try:
    if not os.path.isdir(APPDATA_DIR):
        os.makedirs(APPDATA_DIR)
except Exception:
    pass
LOG_PATH = os.path.join(APPDATA_DIR, 'RoomSpaceManager.log')

# Emperor palette
RED = '#8B111C'
RED2 = '#B32330'
INK = '#303034'
GRAY = '#77777D'
LIGHT = '#F7EFF0'
WHITE = '#FFFFFF'
BORDER = '#D8CBCD'
GREEN = '#327D50'
SELECT = '#F3DADD'
HOVERROW = '#FAF1F2'
WINDOW_BG = '#F8F8F8'
STATUS_BG = '#F3E9EA'
ALT_ROW = '#FBF6F7'
GRID_LINE = '#EADFE0'

# compact layout (v2.1): right-hand tool panel and its fields
TOOL_PANEL_WIDTH = 360
FIELD_WIDTH = 326


def u(value):
    if value is None:
        return u''
    try:
        if isinstance(value, unicode):
            return value
        return unicode(value)
    except NameError:
        return str(value)
    except Exception:
        try:
            return unicode(str(value))
        except Exception:
            return u''


def log(message):
    try:
        stamp = time.strftime('%Y-%m-%d %H:%M:%S')
        with codecs.open(LOG_PATH, 'a', 'utf-8') as fp:
            fp.write(u'{0} | {1}\n'.format(stamp, u(message)))
    except Exception:
        pass


def log_exception(context):
    log(u(context) + u'\n' + u(traceback.format_exc()))


def brush(hex_color):
    h = hex_color.replace('#', '')
    if len(h) == 8:
        return SolidColorBrush(Color.FromArgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)))
    return SolidColorBrush(Color.FromRgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))


# ---------------------------------------------------------------- theme XAML
_THEME_XAML = u'''
<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <!--BTN-->
  <Style x:Key="EkButton" TargetType="Button">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="Button">
          <Grid x:Name="root" RenderTransformOrigin="0.5,0.5">
            <Grid.RenderTransform><ScaleTransform x:Name="sc" ScaleX="1" ScaleY="1"/></Grid.RenderTransform>
            <Border x:Name="bd" CornerRadius="5" Background="{TemplateBinding Background}"
                    BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="{TemplateBinding BorderThickness}"/>
            <Border x:Name="hv" CornerRadius="5" Background="@HOVER_BG@" BorderBrush="@HOVER_BORDER@"
                    BorderThickness="1" Opacity="0" IsHitTestVisible="False"/>
            <Border x:Name="EmperorGlow" CornerRadius="5" Opacity="0" IsHitTestVisible="False" Tag="@GLOW@"/>
            <Border x:Name="pr" CornerRadius="5" Background="@PRESS_BG@" BorderBrush="@HOVER_BORDER@"
                    BorderThickness="1" Opacity="0" IsHitTestVisible="False"/>
            <ContentPresenter Margin="{TemplateBinding Padding}" HorizontalAlignment="Center"
                              VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </Grid>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Trigger.EnterActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.12"/>
                <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.15"/>
              </Storyboard></BeginStoryboard></Trigger.EnterActions>
              <Trigger.ExitActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="hv" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.18"/>
                <DoubleAnimation Storyboard.TargetName="EmperorGlow" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.25"/>
              </Storyboard></BeginStoryboard></Trigger.ExitActions>
            </Trigger>
            <Trigger Property="IsPressed" Value="True">
              <Trigger.EnterActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="pr" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.05"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleX" To="0.97" Duration="0:0:0.06"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleY" To="0.94" Duration="0:0:0.06"/>
              </Storyboard></BeginStoryboard></Trigger.EnterActions>
              <Trigger.ExitActions><BeginStoryboard><Storyboard>
                <DoubleAnimation Storyboard.TargetName="pr" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.12"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleX" To="1" Duration="0:0:0.1"/>
                <DoubleAnimation Storyboard.TargetName="sc" Storyboard.TargetProperty="ScaleY" To="1" Duration="0:0:0.1"/>
              </Storyboard></BeginStoryboard></Trigger.ExitActions>
            </Trigger>
            <Trigger Property="IsKeyboardFocused" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="bd" Property="BorderThickness" Value="2"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="root" Property="Opacity" Value="0.4"/>
              <Setter Property="Cursor" Value="Arrow"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>
  <!--/BTN-->

  <Style TargetType="TabItem">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="TabItem">
          <Border x:Name="bd" Background="Transparent" BorderBrush="Transparent" BorderThickness="0,0,0,3"
                  Padding="16,6,16,5" Margin="0,0,2,0">
            <ContentPresenter x:Name="cp" ContentSource="Header" TextElement.Foreground="@GRAY@"
                              TextElement.FontWeight="Normal" HorizontalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="bd" Property="Background" Value="@LIGHT@"/>
              <Setter TargetName="cp" Property="TextElement.Foreground" Value="@RED@"/>
            </Trigger>
            <Trigger Property="IsSelected" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED@"/>
              <Setter TargetName="bd" Property="Background" Value="@WHITE@"/>
              <Setter TargetName="cp" Property="TextElement.Foreground" Value="@RED@"/>
              <Setter TargetName="cp" Property="TextElement.FontWeight" Value="Bold"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="CheckBox">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Cursor" Value="Hand"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="CheckBox">
          <StackPanel x:Name="root" Orientation="Horizontal" Background="Transparent">
            <Grid Width="17" Height="17" VerticalAlignment="Center">
              <Border x:Name="box" CornerRadius="4" BorderThickness="1.5" BorderBrush="@GRAY@" Background="@WHITE@"/>
              <Path x:Name="tick" Data="M4,8.8 L7,11.8 L13,5" Stroke="White" StrokeThickness="2"
                    StrokeStartLineCap="Round" StrokeEndLineCap="Round" StrokeLineJoin="Round" Visibility="Collapsed"/>
            </Grid>
            <ContentPresenter Margin="7,0,0,0" VerticalAlignment="Center" RecognizesAccessKey="True"/>
          </StackPanel>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="box" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="box" Property="Background" Value="@LIGHT@"/>
            </Trigger>
            <Trigger Property="IsChecked" Value="True">
              <Setter TargetName="box" Property="Background" Value="@RED@"/>
              <Setter TargetName="box" Property="BorderBrush" Value="@RED@"/>
              <Setter TargetName="tick" Property="Visibility" Value="Visible"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="root" Property="Opacity" Value="0.45"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style x:Key="EkTextBox" TargetType="TextBox">
    <Setter Property="OverridesDefaultStyle" Value="True"/>
    <Setter Property="SnapsToDevicePixels" Value="True"/>
    <Setter Property="Template">
      <Setter.Value>
        <ControlTemplate TargetType="TextBox">
          <Border x:Name="bd" CornerRadius="4" Background="{TemplateBinding Background}"
                  BorderBrush="{TemplateBinding BorderBrush}" BorderThickness="1">
            <ScrollViewer x:Name="PART_ContentHost" Margin="{TemplateBinding Padding}" VerticalAlignment="Center"/>
          </Border>
          <ControlTemplate.Triggers>
            <Trigger Property="IsMouseOver" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@GRAY@"/>
            </Trigger>
            <Trigger Property="IsKeyboardFocused" Value="True">
              <Setter TargetName="bd" Property="BorderBrush" Value="@RED2@"/>
              <Setter TargetName="bd" Property="BorderThickness" Value="2"/>
            </Trigger>
            <Trigger Property="IsEnabled" Value="False">
              <Setter TargetName="bd" Property="Opacity" Value="0.5"/>
            </Trigger>
          </ControlTemplate.Triggers>
        </ControlTemplate>
      </Setter.Value>
    </Setter>
  </Style>

  <Style TargetType="DataGridColumnHeader">
    <Setter Property="Background" Value="@LIGHT@"/>
    <Setter Property="Foreground" Value="@RED@"/>
    <Setter Property="FontWeight" Value="SemiBold"/>
    <Setter Property="Padding" Value="7,4,7,4"/>
    <Setter Property="BorderBrush" Value="@BORDER@"/>
    <Setter Property="BorderThickness" Value="0,0,1,2"/>
    <Style.Triggers>
      <Trigger Property="IsMouseOver" Value="True">
        <Setter Property="Background" Value="@SELECT@"/>
      </Trigger>
    </Style.Triggers>
  </Style>

  <Style TargetType="DataGridCell">
    <Setter Property="BorderThickness" Value="0"/>
    <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
    <Setter Property="Padding" Value="4,2,4,2"/>
    <Style.Triggers>
      <DataTrigger Binding="{Binding RelativeSource={RelativeSource AncestorType=DataGridRow}, Path=IsMouseOver}" Value="True">
        <Setter Property="Background" Value="@HOVERROW@"/>
      </DataTrigger>
      <Trigger Property="IsSelected" Value="True">
        <Setter Property="Background" Value="@SELECT@"/>
        <Setter Property="Foreground" Value="@INK@"/>
        <Setter Property="BorderBrush" Value="Transparent"/>
      </Trigger>
    </Style.Triggers>
  </Style>

  <Style TargetType="DataGridRow">
    <Setter Property="MinHeight" Value="23"/>
  </Style>
</ResourceDictionary>
'''

_THEME_CACHE = {}


def theme():
    """Shared ResourceDictionary, or None when styling is unavailable (plain controls are used)."""
    if 'dict' in _THEME_CACHE:
        return _THEME_CACHE['dict']
    result = None
    try:
        from System.IO import StringReader
        from System.Windows.Markup import XamlReader
        xaml = _THEME_XAML
        start = xaml.index(u'<!--BTN-->')
        end = xaml.index(u'<!--/BTN-->')
        block = xaml[start + 10:end]
        normal = block.replace(u'@GLOW@', u'#33B32330').replace(u'@HOVER_BG@', u'#F7EBEC').replace(u'@PRESS_BG@', u'#E8CDD1')
        primary = (block.replace(u'x:Key="EkButton"', u'x:Key="EkPrimaryButton"')
                   .replace(u'@GLOW@', u'#55FFFFFF').replace(u'@HOVER_BG@', u'#33FFFFFF').replace(u'@PRESS_BG@', u'#33000000'))
        xaml = xaml[:start] + normal + primary + xaml[end + 11:]
        values = {'RED': RED, 'RED2': RED2, 'INK': INK, 'GRAY': GRAY, 'LIGHT': LIGHT, 'WHITE': WHITE,
                  'BORDER': BORDER, 'SELECT': SELECT, 'HOVERROW': HOVERROW, 'HOVER_BORDER': RED2}
        for key in values:
            xaml = xaml.replace(u'@' + key + u'@', values[key])
        result = XamlReader.Parse(xaml)
    except Exception:
        log_exception('Theme could not be loaded, using plain controls.')
        result = None
    _THEME_CACHE['dict'] = result
    return result


def enable_glow(window):
    """Emperor mouse-following glow on this window's buttons (shared emperor_ui module)."""
    try:
        import emperor_ui
        emperor_ui.add_extras(window)       # drop-downs, menus, expanders, tooltips
        emperor_ui.enable_mouse_glow(window)
    except Exception:
        log_exception('Mouse glow not attached.')


def apply_style(control, key):
    try:
        th = theme()
        if th is not None and th.Contains(key):
            control.Style = th[key]
            return True
    except Exception:
        log_exception('Style not applied: ' + key)
    return False


def header_brush():
    try:
        from System.Windows.Media import LinearGradientBrush, GradientStop
        from System.Windows import Point
        gb = LinearGradientBrush()
        gb.StartPoint = Point(0, 0)
        gb.EndPoint = Point(1, 0)
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x6E, 0x0C, 0x16), 0.0))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0x8B, 0x11, 0x1C), 0.55))
        gb.GradientStops.Add(GradientStop(Color.FromRgb(0xB3, 0x23, 0x30), 1.0))
        return gb
    except Exception:
        return brush(RED)


# ---------------------------------------------------------------- widgets
def icon_path(name, white=False):
    p = os.path.join(ASSET_DIR, name + ('.dark.png' if white else '.png'))
    if not os.path.exists(p):
        p = os.path.join(ASSET_DIR, name + '.png')
    return p


def image(name, size=18, white=False):
    img = Image()
    img.Width = size
    img.Height = size
    img.Margin = Thickness(0, 0, 7, 0)
    try:
        p = icon_path(name, white)
        if os.path.exists(p):
            img.Source = BitmapImage(Uri(p, UriKind.Absolute))
    except Exception:
        pass
    return img


def text(value, size=12, color=INK, bold=False, wrap=False):
    t = TextBlock()
    t.Text = u(value)
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = size
    t.Foreground = brush(color)
    t.FontWeight = FontWeights.Bold if bold else FontWeights.Normal
    t.TextWrapping = TextWrapping.Wrap if wrap else TextWrapping.NoWrap
    t.Margin = Thickness(0, 1, 0, 1)
    return t


def button(label, icon=None, primary=False, width=None, tooltip=None):
    b = Button()
    b.Margin = Thickness(3)
    b.Padding = Thickness(9, 4, 9, 4)
    b.MinHeight = 30
    b.Cursor = Cursors.Hand
    b.BorderThickness = Thickness(1)
    b.BorderBrush = brush(RED if primary else BORDER)
    b.Background = brush(RED if primary else WHITE)
    b.Foreground = brush(WHITE if primary else RED)
    b.FontFamily = FontFamily('Segoe UI')
    b.FontSize = 12
    sp = StackPanel()
    sp.Orientation = Orientation.Horizontal
    sp.VerticalAlignment = VerticalAlignment.Center
    if icon:
        sp.Children.Add(image(icon, 16, primary))
    t = text(label, 12, WHITE if primary else RED, primary)
    if not primary:
        t.FontWeight = FontWeights.SemiBold
    t.VerticalAlignment = VerticalAlignment.Center
    sp.Children.Add(t)
    b.Content = sp
    if width is not None:
        b.Width = width
    if tooltip:
        b.ToolTip = u(tooltip)
    if not _emperor_button_style(b, primary):
        apply_style(b, 'EkPrimaryButton' if primary else 'EkButton')
    return b


def _emperor_button_style(b, primary):
    """Use the exact button style of the other Emperor windows (lib/emperor_ui.py)."""
    try:
        import emperor_ui
        d = emperor_ui.dictionary()
        if d is None:
            log('Emperor theme dictionary did not load (button keeps the Room & Space style).')
            return False
        b.Style = d['RedBtn' if primary else 'OutlineBtn']
        b.Padding = Thickness(12, 5, 12, 5)
        b.FontSize = 12.5
        return True
    except Exception:
        log_exception('Emperor button style not applied.')
        return False


def textbox(value='', width=None):
    t = TextBox()
    t.Text = u(value)
    t.FontFamily = FontFamily('Segoe UI')
    t.FontSize = 12
    t.Padding = Thickness(6, 0, 6, 0)          # no vertical padding: the text is centred and never clipped
    t.Margin = Thickness(3, 2, 3, 2)
    t.Height = 26
    t.VerticalContentAlignment = VerticalAlignment.Center
    t.BorderBrush = brush(BORDER)
    t.Background = brush(WHITE)
    t.Foreground = brush(INK)
    if width is not None:
        t.Width = width
    apply_style(t, 'EkTextBox')
    return t


def combo(items, width=None):
    c = ComboBox()
    c.FontFamily = FontFamily('Segoe UI')
    c.FontSize = 12
    c.Margin = Thickness(3, 2, 3, 2)
    c.Padding = Thickness(6, 3, 6, 3)
    c.Height = 26
    c.BorderBrush = brush(BORDER)
    c.Background = brush(WHITE)
    for item in items:
        c.Items.Add(u(item))
    if c.Items.Count:
        c.SelectedIndex = 0
    if width is not None:
        c.Width = width
    return c


def checkbox(label, checked=False, tooltip=None):
    c = CheckBox()
    c.Content = u(label)
    c.IsChecked = bool(checked)
    c.Margin = Thickness(5, 5, 8, 2)
    c.FontFamily = FontFamily('Segoe UI')
    c.FontSize = 12
    c.Foreground = brush(INK)
    if tooltip:
        c.ToolTip = u(tooltip)
    return c


def field_label(value):
    t = text(value, 11, GRAY, False)
    t.Margin = Thickness(4, 4, 3, 0)
    return t


def hint(value):
    t = text(value, 11, GRAY, False, True)
    t.Margin = Thickness(5, 2, 5, 4)
    return t


def section(title, child):
    """White card with a red title bar line - the Emperor group style."""
    border = Border()
    border.Background = brush(WHITE)
    border.BorderBrush = brush(BORDER)
    border.BorderThickness = Thickness(1)
    border.CornerRadius = CornerRadius(6)
    border.Padding = Thickness(7, 5, 7, 6)
    border.Margin = Thickness(0, 0, 0, 6)
    stack = StackPanel()
    head = Border()
    head.BorderBrush = brush(SELECT)
    head.BorderThickness = Thickness(0, 0, 0, 1)
    head.Padding = Thickness(2, 0, 2, 4)
    head.Margin = Thickness(0, 0, 0, 3)
    head.Child = text(title, 11.5, RED, True)
    stack.Children.Add(head)
    stack.Children.Add(child)
    border.Child = stack
    return border


def hstack(*children):
    sp = StackPanel()
    sp.Orientation = Orientation.Horizontal
    for c in children:
        sp.Children.Add(c)
    return sp


def vstack(*children):
    sp = StackPanel()
    sp.Orientation = Orientation.Vertical
    for c in children:
        sp.Children.Add(c)
    return sp
